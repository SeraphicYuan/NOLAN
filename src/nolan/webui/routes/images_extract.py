"""Images Extract routes for the NOLAN hub.

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

    # ==================== Asset extraction (link -> assets) ====================

    @app.get("/extract", response_class=HTMLResponse)
    async def extract_page():
        tpl = templates_dir / "extract.html"
        if tpl.exists():
            return tpl.read_text(encoding="utf-8")
        return "<h1>extract.html not found</h1>"

    @app.post("/api/extract-assets")
    async def api_extract_assets(body: dict = Body(...)):
        """Extract image assets from a URL.

        Without ``download`` runs synchronously and returns the found assets for
        a gallery preview; with ``download`` starts a background job.
        """
        url = (body.get("url") or "").strip()
        if not url:
            raise HTTPException(status_code=400, detail="url is required")
        limit = body.get("limit") or None

        if body.get("download") or body.get("save_to_library"):
            from nolan.webui import operations
            job = job_manager.start(
                "extract-assets", operations.extract_assets, meta={"url": url},
                url=url, limit=limit, download=bool(body.get("download", True)),
                dest=(body.get("dest") or None),
                save_to_library=bool(body.get("save_to_library")),
                scope=(body.get("scope") or "global"),
                project=(body.get("project") or None),
            )
            return {"job_id": job.id, "type": "extract-assets"}

        import asyncio as _asyncio
        from nolan.extractors import extract_from_url, get_extractor
        ex = get_extractor(url)
        try:
            results = await _asyncio.to_thread(extract_from_url, url, limit=limit)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"extract failed: {e}")
        return {"extractor": ex.name, "count": len(results),
                "results": [r.to_dict() for r in results]}

    # ==================== Picture library ====================

    @app.get("/images", response_class=HTMLResponse)
    async def images_page():
        tpl = templates_dir / "images.html"
        if tpl.exists():
            return tpl.read_text(encoding="utf-8")
        return "<h1>images.html not found</h1>"

    def _open_imagelib(scope: str, project: Optional[str]):
        from nolan.imagelib import ImageLibrary
        return ImageLibrary(scope=scope or "global", project=(project or None))

    def _img_dict(asset, score, scope, project):
        return {
            "id": asset.id, "title": asset.title, "license": asset.license,
            "source": asset.source, "source_url": asset.source_url,
            "width": asset.width, "height": asset.height, "score": score,
            "scope": scope, "scope_project": project,
            "raw": f"/api/images/raw?scope={scope}&project={project or ''}&id={asset.id}",
        }

    @app.get("/api/images/search")
    async def api_images_search(q: str, scope: str = "global", project: str = None,
                                k: int = 24, license: str = None):
        import asyncio as _asyncio

        def _do():
            from nolan.imagelib import ImageLibrary
            scopes = []
            if scope in ("global", "both"):
                scopes.append(("global", None))
            if scope in ("project", "both") and project:
                scopes.append(("project", project))
            if not scopes:
                scopes = [("global", None)]
            hits = []
            for sc, pr in scopes:
                lib = ImageLibrary(scope=sc, project=pr)
                for h in lib.search(q, k=k, license_contains=license):
                    hits.append(_img_dict(h.asset, h.score, sc, pr))
            hits.sort(key=lambda d: (d["score"] or 0), reverse=True)
            return hits[:k]

        return {"query": q, "results": await _asyncio.to_thread(_do)}

    @app.get("/api/images/list")
    async def api_images_list(scope: str = "global", project: str = None,
                              source: str = None, license: str = None,
                              status: str = "active", limit: int = 60):
        lib = _open_imagelib(scope, project)
        items = [_img_dict(a, None, scope, project)
                 for a in lib.list(status=status, source=source,
                                   license_contains=license, limit=limit)]
        return {"results": items, "stats": lib.stats()}

    @app.get("/api/images/raw")
    async def api_images_raw(id: int, scope: str = "global", project: str = None):
        lib = _open_imagelib(scope, project)
        a = lib.catalog.get(id)
        if not a:
            raise HTTPException(status_code=404, detail="asset not found")
        path = (lib.base / a.path).resolve()
        if not str(path).startswith(str(lib.base.resolve())) or not path.exists():
            raise HTTPException(status_code=404, detail="file missing")
        return FileResponse(str(path))

    @app.post("/api/images/{asset_id}/reject")
    async def api_images_reject(asset_id: int, body: dict = Body(default={})):
        lib = _open_imagelib(body.get("scope", "global"), body.get("project"))
        lib.set_status(asset_id, "rejected")
        return {"ok": True, "id": asset_id}

    @app.post("/api/images/add")
    async def api_images_add(body: dict = Body(...)):
        """Ingest an image by URL into the library (tagged with an optional topic)."""
        import asyncio as _asyncio
        url = (body.get("url") or "").strip()
        if not url:
            raise HTTPException(status_code=400, detail="url is required")

        def _do():
            lib = _open_imagelib(body.get("scope", "global"), body.get("project"))
            asset, created = lib.add_url(
                url, source=(body.get("source") or "web"),
                license=body.get("license"), query=body.get("query"))
            return {"id": asset.id, "created": created, "title": asset.title}
        try:
            return await _asyncio.to_thread(_do)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"add failed: {e}")

    @app.post("/api/images/{asset_id}/promote")
    async def api_images_promote(asset_id: int, body: dict = Body(default={})):
        """Copy a project asset into the global library."""
        import asyncio as _asyncio
        project = body.get("project")
        if not project:
            raise HTTPException(status_code=400, detail="project is required")

        def _do():
            from nolan.imagelib import promote_to_global
            asset, created = promote_to_global(project, asset_id)
            return {"ok": True, "global_id": asset.id, "created": created}
        try:
            return await _asyncio.to_thread(_do)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/images/{asset_id}/cutout")
    async def api_images_cutout(asset_id: int, body: dict = Body(default={})):
        """Remove an image's background -> new transparent-PNG asset in the same library."""
        import asyncio as _asyncio
        import os
        import tempfile
        model = body.get("model", "birefnet")
        scope = body.get("scope", "global")
        project = body.get("project")

        def _do():
            from nolan.cutout import remove_background
            lib = _open_imagelib(scope, project)
            a = lib.catalog.get(asset_id)
            if not a:
                raise HTTPException(status_code=404, detail="asset not found")
            src = (lib.base / a.path).resolve()
            if not str(src).startswith(str(lib.base.resolve())) or not src.exists():
                raise HTTPException(status_code=404, detail="file missing")
            rgba = remove_background(str(src), model=model,
                                     alpha_matting=bool(body.get("alpha_matting")))
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            try:
                rgba.save(tmp.name)
                tmp.close()
                title = (a.title or f"asset {asset_id}") + " (cutout)"
                new_asset, created = lib.add_file(
                    tmp.name, source="cutout", title=title,
                    tags=["cutout", model], describe=False)
            finally:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass
            return {**_img_dict(new_asset, None, scope, project), "created": created}

        try:
            return await _asyncio.to_thread(_do)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"cutout failed: {e}")

    @app.post("/api/images/{asset_id}/cutout/preview")
    async def api_images_cutout_preview(asset_id: int, body: dict = Body(default={})):
        """Preview a cutout as a transparent PNG — does NOT save to the library."""
        import asyncio as _asyncio
        from io import BytesIO
        from starlette.responses import Response
        model = body.get("model", "birefnet")
        scope = body.get("scope", "global")
        project = body.get("project")

        def _do():
            from nolan.cutout import remove_background
            lib = _open_imagelib(scope, project)
            a = lib.catalog.get(asset_id)
            if not a:
                raise HTTPException(status_code=404, detail="asset not found")
            src = (lib.base / a.path).resolve()
            if not str(src).startswith(str(lib.base.resolve())) or not src.exists():
                raise HTTPException(status_code=404, detail="file missing")
            rgba = remove_background(str(src), model=model,
                                     alpha_matting=bool(body.get("alpha_matting")))
            buf = BytesIO()
            rgba.save(buf, format="PNG")
            return buf.getvalue()

        try:
            data = await _asyncio.to_thread(_do)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"cutout failed: {e}")
        return Response(content=data, media_type="image/png")

    @app.get("/api/images/stats")
    async def api_images_stats(scope: str = "global", project: str = None):
        return _open_imagelib(scope, project).stats()
