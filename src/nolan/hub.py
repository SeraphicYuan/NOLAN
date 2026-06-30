"""Unified Hub for NOLAN web interfaces."""

import asyncio
import json
from pathlib import Path
from typing import Optional, List, Dict

import httpx
from urllib.parse import quote
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, Body
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

RENDER_SERVICE_URL = "http://127.0.0.1:3010"


def _find_scene_plan(directory: Path) -> Optional[Path]:
    """Find scene_plan.json in a directory or its output/ subdirectory."""
    scene_plan = directory / "scene_plan.json"
    if scene_plan.exists():
        return scene_plan
    scene_plan = directory / "output" / "scene_plan.json"
    if scene_plan.exists():
        return scene_plan
    return None


def _parse_project(directory: Path, scene_plan: Path) -> Dict:
    """Parse a project directory into metadata dict."""
    # Parse scene plan to get metadata
    try:
        data = json.loads(scene_plan.read_text(encoding="utf-8"))
        sections = data.get("sections", {})
        scene_count = sum(len(scenes) for scenes in sections.values())
        section_names = list(sections.keys())
    except (json.JSONDecodeError, IOError):
        scene_count = 0
        section_names = []

    # Check for audio in project's assets folder
    has_audio = False
    voiceover_dir = directory / "assets" / "voiceover"
    if voiceover_dir.exists():
        for ext in [".mp3", ".wav", ".m4a", ".ogg"]:
            if (voiceover_dir / f"voiceover{ext}").exists():
                has_audio = True
                break

    # flow projects self-declare their video type in flow.spec.json (e.g. "art")
    video_type = None
    flow_spec = directory / "flow.spec.json"
    if flow_spec.exists():
        try:
            video_type = json.loads(flow_spec.read_text(encoding="utf-8")).get("flow")
        except (json.JSONDecodeError, IOError):
            pass

    return {
        "name": directory.name,
        "path": str(directory),
        "scene_plan_path": str(scene_plan),
        "scene_count": scene_count,
        "sections": section_names,
        "has_audio": has_audio,
        "video_type": video_type,
    }


# Subdirs that are project *internals*, never separate projects — don't descend.
_PROJECT_SKIP_DIRS = {
    "assets", "clips", "work", "output", "source", "frames", "voiceover",
    "vectors", ".orchestrator", ".nolan", "node_modules", "__pycache__", ".git",
}


def _scan_into(base: Path, projects_dir: Path, projects: List[Dict], depth: int, max_depth: int) -> None:
    scene_plan = _find_scene_plan(base)
    if scene_plan:
        info = _parse_project(base, scene_plan)
        # Name nested projects by their path relative to projects_dir so they stay
        # unique and resolvable by _get_project_dir (projects_dir / name).
        try:
            rel = base.relative_to(projects_dir)
            info["name"] = projects_dir.name if rel == Path(".") else str(rel).replace("\\", "/")
        except ValueError:
            pass
        projects.append(info)
    if depth >= max_depth:
        return
    try:
        children = sorted(base.iterdir())
    except OSError:
        return
    for item in children:
        if item.is_dir() and item.name not in _PROJECT_SKIP_DIRS and not item.name.startswith("."):
            _scan_into(item, projects_dir, projects, depth + 1, max_depth)


def scan_projects(projects_dir: Path, max_depth: int = 3) -> List[Dict]:
    """Scan a directory tree for valid NOLAN projects (dirs with scene_plan.json).

    Recurses up to `max_depth` so nested segment-builder outputs (e.g.
    `<linear project>/segment_xyz/`) are discoverable. Nested projects are named
    by their path relative to `projects_dir` (e.g. "US Economy/segment_xyz").

    Returns:
        List of project info dicts with name, path, scene_count, etc.
    """
    projects: List[Dict] = []
    if not projects_dir.exists():
        return projects
    _scan_into(projects_dir, projects_dir, projects, depth=0, max_depth=max_depth)
    projects.sort(key=lambda p: p["name"].lower())
    return projects


def _resolve_assemble_audio(proj_dir: Path, audio: Optional[str]) -> Optional[Path]:
    """Resolve narration audio for assemble.

    Explicit `audio` (absolute or project-relative), else the project's standard
    voiceover (`assets/voiceover/voiceover.{mp3,wav,m4a,ogg}`). Returns an existing
    Path or None.
    """
    if audio:
        p = Path(audio)
        if p.exists():
            return p
        cand = proj_dir / audio
        return cand if cand.exists() else None
    for ext in (".mp3", ".wav", ".m4a", ".ogg"):
        c = proj_dir / "assets" / "voiceover" / f"voiceover{ext}"
        if c.exists():
            return c
    return None


