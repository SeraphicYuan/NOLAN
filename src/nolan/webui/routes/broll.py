"""Broll routes for the NOLAN hub.

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
    templates_dir = ctx.templates_dir
    db_path = ctx.db_path
    job_manager = ctx.job_manager

    # ==================== Evocative (tonal) b-roll search ====================

    @app.get("/broll", response_class=HTMLResponse)
    async def broll_page():
        return (templates_dir / "broll.html").read_text(encoding="utf-8")

    @app.get("/api/broll/providers")
    async def api_broll_providers():
        from nolan.config import load_config
        from nolan.evoke_broll import available_video_providers
        return {"providers": available_video_providers(load_config())}

    @app.post("/api/broll/evoke")
    async def api_broll_evoke(body: dict = Body(...)):
        from nolan.config import load_config
        from nolan.webui import operations
        line = (body.get("line") or "").strip()
        if not line:
            raise HTTPException(status_code=400, detail="line is required")
        srcs = body.get("sources")
        med = body.get("media")
        job = job_manager.start(
            "evoke-broll", operations.evoke_broll, config=load_config(),
            line=line, operator=(body.get("operator") or "tonal"),
            mode=(body.get("mode") or "stock"),
            period=(body.get("period") or "").strip(), locale=(body.get("locale") or "").strip(),
            literalness=body.get("literalness", 0.25), mood=(body.get("mood") or None),
            sources=(srcs if isinstance(srcs, list) and srcs else None),
            media=(med if isinstance(med, list) and med else None),
            project=(body.get("project") or None),
            gen_style=(body.get("gen_style") or "Fooocus Cinematic"),
            beat=(body.get("beat") if isinstance(body.get("beat"), int) else None),
        )
        return {"job_id": job.id, "type": "evoke-broll"}

    @app.get("/api/broll/projects")
    async def api_broll_projects():
        """Projects with a script → selectable as ScriptContext on /broll (with their beats)."""
        from nolan.webui import operations
        import asyncio as _a
        projects = await _a.get_event_loop().run_in_executor(None, operations.list_context_projects)
        return {"projects": projects}

    @app.post("/api/broll/preview")
    async def api_broll_preview(body: dict = Body(...)):
        from nolan.config import load_config
        from nolan.webui import operations
        src = (body.get("src") or "").strip()
        if not src:
            raise HTTPException(status_code=400, detail="src is required")
        job = job_manager.start(
            "broll-preview", operations.preview_motion, config=load_config(),
            src=src, motion_id=(body.get("motion_id") or "ken-burns-in"), kind=(body.get("kind") or "image"),
        )
        return {"job_id": job.id, "type": "broll-preview"}

    @app.post("/api/broll/split")
    async def api_broll_split(body: dict = Body(...)):
        from nolan.config import load_config
        from nolan.webui import operations
        left, right = (body.get("left_src") or "").strip(), (body.get("right_src") or "").strip()
        if not left or not right:
            raise HTTPException(status_code=400, detail="left_src and right_src are required")
        job = job_manager.start(
            "broll-split", operations.preview_split, config=load_config(),
            left_src=left, right_src=right,
            left_label=(body.get("left_label") or ""), right_label=(body.get("right_label") or ""),
        )
        return {"job_id": job.id, "type": "broll-split"}

    @app.post("/api/broll/stat")
    async def api_broll_stat(body: dict = Body(...)):
        from nolan.config import load_config
        from nolan.webui import operations
        src = (body.get("src") or "").strip()
        if not src:
            raise HTTPException(status_code=400, detail="src is required")
        if body.get("value") in (None, ""):
            raise HTTPException(status_code=400, detail="value is required")
        job = job_manager.start(
            "broll-stat", operations.preview_stat, config=load_config(),
            src=src, value=body.get("value"), prefix=(body.get("prefix") or ""),
            suffix=(body.get("suffix") or ""), caption=(body.get("caption") or ""),
            decimals=int(body.get("decimals") or 0), theme=(body.get("theme") or "dark-editorial"),
            accent=(body.get("accent") or ""),
        )
        return {"job_id": job.id, "type": "broll-stat"}

    # ==================== Vector index management ====================

    @app.post("/api/sync-vectors")
    async def api_sync_vectors(body: dict = Body(default={})):
        from nolan.config import load_config
        from nolan.webui import operations
        config = load_config()
        effective_db = db_path or Path(config.indexing.database).expanduser()
        job = job_manager.start(
            "sync-vectors", operations.sync_vectors,
            db_path=effective_db, project_id=(body.get("project_id") or None),
        )
        return {"job_id": job.id, "type": "sync-vectors"}
