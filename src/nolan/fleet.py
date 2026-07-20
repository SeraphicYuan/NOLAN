"""Scene-edit agent fleet — dispatch scene work to named Claude Code tmux agents
(nolan1, nolan2, …) and track their state via per-agent status files.

Each agent reports progress by writing `.nolan/agents/<agent>.json` (a step in the
`nolan-scene-edit` skill). The hub reads these + the live tmux session list to render
a fleet panel on /scenes. Fire-and-forget send-keys can't be queried, so the status
file IS the source of truth for "is nolan4 working / done?".
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]   # src/nolan/fleet.py -> repo
FLEET_DIR = _REPO_ROOT / ".nolan" / "agents"
AGENT_PREFIX = "nolan"            # tmux sessions that count as scene-edit workers

# State machine the skill writes: dispatched -> working -> done | error (else idle).
STATES = {"idle", "dispatched", "working", "done", "error"}


def _status_path(agent: str) -> Path:
    return FLEET_DIR / f"{agent}.json"


def write_status(agent: str, **fields) -> dict:
    """Merge-update an agent's status file atomically. Stamps updated_at."""
    FLEET_DIR.mkdir(parents=True, exist_ok=True)
    data = read_status(agent) or {"agent": agent}
    data.update({k: v for k, v in fields.items() if v is not None})
    data["agent"] = agent
    data["updated_at"] = time.time()
    tmp = _status_path(agent).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, _status_path(agent))
    return data


def read_status(agent: str) -> Optional[dict]:
    p = _status_path(agent)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _live_sessions() -> List[str]:
    try:
        from nolan.webui.operations import list_tmux_sessions
        return list_tmux_sessions()
    except Exception:
        return []


def fleet(prefix: str = AGENT_PREFIX) -> List[dict]:
    """Live scene-edit agents = tmux sessions named <prefix>* joined with status.

    Includes sessions with no status file (state 'idle') and stale status files
    whose session has gone away (session_alive False).
    """
    sessions = [s for s in _live_sessions() if s.startswith(prefix)]
    seen = set()
    out: List[dict] = []
    for s in sorted(sessions):
        seen.add(s)
        st = read_status(s) or {}
        out.append({"agent": s, "session_alive": True,
                    "state": st.get("state", "idle"),
                    "project": st.get("project"), "scene_ids": st.get("scene_ids"),
                    "note": st.get("note"), "message": st.get("message"),
                    "result": st.get("result"), "error": st.get("error"),
                    "updated_at": st.get("updated_at")})
    # status files whose tmux session is gone (so the board doesn't lie)
    if FLEET_DIR.exists():
        for f in sorted(FLEET_DIR.glob(f"{prefix}*.json")):
            name = f.stem
            if name not in seen:
                st = read_status(name) or {}
                out.append({"agent": name, "session_alive": False,
                            "state": st.get("state", "idle"), "project": st.get("project"),
                            "scene_ids": st.get("scene_ids"), "note": st.get("note"),
                            "message": st.get("message"), "result": st.get("result"),
                            "error": st.get("error"), "updated_at": st.get("updated_at")})
    return out


def build_dispatch_prompt(agent: str, plan_path: str, scene_ids: List[str], note: str) -> str:
    """One-line prompt sent to the agent's tmux session (Claude Code with the skill)."""
    ids = ", ".join(scene_ids)
    return (
        f"Use the nolan-scene-edit skill. You are fleet agent '{agent}'. "
        f"Plan: \"{plan_path}\". Scene(s) to rework, one by one: {ids}. "
        f"Human note: \"{note}\". "
        f"Report progress to .nolan/agents/{agent}.json (state working->done|error, "
        f"plus scene_ids, message, and a result list) as you go — start by writing state 'working'. "
        f"Edit and re-render ONLY the named scene(s); leave all others untouched. "
        f"Capability catalog (editing techniques / motion effects / pairing operators, each with "
        f"when-to-use): run `nolan capabilities` or GET /api/map — pick from what exists, "
        f"and read skills/common/editing-craft.md, motion-craft.md, pairing-craft.md for the craft."
    )


