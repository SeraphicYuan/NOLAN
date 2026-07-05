"""Core routes for the NOLAN hub.

Moved verbatim from ``nolan.hub.create_hub_app`` (hub split). ``register(app,
ctx)`` unpacks the shared hub context into locals with the original closure
names, then registers the routes unchanged.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional, List, Dict

import httpx
from urllib.parse import quote
from fastapi import HTTPException, Query, UploadFile, File, Form, Body
from fastapi.responses import HTMLResponse, FileResponse


def register(app, ctx):
    gen_dir = ctx.gen_dir
    db_path = ctx.db_path
    render_service_url = ctx.render_service_url

    @app.get("/api/broll-galleries")
    async def api_broll_galleries():
        """List generated gallery HTML files under _broll_generated for one-click access."""
        import re
        items = []
        for p in sorted(gen_dir.glob("*.html"), key=lambda f: f.stat().st_mtime, reverse=True):
            label = p.stem.replace("_", " ").strip()
            # try the <title> for a nicer label
            try:
                head = p.read_text(encoding="utf-8", errors="ignore")[:2000]
                m = re.search(r"<title>(.*?)</title>", head, re.I | re.S)
                if m and m.group(1).strip():
                    label = m.group(1).strip()
            except OSError:
                pass
            items.append({"name": p.stem, "url": f"/broll-gen/{p.name}",
                          "label": label, "mtime": p.stat().st_mtime})
        return {"galleries": items}

    # ==================== Job Manager (background operations) ====================
    from nolan.webui.jobs import get_job_manager
    job_manager = get_job_manager()

    @app.get("/api/jobs")
    async def jobs_list(type: Optional[str] = None):
        return [j.to_dict(include_logs=False) for j in job_manager.list(job_type=type)]

    @app.get("/api/jobs/{job_id}")
    async def jobs_get(job_id: str):
        job = job_manager.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        return job.to_dict()

    @app.post("/api/jobs/{job_id}/cancel")
    async def jobs_cancel(job_id: str):
        return {"cancelled": job_manager.cancel(job_id)}

    @app.get("/api/library/tmux-sessions")
    async def list_tmux_sessions():
        """List tmux sessions available as agent-dispatch targets.

        Top-level (not gated behind the library DB) so the agent selector on
        /script-projects and /script-styles works regardless of library state.
        Path kept under /library/api for frontend back-compat."""
        from nolan.webui import operations
        import asyncio as _asyncio
        sessions = await _asyncio.get_event_loop().run_in_executor(
            None, operations.list_tmux_sessions)
        return {"sessions": sessions}

    @app.on_event("startup")
    async def _auto_reconcile_vectors():
        """On boot, embed any indexed-but-unsearchable videos (incremental → cheap if
        nothing to do). Non-blocking: runs as a background job so the hub stays responsive."""
        try:
            from nolan.config import load_config
            from nolan.indexer import VideoIndex
            from nolan.vector_search import VectorSearch
            from nolan.webui import operations
            eff = db_path or Path(load_config().indexing.database).expanduser()
            if not (eff and Path(eff).exists() and (Path(eff).parent / "vectors").exists()):
                return
            vs = VectorSearch(Path(eff).parent / "vectors", index=VideoIndex(Path(eff)))
            summary = vs.get_embedding_status()["summary"]
            if summary["needs_embedding"] > 0:
                job_manager.start(
                    "sync-vectors", operations.sync_vectors, db_path=Path(eff), project_id=None,
                )
        except Exception:
            pass  # never block hub startup on reconcile

    async def _render_service_up() -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{render_service_url}/")
                return r.status_code < 500
        except Exception:
            return False

    ctx.job_manager = job_manager
    ctx._render_service_up = _render_service_up
