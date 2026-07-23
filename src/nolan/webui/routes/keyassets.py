"""/keyassets — the Key-Assets Anchored Pool: the hero pull-list (plan) + collected-asset gallery.

Kept SEPARATE from /pool (acquisition pool) — distinct artifacts — but both feed authoring.

GET  /keyassets                       the page (static shell; data fetched client-side)
GET  /api/keyassets?project=<slug>    the pull-list view (nolan.keyassets.view.build_view)
GET  /api/keyassets/file?project=&path=   serve a collected asset file (guarded to the project dir)
"""
from pathlib import Path

from fastapi import HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse


def register(app, ctx):
    templates_dir = Path(ctx.templates_dir)

    def _project_dir(project: str) -> Path:
        # Resolve at REQUEST time (not register time): ctx.projects_dir may be None when the hub is
        # built without a projects directory, and Path(None) would crash create_hub_app for EVERY route.
        if not project:
            raise HTTPException(status_code=400, detail="project required")
        if not ctx.projects_dir:
            raise HTTPException(status_code=503, detail="projects directory not configured")
        d = Path(ctx.projects_dir) / project
        if not d.is_dir():
            raise HTTPException(status_code=404, detail=f"project not found: {project}")
        return d

    @app.get("/keyassets", response_class=HTMLResponse)
    async def keyassets_page():
        return (templates_dir / "keyassets.html").read_text(encoding="utf-8")

    @app.get("/api/keyassets/projects")
    async def keyassets_projects():
        """Projects that HAVE a key-assets plan (proposal or canonical) — the dropdown source, so a
        scriptgen-only project (no scene plan, excluded from /api/scenes/projects) still shows up."""
        base = Path(ctx.projects_dir) if ctx.projects_dir else None
        if not base or not base.is_dir():
            return []
        return [d.name for d in sorted(base.iterdir())
                if d.is_dir() and ((d / "key_assets.proposal.json").exists() or (d / "key_assets.json").exists())]

    @app.get("/api/keyassets")
    async def keyassets_get(project: str = Query(...)):
        from nolan.keyassets.view import build_view
        return build_view(_project_dir(project))

    @app.get("/api/keyassets/file")
    async def keyassets_file(project: str = Query(...), path: str = Query(...)):
        base = _project_dir(project).resolve()
        f = (base / path).resolve()
        if not str(f).startswith(str(base)) or not f.is_file():   # no path escape out of the project
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(str(f))