def _flow_context(plan_path: str, scene_ids: List[str]) -> Optional[dict]:
    """If plan_path belongs to a flow project, gather context for a flow-aware prompt; else None."""
    project = Path(plan_path).parent
    spec_f = project / "flow.spec.json"
    if not spec_f.exists():
        return None
    spec = json.loads(spec_f.read_text(encoding="utf-8"))
    flow_id = spec.get("flow", "flow")
    palette: List[str] = []
    try:
        reg = json.loads((_REPO_ROOT / "web-video-lab" / "flows" / "registry.json").read_text(encoding="utf-8"))
        t = next((t for t in reg.get("types", []) if t["id"] == flow_id), None)
        palette = (t or {}).get("palette", [])
    except (OSError, json.JSONDecodeError):
        pass
    from nolan import composition as _composition
    beats = {}
    try:
        rows = [s for sec in json.loads(Path(plan_path).read_text(encoding="utf-8")).get("sections", {}).values() for s in sec]
        for r in rows:
            if r.get("id") in scene_ids:
                # the beat's macro layout: its authored archetype, else derived from its block
                archetype = r.get("archetype") or _composition.block_archetype(r.get("block"))
                beats[r["id"]] = {"block": r.get("block"), "archetype": archetype,
                                  "tray": [a.get("src") for a in (r.get("assets") or [])],
                                  "wishlist": [w.get("want") for w in (r.get("wishlist") or []) if w.get("want")]}
    except (OSError, json.JSONDecodeError):
        pass
    return {"flow": flow_id, "theme": spec.get("theme"), "palette": palette, "beats": beats}


def build_flow_dispatch_prompt(agent: str, plan_path: str, scene_ids: List[str], note: str, ctx: dict) -> str:
    """Flow-aware prompt — carries the flow id/theme/palette + per-beat asset state + the
    flow-edit contract (edit the spec not the view, reuse blocks, chapter-block re-render)."""
    from nolan.skills import skill_path
    edit_contract = skill_path("flow.edit-contract") or "skills/flow/edit-contract.md"
    spec_path = str(Path(plan_path).parent / "flow.spec.json")
    lines = []
    for bid in scene_ids:
        b = ctx["beats"].get(bid, {})
        bits = [f"block={b.get('block')}"]
        if b.get("archetype"):
            bits.append(f"archetype={b['archetype']} (the beat's macro layout — keep it)")
        if b.get("tray"):
            bits.append(f"the human added {len(b['tray'])} asset(s) to its tray — use them")
        if b.get("wishlist"):
            bits.append("wishlist: " + "; ".join(b["wishlist"]))
        lines.append(f"{bid} ({', '.join(bits)})")
    return (
        f"You are fleet agent '{agent}' editing a FLOW video (flow='{ctx['flow']}', theme='{ctx['theme']}'). "
        f"FIRST read {edit_contract} — the flow-edit contract; it OVERRIDES the generic "
        f"nolan-scene-edit skill. Edit the SOURCE OF TRUTH \"{spec_path}\" (NOT scene_plan.json — that's a "
        f"regenerated view). Beat(s) to rework: {'; '.join(lines)}. Human note: \"{note}\". "
        f"Pick blocks ONLY from the palette: {', '.join(ctx['palette'])}. "
        f"REUSE before rebuilding: before authoring any new block, check the palette + the ONE block "
        f"library render-service/remotion-lib/src/blocks/library/ (40 blocks — ArtworkStage, DetailLoupe, "
        f"PhotoGrid, PhotoMontage, …) and reuse it; only author a genuinely new block if none fits. "
        f"Use assets already bound/added to the beat; source new only if needed. "
        f"Re-render ONLY the named beat(s) via the chapter-block mechanism: "
        f"rerender_scenes(\"{plan_path}\", {scene_ids}). Leave neighbors untouched. "
        f"Capability catalog (editing/motion/pairing/composition, each with when-to-use): `nolan capabilities` "
        f"or GET /api/map; craft docs in skills/common/*-craft.md. "
        f"Report to .nolan/agents/{agent}.json (state working->done|error, scene_ids, message, result); "
        f"start by writing state 'working'."
    )


def _resolve_note_mentions(plan_path: str, scene_ids: List[str], note: str) -> str:
    """Expand `@<asset-id>` mentions in the note using the named scenes' bound assets."""
    if not note or "@" not in note:
        return note
    try:
        from nolan.iterate.engine import load_plan_raw, find_scene
        from nolan.iterate.revise import resolve_asset_mentions
        data = load_plan_raw(Path(plan_path))
        assets = []
        for sid in scene_ids:
            s = find_scene(data, sid)
            if s:
                assets.extend(s.get("assets") or [])
        return resolve_asset_mentions(note, assets)
    except Exception:
        return note


