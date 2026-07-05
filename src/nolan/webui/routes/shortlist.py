"""Per-project asset shortlist routes.

The shortlist is the curation pool that bridges the picture/clip libraries to an
essay's scenes. Items are stored (see :mod:`nolan.shortlist`) in the same shape
the ``/scenes`` asset picker consumes, so the picker's "Shortlist" source can add
them to scenes through the existing ``POST /api/scenes/scene/assets`` seam with no
translation.
"""
from pathlib import Path

from fastapi import Body, HTTPException, Query

from nolan import shortlist as _shortlist


def register(app, ctx):
    projects_dir = ctx.projects_dir

    def _project_dir(project: str) -> Path:
        """Resolve a project slug to its directory (mirrors scenes _get_project_dir)."""
        if not projects_dir:
            raise HTTPException(status_code=404, detail="no projects directory configured")
        project = (project or "").strip()
        if not project:
            raise HTTPException(status_code=400, detail="project is required")
        if projects_dir.name == project:
            return projects_dir
        candidate = projects_dir / project
        if candidate.exists() and candidate.is_dir():
            return candidate
        raise HTTPException(status_code=404, detail=f"project not found: {project}")

    @app.get("/api/shortlist")
    async def shortlist_get(project: str = Query(...)):
        return {"project": project, "items": _shortlist.load(_project_dir(project))}

    @app.post("/api/shortlist/add")
    async def shortlist_add(body: dict = Body(...)):
        project = (body.get("project") or "").strip()
        items = body.get("items") or []
        if not isinstance(items, list) or not items:
            raise HTTPException(status_code=400, detail="items (non-empty list) is required")
        updated = _shortlist.add(_project_dir(project), items)
        return {"project": project, "items": updated, "count": len(updated)}

    @app.post("/api/shortlist/remove")
    async def shortlist_remove(body: dict = Body(...)):
        project = (body.get("project") or "").strip()
        keys = body.get("keys") or []
        updated = _shortlist.remove(_project_dir(project), keys)
        return {"project": project, "items": updated, "count": len(updated)}

    @app.post("/api/shortlist/clear")
    async def shortlist_clear(body: dict = Body(...)):
        project = (body.get("project") or "").strip()
        _shortlist.clear(_project_dir(project))
        return {"project": project, "items": [], "count": 0}
