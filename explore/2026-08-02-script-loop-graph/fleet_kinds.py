"""Ephemeral, named, bounded agent fleets — the lifecycle Phase 2 needs.

`nolan.fleet` already does most of this for ONE kind of worker. It has spawn/kill, per-agent
status files, tmux liveness, and — the useful precedent — an ephemeral `nolan-run-<jobid>-<phase>`
namespace with a registry and a reaper that can tell an in-flight agent from a stale one.

What it does not have, and what a second kind of worker needs:

1. **KINDS.** `AGENT_PREFIX` is a module constant and `dispatch()` takes scene-edit arguments
   (`plan_path`, `scene_ids`). A script-loop worker shares none of that vocabulary.
2. **ATOMIC RESERVATION.** `next_session_name()` reads the live session list and returns the
   lowest unused name — then the caller creates it. Two callers racing get the SAME name and one
   silently loses its agent. Fixed here by letting **tmux be the lock**: `new-session` fails if
   the name exists, so the create IS the reservation and a collision just retries.
3. **A CONCURRENCY CEILING.** Nothing currently refuses to spawn the eleventh agent. Each one is
   a Claude session billing tokens, so an unbounded loop is an unbounded bill.
4. **A COMPLETION SIGNAL THAT SURVIVES THE AGENT.** `fleet` waits on the agent writing its own
   status file. That is a promise the agent might not keep — it can crash after doing the work,
   or before. Here the caller supplies a PREDICATE over the artifact it actually wants, which is
   true regardless of how the agent felt about it.

EPHEMERAL BY DEFAULT: reserve → dispatch → await the artifact → release. Warm pooling across
rounds is deliberately not built; the loop's state lives in files, so a warm agent buys less than
it looks and costs a lifecycle that can leak.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from nolan import fleet as _f

REPO = Path(__file__).resolve().parents[2]
# Reservations live beside the existing per-agent status files so one reaper can see everything,
# but in their own file so this experiment cannot corrupt the scene-edit board.
RESV_DIR = REPO / ".nolan" / "reservations"


def ensure_tmux(timeout_s: int = 90) -> bool:
    """Wake WSL before any fleet call, and say so if it cannot be woken.

    A DEFECT IN `nolan.fleet` THIS WORKS AROUND, worth carrying to promotion: `_tmux()` uses a
    fixed 8-second timeout. Measured on this host, `wsl.exe tmux -V` costs 0.09-0.58s once the VM
    is warm — but a COLD WSL boot exceeds 8s, so the first fleet call after the machine has been
    idle raises `TimeoutExpired` and every call after it succeeds. An intermittent that
    self-conceals on retry is the worst shape of failure for an unattended loop, which is exactly
    what Phase 2 is.

    Fixing it properly means a longer timeout on the first call (or an explicit warmup) inside
    `nolan.fleet` itself. Not done here: production code does not get patched from the sandbox.
    """
    import subprocess
    base = ["tmux"] if __import__("shutil").which("tmux") else ["wsl.exe", "tmux"]
    try:
        return subprocess.run(base + ["-V"], capture_output=True, text=True,
                              timeout=timeout_s).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@dataclass(frozen=True)
class FleetKind:
    """One species of worker. Everything that differs between fleets lives here rather than as a
    module constant, which is what makes a second fleet possible at all."""

    name: str
    prefix: str                      # tmux session prefix, e.g. "nolan-script-"
    ttl_s: int = 2700                # older than this with no heartbeat ⇒ stale ⇒ reapable
    max_concurrent: int = 4          # refuse the N+1th — every agent is a billing session
    # What to launch. Pluggable so the LIFECYCLE can be tested with `sh -c 'sleep 2; touch x'`
    # instead of a Claude session — the same reason Phase 0 replays recorded runs instead of
    # generating new ones. Mechanism and behaviour are separate questions.
    launch: str = "claude --dangerously-skip-permissions"


SCRIPT_LOOP = FleetKind(name="script-loop", prefix="nolan-script-", ttl_s=1800, max_concurrent=3)
# For testing the lifecycle itself. `launch=""` because `tmux new-session` ALREADY starts a
# shell — giving it a command instead occupies the pane, and dispatched keystrokes then go to a
# process that is not reading them. (Found the hard way: a probe that launched `sleep 600` sat
# there while every dispatch vanished and `await_done` correctly reported a timeout.)
PROBE = FleetKind(name="probe", prefix="nolan-probe-", ttl_s=120, max_concurrent=4, launch="")


@dataclass
class Reservation:
    kind: str
    session: str
    started_at: float
    meta: Dict = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return RESV_DIR / f"{self.session}.json"


def _write(res: Reservation) -> None:
    RESV_DIR.mkdir(parents=True, exist_ok=True)
    res.path.write_text(json.dumps({
        "kind": res.kind, "session": res.session,
        "started_at": res.started_at, "meta": res.meta}), encoding="utf-8")


def _read(p: Path) -> Optional[Reservation]:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return Reservation(kind=d["kind"], session=d["session"],
                           started_at=float(d.get("started_at") or 0), meta=d.get("meta") or {})
    except (OSError, ValueError, KeyError):
        return None


def roster(kind: FleetKind) -> List[Reservation]:
    """Every reservation of this kind, live or not. Reads the DISK, not memory, so a reaper in
    another process sees the same picture."""
    if not RESV_DIR.is_dir():
        return []
    out = []
    for p in sorted(RESV_DIR.glob("*.json")):
        r = _read(p)
        if r and r.kind == kind.name:
            out.append(r)
    return out


def live(kind: FleetKind) -> List[Reservation]:
    sessions = set(_f._live_sessions())
    return [r for r in roster(kind) if r.session in sessions]


def reserve(kind: FleetKind, *, meta: Optional[Dict] = None,
            tries: int = 8) -> Optional[Reservation]:
    """Atomically claim a session of `kind`, or None if the ceiling is reached.

    TMUX IS THE LOCK. `new-session -d -s <name>` fails when the name is taken, so creating the
    session IS the reservation — there is no check-then-act window for a second caller to slip
    through. `nolan.fleet.next_session_name` + `spawn` has exactly that window.
    """
    if len(live(kind)) >= kind.max_concurrent:
        return None
    existing = set(_f._live_sessions())
    n = 1
    for _ in range(tries):
        while f"{kind.prefix}{n}" in existing:
            n += 1
        name = f"{kind.prefix}{n}"
        r = _f._tmux(["new-session", "-d", "-s", name, "-c", _f._wsl_repo_dir()])
        if r.returncode == 0:
            res = Reservation(kind=kind.name, session=name, started_at=time.time(),
                              meta=dict(meta or {}))
            _write(res)
            if kind.launch:
                _f._tmux(["send-keys", "-t", name, "-l", kind.launch])
                time.sleep(0.3)                  # the TUI debounces PTY input
                _f._tmux(["send-keys", "-t", name, "Enter"])
            return res
        n += 1                                   # lost the race (or a bad name) — take the next
        existing.add(name)
    return None


def release(res: Reservation) -> bool:
    """Kill the session and clear the reservation. Safe to call twice — releasing an agent that
    already died is the NORMAL path, not an error."""
    ok = _f.kill(res.session)
    res.path.unlink(missing_ok=True)
    return ok


def reap(kind: FleetKind) -> List[str]:
    """Kill reservations that are stale or orphaned. Returns what it killed.

    Two reasons to reap, and they are different:
      * **orphaned** — the reservation file outlived its tmux session. Nothing to kill; the file
        is a ghost on the board and gets cleared.
      * **stale** — the session is alive but older than `ttl_s`. Something hung. This is the case
        that costs money, and the one an unattended loop must handle without a human noticing.
    """
    now = time.time()
    sessions = set(_f._live_sessions())
    killed = []
    for r in roster(kind):
        if r.session not in sessions:
            r.path.unlink(missing_ok=True)
            killed.append(f"{r.session} (orphaned reservation)")
        elif now - r.started_at > kind.ttl_s:
            release(r)
            killed.append(f"{r.session} (stale, {int(now - r.started_at)}s > {kind.ttl_s}s)")
    return killed


def dispatch(res: Reservation, text: str) -> bool:
    """Send a prompt to a reserved agent. Fire-and-forget by nature — tmux send-keys cannot be
    queried, which is exactly why completion is judged by artifact rather than by return value."""
    r = _f._tmux(["send-keys", "-t", res.session, "-l", text])
    if r.returncode != 0:
        return False
    time.sleep(0.3)
    return _f._tmux(["send-keys", "-t", res.session, "Enter"]).returncode == 0


# What `await_done` can conclude. `died` and `timeout` are DIFFERENT failures — one means the
# agent is gone and the work will never arrive, the other means it may still be running and the
# caller must decide whether to keep waiting or reap. Collapsing them loses that.
DONE, TIMEOUT, DIED = "done", "timeout", "died"


def await_done(res: Reservation, ready: Callable[[], bool], *,
               timeout_s: float = 900, poll_s: float = 2.0,
               progress: Optional[Callable[[float], None]] = None) -> str:
    """Wait for the ARTIFACT, not for the agent to say it is finished.

    `ready()` is the caller's predicate — "draft-02.md exists AND passes the gate". That is true
    whether the agent reported success, crashed after writing, or never wrote a status file at
    all, and it is the condition the loop actually depends on. An agent's self-report is a claim;
    the artifact is the fact.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if ready():
            return DONE
        if res.session not in set(_f._live_sessions()):
            # One last look: an agent that wrote the artifact and then exited is a SUCCESS, and
            # checking liveness first would call it a death.
            return DONE if ready() else DIED
        if progress:
            progress(deadline - time.time())
        time.sleep(poll_s)
    return DONE if ready() else TIMEOUT
