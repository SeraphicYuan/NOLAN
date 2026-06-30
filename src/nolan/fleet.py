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
        f"Edit and re-render ONLY the named scene(s); leave all others untouched."
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
    beats = {}
    try:
        rows = [s for sec in json.loads(Path(plan_path).read_text(encoding="utf-8")).get("sections", {}).values() for s in sec]
        for r in rows:
            if r.get("id") in scene_ids:
                beats[r["id"]] = {"block": r.get("block"),
                                  "tray": [a.get("src") for a in (r.get("assets") or [])],
                                  "wishlist": [w.get("want") for w in (r.get("wishlist") or []) if w.get("want")]}
    except (OSError, json.JSONDecodeError):
        pass
    return {"flow": flow_id, "theme": spec.get("theme"), "palette": palette, "beats": beats}


def build_flow_dispatch_prompt(agent: str, plan_path: str, scene_ids: List[str], note: str, ctx: dict) -> str:
    """Flow-aware prompt — carries the flow id/theme/palette + per-beat asset state + the
    flow-edit contract (edit the spec not the view, reuse blocks, chapter-block re-render)."""
    spec_path = str(Path(plan_path).parent / "flow.spec.json")
    lines = []
    for bid in scene_ids:
        b = ctx["beats"].get(bid, {})
        bits = [f"block={b.get('block')}"]
        if b.get("tray"):
            bits.append(f"the human added {len(b['tray'])} asset(s) to its tray — use them")
        if b.get("wishlist"):
            bits.append("wishlist: " + "; ".join(b["wishlist"]))
        lines.append(f"{bid} ({', '.join(bits)})")
    return (
        f"You are fleet agent '{agent}' editing a FLOW video (flow='{ctx['flow']}', theme='{ctx['theme']}'). "
        f"FIRST read web-video-lab/flows/FLOW_EDIT.md — the flow-edit contract; it OVERRIDES the generic "
        f"nolan-scene-edit skill. Edit the SOURCE OF TRUTH \"{spec_path}\" (NOT scene_plan.json — that's a "
        f"regenerated view). Beat(s) to rework: {'; '.join(lines)}. Human note: \"{note}\". "
        f"Pick blocks ONLY from the palette: {', '.join(ctx['palette'])}. "
        f"REUSE before rebuilding: before authoring any new block, check the palette + the ONE block "
        f"library render-service/remotion-lib/src/blocks/library/ (40 blocks — ArtworkStage, DetailLoupe, "
        f"PhotoGrid, PhotoMontage, …) and reuse it; only author a genuinely new block if none fits. "
        f"Use assets already bound/added to the beat; source new only if needed. "
        f"Re-render ONLY the named beat(s) via the chapter-block mechanism: "
        f"rerender_scenes(\"{plan_path}\", {scene_ids}). Leave neighbors untouched. "
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
    prompt = (build_flow_dispatch_prompt(agent, str(plan_path), scene_ids, note, ctx) if ctx
              else build_dispatch_prompt(agent, str(plan_path), scene_ids, note))
    _dispatch_to_tmux(agent, prompt)
    return read_status(agent)