def create_hub_app(
    db_path: Optional[Path] = None,
    projects_dir: Optional[Path] = None,
    render_service_url: str = RENDER_SERVICE_URL,
) -> FastAPI:
    """Create the unified NOLAN hub application.

    Args:
        db_path: Path to SQLite database for library features.
        projects_dir: Path to directory containing project folders.
        render_service_url: URL of the render service for showcase.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(title="NOLAN Hub")
    templates_dir = Path(__file__).parent / "templates"
    static_dir = Path(__file__).parent / "static"
    uploads_dir = Path(__file__).parent.parent.parent / "render-service" / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # Shared static assets (theme, nav, job-poll widget).
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # ==================== Job Manager (background operations) ====================
    from nolan.webui.jobs import get_job_manager
    job_manager = get_job_manager()

    @app.get("/api/jobs")
    async def jobs_list(type: Optional[str] = None):
        return [j.to_dict(include_logs=False) for j in job_manager.list(job_type=type)]

    @app.get("/api/jobs/{job_id}")
    async def jobs_get(job_id: str):
        job = job_manager.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        return job.to_dict()

    @app.post("/api/jobs/{job_id}/cancel")
    async def jobs_cancel(job_id: str):
        return {"cancelled": job_manager.cancel(job_id)}

    async def _render_service_up() -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{render_service_url}/")
                return r.status_code < 500
        except Exception:
            return False

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
        )
        return {"job_id": job.id, "type": "process", "project": project_name}

    # ==================== Publish (source -> beautiful HTML article) ====================

    @app.get("/publish", response_class=HTMLResponse)
    async def publish_page():
        tpl = templates_dir / "publish.html"
        if tpl.exists():
            return tpl.read_text(encoding="utf-8")
        return "<h1>publish.html not found</h1>"

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
        pub_root = (Path(__file__).resolve().parents[2] / "projects" / "_published").resolve()
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

    # ==================== Vector index management ====================

    @app.post("/api/sync-vectors")
    async def api_sync_vectors(body: dict = Body(default={})):
        from nolan.config import load_config
        from nolan.webui import operations
        config = load_config()
        effective_db = db_path or Path(config.indexing.database).expanduser()
        job = job_manager.start(
            "sync-vectors", operations.sync_vectors,
            db_path=effective_db, project_id=(body.get("project_id") or None),
        )
        return {"job_id": job.id, "type": "sync-vectors"}

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

    @app.get("/api/images/stats")
    async def api_images_stats(scope: str = "global", project: str = None):
        return _open_imagelib(scope, project).stats()

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

    # ==================== Settings ====================

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page():
        tpl = templates_dir / "settings.html"
        if tpl.exists():
            return tpl.read_text(encoding="utf-8")
        return "<h1>settings.html not found</h1>"

    @app.get("/api/settings")
    async def api_settings_get():
        from nolan.config import load_config
        config = load_config()
        return {
            "vision": {
                "provider": config.vision.provider,
                "model": config.vision.model,
                "reasoning_enabled": config.vision.reasoning_enabled,
                "reasoning_max_tokens": config.vision.reasoning_max_tokens,
            },
            "llm": {
                "provider": config.llm.provider,
                "model": config.llm.model,
                "reasoning_enabled": config.llm.reasoning_enabled,
            },
            "keys": {
                "gemini": bool(config.gemini.api_key),
                "openrouter": bool(config.vision.openrouter_api_key),
            },
            "indexing": {"database": config.indexing.database},
        }

    @app.post("/api/settings")
    async def api_settings_set(body: dict = Body(...)):
        """Persist vision settings to nolan.yaml (vision: block)."""
        import yaml
        cfg_path = Path("nolan.yaml")
        data = {}
        if cfg_path.exists():
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        vision = data.get("vision", {}) or {}
        for key in ("provider", "model", "reasoning_enabled", "reasoning_max_tokens"):
            if key in body:
                vision[key] = body[key]
        data["vision"] = vision
        # LLM block (text tasks) — accepts a nested "llm" object in the body.
        if isinstance(body.get("llm"), dict):
            llm = data.get("llm", {}) or {}
            for key in ("provider", "model", "reasoning_enabled"):
                if key in body["llm"]:
                    llm[key] = body["llm"][key]
            data["llm"] = llm
        cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        return {"saved": True, "vision": vision, "llm": data.get("llm")}

    # ==================== Asset matching (Phase 3) ====================

    @app.post("/api/match")
    async def api_match(body: dict = Body(...)):
        from nolan.config import load_config
        from nolan.webui import operations
        project = (body.get("project") or "").strip()
        if not project:
            raise HTTPException(status_code=400, detail="project is required")
        kind = body.get("kind", "broll")
        if kind in ("broll", "broll-video"):
            # Consolidated b-roll matcher (query-variant fallback + multi-source +
            # library-first). "broll-video" prefers video clips; "broll" prefers
            # stock images. The legacy single-query matcher is retired from this path.
            job = job_manager.start(
                "match", operations.match_broll_v2,
                meta={"project": project, "kind": kind},
                config=load_config(), project_name=project,
                prefer_video=bool(body.get("prefer_video", kind == "broll-video")),
                max_results=int(body.get("max_results", 4)),
                use_vision=bool(body.get("use_vision", False)),
                semantic=bool(body.get("semantic", True)),
            )
            return {"job_id": job.id, "type": "match"}
        job = job_manager.start(
            "match", operations.match_assets,
            meta={"project": project, "kind": kind},
            config=load_config(), project_name=project,
            source=body.get("source", "wikimedia"),
            max_results=int(body.get("max_results", 5)),
            kind=kind,
        )
        return {"job_id": job.id, "type": "match"}

    @app.post("/api/materialize-clips")
    async def api_materialize_clips(body: dict = Body(...)):
        from nolan.config import load_config
        from nolan.webui import operations
        project = (body.get("project") or "").strip()
        if not project:
            raise HTTPException(status_code=400, detail="project is required")
        job = job_manager.start(
            "materialize-clips", operations.materialize_clips, meta={"project": project},
            config=load_config(), project_name=project,
            max_clip_seconds=float(body.get("max_clip_seconds", 10.0)),
        )
        return {"job_id": job.id, "type": "materialize-clips"}

    @app.post("/api/generate")
    async def api_generate(body: dict = Body(...)):
        from nolan.config import load_config
        from nolan.webui import operations
        project = (body.get("project") or "").strip()
        if not project:
            raise HTTPException(status_code=400, detail="project is required")
        job = job_manager.start(
            "generate", operations.generate_assets, meta={"project": project},
            config=load_config(), project_name=project,
            workflow_name=(body.get("workflow") or None),
            style_cohesion=bool(body.get("style_cohesion", True)),
        )
        return {"job_id": job.id, "type": "generate"}

    # ==================== ComfyUI / Generation workflows ====================

    @app.get("/comfyui", response_class=HTMLResponse)
    async def comfyui_page():
        tpl = templates_dir / "comfyui.html"
        if tpl.exists():
            return tpl.read_text(encoding="utf-8")
        return "<h1>comfyui.html not found</h1>"

    @app.get("/api/comfyui/status")
    async def api_comfyui_status():
        from nolan.config import load_config
        from nolan.webui import operations
        return await operations.comfyui_status(load_config())

    @app.get("/api/comfyui/workflows")
    async def api_comfyui_workflows():
        from nolan.workflow_registry import get_registry
        return [e.to_dict() for e in get_registry().list()]

    @app.post("/api/comfyui/workflows")
    async def api_comfyui_add_workflow(body: dict = Body(...)):
        from nolan.workflow_registry import get_registry, WorkflowEntry
        from nolan.comfyui import load_workflow_file, find_prompt_nodes, find_style_node
        import re as _re
        name = (body.get("name") or "").strip()
        wf_json = body.get("workflow_json")
        if not name or wf_json is None:
            raise HTTPException(status_code=400, detail="name and workflow_json are required")
        slug = _re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-").lower() or "workflow"
        wf_dir = Path("workflows") / "image"
        wf_dir.mkdir(parents=True, exist_ok=True)
        wf_path = wf_dir / f"{slug}.json"
        wf_path.write_text(json.dumps(wf_json, indent=2), encoding="utf-8")
        # Normalize (UI→API) + auto-detect prompt node + style selector if present.
        prompt_node = body.get("prompt_node") or None
        style = None
        try:
            wf = load_workflow_file(wf_path)
            if not prompt_node:
                prompt_node = find_prompt_nodes(wf).get("positive")
            style = find_style_node(wf)
        except Exception:
            pass
        entry = WorkflowEntry(
            name=slug, description=body.get("description", ""),
            file=str(wf_path).replace("\\", "/"), checkpoint=body.get("checkpoint"),
            prompt_node=prompt_node,
            width=int(body.get("width", 1024)), height=int(body.get("height", 1024)),
            steps=int(body.get("steps", 25)), styles=body.get("styles", []),
            style_node=(style or {}).get("node"),
            style_group=(style or {}).get("group"),
            default_style=(style or {}).get("default"),
        )
        get_registry().add(entry)
        return {"saved": True, "entry": entry.to_dict()}

    @app.delete("/api/comfyui/workflows/{name}")
    async def api_comfyui_delete_workflow(name: str):
        from nolan.workflow_registry import get_registry
        return {"removed": get_registry().remove(name)}

    @app.post("/api/comfyui/sample")
    async def api_comfyui_sample(body: dict = Body(...)):
        from nolan.config import load_config
        from nolan.webui import operations
        prompt = (body.get("prompt") or "").strip()
        if not prompt:
            raise HTTPException(status_code=400, detail="prompt is required")
        job = job_manager.start(
            "comfyui-sample", operations.comfyui_sample,
            meta={"workflow": body.get("workflow")},
            config=load_config(), workflow_name=(body.get("workflow") or None), prompt=prompt,
            width=body.get("width"), height=body.get("height"), steps=body.get("steps"),
            style=(body.get("style") or None),
        )
        return {"job_id": job.id, "type": "comfyui-sample"}

    @app.get("/api/comfyui/styles")
    async def api_comfyui_styles(workflow: str = ""):
        """Style-selector options for a workflow (for the Sample runner dropdown)."""
        from nolan.workflow_registry import get_registry
        entry = get_registry().get(workflow)
        if not entry or not entry.style_node:
            return {"options": [], "default": None}
        options = list(entry.styles or [])
        if entry.style_group:
            sp = Path("workflows") / "styles" / f"{entry.style_group}.json"
            if sp.exists():
                try:
                    options = json.loads(sp.read_text(encoding="utf-8"))
                except Exception:
                    pass
        return {"options": options, "default": entry.default_style}

    @app.get("/comfyui/preview/{filename:path}")
    async def comfyui_preview(filename: str):
        path = Path("samples") / filename
        if not path.exists():
            raise HTTPException(status_code=404, detail="sample not found")
        return FileResponse(str(path))

    # ==================== Render / Assemble (Phase 4) ====================

    @app.post("/api/render-clips")
    async def api_render_clips(body: dict = Body(...)):
        from nolan.webui import operations
        project = (body.get("project") or "").strip()
        plan = Path("projects") / project / "scene_plan.json"
        if not plan.exists():
            raise HTTPException(status_code=400, detail=f"no scene_plan.json for '{project}'")
        args = ["render-clips", str(plan)]
        if body.get("force"):
            args.append("--force")
        job = job_manager.start("render-clips", operations.run_cli,
                                meta={"project": project}, args=args, label="render-clips")
        return {"job_id": job.id, "type": "render-clips"}

    @app.post("/api/assemble")
    async def api_assemble(body: dict = Body(...)):
        from nolan.webui import operations
        project = (body.get("project") or "").strip()
        proj_dir = Path("projects") / project
        plan = proj_dir / "scene_plan.json"
        if not plan.exists():
            raise HTTPException(status_code=400, detail=f"no scene_plan.json for '{project}'")
        audio = _resolve_assemble_audio(proj_dir, body.get("audio_file"))
        if not audio:
            raise HTTPException(status_code=400, detail=(
                "no narration audio — provide audio_file or add "
                "assets/voiceover/voiceover.mp3 to the project"))
        # audio is a POSITIONAL arg to `nolan assemble` (was wrongly sent as --audio-file).
        args = ["assemble", str(plan), str(audio)]
        if body.get("output"):
            args += ["--output", body["output"]]
        job = job_manager.start("assemble", operations.run_cli,
                                meta={"project": project}, args=args, label="assemble")
        return {"job_id": job.id, "type": "assemble"}

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
        return status

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

    # ==================== Library Routes ====================

    if db_path and db_path.exists():
        import sqlite3
        from nolan.indexer import VideoIndex
        from urllib.parse import unquote

        index = VideoIndex(db_path)
        library_template = templates_dir / "library.html"

        @app.get("/library", response_class=HTMLResponse)
        async def library_home():
            """Serve the library viewer page."""
            return library_template.read_text(encoding="utf-8")

        @app.get("/library/api/projects")
        async def library_list_projects():
            """List all projects with video counts."""
            with sqlite3.connect(db_path) as conn:
                cursor = conn.execute("""
                    SELECT p.id, p.slug, p.name, p.description, p.path,
                           COUNT(v.id) as video_count
                    FROM projects p
                    LEFT JOIN videos v ON p.id = v.project_id
                    GROUP BY p.id
                    ORDER BY p.name
                """)
                projects = []
                for row in cursor.fetchall():
                    projects.append({
                        "id": row[0], "slug": row[1], "name": row[2],
                        "description": row[3], "path": row[4], "video_count": row[5],
                    })
                return {"projects": projects, "total": len(projects)}

        @app.get("/library/api/videos")
        async def library_list_videos(
            project: Optional[str] = Query(default=None),
        ):
            """List all indexed videos."""
            with sqlite3.connect(db_path) as conn:
                if project:
                    cursor = conn.execute("""
                        SELECT v.path, v.duration, v.indexed_at, v.has_transcript,
                               COUNT(s.id) as segment_count, v.project_id,
                               p.slug as project_slug, p.name as project_name
                        FROM videos v
                        LEFT JOIN segments s ON v.id = s.video_id
                        LEFT JOIN projects p ON v.project_id = p.id
                        WHERE p.slug = ? OR p.id = ?
                        GROUP BY v.id ORDER BY v.indexed_at DESC
                    """, (project, project))
                else:
                    cursor = conn.execute("""
                        SELECT v.path, v.duration, v.indexed_at, v.has_transcript,
                               COUNT(s.id) as segment_count, v.project_id,
                               p.slug as project_slug, p.name as project_name
                        FROM videos v
                        LEFT JOIN segments s ON v.id = s.video_id
                        LEFT JOIN projects p ON v.project_id = p.id
                        GROUP BY v.id ORDER BY v.indexed_at DESC
                    """)
                videos = []
                for row in cursor.fetchall():
                    video_path = Path(row[0])
                    videos.append({
                        "path": row[0], "name": video_path.name,
                        "duration": row[1], "duration_formatted": _format_duration(row[1]),
                        "indexed_at": row[2], "has_transcript": bool(row[3]),
                        "segment_count": row[4], "project_id": row[5],
                        "project_slug": row[6], "project_name": row[7],
                    })
                return {"videos": videos, "total": len(videos), "project_filter": project}

        @app.get("/library/api/videos/{video_path:path}/segments")
        async def library_get_segments(video_path: str):
            """Get segments for a video."""
            video_path = unquote(video_path)
            segments = index.get_segments(video_path)
            if not segments:
                raise HTTPException(status_code=404, detail="Video not found")
            return {
                "video_path": video_path,
                "segments": [_segment_to_dict(s) for s in segments],
                "total": len(segments),
            }

        @app.get("/library/api/videos/{video_path:path}/clusters")
        async def library_get_clusters(video_path: str):
            """Get clusters for a video."""
            from nolan.clustering import cluster_segments
            video_path = unquote(video_path)
            clusters = index.get_clusters(video_path)
            if not clusters:
                segments = index.get_segments(video_path)
                if not segments:
                    raise HTTPException(status_code=404, detail="Video not found")
                computed = cluster_segments(segments)
                clusters = [_computed_cluster_to_dict(c) for c in computed]
            else:
                clusters = [_stored_cluster_to_dict(c, index) for c in clusters]
            return {"video_path": video_path, "clusters": clusters, "total": len(clusters)}

        @app.get("/library/api/search")
        async def library_search(
            q: str = Query(..., min_length=1),
            limit: int = Query(default=50, le=200),
            fields: Optional[str] = Query(default=None),
            search_type: str = Query(default="all"),
            project: Optional[str] = Query(default=None),
        ):
            """Search segments and clusters."""
            field_list = fields.split(",") if fields else None
            project_id = index.resolve_project(project) if project else None
            results = {"query": q, "fields": field_list, "search_type": search_type}
            if search_type in ("all", "segments"):
                segment_results = index.search(q, limit=limit, fields=field_list, project_id=project_id)
                results["segments"] = [_segment_to_dict(s) for s in segment_results]
                results["segment_count"] = len(segment_results)
            if search_type in ("all", "clusters"):
                cluster_results = index.search_clusters(q, limit=limit, fields=field_list, project_id=project_id)
                results["clusters"] = cluster_results
                results["cluster_count"] = len(cluster_results)
            return results

        @app.get("/library/api/search/semantic")
        async def library_semantic_search(
            q: str = Query(..., min_length=1),
            limit: int = Query(default=20, le=100),
            search_type: str = Query(default="both"),
            project: Optional[str] = Query(default=None),
        ):
            """Semantic search using vector embeddings."""
            from nolan.vector_search import VectorSearch
            vector_db_path = db_path.parent / "vectors"
            if not vector_db_path.exists():
                raise HTTPException(status_code=503, detail="Run 'nolan sync-vectors' first")
            vector_search = VectorSearch(vector_db_path, index=index)
            stats = vector_search.get_stats()
            if stats['segments'] == 0 and stats['clusters'] == 0:
                raise HTTPException(status_code=503, detail="Vector database empty")
            project_id = index.resolve_project(project) if project else None
            results = vector_search.search(query=q, limit=limit, search_level=search_type, project_id=project_id)
            formatted = [{
                "score": r.score, "score_percent": f"{r.score * 100:.1f}%",
                "content_type": r.content_type, "video_path": r.video_path,
                "video_name": Path(r.video_path).name if r.video_path else "",
                "timestamp_start": r.timestamp_start, "timestamp_end": r.timestamp_end,
                "timestamp_formatted": f"{int(r.timestamp_start // 60):02d}:{int(r.timestamp_start % 60):02d}",
                "description": r.description, "transcript": r.transcript,
                "people": r.people, "location": r.location, "objects": r.objects,
            } for r in results]
            return {"query": q, "results": formatted, "total": len(formatted), "vector_stats": stats}

        @app.get("/library/api/stats")
        async def library_stats():
            """Get library statistics."""
            with sqlite3.connect(db_path) as conn:
                video_count = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
                segment_count = conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
                total_duration = conn.execute("SELECT SUM(duration) FROM videos").fetchone()[0] or 0
                return {
                    "video_count": video_count, "segment_count": segment_count,
                    "total_duration": total_duration,
                    "total_duration_formatted": _format_duration(total_duration),
                }

        @app.get("/library/video/{video_path:path}")
        async def library_serve_video(video_path: str):
            """Serve video file."""
            from urllib.parse import unquote
            video_path = unquote(video_path)
            file_path = Path(video_path)
            if not file_path.exists():
                raise HTTPException(status_code=404, detail="Video not found")
            media_types = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime"}
            return FileResponse(file_path, media_type=media_types.get(file_path.suffix.lower(), "video/mp4"))

        # ==================== Saved Clips (manual cuts) ====================

        clips_template = templates_dir / "clips.html"

        @app.get("/clips", response_class=HTMLResponse)
        async def clips_home():
            """Serve the clips search / library page."""
            if clips_template.exists():
                return clips_template.read_text(encoding="utf-8")
            return "<h1>clips.html not found</h1>"

        def _resolve_scope(projects: Optional[str]) -> Optional[List[str]]:
            """Turn a comma-separated list of slugs/ids into project ids.

            Returns None for 'all projects' (empty / 'all')."""
            if not projects or projects.strip().lower() in ("all", ""):
                return None
            ids = []
            for token in projects.split(","):
                token = token.strip()
                if not token:
                    continue
                resolved = index.resolve_project(token) or token
                ids.append(resolved)
            return ids or None

        @app.get("/library/api/clips")
        async def clips_list(projects: Optional[str] = Query(default=None)):
            """List saved clips, optionally scoped to a set of projects."""
            scope = _resolve_scope(projects)
            return {"clips": index.list_saved_clips(project_ids=scope),
                    "scope": scope}

        @app.post("/library/api/clips")
        async def clips_create(body: dict = Body(...)):
            """Create a saved clip from a manual in/out selection."""
            source = (body.get("source_video_path") or "").strip()
            if not source:
                raise HTTPException(status_code=400, detail="source_video_path is required")
            try:
                clip_start = float(body.get("clip_start"))
                clip_end = float(body.get("clip_end"))
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="clip_start and clip_end must be numbers")
            if clip_end <= clip_start:
                raise HTTPException(status_code=400, detail="clip_end must be greater than clip_start")
            tags = body.get("tags") or None
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()] or None
            project = (body.get("project") or "").strip() or None
            project_id = index.resolve_project(project) if project else None
            clip_id = index.add_saved_clip(
                source_video_path=source,
                clip_start=clip_start, clip_end=clip_end,
                label=(body.get("label") or None),
                tags=tags, project_id=project_id,
            )
            return {"clip": index.get_saved_clip(clip_id)}

        @app.delete("/library/api/clips/{clip_id}")
        async def clips_delete(clip_id: str):
            if not index.delete_saved_clip(clip_id):
                raise HTTPException(status_code=404, detail="clip not found")
            return {"deleted": clip_id}

        @app.post("/library/api/clips/{clip_id}/materialize")
        async def clips_materialize(clip_id: str, body: dict = Body(default={})):
            """Materialize a saved clip (none|file|frames) as a background job."""
            from nolan.webui import operations
            if not index.get_saved_clip(clip_id):
                raise HTTPException(status_code=404, detail="clip not found")
            form = (body.get("form") or "file").strip()
            job = job_manager.start(
                "materialize-clip", operations.materialize_clip,
                meta={"clip_id": clip_id, "form": form},
                db_path=db_path, clip_id=clip_id, form=form,
                num_frames=int(body.get("num_frames", 6)),
                force=bool(body.get("force", False)),
            )
            return {"job_id": job.id, "type": "materialize-clip"}

        @app.get("/library/api/tmux-sessions")
        async def list_tmux_sessions():
            """List tmux sessions available as analysis-agent targets."""
            from nolan.webui import operations
            import asyncio as _asyncio
            sessions = await _asyncio.get_event_loop().run_in_executor(
                None, operations.list_tmux_sessions)
            return {"sessions": sessions}

        @app.post("/library/api/clips/{clip_id}/analyze-effect")
        async def clips_analyze_effect(clip_id: str, body: dict = Body(default={})):
            """Dispatch a clip to a tmux Claude agent for effect analysis."""
            from nolan.webui import operations
            if not index.get_saved_clip(clip_id):
                raise HTTPException(status_code=404, detail="clip not found")
            session = (body.get("session") or "nolan2").strip() or "nolan2"
            job = job_manager.start(
                "analyze-effect", operations.analyze_effect,
                meta={"clip_id": clip_id, "session": session},
                db_path=db_path, clip_id=clip_id,
                num_frames=int(body.get("num_frames", 10)),
                session=session,
            )
            return {"job_id": job.id, "type": "analyze-effect"}

        @app.get("/library/api/clips/{clip_id}/analysis")
        async def clips_analysis(clip_id: str):
            """Return the nolan2 agent's effect-analysis findings, if written yet."""
            analysis = Path("projects") / "_clips" / clip_id / "effect_analysis.md"
            if not analysis.exists():
                raise HTTPException(status_code=404, detail="no analysis yet")
            return {"clip_id": clip_id, "content": analysis.read_text(encoding="utf-8")}

        @app.get("/library/api/clips/search")
        async def clips_search(
            q: str = Query(default="", description="keyword query (optional)"),
            projects: Optional[str] = Query(default=None),
            limit: int = Query(default=50, le=200),
        ):
            """Scoped search across saved clips + auto-snippets (segments/clusters)."""
            scope = _resolve_scope(projects)
            saved = index.list_saved_clips(project_ids=scope)
            if q:
                ql = q.lower()
                saved = [c for c in saved
                         if ql in (c.get("label") or "").lower()
                         or any(ql in str(t).lower() for t in (c.get("tags") or []))
                         or ql in (c.get("video_name") or "").lower()]
            result = {"query": q, "scope": scope, "saved_clips": saved,
                      "saved_clip_count": len(saved)}
            if q:
                segs = index.search(q, limit=limit, project_ids=scope)
                clus = index.search_clusters(q, limit=limit, project_ids=scope)
                result["segments"] = [_segment_to_dict(s) for s in segs]
                result["segment_count"] = len(segs)
                result["clusters"] = clus
                result["cluster_count"] = len(clus)
            else:
                result["segments"] = []
                result["segment_count"] = 0
                result["clusters"] = []
                result["cluster_count"] = 0
            return result

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

    # ==================== Script Projects (subject + style + sources → script.md) ====================

    from nolan.scriptwriter import ScriptProjectStore
    script_project_store = ScriptProjectStore(Path("projects"))
    script_projects_template = templates_dir / "script_projects.html"

    @app.get("/script-projects", response_class=HTMLResponse)
    async def script_projects_page():
        if script_projects_template.exists():
            return script_projects_template.read_text(encoding="utf-8")
        return "<h1>script_projects.html not found</h1>"

    @app.get("/api/script-projects")
    async def script_projects_list():
        return {"projects": script_project_store.list()}

    @app.post("/api/script-projects")
    async def script_projects_create(body: dict = Body(...)):
        name = (body.get("name") or "").strip()
        subject = (body.get("subject") or "").strip()
        style_id = (body.get("style_id") or "").strip()
        if not subject or not style_id:
            raise HTTPException(status_code=400, detail="subject and style_id are required")
        if not style_store.exists(style_id):
            raise HTTPException(status_code=400, detail=f"unknown style_id: {style_id}")
        slug = script_project_store.create(
            name or subject, subject=subject, style_id=style_id,
            angle=(body.get("angle") or "").strip(),
            pivot=(body.get("pivot") or "").strip(),
            target_minutes=float(body.get("target_minutes") or 8.0),
            description=(body.get("description") or "").strip(),
        )
        # C1: link the new FS project to the library DB so it's one project, not two.
        if db_path and db_path.exists():
            try:
                from nolan import projects as _projects
                from nolan.indexer import VideoIndex
                proj = _projects.get_project(slug, projects_dir or _projects.DEFAULT_ROOT)
                if proj:
                    _projects.link_db_project(VideoIndex(db_path), proj)
            except Exception:
                pass  # linking is best-effort; never block project creation
        return {"project": script_project_store.get(slug)}

    @app.get("/api/script-projects/{slug}")
    async def script_projects_get(slug: str):
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        return script_project_store.get(slug)

    @app.delete("/api/script-projects/{slug}")
    async def script_projects_delete(slug: str):
        if not script_project_store.delete(slug):
            raise HTTPException(status_code=404, detail="project not found")
        return {"deleted": slug}

    @app.post("/api/script-projects/{slug}/add-source")
    async def script_projects_add_source(slug: str, body: dict = Body(...)):
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        kind = (body.get("kind") or "").strip()
        url = (body.get("url") or "").strip() or None
        text = body.get("text") or None
        if kind not in ("url", "paste", "file", "reference"):
            raise HTTPException(status_code=400, detail="kind must be url/paste/file/reference")
        if kind == "url" and not url:
            raise HTTPException(status_code=400, detail="url required for kind=url")
        if kind in ("paste", "file") and not text:
            raise HTTPException(status_code=400, detail="text required for kind=paste/file")
        entry = script_project_store.add_source(
            slug, kind=kind, title=(body.get("title") or "").strip(), url=url, text=text)
        return {"source": entry}

    @app.post("/api/script-projects/{slug}/upload-file")
    async def script_projects_upload_file(slug: str, file: UploadFile = File(...)):
        """Add an uploaded .txt/.md/.srt/.vtt source to a project (saved to raw/)."""
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        raw = await file.read()
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
        entry = script_project_store.add_source(slug, kind="file", title=title, text=text)
        return {"source": entry}

    @app.post("/api/script-projects/{slug}/remove-source/{sid}")
    async def script_projects_remove_source(slug: str, sid: str):
        if not script_project_store.remove_source(slug, sid):
            raise HTTPException(status_code=404, detail="source not found")
        return {"removed": sid}

    @app.get("/api/script-projects/{slug}/artifact/{name}")
    async def script_projects_artifact(slug: str, name: str):
        """Read a grounding artifact: brief|facts|factcheck|citations|sources."""
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        content = script_project_store.read_artifact(slug, name)
        if content is None:
            raise HTTPException(status_code=404, detail=f"no {name} yet")
        return {"slug": slug, "name": name, "content": content}

    @app.get("/api/script-projects/{slug}/source/{sid}")
    async def script_projects_source_text(slug: str, sid: str):
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        content = script_project_store.read_source_text(slug, sid)
        if content is None:
            raise HTTPException(status_code=404, detail="no fetched text for this source")
        return {"slug": slug, "sid": sid, "content": content}

    @app.post("/api/script-projects/{slug}/write")
    async def script_projects_write(slug: str, body: dict = Body(default={})):
        from nolan.webui import operations
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        session = (body.get("session") or "nolan2").strip() or "nolan2"
        job = job_manager.start(
            "write-script", operations.write_script,
            meta={"slug": slug, "session": session},
            store_root="projects", slug=slug, session=session,
        )
        return {"job_id": job.id, "type": "write-script"}

    @app.get("/api/script-projects/{slug}/script")
    async def script_projects_script(slug: str):
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        content = script_project_store.read_script(slug)
        if content is None:
            raise HTTPException(status_code=404, detail="no script yet")
        return {"slug": slug, "content": content}

    # ==================== Voices (TTS + voice cloning) ====================

    from nolan.voice_library import VoiceLibrary
    voice_lib = VoiceLibrary(Path("voices"))
    voices_template = templates_dir / "voices.html"

    def _tts_enabled() -> bool:
        try:
            from nolan.config import load_config
            return bool(load_config().tts.enabled)
        except Exception:
            return False

    @app.get("/voices", response_class=HTMLResponse)
    async def voices_page():
        if voices_template.exists():
            return voices_template.read_text(encoding="utf-8")
        return "<h1>voices.html not found</h1>"

    @app.get("/api/voices")
    async def voices_list():
        return {"voices": voice_lib.list(), "tts_enabled": _tts_enabled()}

    @app.delete("/api/voices/{voice_id}")
    async def voices_delete(voice_id: str):
        if not voice_lib.delete(voice_id):
            raise HTTPException(status_code=404, detail="voice not found")
        return {"deleted": voice_id}

    @app.get("/api/voices/{voice_id}/sample")
    async def voices_sample(voice_id: str):
        p = voice_lib.sample_path(voice_id)
        if not p.exists():
            raise HTTPException(status_code=404, detail="no sample")
        return FileResponse(p, media_type="audio/wav")

    @app.post("/api/voices/upload")
    async def voices_upload(file: UploadFile = File(...), name: str = Form(...),
                            ref_text: str = Form(None)):
        import tempfile
        raw = await file.read()
        suffix = Path(file.filename or "audio").suffix or ".audio"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
            tf.write(raw)
            tmp = Path(tf.name)
        try:
            meta = voice_lib.create_from_audio(name, tmp, ref_text=(ref_text or None),
                                               source="upload", source_ref=file.filename)
        finally:
            tmp.unlink(missing_ok=True)
        return {"voice": meta}

    @app.get("/api/voices/wpm")
    async def voices_wpm(voice_id: str = Query(default=None), sample_token: str = Query(default=None)):
        """Detect a reference voice's words-per-minute + suggest a Pace to match."""
        import asyncio as _asyncio
        from nolan.webui import operations
        ref_text = None
        if voice_id:
            v = voice_lib.get(voice_id)
            if not v:
                raise HTTPException(status_code=404, detail="voice not found")
            wav = voice_lib.sample_path(voice_id)
            ref_text = v.get("ref_text")
        elif sample_token:
            wav = voice_lib.temp_sample_path(sample_token)
            if not wav.exists():
                raise HTTPException(status_code=404, detail="sample not found")
        else:
            raise HTTPException(status_code=400, detail="voice_id or sample_token required")
        return await _asyncio.get_event_loop().run_in_executor(
            None, operations.detect_voice_wpm, str(wav), ref_text)

    @app.post("/api/voices/from-clip")
    async def voices_from_clip(body: dict = Body(...)):
        """Clone a voice from a saved Clip's audio (from the library)."""
        from nolan.config import load_config
        from nolan.indexer import VideoIndex
        clip_id = (body.get("clip_id") or "").strip()
        name = (body.get("name") or "").strip()
        if not clip_id or not name:
            raise HTTPException(status_code=400, detail="clip_id and name are required")
        eff_db = db_path or Path(load_config().indexing.database).expanduser()
        if not eff_db.exists():
            raise HTTPException(status_code=400, detail="library DB not found")
        clip = VideoIndex(eff_db).get_saved_clip(clip_id)
        if not clip:
            raise HTTPException(status_code=404, detail="clip not found")
        meta = voice_lib.create_from_clip(
            name, clip["source_video_path"], clip["clip_start"], clip["clip_end"],
            ref_text=(body.get("ref_text") or None), clip_id=clip_id)
        return {"voice": meta}

    @app.post("/api/generate-voiceover")
    async def api_generate_voiceover(body: dict = Body(...)):
        from nolan.config import load_config
        from nolan.webui import operations
        project = (body.get("project") or "").strip() or None
        script_project = (body.get("script_project") or "").strip() or None
        if not project and not script_project:
            raise HTTPException(status_code=400, detail="project or script_project is required")
        mode = (body.get("mode") or "full").strip()
        if mode not in ("full", "segments"):
            raise HTTPException(status_code=400, detail="mode must be 'full' or 'segments'")
        # Resolve the active voice the same way the studio does: a saved voice,
        # an ephemeral cropped/uploaded sample, or a voice-design instruct.
        ref_audio = ref_text = None
        voice_id = (body.get("voice_id") or "").strip() or None
        sample_token = (body.get("sample_token") or "").strip()
        if sample_token:
            sp = voice_lib.temp_sample_path(sample_token)
            if not sp.exists():
                raise HTTPException(status_code=404, detail="sample not found")
            ref_audio = str(sp)
            ref_text = (body.get("ref_text") or None)
            voice_id = None
        job = job_manager.start(
            "generate-voiceover", operations.generate_voiceover,
            meta={"project": project or script_project, "mode": mode},
            config=load_config(), project=project, script_project=script_project,
            mode=mode, voice_id=voice_id, ref_audio=ref_audio, ref_text=ref_text,
            instruct=(body.get("instruct") or None),
            num_step=(int(body["num_step"]) if body.get("num_step") else None),
            speed=(float(body["speed"]) if body.get("speed") else None),
            language_id=(body.get("language_id") or None),
            tempo=float(body.get("tempo") or 1.0),
        )
        return {"job_id": job.id, "type": "generate-voiceover"}

    @app.post("/api/generate-captions")
    async def api_generate_captions(body: dict = Body(...)):
        from nolan.config import load_config
        from nolan.webui import operations
        project = (body.get("project") or "").strip()
        if not project:
            raise HTTPException(status_code=400, detail="project is required")
        job = job_manager.start(
            "generate-captions", operations.generate_captions,
            meta={"project": project}, config=load_config(), project=project,
        )
        return {"job_id": job.id, "type": "generate-captions"}

    @app.get("/api/voiceover-info/{project}")
    async def api_voiceover_info(project: str):
        """Report a project's existing voiceover outputs (full mp3 + segments + captions)."""
        vo = Path("projects") / project / "assets" / "voiceover"
        full = (vo / "voiceover.mp3").exists()
        segs = []
        sj = vo / "segments" / "segments.json"
        if sj.exists():
            try:
                segs = (json.loads(sj.read_text(encoding="utf-8")) or {}).get("segments", [])
            except Exception:
                segs = []
        captions = (vo / "voiceover.srt").exists()
        return {"project": project, "full": full, "segments": segs, "captions": captions}

    @app.get("/api/voiceover/{project}/{path:path}")
    async def api_voiceover_file(project: str, path: str):
        """Serve a project's voiceover output (audio, or .srt/.vtt/.json captions)."""
        from urllib.parse import unquote
        safe = unquote(path).replace("\\", "/")
        if ".." in safe:
            raise HTTPException(status_code=400, detail="bad path")
        p = Path("projects") / project / "assets" / "voiceover" / safe
        if not p.exists():
            raise HTTPException(status_code=404, detail="not found")
        mt = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".srt": "application/x-subrip",
              ".vtt": "text/vtt", ".json": "application/json"}.get(
                  p.suffix.lower(), "application/octet-stream")
        return FileResponse(p, media_type=mt)

    # ---- TTS Studio (single-utterance playground) ----
    tts_template = templates_dir / "tts.html"

    @app.get("/tts", response_class=HTMLResponse)
    async def tts_page():
        if tts_template.exists():
            return tts_template.read_text(encoding="utf-8")
        return "<h1>tts.html not found</h1>"

    @app.post("/api/tts/sample")
    async def tts_sample_upload(file: UploadFile = File(...)):
        """Create an ephemeral cloning sample from an uploaded audio file."""
        import tempfile
        from uuid import uuid4
        raw = await file.read()
        suffix = Path(file.filename or "audio").suffix or ".audio"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
            tf.write(raw)
            tmp = Path(tf.name)
        token = uuid4().hex[:12]
        try:
            voice_lib.make_temp_sample(token, src_audio=tmp)
        finally:
            tmp.unlink(missing_ok=True)
        return {"token": token, "sample_url": f"/api/tts/sample/{token}"}

    @app.post("/api/tts/sample-from-library")
    async def tts_sample_from_library(body: dict = Body(...)):
        """Create an ephemeral cloning sample by cropping a library video's audio."""
        from uuid import uuid4
        video_path = (body.get("video_path") or "").strip()
        try:
            start = float(body.get("start"))
            end = float(body.get("end"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="start and end (seconds) are required")
        if not video_path:
            raise HTTPException(status_code=400, detail="video_path is required")
        if not Path(video_path).exists():
            raise HTTPException(status_code=404, detail="video not found")
        token = uuid4().hex[:12]
        try:
            voice_lib.make_temp_sample(token, video_path=video_path, start=start, end=end)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"token": token, "sample_url": f"/api/tts/sample/{token}",
                "duration": round(end - start, 2)}

    @app.get("/api/tts/sample/{token}")
    async def tts_sample_get(token: str):
        p = voice_lib.temp_sample_path(token)
        if not p.exists():
            raise HTTPException(status_code=404, detail="sample not found")
        return FileResponse(p, media_type="audio/wav")

    @app.post("/api/voices/save-sample")
    async def voices_save_sample(body: dict = Body(...)):
        token = (body.get("token") or "").strip()
        name = (body.get("name") or "").strip()
        if not token or not name:
            raise HTTPException(status_code=400, detail="token and name are required")
        if not voice_lib.temp_sample_path(token).exists():
            raise HTTPException(status_code=404, detail="sample not found")
        meta = voice_lib.promote_temp(token, name, ref_text=(body.get("ref_text") or None))
        return {"voice": meta}

    @app.post("/api/tts/synthesize")
    async def api_tts_synthesize(body: dict = Body(...)):
        from nolan.config import load_config
        from nolan.webui import operations
        text = (body.get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="text is required")
        # Resolve the voice reference: saved voice | ephemeral sample | none/instruct.
        ref_audio = ref_text = None
        voice_id = (body.get("voice_id") or "").strip()
        sample_token = (body.get("sample_token") or "").strip()
        if voice_id:
            v = voice_lib.get(voice_id)
            if not v:
                raise HTTPException(status_code=404, detail="voice not found")
            ref_audio = str(voice_lib.sample_path(voice_id))
            ref_text = v.get("ref_text")
        elif sample_token:
            sp = voice_lib.temp_sample_path(sample_token)
            if not sp.exists():
                raise HTTPException(status_code=404, detail="sample not found")
            ref_audio = str(sp)
            ref_text = (body.get("ref_text") or None)
        job = job_manager.start(
            "tts-synthesize", operations.tts_synthesize,
            meta={"chars": len(text)},
            config=load_config(), text=text, ref_audio=ref_audio, ref_text=ref_text,
            instruct=(body.get("instruct") or None),
            num_step=(int(body["num_step"]) if body.get("num_step") else None),
            speed=(float(body["speed"]) if body.get("speed") else None),
            language_id=(body.get("language_id") or None),
            tempo=float(body.get("tempo") or 1.0),
        )
        return {"job_id": job.id, "type": "tts-synthesize"}

    @app.get("/api/tts/output/{token}")
    async def tts_output_get(token: str):
        p = Path("voices") / "_tts_out" / f"{token}.wav"
        if not p.exists():
            raise HTTPException(status_code=404, detail="output not found")
        return FileResponse(p, media_type="audio/wav")

    @app.get("/api/project/{project}/script")
    async def api_project_script(project: str):
        """Return a project's narration text (for the TTS Studio text source)."""
        base = Path("projects") / project
        md = base / "script.md"
        if md.exists():
            return {"project": project, "script": md.read_text(encoding="utf-8")}
        js = base / "script.json"
        if js.exists():
            from nolan.script import Script
            s = Script.load_json(str(js))
            return {"project": project, "script": "\n\n".join(x.narration for x in s.sections)}
        raise HTTPException(status_code=404, detail="no script for project")

    # ==================== Video Styles (reference videos → visual style guide) ====================

    from nolan.video_style import VideoStyleStore
    video_style_store = VideoStyleStore(Path("video_styles"))
    video_styles_template = templates_dir / "video_styles.html"

    @app.get("/video-styles", response_class=HTMLResponse)
    async def video_styles_page():
        if video_styles_template.exists():
            return video_styles_template.read_text(encoding="utf-8")
        return "<h1>video_styles.html not found</h1>"

    @app.get("/api/video-styles")
    async def video_styles_list():
        return {"styles": video_style_store.list()}

    @app.post("/api/video-styles")
    async def video_styles_create(body: dict = Body(...)):
        name = (body.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        return {"style": video_style_store.get(video_style_store.create(name))}

    @app.get("/api/video-styles/{style_id}")
    async def video_styles_get(style_id: str):
        if not video_style_store.exists(style_id):
            raise HTTPException(status_code=404, detail="video style not found")
        return video_style_store.get(style_id)

    @app.delete("/api/video-styles/{style_id}")
    async def video_styles_delete(style_id: str):
        if not video_style_store.delete(style_id):
            raise HTTPException(status_code=404, detail="video style not found")
        return {"deleted": style_id}

    @app.post("/api/video-styles/{style_id}/add-video")
    async def video_styles_add_video(style_id: str, body: dict = Body(...)):
        if not video_style_store.exists(style_id):
            raise HTTPException(status_code=404, detail="video style not found")
        vp = (body.get("video_path") or "").strip()
        if not vp:
            raise HTTPException(status_code=400, detail="video_path is required")
        entry = video_style_store.add_video(
            style_id, video_path=vp, title=(body.get("title") or "").strip(),
            duration=body.get("duration"), indexed=bool(body.get("indexed")))
        return {"source": entry}

    @app.post("/api/video-styles/{style_id}/remove-source/{slug}")
    async def video_styles_remove_source(style_id: str, slug: str):
        if not video_style_store.remove_source(style_id, slug):
            raise HTTPException(status_code=404, detail="source not found")
        return {"removed": slug}

    @app.post("/api/video-styles/{style_id}/pair-script")
    async def video_styles_pair_script(style_id: str, body: dict = Body(...)):
        if not video_style_store.exists(style_id):
            raise HTTPException(status_code=404, detail="video style not found")
        ssid = (body.get("script_style_id") or "").strip() or None
        if ssid and not style_store.exists(ssid):
            raise HTTPException(status_code=400, detail=f"unknown script style: {ssid}")
        video_style_store.pair_script_style(style_id, ssid)
        return {"style_id": style_id, "script_style_id": ssid}

    @app.post("/api/video-styles/{style_id}/analyze")
    async def video_styles_analyze(style_id: str, body: dict = Body(default={})):
        from nolan.config import load_config
        from nolan.webui import operations
        if not video_style_store.exists(style_id):
            raise HTTPException(status_code=404, detail="video style not found")
        config = load_config()
        effective_db = db_path or Path(config.indexing.database).expanduser()
        session = (body.get("session") or "nolan2").strip() or "nolan2"
        job = job_manager.start(
            "analyze-video-style", operations.analyze_video_style,
            meta={"style_id": style_id, "session": session},
            config=config, store_root="video_styles", db_path=effective_db,
            style_id=style_id, session=session,
            provider=(body.get("provider") or "openrouter"),
            enable_vision=bool(body.get("enable_vision", True)))
        return {"job_id": job.id, "type": "analyze-video-style"}

    @app.get("/api/video-styles/{style_id}/guide")
    async def video_styles_guide(style_id: str):
        guide = video_style_store.read_guide(style_id)
        if guide is None:
            raise HTTPException(status_code=404, detail="no guide yet")
        return {"style_id": style_id, "content": guide}

    @app.get("/api/video-styles/{style_id}/extract/{slug}")
    async def video_styles_extract(style_id: str, slug: str):
        ex = video_style_store.read_extract(style_id, slug)
        if ex is None:
            raise HTTPException(status_code=404, detail="no extract yet")
        return ex

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
            Path(__file__).parent.parent.parent / "render-service" / "public" / "previews" / filename,
            Path(__file__).parent.parent.parent / "render-service" / "output" / filename,
        ]
        for path in locations:
            if path.exists():
                return FileResponse(path)
        raise HTTPException(status_code=404, detail="Preview not found")

    @app.get("/showcase/output/{filename:path}")
    async def showcase_output(filename: str):
        """Serve rendered output."""
        path = Path(__file__).parent.parent.parent / "render-service" / "output" / filename
        if not path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(path)

    # ==================== Scenes Routes (Dynamic Project Selection) ====================

    scenes_template = templates_dir / "scenes.html"

    def _get_project_dir(project_name: str) -> Optional[tuple]:
        """Get project directory and scene_plan path by name.

        Returns:
            Tuple of (project_path, scene_plan_path) or None if not found.
        """
        if not projects_dir:
            return None

        # Check if projects_dir itself matches (e.g., "output" project)
        if projects_dir.name == project_name:
            scene_plan = _find_scene_plan(projects_dir)
            if scene_plan:
                return (projects_dir, scene_plan)

        # Check subdirectory
        project_path = projects_dir / project_name
        if project_path.exists():
            scene_plan = _find_scene_plan(project_path)
            if scene_plan:
                return (project_path, scene_plan)

        return None

    @app.get("/scenes", response_class=HTMLResponse)
    async def scenes_home():
        """Serve the scenes viewer page."""
        if scenes_template.exists():
            return scenes_template.read_text(encoding="utf-8")
        return "<h1>Scenes template not found</h1>"

    @app.get("/scenes/api/projects")
    async def scenes_list_projects():
        """List available projects for scenes viewer."""
        projects = scan_projects(projects_dir) if projects_dir else []
        return {"projects": projects, "total": len(projects)}

    @app.get("/scenes/api/scenes/flat")
    async def scenes_get_flat(project: str = Query(..., description="Project name")):
        """Get scenes as flat list for a specific project."""
        result = _get_project_dir(project)
        if not result:
            raise HTTPException(status_code=404, detail=f"Project '{project}' not found")

        project_path, scene_plan_path = result
        # flow projects: refresh the scene-plan VIEW from the source-of-truth flow.spec.json
        from nolan.flows.project import is_flow_project
        if is_flow_project(project_path) and (project_path / "flow.job.json").exists():
            from nolan.flows.scene_view import build_scene_plan
            scene_plan_path = build_scene_plan(project_path)
        data = json.loads(scene_plan_path.read_text(encoding="utf-8"))
        scenes = []
        sections = list(data.get("sections", {}).keys())
        for section_name, section_scenes in data.get("sections", {}).items():
            for scene in section_scenes:
                scene["_section"] = section_name
                scenes.append(scene)
        scenes.sort(key=lambda s: s.get("start_seconds") or 0)
        from nolan.iterate import detect_pipeline, editable_fields
        pipeline = detect_pipeline(scene_plan_path)
        return {"scenes": scenes, "sections": sections, "project": project,
                "pipeline": pipeline, "editable_fields": sorted(editable_fields(pipeline))}

    @app.get("/scenes/api/audio-info")
    async def scenes_audio_info(project: str = Query(..., description="Project name")):
        """Get voiceover audio info for a specific project."""
        result = _get_project_dir(project)
        if not result:
            raise HTTPException(status_code=404, detail=f"Project '{project}' not found")

        project_path, _ = result
        voiceover_dir = project_path / "assets" / "voiceover"
        if voiceover_dir.exists():
            for ext in [".mp3", ".wav", ".m4a", ".ogg"]:
                audio_file = voiceover_dir / f"voiceover{ext}"
                if audio_file.exists():
                    return {
                        "path": f"/scenes/assets/{project}/voiceover/voiceover{ext}",
                        "exists": True,
                        "project": project,
                    }
        return {"path": None, "exists": False, "project": project}

    _MEDIA_TYPES = {
        ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".ogg": "audio/ogg",
        ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
    }

    @app.get("/scenes/assets/{project}/{asset_path:path}")
    async def scenes_serve_asset(project: str, asset_path: str):
        """Serve asset files for a specific project (path-traversal contained)."""
        result = _get_project_dir(project)
        if not result:
            raise HTTPException(status_code=404, detail=f"Project '{project}' not found")

        project_path, _ = result
        root = project_path.resolve()
        try:
            fp = (project_path / "assets" / asset_path).resolve()
        except OSError:
            raise HTTPException(status_code=404, detail="Asset not found")
        # Contain to the project's assets dir — reject `..` escapes.
        if not (root in fp.parents) or not fp.is_file():
            raise HTTPException(status_code=404, detail="Asset not found")
        return FileResponse(fp, media_type=_MEDIA_TYPES.get(fp.suffix.lower(),
                                                            "application/octet-stream"))

    @app.get("/scenes/file")
    async def scenes_file(project: str = Query(...), path: str = Query(...)):
        """Serve a project file by relative path (handles nested project names and
        both clip locations: `<proj>/clips/x.mp4` segment, `<proj>/assets/...` linear)."""
        result = _get_project_dir(project)
        if not result:
            raise HTTPException(status_code=404, detail=f"Project '{project}' not found")
        project_path, _ = result
        root = project_path.resolve()
        for candidate in (project_path / path, project_path / "assets" / path):
            try:
                fp = candidate.resolve()
            except OSError:
                continue
            if (fp == root or root in fp.parents) and fp.is_file():  # contain to project
                return FileResponse(fp, media_type=_MEDIA_TYPES.get(fp.suffix.lower(),
                                                                    "application/octet-stream"))
        raise HTTPException(status_code=404, detail="Asset not found")

    @app.post("/scenes/api/scene/revise")
    async def scenes_revise(payload: dict = Body(...)):
        """Apply a human comment (`note`) or a direct field `patch` to one scene."""
        project = payload.get("project")
        scene_id = payload.get("scene_id")
        note = payload.get("note")
        patch = payload.get("patch")
        if not (project and scene_id):
            raise HTTPException(status_code=400, detail="project and scene_id are required")
        result = _get_project_dir(project)
        if not result:
            raise HTTPException(status_code=404, detail=f"Project '{project}' not found")
        project_path, scene_plan_path = result
        from nolan import iterate
        pipeline = iterate.detect_pipeline(scene_plan_path)
        if pipeline == "flow":
            # flow projects: edits write to the source-of-truth flow.spec.json (not the view).
            from nolan.flows.edit import patch_beat
            from nolan.flows.scene_view import beat_index, build_scene_plan
            if not patch:
                raise HTTPException(status_code=400,
                                    detail="flow projects accept a direct field `patch` "
                                           "(the LLM `note` path is the authoring-mode refine).")
            patch_beat(project_path, beat_index(scene_id), patch)
            build_scene_plan(project_path)
            return {"applied": patch, "pipeline": "flow"}
        client = None
        words = None
        if note:
            from nolan.config import load_config
            from nolan.llm import create_text_llm
            client = create_text_llm(load_config())
            # VO word-timing for {cue:"..."} in a photo_brief (cached after first call)
            words = await asyncio.to_thread(iterate.scene_words, scene_plan_path)
        try:
            applied = await iterate.apply_edit(scene_plan_path, scene_id, patch=patch,
                                               note=note, client=client, pipeline=pipeline,
                                               transcript_words=words)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return {"applied": applied, "pipeline": pipeline}

    @app.post("/scenes/api/scene/assets")
    async def scenes_scene_assets(payload: dict = Body(...)):
        """Manage a scene's asset tray (add/remove/reorder/place/label).

        The tray is the human-curated set of assets a later comment can reference
        ({ref:'<id>'}). Edits here do NOT invalidate the rendered clip — only a
        comment/re-render does. Library images are resolved to a real path server-side.
        """
        project = payload.get("project")
        scene_id = payload.get("scene_id")
        op = payload.get("op")
        if not (project and scene_id and op):
            raise HTTPException(status_code=400, detail="project, scene_id, op are required")
        result = _get_project_dir(project)
        if not result:
            raise HTTPException(status_code=404, detail=f"Project '{project}' not found")
        project_path, scene_plan_path = result
        from nolan import iterate
        data = iterate.load_plan_raw(scene_plan_path)
        scene = iterate.find_scene(data, scene_id)
        if scene is None:
            raise HTTPException(status_code=404, detail=f"scene '{scene_id}' not found")
        assets = list(scene.get("assets") or [])

        def _next_id():
            used = {a.get("id") for a in assets}
            i = 1
            while f"a{i}" in used:
                i += 1
            return f"a{i}"

        def _find(aid):
            return next((a for a in assets if a.get("id") == aid), None)

        if op == "add":
            source = payload.get("source", "library")
            if source == "library":
                from nolan.imagelib import ImageLibrary
                lib = ImageLibrary(scope=payload.get("scope", "global"),
                                   project=payload.get("scope_project"))
                iid = int(payload["image_id"])
                a = lib.catalog.get(iid)
                if not a:
                    raise HTTPException(status_code=404, detail="library image not found")
                asset = {"id": _next_id(), "kind": "image", "src": str(lib.abs_path(a)),
                         "label": (payload.get("label") or (a.title or "").strip().rstrip(".")),
                         "thumb": f"/api/images/raw?scope={payload.get('scope', 'global')}"
                                  f"&project={payload.get('scope_project') or ''}&id={iid}"}
            elif source == "clip":
                src = payload.get("source_video_path")
                if not src:
                    raise HTTPException(status_code=400, detail="source_video_path required")
                asset = {"id": _next_id(), "kind": "clip", "src": src}
                for k in ("clip_start", "clip_end"):
                    if payload.get(k) is not None:
                        asset[k] = float(payload[k])
                if payload.get("label"):
                    asset["label"] = payload["label"]
                asset["thumb"] = (f"/scenes/api/frame-thumb?project={project}"
                                  f"&src={quote(str(src))}&t={asset.get('clip_start', 0)}")
            elif source == "path":
                p = payload.get("path")
                if not p:
                    raise HTTPException(status_code=400, detail="path required")
                asset = {"id": _next_id(), "kind": payload.get("kind", "image"), "src": p}
                if payload.get("label"):
                    asset["label"] = payload["label"]
            else:
                raise HTTPException(status_code=400, detail=f"unknown source {source!r}")
            assets.append(asset)
        elif op == "remove":
            assets = [a for a in assets if a.get("id") != payload.get("asset_id")]
        elif op == "reorder":
            order = payload.get("order") or []
            idx = {a.get("id"): a for a in assets}
            assets = [idx[i] for i in order if i in idx] + [a for a in assets if a.get("id") not in set(order)]
        elif op in ("set_place", "set_label"):
            a = _find(payload.get("asset_id"))
            if not a:
                raise HTTPException(status_code=404, detail="asset_id not found")
            if op == "set_place":
                pl = payload.get("place")
                if pl:
                    a["place"] = [float(pl[0]), float(pl[1])]
                else:
                    a.pop("place", None)
            else:
                a["label"] = payload.get("label", "")
        else:
            raise HTTPException(status_code=400, detail=f"unknown op {op!r}")

        # flow projects: an "add" binds the asset into the beat's block prop (the spec is
        # truth), so the next per-beat re-render shows it. The tray view is regenerated.
        from nolan.flows.project import is_flow_project
        if op == "add" and is_flow_project(project_path):
            from nolan.flows.edit import set_beat_asset
            from nolan.flows.scene_view import beat_index, build_scene_plan
            set_beat_asset(project_path, beat_index(scene_id), asset["src"])
            build_scene_plan(project_path)
            return {"assets": assets, "bound": asset["src"], "flow": True}
        # Direct save: tray edits are not render-invalidating (unlike apply_edit).
        scene["assets"] = assets
        iterate.save_plan_raw(scene_plan_path, data)
        return {"assets": assets}

    def _flow_project_path(project: str) -> Path:
        """Resolve a flow project by name (works before any render/scene_plan exists)."""
        pp = (projects_dir / project) if projects_dir else None
        if not (pp and pp.exists()):
            raise HTTPException(status_code=404, detail=f"Project '{project}' not found")
        from nolan.flows.project import is_flow_project
        if not is_flow_project(pp):
            raise HTTPException(status_code=400, detail=f"'{project}' is not a flow project")
        return pp

    @app.post("/scenes/api/flow/refine")
    async def scenes_flow_refine(payload: dict = Body(...)):
        """Authoring mode (Gate A): dispatch a fleet agent to refine the per-beat plan."""
        project = payload.get("project")
        agent = payload.get("agent") or "nolan4"
        if not project:
            raise HTTPException(status_code=400, detail="project required")
        pp = _flow_project_path(project)
        from nolan.flows.authoring import dispatch_refine
        draft = await asyncio.to_thread(dispatch_refine, pp, agent)
        return {"dispatched": agent, "draft": str(draft)}

    @app.post("/scenes/api/flow/accept")
    async def scenes_flow_accept(payload: dict = Body(...)):
        """Authoring mode (Gate A → accepted): promote the refined draft to flow.spec.json."""
        project = payload.get("project")
        if not project:
            raise HTTPException(status_code=400, detail="project required")
        pp = _flow_project_path(project)
        from nolan.flows.authoring import accept_draft
        plan = await asyncio.to_thread(accept_draft, pp)
        return {"accepted": True, "scene_plan": str(plan)}

    @app.get("/scenes/api/frame-thumb")
    async def scenes_frame_thumb(src: str, t: float = 0.0, project: str = None):
        """A single cached JPEG frame from a video at time `t` — for clip thumbnails."""
        import hashlib
        import subprocess
        import tempfile
        import imageio_ffmpeg
        # resolve src: absolute, project-relative, or repo-root-relative
        cands = [Path(src)]
        if project:
            pr = _get_project_dir(project)
            if pr:
                cands.append(pr[0] / src)
        cands.append(Path(__file__).resolve().parents[2] / src)
        path = next((c for c in cands if c.exists()), None)
        if not path:
            raise HTTPException(status_code=404, detail="video not found")
        key = hashlib.md5(f"{path}|{t:.2f}".encode()).hexdigest()
        out = Path(tempfile.gettempdir()) / "nolan_thumbs" / f"{key}.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        if not out.exists():
            ff = imageio_ffmpeg.get_ffmpeg_exe()
            await asyncio.to_thread(subprocess.run,
                [ff, "-y", "-ss", str(t), "-i", str(path), "-frames:v", "1",
                 "-vf", "scale=240:-1", "-loglevel", "error", str(out)],
                timeout=20, capture_output=True)
        if out.exists():
            return FileResponse(str(out), media_type="image/jpeg")
        raise HTTPException(status_code=404, detail="could not extract frame")

    # ComfyUI model -> (workflow file, prompt node) for generated scenes.
    _COMFY_WF = {"flux-dev": ("workflows/image/flux-dev-fp8.json", "6"),
                 "z-image": ("workflows/image/basic-z-image.json", "27")}

    @app.post("/scenes/api/rerender")
    async def scenes_rerender(payload: dict = Body(...)):
        """Re-render the named scenes (background job); reassembles when done."""
        project = payload.get("project")
        scene_ids = payload.get("scene_ids") or []
        model = payload.get("comfyui_model") or "flux-dev"
        if model not in _COMFY_WF:
            model = "flux-dev"
        if not (project and scene_ids):
            raise HTTPException(status_code=400, detail="project and scene_ids are required")
        result = _get_project_dir(project)
        if not result:
            raise HTTPException(status_code=404, detail=f"Project '{project}' not found")
        _, scene_plan_path = result
        from nolan import iterate
        pipeline = iterate.detect_pipeline(scene_plan_path)
        wf, node = _COMFY_WF[model]

        async def worker(job, plan_path, ids, pipeline, wf, node, model):
            job.message = f"Re-rendering {len(ids)} scene(s) [{pipeline}, {model}]…"

            def _do():
                # Both pipelines may re-resolve an edited scene's library match, which
                # needs config (index DB) + an LLM client.
                from nolan.config import load_config
                from nolan.llm import create_text_llm
                config = load_config()
                client = create_text_llm(config)
                return iterate.rerender_scenes(plan_path, ids, pipeline=pipeline,
                                               llm_client=client, nolan_config=config,
                                               comfyui_workflow=wf, comfyui_prompt_node=node)

            final = await asyncio.to_thread(_do)
            # Flag any scene that silently degraded (search-miss -> generation/card).
            data = iterate.load_plan_raw(plan_path)
            fell_back = [sc.get("id") for _, sc in iterate.iter_scenes(data)
                         if sc.get("id") in set(ids)
                         and any(k in str(sc.get("resolved_source") or "") for k in ("miss", "fallback"))]
            if fell_back:
                job.message = f"Done, but {len(fell_back)} fell back: {', '.join(fell_back)}"
            return {"final": str(final) if final else None, "fell_back": fell_back}

        job = job_manager.start("rerender", worker,
                                meta={"project": project, "scenes": scene_ids,
                                      "pipeline": pipeline, "model": model},
                                plan_path=scene_plan_path, ids=scene_ids, pipeline=pipeline,
                                wf=wf, node=node, model=model)
        return {"job_id": job.id, "pipeline": pipeline, "model": model}

    @app.get("/scenes/api/fleet")
    async def scenes_fleet():
        """Live scene-edit agents (nolan* tmux sessions) joined with their status files."""
        from nolan import fleet
        return {"agents": fleet.fleet()}

    @app.post("/scenes/api/dispatch")
    async def scenes_dispatch(payload: dict = Body(...)):
        """Send selected scene(s) + a note to a named Claude Code agent (tmux)."""
        from nolan import fleet
        project = payload.get("project")
        scene_ids = payload.get("scene_ids") or []
        note = (payload.get("note") or "").strip()
        agent = payload.get("agent")
        if not (project and scene_ids and note and agent):
            raise HTTPException(status_code=400, detail="project, scene_ids, note, agent are all required")
        live = {a["agent"] for a in fleet.fleet() if a["session_alive"]}
        if agent not in live:
            raise HTTPException(status_code=409, detail=f"agent '{agent}' is not a live tmux session")
        result = _get_project_dir(project)
        if not result:
            raise HTTPException(status_code=404, detail=f"Project '{project}' not found")
        _, scene_plan_path = result
        try:
            status = fleet.dispatch(agent, str(scene_plan_path), project, scene_ids, note)
        except Exception as e:  # noqa: BLE001 - surface tmux/dispatch failures to the UI
            raise HTTPException(status_code=502, detail=f"dispatch failed: {e}")
        return {"dispatched": True, "agent": agent, "status": status}

    # ==================== Agents Routes (Orchestrator Dashboard) ====================

    if projects_dir:
        from nolan.orchestrator import dashboard as agents_dashboard

        agents_template = templates_dir / "agents.html"
        repo_root = Path(__file__).parent.parent.parent

        @app.get("/agents", response_class=HTMLResponse)
        async def agents_home():
            """Serve the agents dashboard page."""
            if agents_template.exists():
                return agents_template.read_text(encoding="utf-8")
            return "<h1>Agents template not found</h1>"

        @app.get("/api/agents")
        async def agents_list():
            """List all projects with .orchestrator/ folders + their state."""
            return {"projects": agents_dashboard.list_all_projects(projects_dir)}

        @app.get("/api/agents/{slug}/state")
        async def agents_state(slug: str):
            project_path = projects_dir / slug
            if not (project_path / ".orchestrator").exists():
                raise HTTPException(status_code=404, detail="project has no .orchestrator/")
            return agents_dashboard.project_summary(project_path)

        @app.get("/api/agents/{slug}/checkpoint")
        async def agents_checkpoint(slug: str):
            project_path = projects_dir / slug
            body = agents_dashboard.latest_checkpoint(project_path)
            if body is None:
                raise HTTPException(status_code=404, detail="no CHECKPOINT.md")
            return {"slug": slug, "body": body}

        @app.get("/api/agents/{slug}/stream")
        async def agents_stream(slug: str, since: int = 0):
            project_path = projects_dir / slug
            if not (project_path / ".orchestrator").exists():
                raise HTTPException(status_code=404, detail="project has no .orchestrator/")
            return {
                "slug": slug,
                "modules": agents_dashboard.read_all_streams(project_path, since_seq=since),
            }

        @app.post("/api/agents/{slug}/feedback")
        async def agents_feedback(slug: str, body: dict = Body(...)):
            project_path = projects_dir / slug
            if not (project_path / ".orchestrator").exists():
                raise HTTPException(status_code=404, detail="project has no .orchestrator/")
            text = (body.get("body") or "").strip()
            if not text:
                raise HTTPException(status_code=400, detail="empty feedback body")
            path = agents_dashboard.write_feedback(project_path, text)
            return {"slug": slug, "path": str(path.relative_to(project_path))}

        @app.post("/api/agents/{slug}/run")
        async def agents_run(slug: str):
            project_path = projects_dir / slug
            if not project_path.exists():
                raise HTTPException(status_code=404, detail="project not found")
            return agents_dashboard.trigger_orchestrate(project_path, repo_root)

        @app.post("/api/agents/{slug}/refine")
        async def agents_refine(slug: str, body: dict = Body(...)):
            project_path = projects_dir / slug
            if not project_path.exists():
                raise HTTPException(status_code=404, detail="project not found")
            target = (body.get("target") or "").strip()
            if not target:
                raise HTTPException(status_code=400, detail="missing 'target' step name")
            if agents_dashboard.unconsumed_feedback_count(project_path) == 0:
                raise HTTPException(
                    status_code=400,
                    detail="no unconsumed feedback files; save feedback first",
                )
            return agents_dashboard.trigger_orchestrate(
                project_path, repo_root, refine_target=target
            )

    return app


