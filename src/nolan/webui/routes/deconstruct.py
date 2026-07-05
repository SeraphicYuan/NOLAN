"""Deconstruct routes for the NOLAN hub.

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
    script_project_store = ctx.script_project_store

    # ==================== Video deconstruction (inverse Director) ====================

    from nolan.deconstruct import DeconstructionStore
    deconstruct_store = DeconstructionStore(Path("video_deconstructions"))
    deconstruct_template = templates_dir / "deconstruct.html"

    @app.get("/deconstruct", response_class=HTMLResponse)
    async def deconstruct_page():
        if deconstruct_template.exists():
            return deconstruct_template.read_text(encoding="utf-8")
        return "<h1>deconstruct.html not found</h1>"

    @app.get("/api/deconstruct")
    async def deconstruct_list():
        return {"deconstructions": deconstruct_store.list()}

    @app.post("/api/deconstruct/run")
    async def deconstruct_run(body: dict = Body(...)):
        """Deconstruct one ingested library video (job + agent dispatch)."""
        from nolan.config import load_config
        from nolan.webui import operations
        video_path = (body.get("video_path") or "").strip()
        if not video_path:
            raise HTTPException(status_code=400, detail="video_path required")
        config = load_config()
        effective_db = db_path or Path(config.indexing.database).expanduser()
        session = (body.get("session") or "nolan2").strip() or "nolan2"
        job = job_manager.start(
            "deconstruct-video", operations.deconstruct_video,
            meta={"video_path": video_path, "session": session},
            config=config, store_root="video_deconstructions",
            db_path=effective_db, video_path=video_path, session=session,
            provider=(body.get("provider") or "openrouter"),
            enable_vision=bool(body.get("enable_vision", True)),
            use_llm=bool(body.get("use_llm", True)),
            profile=(body.get("profile") or "balanced"))
        return {"job_id": job.id, "type": "deconstruct-video"}

    @app.get("/api/deconstruct/{slug}")
    async def deconstruct_get(slug: str):
        meta = deconstruct_store.get(slug)
        if meta is None:
            raise HTTPException(status_code=404, detail="deconstruction not found")
        return meta

    @app.delete("/api/deconstruct/{slug}")
    async def deconstruct_delete(slug: str):
        if not deconstruct_store.delete(slug):
            raise HTTPException(status_code=404, detail="deconstruction not found")
        return {"deleted": slug}

    @app.get("/api/deconstruct/{slug}/artifact/{name}")
    async def deconstruct_artifact(slug: str, name: str):
        """Read an artifact: extract | plan | breakdown | task."""
        if name not in ("extract", "plan", "breakdown", "task"):
            raise HTTPException(status_code=400, detail="name must be extract/plan/breakdown/task")
        content = deconstruct_store.read_text(slug, name)
        if content is None:
            raise HTTPException(status_code=404, detail=f"no {name} yet")
        return {"slug": slug, "name": name, "content": content}

    @app.get("/api/deconstruct/{slug}/frame/{fname}")
    async def deconstruct_frame(slug: str, fname: str):
        fp = deconstruct_store.frames_dir(slug) / Path(fname).name
        if not fp.exists():
            raise HTTPException(status_code=404, detail="frame not found")
        return FileResponse(str(fp), media_type="image/jpeg")

    @app.post("/api/deconstruct/{slug}/export-template")
    async def deconstruct_export_template(slug: str):
        """Promote the recovered structure to a matchable scene-plan template."""
        from nolan.deconstruct.export import export_scene_plan_template
        meta = deconstruct_store.get(slug)
        extract = deconstruct_store.read_extract(slug)
        if meta is None or extract is None:
            raise HTTPException(status_code=404, detail="deconstruction/extract not found")
        res = export_scene_plan_template(extract, slug, meta.get("title") or slug)
        return res

    @app.post("/api/deconstruct/{slug}/clone")
    async def deconstruct_clone(slug: str, body: dict = Body(...)):
        """Seed a new script project with this deconstruction's beat structure."""
        from nolan.deconstruct.clone import clone_to_script_project
        extract = deconstruct_store.read_extract(slug)
        if extract is None:
            raise HTTPException(status_code=404, detail="no extract for this deconstruction")
        subject = (body.get("subject") or "").strip()
        style_id = (body.get("style_id") or "").strip()
        if not subject or not style_id:
            raise HTTPException(status_code=400, detail="subject and style_id required")
        res = clone_to_script_project(
            extract, slug, subject=subject, style_id=style_id,
            target_minutes=float(body.get("target_minutes") or 8.0))
        return res

    @app.post("/api/deconstruct/{slug}/send-plan")
    async def deconstruct_send_plan(slug: str, body: dict = Body(...)):
        """Copy recovered_plan.json into a project as its scene_plan.json.

        The recovered plan is scene_plan-schema by construction, so the /scenes
        page and Director steps 3-6 (tempo/clips/slides/render) operate on it.
        An existing scene_plan.json requires confirm=true and is backed up.
        """
        import json as _json
        plan = deconstruct_store.read_extract(slug) and deconstruct_store.read_text(slug, "plan")
        if not plan:
            raise HTTPException(status_code=404, detail="no recovered plan for this deconstruction")
        project_slug = (body.get("project_slug") or "").strip()
        if not project_slug:
            raise HTTPException(status_code=400, detail="project_slug required")
        pdir = Path("projects") / project_slug
        if not (pdir / "project.yaml").exists():
            raise HTTPException(status_code=404, detail=f"project not found: {project_slug}")
        target = pdir / "scene_plan.json"
        backed_up = False
        if target.exists():
            if not body.get("confirm"):
                raise HTTPException(status_code=409,
                                    detail="project already has scene_plan.json — pass confirm=true to replace (a .bak is kept)")
            target.replace(pdir / "scene_plan.json.bak")
            backed_up = True
        target.write_text(plan, encoding="utf-8")
        n_scenes = sum(len(v) for v in _json.loads(plan).get("sections", {}).values())
        return {"project_slug": project_slug, "scenes": n_scenes, "backed_up": backed_up}

    @app.post("/api/source-art")
    async def source_art_run(body: dict = Body(...)):
        """Source public-domain artworks for a project's archival-art scenes (job)."""
        from nolan.config import load_config
        from nolan.webui import operations
        project = (body.get("project") or "").strip()
        if not project:
            raise HTTPException(status_code=400, detail="project required")
        if not (Path("projects") / project / "scene_plan.json").exists():
            raise HTTPException(status_code=404, detail="project has no scene_plan.json")
        job = job_manager.start(
            "source-art", operations.source_art,
            meta={"project": project},
            config=load_config(), project=project)
        return {"job_id": job.id, "type": "source-art"}

    @app.post("/api/script-projects/{slug}/attach-deconstruction")
    async def script_projects_attach_deconstruction(slug: str, body: dict = Body(...)):
        """Attach a deconstruction's structure to an EXISTING script project."""
        from nolan.deconstruct.clone import attach_reference
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="script project not found")
        dec_slug = (body.get("deconstruction") or "").strip()
        extract = deconstruct_store.read_extract(dec_slug) if dec_slug else None
        if extract is None:
            raise HTTPException(status_code=404, detail="deconstruction/extract not found")
        try:
            res = attach_reference(extract, dec_slug, slug,
                                   replace_beatmap=bool(body.get("replace_beatmap")))
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return res
