"""Script Styles routes for the NOLAN hub.

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
    job_manager = ctx.job_manager

    # ==================== Script Styles (transcript corpora → style guides) ====================

    from nolan.script_style import ScriptStyleStore
    style_store = ScriptStyleStore(Path("script_styles"))
    script_styles_template = templates_dir / "script_styles.html"

    @app.get("/script-styles", response_class=HTMLResponse)
    async def script_styles_page():
        if script_styles_template.exists():
            return script_styles_template.read_text(encoding="utf-8")
        return "<h1>script_styles.html not found</h1>"

    @app.get("/api/script-styles")
    async def script_styles_list():
        return {"styles": style_store.list()}

    @app.post("/api/script-styles")
    async def script_styles_create(body: dict = Body(...)):
        name = (body.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        style_id = style_store.create(name)
        return {"style": style_store.get(style_id)}

    @app.get("/api/script-styles/{style_id}")
    async def script_styles_get(style_id: str):
        if not style_store.exists(style_id):
            raise HTTPException(status_code=404, detail="style not found")
        return style_store.get(style_id)

    @app.delete("/api/script-styles/{style_id}")
    async def script_styles_delete(style_id: str):
        if not style_store.delete(style_id):
            raise HTTPException(status_code=404, detail="style not found")
        return {"deleted": style_id}

    @app.post("/api/script-styles/{style_id}/add-text")
    async def script_styles_add_text(style_id: str, body: dict = Body(...)):
        """Add a pasted transcript to the corpus."""
        if not style_store.exists(style_id):
            raise HTTPException(status_code=404, detail="style not found")
        text = (body.get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="text is required")
        title = (body.get("title") or "Pasted transcript").strip()
        entry = style_store.add_source(style_id, text=text, title=title, source_type="upload")
        return {"source": entry}

    @app.post("/api/script-styles/{style_id}/upload-file")
    async def script_styles_upload_file(style_id: str, file: UploadFile = File(...)):
        """Add an uploaded .txt/.srt/.vtt transcript to the corpus."""
        if not style_store.exists(style_id):
            raise HTTPException(status_code=404, detail="style not found")
        raw = (await file.read())
        suffix = Path(file.filename or "").suffix.lower()
        if suffix in (".srt", ".vtt"):
            import tempfile
            from nolan.transcript import TranscriptLoader
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
                tf.write(raw)
                tmp = Path(tf.name)
            try:
                text = TranscriptLoader.load(tmp).full_text
            finally:
                tmp.unlink(missing_ok=True)
        else:
            text = raw.decode("utf-8", errors="replace")
        title = Path(file.filename or "uploaded").stem or "uploaded"
        entry = style_store.add_source(style_id, text=text, title=title, source_type="upload")
        return {"source": entry}

    @app.post("/api/script-styles/{style_id}/add-youtube")
    async def script_styles_add_youtube(style_id: str, body: dict = Body(...)):
        """Fetch transcripts for a list of YouTube URLs (background job)."""
        from nolan.webui import operations
        if not style_store.exists(style_id):
            raise HTTPException(status_code=404, detail="style not found")
        urls = body.get("urls") or []
        if isinstance(urls, str):
            urls = [u.strip() for u in urls.splitlines() if u.strip()]
        if not urls:
            raise HTTPException(status_code=400, detail="urls required")
        job = job_manager.start(
            "fetch-transcripts", operations.fetch_transcripts,
            meta={"style_id": style_id, "count": len(urls)},
            store_root="script_styles", style_id=style_id, urls=urls,
            request_delay=float(body.get("request_delay", 2.0)),
            max_retries=int(body.get("max_retries", 3)),
        )
        return {"job_id": job.id, "type": "fetch-transcripts"}

    @app.post("/api/script-styles/{style_id}/add-channel")
    async def script_styles_add_channel(style_id: str, body: dict = Body(...)):
        """Fetch transcripts from a YouTube channel (last-N or date window)."""
        from nolan.webui import operations
        if not style_store.exists(style_id):
            raise HTTPException(status_code=404, detail="style not found")
        channel = (body.get("channel") or "").strip()
        if not channel:
            raise HTTPException(status_code=400, detail="channel is required")
        mode = (body.get("mode") or "count").strip()
        job = job_manager.start(
            "fetch-channel", operations.fetch_channel,
            meta={"style_id": style_id, "channel": channel, "mode": mode},
            store_root="script_styles", style_id=style_id, channel=channel,
            mode=mode, count=int(body.get("count", 10)),
            date_after=(body.get("date_after") or None),
            date_before=(body.get("date_before") or None),
            request_delay=float(body.get("request_delay", 2.0)),
            max_retries=int(body.get("max_retries", 3)),
        )
        return {"job_id": job.id, "type": "fetch-channel"}

    @app.post("/api/script-styles/{style_id}/remove-source/{slug}")
    async def script_styles_remove_source(style_id: str, slug: str):
        if not style_store.remove_source(style_id, slug):
            raise HTTPException(status_code=404, detail="source not found")
        return {"removed": slug}

    @app.post("/api/script-styles/{style_id}/analyze")
    async def script_styles_analyze(style_id: str, body: dict = Body(default={})):
        """Run Stage-B analysis: per-transcript extraction + agent synthesis."""
        from nolan.config import load_config
        from nolan.webui import operations
        if not style_store.exists(style_id):
            raise HTTPException(status_code=404, detail="style not found")
        session = (body.get("session") or "nolan2").strip() or "nolan2"
        job = job_manager.start(
            "analyze-style", operations.analyze_style,
            meta={"style_id": style_id, "session": session},
            config=load_config(), store_root="script_styles",
            style_id=style_id, session=session,
        )
        return {"job_id": job.id, "type": "analyze-style"}

    @app.get("/api/script-styles/{style_id}/guide")
    async def script_styles_guide(style_id: str):
        guide = style_store.read_guide(style_id)
        if guide is None:
            raise HTTPException(status_code=404, detail="no guide yet")
        return {"style_id": style_id, "content": guide}

    ctx.style_store = style_store
