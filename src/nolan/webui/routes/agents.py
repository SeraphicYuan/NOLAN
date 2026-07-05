"""Agents routes for the NOLAN hub.

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
    projects_dir = ctx.projects_dir

    # ==================== Agents Routes (Orchestrator Dashboard) ====================

    if projects_dir:
        from nolan.orchestrator import dashboard as agents_dashboard

        agents_template = templates_dir / "agents.html"
        repo_root = ctx.repo_root

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
                return {"slug": slug, "modules": []}   # not started yet — no streams, not an error
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
        async def agents_run(slug: str, body: dict = Body(default={})):
            project_path = projects_dir / slug
            if not project_path.exists():
                raise HTTPException(status_code=404, detail="project not found")
            agent = (body.get("agent") or "").strip() or None   # dispatch to a chosen NOLAN agent, else run locally
            auto = bool(body.get("auto"))   # run all remaining steps (--auto) vs. advance one
            return agents_dashboard.trigger_orchestrate(project_path, repo_root, agent=agent, auto=auto)

        @app.get("/api/agents/{slug}/plan")
        async def agents_plan(slug: str):
            """Read-only authored plan (style_guide.md + scene_plan.json summary) for inline viewing."""
            project_path = projects_dir / slug
            if not project_path.exists():
                raise HTTPException(status_code=404, detail="project not found")
            return agents_dashboard.read_authored_plan(project_path)

        @app.get("/api/agents/{slug}/runlog")
        async def agents_runlog(slug: str):
            """Tail of the last local orchestrate subprocess logs (for surfacing run failures)."""
            project_path = projects_dir / slug
            if not project_path.exists():
                raise HTTPException(status_code=404, detail="project not found")
            return agents_dashboard.read_run_logs(project_path)

        @app.get("/api/agents/{slug}/output")
        async def agents_output(slug: str):
            """Serve the rendered final.mp4 for a project (the render step's output)."""
            project_path = projects_dir / slug
            final = project_path / "output" / "final.mp4"
            if not project_path.exists() or not final.exists():
                raise HTTPException(status_code=404, detail="no rendered output")
            return FileResponse(final, media_type="video/mp4")

        @app.delete("/api/agents/{slug}/feedback/{name}")
        async def agents_feedback_delete(slug: str, name: str):
            """Delete a saved feedback file (review_<n>.md)."""
            project_path = projects_dir / slug
            if not project_path.exists():
                raise HTTPException(status_code=404, detail="project not found")
            try:
                ok = agents_dashboard.delete_feedback(project_path, name)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            if not ok:
                raise HTTPException(status_code=404, detail="feedback file not found")
            return {"deleted": name}

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
