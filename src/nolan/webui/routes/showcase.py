"""Showcase routes for the NOLAN hub.

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
    render_service_url = ctx.render_service_url
    uploads_dir = ctx.uploads_dir

    # ==================== Showcase Routes ====================

    showcase_template = templates_dir / "showcase.html"

    @app.get("/showcase", response_class=HTMLResponse)
    async def showcase_home():
        """Serve the showcase page."""
        return showcase_template.read_text(encoding="utf-8")

    @app.get("/showcase/api/effects")
    async def showcase_list_effects(category: Optional[str] = None):
        """List effects from render service."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"{render_service_url}/effects"
                if category:
                    url += f"?category={category}"
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Render service unavailable")
        except httpx.HTTPStatusError:
            raise HTTPException(status_code=503, detail="Render service error")

    @app.get("/showcase/api/effects/{effect_id}")
    async def showcase_get_effect(effect_id: str):
        """Get specific effect details."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{render_service_url}/effects/{effect_id}")
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Effect not found")
            raise HTTPException(status_code=500, detail=str(e))
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Render service unavailable")

    @app.post("/showcase/api/upload")
    async def showcase_upload(file: UploadFile = File(...)):
        """Upload file for effects."""
        import uuid
        ext = Path(file.filename).suffix if file.filename else ".bin"
        filename = f"{uuid.uuid4()}{ext}"
        filepath = uploads_dir / filename
        content = await file.read()
        filepath.write_bytes(content)
        return {"filename": filename, "path": str(filepath.absolute()), "size": len(content)}

    @app.post("/showcase/api/render")
    async def showcase_render(effect: str = Form(...), params: str = Form(...)):
        """Submit render job."""
        try:
            params_dict = json.loads(params)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid params JSON")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{render_service_url}/render",
                    json={"effect": effect, "params": params_dict},
                )
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Render service unavailable")

    @app.get("/showcase/api/render/status/{job_id}")
    async def showcase_render_status(job_id: str):
        """Get render job status."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{render_service_url}/render/status/{job_id}")
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Render service unavailable")

    @app.get("/showcase/api/render/result/{job_id}")
    async def showcase_render_result(job_id: str):
        """Get render job result."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{render_service_url}/render/result/{job_id}")
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Render service unavailable")

    @app.get("/showcase/preview/{filename:path}")
    async def showcase_preview(filename: str):
        """Serve preview files."""
        locations = [
            ctx.repo_root / "render-service" / "public" / "previews" / filename,
            ctx.repo_root / "render-service" / "output" / filename,
        ]
        for path in locations:
            if path.exists():
                return FileResponse(path)
        raise HTTPException(status_code=404, detail="Preview not found")

    @app.get("/showcase/output/{filename:path}")
    async def showcase_output(filename: str):
        """Serve rendered output."""
        path = ctx.repo_root / "render-service" / "output" / filename
        if not path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(path)
