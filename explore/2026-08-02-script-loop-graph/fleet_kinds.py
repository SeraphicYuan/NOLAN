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

TWO SAFETY INVARIANTS, because NOLAN will grow more agent loops and they must not collide with
each other or with a human's own sessions:

  **1. NAMES ARE UNIQUE BY CONSTRUCTION, NOT BY SEARCH.** No enumeration of the live list, no
  "lowest unused index", no retry-on-collision. `nfleet-<kind>-<8 hex>` cannot collide, so there
  is no race to lose and no dependence on reading tmux correctly.

  **2. WE NEVER TOUCH A SESSION WE DID NOT CREATE.** `nolan1..6` are a human's, made by hand for
  other work, and `nolan.fleet.fleet()` selects with `startswith(prefix)` — which means anything
  named `nolan*` lands on the scene-edit board and in any loop iterating it. An earlier draft of
  this module used the prefix `nolan-probe-` and its throwaway test agents duly appeared on that
  board. So: everything we create lives under `nfleet-`, which `startswith("nolan")` does not
  match, and `release()`/`reap()` REFUSE any session absent from our own registry. Prefix
  matching is never sufficient authority to kill.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from nolan import fleet as _f

REPO = Path(__file__).resolve().parents[2]
# Reservations live beside the existing per-agent status files so one reaper can see everything,
# but in their own directory so this experiment cannot corrupt the scene-edit board.
RESV_DIR = REPO / ".nolan" / "reservations"

# EVERY session this module creates begins with this, and NOTHING ELSE MAY. Deliberately not
# "nolan": `nolan.fleet.fleet()` selects sessions with `startswith(prefix)` and is normally called
# with "nolan", so a `nolan-*` name of ours would appear on the human's scene-edit board and in
# anything iterating it. `nfleet-` is invisible to that filter.
OWNED_ROOT = "nfleet-"


def _new_name(kind: "FleetKind") -> str:
    """`nfleet-<kind>-<8 hex>` — unique by CONSTRUCTION.

    The alternative (scan the live list, take the lowest unused index) is what the existing fleet
    does, and it is wrong twice over: it races two callers onto one name, and it depends on
    reading tmux correctly at exactly the wrong moment. A random suffix needs neither. 8 hex is
    2^32 of room against a fleet that will never hold more than single digits.
    """
    return f"{OWNED_ROOT}{kind.name}-{uuid.uuid4().hex[:8]}"


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
    module constant, which is what makes a second fleet possible at all.

    There is no `prefix` field: the session name is derived from `name` under `OWNED_ROOT`, so a
    kind cannot be given a prefix that collides with a human's sessions or another loop's.
    """

    name: str                        # short slug; becomes `nfleet-<name>-<hex>`
    ttl_s: int = 2700                # older than this with no heartbeat ⇒ stale ⇒ reapable
    max_concurrent: int = 4          # refuse the N+1th — every agent is a billing session
    # What to launch. Pluggable so the LIFECYCLE can be tested with `sh -c 'sleep 2; touch x'`
    # instead of a Claude session — the same reason Phase 0 replays recorded runs instead of
    # generating new ones. Mechanism and behaviour are separate questions.
    launch: str = "claude --dangerously-skip-permissions"


SCRIPT_LOOP = FleetKind(name="script", ttl_s=1800, max_concurrent=3)
# For testing the lifecycle itself. `launch=""` because `tmux new-session` ALREADY starts a
# shell — giving it a command instead occupies the pane, and dispatched keystrokes then go to a
# process that is not reading them. (Found the hard way: a probe that launched `sleep 600` sat
# there while every dispatch vanished and `await_done` correctly reported a timeout.)
PROBE = FleetKind(name="probe", ttl_s=120, max_concurrent=4, launch="")


class NotOurs(RuntimeError):
    """Refusing to act on a session this module did not create.

    The failure it prevents: `nolan1`..`nolan6` are a human's, made by hand for other work. A
    reaper that selects by prefix — or a config typo that widens one — would kill them silently
    and the operator would find their work gone with no error anywhere. So authority to kill comes
    from OUR OWN REGISTRY, never from the shape of a name, and the refusal is loud.
    """


def _owned(session: str) -> bool:
    """Did we create this? Both conditions, and neither alone is sufficient.

    The registry is the real authority; the `OWNED_ROOT` check is a second lock so that a corrupt
    or hand-edited reservation file still cannot point us at `nolan3`.
    """
    if not session.startswith(OWNED_ROOT):
        return False
    return (RESV_DIR / f"{session}.json").exists()


def _require_ours(session: str) -> None:
    if not _owned(session):
        raise NotOurs(
            f"refusing to touch tmux session {session!r}: not created by this fleet "
            f"(needs the {OWNED_ROOT!r} prefix AND a reservation on disk). "
            f"Sessions like nolan1..nolan6 belong to a human and are never ours to kill.")


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


def reserve(kind: FleetKind, *, meta: Optional[Dict] = None) -> Optional[Reservation]:
    """Claim a session of `kind`, or None if the ceiling is reached.

    NO SEARCH, NO RETRY. The name comes from `_new_name` and cannot collide, so there is nothing
    to enumerate and no race to lose. The reservation is written BEFORE the session is created:
    if `new-session` then fails, the stale reservation is cleaned up here rather than left to a
    reaper — and if this process dies between the two, the reaper sees a reservation with no
    session and clears it as an orphan. Writing it after would leave the opposite: a live session
    nothing owns, which by these rules nothing may ever kill.
    """
    if len(live(kind)) >= kind.max_concurrent:
        return None
    name = _new_name(kind)
    res = Reservation(kind=kind.name, session=name, started_at=time.time(),
                      meta=dict(meta or {}))
    _write(res)
    r = _f._tmux(["new-session", "-d", "-s", name, "-c", _f._wsl_repo_dir()])
    if r.returncode != 0:
        res.path.unlink(missing_ok=True)
        return None
    if kind.launch:
        _f._tmux(["send-keys", "-t", name, "-l", kind.launch])
        time.sleep(0.3)                          # the TUI debounces PTY input
        _f._tmux(["send-keys", "-t", name, "Enter"])
    return res


def release(res: Reservation) -> bool:
    """Kill the session and clear the reservation.

    REFUSES anything not ours (`NotOurs`). Safe to call twice — releasing an agent that already
    died is the NORMAL path, not an error, so a missing session is success rather than failure.
    """
    _require_ours(res.session)
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
    # ITERATES OUR REGISTRY, never the live session list. A reaper that walked tmux and matched on
    # a prefix is one config typo away from killing a human's `nolan3` — so the only sessions it
    # can even see are ones we recorded creating.
    for r in roster(kind):
        if not _owned(r.session):
            continue                             # belt and braces; `roster` only reads our dir
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
