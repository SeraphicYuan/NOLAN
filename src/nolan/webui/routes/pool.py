"""/pool — the project asset pool (media bin) routes.

GET  /pool                       the page
GET  /api/pool?project=          the derived pool (nolan.asset_pool)
POST /api/pool/shortlist         add a pool item to the shortlist
                                 {project, path, kind, scene_hint?, note?}

The pool is a DERIVED view; the only mutation here goes through the existing
shortlist store (usage tags are render-only by design — nothing in this
module can mark an asset "in-video").
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Body, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse

_MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".gif": "image/gif",
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
    ".m4v": "video/mp4",
}


def register(app, ctx):
    templates_dir = ctx.templates_dir
    projects_dir = ctx.projects_dir

    def _project_dir(project: str) -> Path:
        if not projects_dir:
            raise HTTPException(status_code=400, detail="no projects dir")
        p = Path(projects_dir) / project
        if not p.is_dir():
            raise HTTPException(status_code=404,
                                detail=f"project {project!r} not found")
        return p

    @app.get("/pool", response_class=HTMLResponse)
    async def pool_page():
        tpl = templates_dir / "pool.html"
        if tpl.exists():
            return tpl.read_text(encoding="utf-8")
        raise HTTPException(status_code=404, detail="pool.html missing")

    @app.get("/api/pool")
    async def pool_get(project: str = Query(...)):
        from nolan.asset_pool import build_pool
        return build_pool(_project_dir(project))

    @app.get("/api/pool/file")
    async def pool_file(path: str = Query(...)):
        """Serve a pool media file. Pool paths are absolute; unlike
        /scenes/file this is contained to the PROJECTS root so shortlist
        items resolved from projects/_library/** are viewable too."""
        if not projects_dir:
            raise HTTPException(status_code=400, detail="no projects dir")
        root = Path(projects_dir).resolve()
        try:
            fp = Path(path).resolve()
        except OSError:
            raise HTTPException(status_code=400, detail="bad path")
        if root not in fp.parents or not fp.is_file():
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(str(fp), media_type=_MEDIA_TYPES.get(
            fp.suffix.lower(), "application/octet-stream"))

    @app.post("/api/pool/shortlist")
    async def pool_shortlist(body: dict = Body(...)):
        project = (body.get("project") or "").strip()
        path = (body.get("path") or "").strip()
        if not (project and path):
            raise HTTPException(status_code=400,
                                detail="project and path are required")
        pdir = _project_dir(project)
        from nolan import shortlist
        item = {
            "key": f"path:{path}",
            "kind": body.get("kind") or "image",
            "label": Path(path).name,
            "payload": {"op": "add", "source": "path", "path": path,
                        "kind": body.get("kind") or "image"},
        }
        if body.get("scene_hint"):
            item["scene_hint"] = body["scene_hint"]
        if body.get("note"):
            item["note"] = body["note"]
        items = shortlist.add(pdir, [item])
        return {"project": project, "count": len(items), "added": item["key"]}