def _format_duration(seconds: Optional[float]) -> str:
    """Format duration to HH:MM:SS or MM:SS."""
    if seconds is None or seconds <= 0:
        return "0:00"
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _segment_to_dict(segment) -> dict:
    """Convert VideoSegment to dict."""
    return {
        "video_path": segment.video_path,
        "video_name": Path(segment.video_path).name,
        "timestamp_start": segment.timestamp_start,
        "timestamp_end": segment.timestamp_end,
        "timestamp_formatted": segment.timestamp_formatted,
        "duration": segment.duration,
        "frame_description": segment.frame_description,
        "transcript": segment.transcript,
        "combined_summary": segment.combined_summary,
        "inferred_context": segment.inferred_context.to_dict() if segment.inferred_context else None,
        "sample_reason": segment.sample_reason,
    }


def _computed_cluster_to_dict(cluster) -> dict:
    """Convert computed cluster to dict."""
    return {
        "id": cluster.id,
        "timestamp_start": cluster.timestamp_start,
        "timestamp_end": cluster.timestamp_end,
        "timestamp_formatted": cluster.timestamp_formatted,
        "duration": cluster.duration,
        "segment_count": len(cluster.segments),
        "cluster_summary": cluster.cluster_summary,
        "people": cluster.people,
        "locations": cluster.locations,
        "combined_transcript": cluster.combined_transcript,
        "segments": [_segment_to_dict(s) for s in cluster.segments],
    }


