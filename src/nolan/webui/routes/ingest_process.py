"""Ingest Process routes for the NOLAN hub.

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

    # ==================== Ingest (Add to Library) ====================

    @app.get("/library/add", response_class=HTMLResponse)
    async def library_add_page():
        tpl = templates_dir / "ingest.html"
        if tpl.exists():
            return tpl.read_text(encoding="utf-8")
        return "<h1>ingest.html not found</h1>"

    @app.post("/api/ingest")
    async def api_ingest(body: dict = Body(...)):
        from nolan.config import load_config
        from nolan.webui import operations
        config = load_config()
        effective_db = db_path or Path(config.indexing.database).expanduser()
        target = (body.get("target") or "").strip()
        if not target:
            raise HTTPException(status_code=400, detail="target (file path or URL) is required")
        job = job_manager.start(
            "ingest", operations.ingest,
            meta={"target": target, "source_type": body.get("source_type", "file")},
            config=config, db_path=effective_db,
            source_type=body.get("source_type", "file"),
            target=target,
            provider=body.get("provider", "openrouter"),
            model=(body.get("model") or None),
            reasoning_enabled=body.get("reasoning_enabled"),
            reasoning_max_tokens=body.get("reasoning_max_tokens"),
            project_dir=(body.get("project") or None),
            force=bool(body.get("force", False)),
            whisper_fallback=bool(body.get("whisper_fallback", True)),
        )
        return {"job_id": job.id, "type": "ingest"}

    # ==================== Essay -> Process wizard ====================

    @app.get("/process", response_class=HTMLResponse)
    async def process_page():
        tpl = templates_dir / "process.html"
        if tpl.exists():
            return tpl.read_text(encoding="utf-8")
        return "<h1>process.html not found</h1>"

    @app.post("/api/process")
    async def api_process(body: dict = Body(...)):
        from nolan.config import load_config
        from nolan.webui import operations
        essay_text = (body.get("essay_text") or "").strip()
        project_name = (body.get("project_name") or "").strip()
        if not essay_text:
            raise HTTPException(status_code=400, detail="essay_text is required")
        if not project_name:
            raise HTTPException(status_code=400, detail="project_name is required")
        # sanitize project name into a slug-safe folder
        import re as _re
        project_name = _re.sub(r"[^a-zA-Z0-9_-]+", "-", project_name).strip("-").lower() or "project"
        job = job_manager.start(
            "process", operations.process_essay,
            meta={"project": project_name},
            config=load_config(), essay_text=essay_text, project_name=project_name,
            skip_scenes=bool(body.get("skip_scenes", False)),
            style_id=(body.get("style_id") or None),
            style_pack=(body.get("style_pack") or None),
        )
        return {"job_id": job.id, "type": "process", "project": project_name}

    @app.get("/api/style-packs")
    async def api_style_packs():
        """The style-pack registry, for creation-time selection."""
        from nolan.style_packs import load_packs
        return {"packs": [{"id": p["id"],
                           "description": p.get("description", "")}
                          for p in load_packs().values()]}

    # ==================== Publish (source -> beautiful HTML article) ====================

    @app.get("/publish", response_class=HTMLResponse)
    async def publish_page():
        tpl = templates_dir / "publish.html"
        if tpl.exists():
            return tpl.read_text(encoding="utf-8")
        return "<h1>publish.html not found</h1>"

    # ── Skills registry UI (the hybrid pipeline's agent-facing skills) ──
    @app.get("/skills", response_class=HTMLResponse)
    async def skills_page():
        tpl = templates_dir / "skills.html"
        if tpl.exists():
            return tpl.read_text(encoding="utf-8")
        return "<h1>skills.html not found</h1>"

    @app.get("/api/skills")
    async def skills_index():
        from nolan import skills as sk
        return {"skills": sk.ui_index(), "lint": [list(i) for i in sk.lint_skills()]}

    @app.get("/api/skills/graph")
    async def skills_graph():
        from nolan import skills as sk
        return sk.ui_graph()

    @app.get("/api/skills/{skill_id}")
    async def skill_detail(skill_id: str):
        from nolan import skills as sk
        d = sk.ui_detail(skill_id)
        if d is None:
            raise HTTPException(status_code=404, detail=f"no skill '{skill_id}'")
        return d

    @app.post("/api/publish")
    async def api_publish(body: dict = Body(...)):
        from nolan.config import load_config
        from nolan.webui import operations
        src = (body.get("source") or "").strip()
        if not src:
            raise HTTPException(status_code=400, detail="source (URL, file path, or pasted text) is required")
        job = job_manager.start(
            "publish", operations.publish_article,
            meta={"theme": (body.get("theme") or "press")},
            nolan_config=load_config(),
            src=src,
            theme=(body.get("theme") or "press"),
            type=(body.get("type") or "explainer"),
            width=(body.get("width") or "regular"),
            images=(body.get("images") or "none"),
            brand=(body.get("brand") or None),
            cover=bool(body.get("cover", True)),
            slug=(body.get("slug") or None),
        )
        return {"job_id": job.id, "type": "publish"}

    @app.get("/publish/file")
    async def publish_file(slug: str = Query(...)):
        """Serve a published article.html by slug (contained to projects/_published)."""
        pub_root = (ctx.repo_root / "projects" / "_published").resolve()
        try:
            fp = (pub_root / slug / "article" / "article.html").resolve()
        except OSError:
            raise HTTPException(status_code=404, detail="article not found")
        if not (pub_root in fp.parents) or not fp.is_file():
            raise HTTPException(status_code=404, detail="article not found")
        return FileResponse(fp, media_type="text/html")

    # ==================== Import existing script (BYO-script) ====================

    @app.post("/api/import-script")
    async def api_import_script(body: dict = Body(...)):
        from nolan.config import load_config
        from nolan.webui import operations
        video_path = (body.get("video_path") or "").strip()
        project = (body.get("project") or "").strip()
        if not video_path or not project:
            raise HTTPException(status_code=400, detail="video_path and project are required")
        import re as _re
        project = _re.sub(r"[^a-zA-Z0-9_-]+", "-", project).strip("-").lower() or "project"
        job = job_manager.start(
            "import-script", operations.import_script_from_video,
            meta={"project": project},
            config=load_config(), video_path=video_path, project_name=project,
            translate=bool(body.get("translate", True)),
        )
        return {"job_id": job.id, "type": "import-script", "project": project}

    @app.post("/api/design")
    async def api_design(body: dict = Body(...)):
        from nolan.config import load_config
        from nolan.webui import operations
        project = (body.get("project") or "").strip()
        if not project:
            raise HTTPException(status_code=400, detail="project is required")
        job = job_manager.start(
            "design", operations.design, meta={"project": project},
            config=load_config(), project_name=project,
            llm_provider=(body.get("llm_provider") or None),
            llm_model=(body.get("llm_model") or None),
            reasoning=body.get("reasoning"),
            source_project=(body.get("source_project") or None),
        )
        return {"job_id": job.id, "type": "design"}
