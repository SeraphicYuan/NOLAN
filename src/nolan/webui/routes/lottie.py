"""Lottie routes for the NOLAN hub.

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
    render_service_url = ctx.render_service_url

    # ==================== Lottie showcase ====================

    @app.get("/lottie", response_class=HTMLResponse)
    async def lottie_page():
        tpl = templates_dir / "lottie.html"
        return tpl.read_text(encoding="utf-8") if tpl.exists() else "<h1>lottie.html not found</h1>"

    def _lottie_dict(t):
        return {"id": t.id, "name": t.name, "category": t.category, "source": t.source,
                "tags": t.tags, "width": t.width, "height": t.height,
                "duration": t.duration_seconds, "has_schema": t.has_schema,
                "schema_fields": t.schema_fields, "license": t.license, "author": t.author,
                "raw": f"/api/lottie/{t.id}/raw"}

    @app.get("/api/lottie")
    async def api_lottie_list(category: str = None, q: str = None):
        from nolan.template_catalog import TemplateCatalog
        cat = TemplateCatalog()
        items = cat.list_by_category(category) if category else cat.list_all()
        if q:
            ql = q.lower()
            items = [t for t in items if ql in t.name.lower() or ql in t.category.lower()
                     or any(ql in tag.lower() for tag in t.tags)]
        return {"templates": [_lottie_dict(t) for t in items],
                "categories": cat.categories(), "total": len(items)}

    @app.get("/api/lottie/{template_id}")
    async def api_lottie_get(template_id: str):
        from nolan.template_catalog import TemplateCatalog
        t = TemplateCatalog().get(template_id)
        if not t:
            raise HTTPException(status_code=404, detail="template not found")
        return _lottie_dict(t)

    @app.get("/api/lottie/{template_id}/raw")
    async def api_lottie_raw(template_id: str):
        from nolan.template_catalog import TemplateCatalog
        cat = TemplateCatalog()
        t = cat.get(template_id)
        if not t:
            raise HTTPException(status_code=404, detail="template not found")
        fp = cat.get_full_path(t).resolve()
        if not fp.exists():
            raise HTTPException(status_code=404, detail="file missing")
        return FileResponse(str(fp), media_type="application/json")

    @app.post("/api/lottie/render")
    async def api_lottie_render(body: dict = Body(...)):
        from nolan.webui import operations
        template_id = (body.get("id") or "").strip()
        if not template_id:
            raise HTTPException(status_code=400, detail="id is required")
        overrides = {}
        if body.get("fields"):
            overrides["fields"] = body["fields"]
        if body.get("text"):
            overrides["text"] = body["text"]
        if body.get("colors"):
            overrides["colors"] = body["colors"]
        job = job_manager.start(
            "lottie-render", operations.render_lottie_preview, meta={"id": template_id},
            template_id=template_id, overrides=overrides,
            duration=body.get("duration"), service_url=render_service_url)
        return {"job_id": job.id, "type": "lottie-render"}

    @app.get("/api/lottie/preview/{name}")
    async def api_lottie_preview(name: str):
        root = (Path("_library") / "lottie_previews").resolve()
        fp = (root / name).resolve()
        if not (root in fp.parents) or not fp.is_file():
            raise HTTPException(status_code=404, detail="preview not found")
        return FileResponse(str(fp), media_type="video/mp4")
