"""Render Assemble routes for the NOLAN hub.

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

from nolan.hub import _resolve_assemble_audio


def register(app, ctx):
    job_manager = ctx.job_manager

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
