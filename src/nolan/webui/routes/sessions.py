"""Sessions routes — a fleet console for tmux Claude Code agents.

Spawn / kill / track the agents the hub dispatches script-review, scene-edit, and
effect work to (nolan1, nolan2, …). Backed by :mod:`nolan.fleet` (spawn/kill/
detect_status). tmux runs in WSL; the fleet helpers route through wsl.exe on Windows.
"""

import asyncio

from fastapi import HTTPException, Body
from fastapi.responses import HTMLResponse


def register(app, ctx):
    templates_dir = ctx.templates_dir

    @app.on_event("startup")
    async def _reap_orphan_run_agents():
        """On boot, kill any ephemeral `nolan-run-*` agents orphaned by a prior hub crash."""
        try:
            from nolan import fleet
            killed = await asyncio.to_thread(fleet.reap_run_agents)
            if killed:
                print(f"[sessions] reaped orphaned run-agents: {killed}")
        except Exception:
            pass

    @app.get("/sessions", response_class=HTMLResponse)
    async def sessions_page():
        p = templates_dir / "sessions.html"
        return p.read_text(encoding="utf-8") if p.exists() else "<h1>sessions.html not found</h1>"

    @app.get("/api/sessions")
    async def sessions_list():
        from nolan import fleet
        agents = await asyncio.to_thread(fleet.fleet_detailed)
        return {"agents": agents}

    @app.post("/api/sessions/spawn")
    async def sessions_spawn(body: dict = Body(default={})):
        from nolan import fleet
        name = (body.get("name") or "").strip() or None
        dangerous = bool(body.get("dangerous", True))
        res = await asyncio.to_thread(lambda: fleet.spawn(name, dangerous=dangerous))
        if not res.get("ok"):
            raise HTTPException(status_code=400, detail=res.get("error") or "spawn failed")
        return res

    @app.post("/api/sessions/{name}/kill")
    async def sessions_kill(name: str):
        from nolan import fleet
        ok = await asyncio.to_thread(fleet.kill, name)
        if not ok:
            raise HTTPException(status_code=404, detail="session not found or kill failed")
        return {"killed": name}

    @app.get("/api/sessions/{name}/pane")
    async def sessions_pane(name: str, lines: int = 18):
        from nolan import fleet
        txt = await asyncio.to_thread(fleet.capture_pane, name, lines)
        if txt is None:
            raise HTTPException(status_code=404, detail="no pane (session gone?)")
        return {"name": name, "pane": txt}
