"""Video Styles routes for the NOLAN hub.

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
    style_store = ctx.style_store

    # ==================== Video Styles (reference videos → visual style guide) ====================

    from nolan.video_style import VideoStyleStore
    video_style_store = VideoStyleStore(Path("video_styles"))
    video_styles_template = templates_dir / "video_styles.html"

    @app.get("/video-styles", response_class=HTMLResponse)
    async def video_styles_page():
        if video_styles_template.exists():
            return video_styles_template.read_text(encoding="utf-8")
        return "<h1>video_styles.html not found</h1>"

    @app.get("/api/video-styles")
    async def video_styles_list():
        return {"styles": video_style_store.list()}

    @app.post("/api/video-styles")
    async def video_styles_create(body: dict = Body(...)):
        name = (body.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        return {"style": video_style_store.get(video_style_store.create(name))}

    @app.get("/api/video-styles/{style_id}")
    async def video_styles_get(style_id: str):
        if not video_style_store.exists(style_id):
            raise HTTPException(status_code=404, detail="video style not found")
        return video_style_store.get(style_id)

    @app.delete("/api/video-styles/{style_id}")
    async def video_styles_delete(style_id: str):
        if not video_style_store.delete(style_id):
            raise HTTPException(status_code=404, detail="video style not found")
        return {"deleted": style_id}

    @app.post("/api/video-styles/{style_id}/add-video")
    async def video_styles_add_video(style_id: str, body: dict = Body(...)):
        if not video_style_store.exists(style_id):
            raise HTTPException(status_code=404, detail="video style not found")
        vp = (body.get("video_path") or "").strip()
        if not vp:
            raise HTTPException(status_code=400, detail="video_path is required")
        entry = video_style_store.add_video(
            style_id, video_path=vp, title=(body.get("title") or "").strip(),
            duration=body.get("duration"), indexed=bool(body.get("indexed")))
        return {"source": entry}

    @app.post("/api/video-styles/{style_id}/remove-source/{slug}")
    async def video_styles_remove_source(style_id: str, slug: str):
        if not video_style_store.remove_source(style_id, slug):
            raise HTTPException(status_code=404, detail="source not found")
        return {"removed": slug}

    @app.post("/api/video-styles/{style_id}/pair-script")
    async def video_styles_pair_script(style_id: str, body: dict = Body(...)):
        if not video_style_store.exists(style_id):
            raise HTTPException(status_code=404, detail="video style not found")
        ssid = (body.get("script_style_id") or "").strip() or None
        if ssid and not style_store.exists(ssid):
            raise HTTPException(status_code=400, detail=f"unknown script style: {ssid}")
        video_style_store.pair_script_style(style_id, ssid)
        return {"style_id": style_id, "script_style_id": ssid}

    @app.post("/api/video-styles/{style_id}/analyze")
    async def video_styles_analyze(style_id: str, body: dict = Body(default={})):
        from nolan.config import load_config
        from nolan.webui import operations
        if not video_style_store.exists(style_id):
            raise HTTPException(status_code=404, detail="video style not found")
        config = load_config()
        effective_db = db_path or Path(config.indexing.database).expanduser()
        session = (body.get("session") or "nolan2").strip() or "nolan2"
        job = job_manager.start(
            "analyze-video-style", operations.analyze_video_style,
            meta={"style_id": style_id, "session": session},
            config=config, store_root="video_styles", db_path=effective_db,
            style_id=style_id, session=session,
            provider=(body.get("provider") or "openrouter"),
            enable_vision=bool(body.get("enable_vision", True)))
        return {"job_id": job.id, "type": "analyze-video-style"}

    @app.get("/api/video-styles/{style_id}/guide")
    async def video_styles_guide(style_id: str):
        guide = video_style_store.read_guide(style_id)
        if guide is None:
            raise HTTPException(status_code=404, detail="no guide yet")
        return {"style_id": style_id, "content": guide}

    @app.get("/api/video-styles/{style_id}/extract/{slug}")
    async def video_styles_extract(style_id: str, slug: str):
        ex = video_style_store.read_extract(style_id, slug)
        if ex is None:
            raise HTTPException(status_code=404, detail="no extract yet")
        return ex
