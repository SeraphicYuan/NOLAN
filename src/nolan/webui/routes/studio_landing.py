"""Studio Landing routes for the NOLAN hub.

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

from nolan.hub import scan_projects


def register(app, ctx):
    templates_dir = ctx.templates_dir
    db_path = ctx.db_path
    projects_dir = ctx.projects_dir
    render_service_url = ctx.render_service_url
    _render_service_up = ctx._render_service_up

    # ==================== Project Studio (full loop) ====================

    @app.get("/studio", response_class=HTMLResponse)
    async def studio_page():
        tpl = templates_dir / "studio.html"
        if tpl.exists():
            return tpl.read_text(encoding="utf-8")
        return "<h1>studio.html not found</h1>"

    @app.get("/api/project/{project}/status")
    async def api_project_status(project: str):
        """Per-project pipeline-stage status for the Studio view."""
        base = Path("projects") / project
        scene_plan = base / "scene_plan.json"
        status = {
            "project": project,
            "exists": base.exists(),
            "has_essay": (base / "essay.md").exists(),
            "has_script": (base / "script.md").exists(),
            "has_scene_plan": scene_plan.exists(),
            "scenes": 0, "matched": 0, "rendered": 0, "has_final": False,
            "source_videos": 0,
        }
        src = base / "source"
        if src.exists():
            status["source_videos"] = len([p for p in src.glob("*.mp4")])
        if scene_plan.exists():
            try:
                from nolan.scenes import ScenePlan
                plan = ScenePlan.load(str(scene_plan))
                scenes = plan.all_scenes
                status["scenes"] = len(scenes)
                status["matched"] = sum(1 for s in scenes
                                        if getattr(s, "matched_asset", None) or getattr(s, "matched_clip", None))
                status["rendered"] = sum(1 for s in scenes if getattr(s, "rendered_clip", None))
            except Exception as e:
                status["error"] = str(e)
        finals = list(base.glob("*.mp4")) + list((base / "output").glob("*.mp4")) if base.exists() else []
        status["has_final"] = len(finals) > 0
        try:
            from nolan import shortlist as _sl
            status["shortlist"] = len(_sl.load(base))
        except Exception:
            status["shortlist"] = 0
        status["has_voiceover"] = (base / "assets" / "voiceover" / "voiceover.mp3").exists()
        try:
            import yaml as _yaml
            _meta = _yaml.safe_load((base / "project.yaml").read_text(encoding="utf-8")) or {}
            status["render_mode"] = _meta.get("render_mode") or "standard"
            status["voice_id"] = _meta.get("voice_id") or ""
        except Exception:
            status["render_mode"], status["voice_id"] = "standard", ""
        return status

    @app.get("/api/project/{project}/final")
    async def api_project_final(project: str):
        """Stream a project's final video (output/final.mp4)."""
        base = (Path("projects") / project).resolve()
        if Path("projects").resolve() not in base.parents:
            raise HTTPException(status_code=404, detail="bad project")
        fp = base / "output" / "final.mp4"
        if not fp.exists():
            raise HTTPException(status_code=404, detail="no final video")
        return FileResponse(str(fp), media_type="video/mp4")

    # ==================== Landing Page ====================

    @app.get("/", response_class=HTMLResponse)
    async def landing():
        """Serve the hub landing page."""
        hub_template = templates_dir / "hub.html"
        if hub_template.exists():
            return hub_template.read_text(encoding="utf-8")
        return "<h1>Hub template not found</h1>"

    @app.get("/api/status")
    async def hub_status():
        """Get hub status info for landing page."""
        library_available = db_path and db_path.exists()
        projects = scan_projects(projects_dir) if projects_dir else []

        render_up = await _render_service_up()
        return {
            "library": {
                "available": library_available,
                "db_path": str(db_path) if db_path else None,
            },
            "showcase": {
                "available": True,
                "render_service_url": render_service_url,
            },
            "render_service": {
                "available": render_up,
                "url": render_service_url,
            },
            "projects": projects,
        }

    @app.get("/api/projects")
    async def list_unified_projects():
        """Unified project list with capability flags (C1).

        One source of truth across scenes/script/orchestrator/segment, replacing
        the per-page scans. ``library_project_id`` links each FS project to its
        index-DB row (by slug) when a library DB is present.
        """
        from nolan import projects as _projects
        if not projects_dir:
            return {"projects": [], "total": 0}
        idx = None
        if db_path and db_path.exists():
            try:
                from nolan.indexer import VideoIndex
                idx = VideoIndex(db_path)
            except Exception:
                idx = None
        found = _projects.discover_projects(projects_dir, index=idx)
        return {"projects": [p.to_dict() for p in found], "total": len(found)}