def _stored_cluster_to_dict(cluster: dict, index) -> dict:
    """Convert stored cluster to dict."""
    start = cluster.get("timestamp_start", 0)
    end = cluster.get("timestamp_end", 0)
    timestamp_formatted = f"{int(start // 60):02d}:{int(start % 60):02d} - {int(end // 60):02d}:{int(end % 60):02d}"
    segments = []
    video_path = cluster.get("video_path")
    if video_path:
        all_segments = index.get_segments(video_path)
        segments = [_segment_to_dict(s) for s in all_segments if s.timestamp_start >= start and s.timestamp_end <= end + 0.1]
    return {
        "id": cluster.get("cluster_index", cluster.get("id", 0)),
        "timestamp_start": start, "timestamp_end": end,
        "timestamp_formatted": timestamp_formatted,
        "duration": end - start, "segment_count": len(segments),
        "cluster_summary": cluster.get("cluster_summary"),
        "people": cluster.get("people", []),
        "locations": cluster.get("locations", []),
        "combined_transcript": "",
        "segments": segments,
    }


def run_hub(
    host: str = "127.0.0.1",
    port: int = 8011,  # 8001 belongs to SPARTA; the hub uses 8011
    db_path: Optional[Path] = None,
    projects_dir: Optional[Path] = None,
):
    """Run the unified hub server."""
    import uvicorn
    app = create_hub_app(db_path=db_path, projects_dir=projects_dir)
    uvicorn.run(app, host=host, port=port)