def current_session() -> Optional[str]:
    """The tmux session this process runs in, or None. Used to refuse self-dispatch.

    Detect ONLY via $TMUX (set when the caller is genuinely inside a tmux session — i.e. a
    fleet agent), so we never guess. Returns None for the hub (Windows python doesn't inherit
    $TMUX and isn't a fleet worker anyway) — a "best-effort active session" fallback was
    rejected because it could falsely refuse a legit hub dispatch."""
    import os
    import shutil
    import subprocess
    if not os.environ.get("TMUX"):
        return None
    pane = os.environ.get("TMUX_PANE")
    base = ["tmux"] if shutil.which("tmux") else ["wsl.exe", "tmux"]
    args = base + ["display-message"] + (["-t", pane] if pane else []) + ["-p", "#S"]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or None
    except Exception:
        return None


# ============================================================================
# Agent lifecycle — spawn / kill / status of tmux Claude Code agents.
# (Ported from the ATHENA/SPARTA tmux.claude pattern. NOLAN previously only
# send-keys'd to pre-existing sessions; this lets the hub create fresh ones.)
# tmux runs in WSL; on Windows we route through wsl.exe (matching
# operations.list_tmux_sessions / _dispatch_to_tmux).
# ============================================================================

DEFAULT_CLAUDE_ARGS = "--dangerously-skip-permissions"

_IDLE_PATTERNS = [r"bypass permissions", r"shift\+tab to cycle", r"^>\s*$", r"^❯\s*$", r"^\$\s*$"]
_BUSY_PATTERNS = [r"esc to interrupt", r"⏳", r"[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]",
                  r"\b(Running|Reading|Searching|Writing|Editing|Baking|Concocting)\b",
                  r"tokens\)"]
_PERMISSION_PATTERNS = [r"Do you want to", r"❯ \d\. Yes", r"\[y/n\]", r"Allow\b.*Deny"]


def _tmux(args: List[str], timeout: int = 8) -> subprocess.CompletedProcess:
    """Run a tmux command, routing through wsl.exe on Windows."""
    base = ["tmux"] if shutil.which("tmux") else ["wsl.exe", "tmux"]
    return subprocess.run(base + args, capture_output=True, text=True, timeout=timeout)


def _sanitize(name: str) -> str:
    """tmux forbids '.' and ':' in session names."""
    return re.sub(r"[.:]", "-", (name or "").strip())


def _wsl_repo_dir() -> str:
    """The repo root as a WSL path (tmux runs in WSL even when the hub is on Windows)."""
    s = str(_REPO_ROOT)
    if len(s) >= 2 and s[1] == ":":            # Windows drive path -> /mnt/<drive>/...
        return f"/mnt/{s[0].lower()}{s[2:].replace(chr(92), '/')}"
    return s


def has_session(name: str) -> bool:
    try:
        return _tmux(["has-session", "-t", _sanitize(name)]).returncode == 0
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


def capture_pane(name: str, lines: int = 16) -> Optional[str]:
    """Plain-text (no ANSI) snapshot of an agent's pane, or None if unreachable."""
    try:
        r = _tmux(["capture-pane", "-t", _sanitize(name), "-p", "-S", f"-{max(1, lines)}"])
        return r.stdout if r.returncode == 0 else None
    except (FileNotFoundError, subprocess.SubprocessError):
        return None


def detect_status(name: str) -> str:
    """Coarse liveness of a Claude agent: booting|idle|busy|waiting_permission|disconnected|unknown."""
    if not has_session(name):
        return "disconnected"
    pane = capture_pane(name, lines=10)
    if pane is None:
        return "disconnected"
    lines = [ln for ln in pane.splitlines() if ln.strip()]
    if not lines:
        return "booting"
    tail = "\n".join(lines[-6:])
    for pat in _PERMISSION_PATTERNS:
        if re.search(pat, tail):
            return "waiting_permission"
    for pat in _BUSY_PATTERNS:
        if re.search(pat, tail):
            return "busy"
    for pat in _IDLE_PATTERNS:
        if re.search(pat, tail, re.M):
            return "idle"
    return "unknown"


