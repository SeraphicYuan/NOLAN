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


def dispatch(agent: str, plan_path: str, project: str, scene_ids: List[str], note: str) -> dict:
    """Write the initial status and send the task to the agent's tmux session."""
    from nolan.webui.operations import _dispatch_to_tmux
    write_status(agent, state="dispatched", project=project, plan=str(plan_path),
                 scene_ids=scene_ids, note=note, message="dispatched", result=None, error=None,
                 started_at=time.time())
    _dispatch_to_tmux(agent, build_dispatch_prompt(agent, str(plan_path), scene_ids, note))
    return read_status(agent)
