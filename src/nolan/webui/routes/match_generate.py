"""Match Generate routes for the NOLAN hub.

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
                knowledge=bool(body.get("knowledge", False)),
                knowledge_kind=str(body.get("knowledge_kind", "any")),
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