def next_session_name(prefix: str = AGENT_PREFIX) -> str:
    """Lowest unused ``<prefix><n>`` (n≥1) among live sessions."""
    live = set(_live_sessions())
    i = 1
    while f"{prefix}{i}" in live:
        i += 1
    return f"{prefix}{i}"


def spawn(name: Optional[str] = None, *, dangerous: bool = True,
          working_dir: Optional[str] = None) -> dict:
    """Create a detached tmux session in the NOLAN repo and launch Claude Code in it.

    Returns ``{ok, session, error}``. The agent boots asynchronously; poll
    :func:`detect_status` (or the pane) until it reports ``idle`` before dispatching work.
    """
    name = _sanitize(name) if name else next_session_name()
    if has_session(name):
        return {"ok": False, "session": name, "error": "session already exists"}
    wd = working_dir or _wsl_repo_dir()
    try:
        r = _tmux(["new-session", "-d", "-s", name, "-c", wd])
        if r.returncode != 0:
            return {"ok": False, "session": name,
                    "error": (r.stderr or "failed to create tmux session").strip()}
        cli = ("claude " + (DEFAULT_CLAUDE_ARGS if dangerous else "")).strip()
        _tmux(["send-keys", "-t", name, "-l", cli])
        time.sleep(0.3)                          # TUI debounces PTY input
        _tmux(["send-keys", "-t", name, "Enter"])
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        return {"ok": False, "session": name, "error": str(e)}
    write_status(name, state="spawned", spawned=True, working_dir=wd,
                 message="spawned by hub — booting claude", result=None, error=None,
                 started_at=time.time())
    return {"ok": True, "session": name, "error": None}


def kill(name: str) -> bool:
    """Kill a session and clear its status file (so the board doesn't show a ghost)."""
    safe = _sanitize(name)
    try:
        ok = _tmux(["kill-session", "-t", safe]).returncode == 0
    except (FileNotFoundError, subprocess.SubprocessError):
        ok = False
    _status_path(safe).unlink(missing_ok=True)
    return ok


def fleet_detailed(prefix: str = AGENT_PREFIX) -> List[dict]:
    """:func:`fleet` joined with a live pane-derived status + the hub-spawned flag."""
    out = fleet(prefix)
    for a in out:
        if a.get("session_alive"):
            a["live_status"] = detect_status(a["agent"])
            a["spawned"] = bool((read_status(a["agent"]) or {}).get("spawned"))
        else:
            a["live_status"] = "gone"
            a["spawned"] = bool((read_status(a["agent"]) or {}).get("spawned"))
    return out


def dispatch(agent: str, plan_path: str, project: str, scene_ids: List[str], note: str) -> dict:
    """Write the initial status and send the task to the agent's tmux session.

    Flow projects get a flow-aware prompt (spec-not-view, palette, block-reuse, chapter-block
    re-render); everything else gets the generic nolan-scene-edit prompt.
    """
    # Guard against self-dispatch: an agent can't be its own fleet worker — the send-keys
    # would type into our own input and silently no-op (status frozen at 'dispatched').
    if agent == current_session():
        raise ValueError(f"refusing self-dispatch: '{agent}' is THIS agent's own tmux session — "
                         "pick a different fleet agent.")
    from nolan.webui.operations import _dispatch_to_tmux
    note = _resolve_note_mentions(str(plan_path), scene_ids, note)
    write_status(agent, state="dispatched", project=project, plan=str(plan_path),
                 scene_ids=scene_ids, note=note, message="dispatched", result=None, error=None,
                 started_at=time.time())
    ctx = _flow_context(str(plan_path), scene_ids)
    # Feedback ledger: the human's beat-edit note is a correction at the Scene-page gate (Gate B).
    # Record it against the skill that governs the edit — the flow-edit contract for flow projects,
    # the generic scene-edit skill otherwise.
    if note:
        try:
            from nolan.skills import record_feedback
            record_feedback("flow.edit-contract" if ctx else "scene-edit", note,
                            ctx={"project": project, "beats": scene_ids})
        except Exception:
            pass   # ledger must never block a dispatch
    prompt = (build_flow_dispatch_prompt(agent, str(plan_path), scene_ids, note, ctx) if ctx
              else build_dispatch_prompt(agent, str(plan_path), scene_ids, note))
    _dispatch_to_tmux(agent, prompt)
    return read_status(agent)
