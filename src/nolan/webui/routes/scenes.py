"""Scenes routes for the NOLAN hub.

Moved verbatim from ``nolan.hub.create_hub_app`` (hub split). ``register(app,
ctx)`` unpacks the shared hub context into locals with the original closure
names, then registers the routes unchanged.
"""

import asyncio
import json
import uuid
from pathlib import Path
from typing import Optional, List, Dict

import httpx
from urllib.parse import quote
from fastapi import HTTPException, Query, UploadFile, File, Form, Body
from fastapi.responses import HTMLResponse, FileResponse

from nolan.hub import scan_projects, _find_scene_plan


def register(app, ctx):
    templates_dir = ctx.templates_dir
    projects_dir = ctx.projects_dir
    job_manager = ctx.job_manager

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

    @app.get("/api/scenes/projects")
    async def scenes_list_projects():
        """List available projects for scenes viewer."""
        projects = scan_projects(projects_dir) if projects_dir else []
        return {"projects": projects, "total": len(projects)}

    @app.get("/api/scenes/scenes/flat")
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

    @app.get("/api/timeline")
    async def timeline_get(project: str = Query(...)):
        """The scene plan derived onto a time axis (nolan.timeline_view):
        sections/scenes/visual-units-with-motion-badges/sfx/VO envelope."""
        result = _get_project_dir(project)
        if not result:
            raise HTTPException(status_code=404,
                                detail=f"Project '{project}' not found")
        project_path, _ = result
        from nolan.timeline_view import build_timeline
        try:
            return build_timeline(project_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    # ---- typed @-mentions (one resolver, called at BOTH note doors) ----------
    def _resolve_note_mentions(note, project, project_path, scene_plan_path,
                               scene_ids=None):
        """Expand `@[scope]token` mentions into explicit references before the
        note reaches the revise LLM or a dispatched agent. Returns
        (resolved_note, unresolved_tokens)."""
        if not note or "@[" not in note:
            return note, []
        from nolan import iterate, mentions
        scenes = []
        try:
            plan = iterate.load_plan_raw(scene_plan_path)
            secs = plan.get("sections") or {}
            groups = secs.values() if isinstance(secs, dict) else secs
            for grp in groups:
                for s in (grp if isinstance(grp, list) else []):
                    if not scene_ids or s.get("id") in scene_ids:
                        scenes.append(s)
        except Exception:
            pass
        clips = None
        if "@[vid]" in note and getattr(ctx, "db_path", None):
            try:
                from nolan.indexer import VideoIndex
                clips = VideoIndex(ctx.db_path).list_saved_clips()
            except Exception:
                clips = None
        return mentions.resolve_mentions(note, project_dir=project_path,
                                         project=project, scenes=scenes,
                                         clips=clips)

    @app.get("/api/motion/registry")
    async def motion_registry():
        """The motion registry, serialized for the UI (Inspector param
        controls + @[motion] autocomplete). Read-only mirror of
        nolan.motion.registry — the registry stays the single source of truth."""
        from dataclasses import asdict
        from nolan.motion.registry import REGISTRY, SHARED
        from nolan.still_motion import STILL_TREATMENTS
        return {
            "treatments": list(STILL_TREATMENTS),
            "shared": {k: asdict(p) for k, p in SHARED.items()},
            "effects": [{
                "id": e.id, "backend": e.backend, "category": e.category,
                "purpose": e.purpose, "when_to_use": e.when_to_use,
                "duration_default": e.duration_default,
                "content": [asdict(p) for p in e.content],
                "style": [asdict(p) for p in e.style],
                "shared": e.shared,
            } for e in REGISTRY],
        }

    # ---- timeline edits (P3) -------------------------------------------------
    def _plan_for(project: str):
        result = _get_project_dir(project)
        if not result:
            raise HTTPException(status_code=404,
                                detail=f"Project '{project}' not found")
        _, scene_plan_path = result
        from nolan import iterate
        return scene_plan_path, iterate.load_plan_raw(scene_plan_path)

    @app.post("/api/timeline/treatment")
    async def timeline_treatment(payload: dict = Body(...)):
        """Lock/unlock a scene's camera treatment (authored still_treatment).
        `treatment` must be in STILL_TREATMENTS; null/empty clears the lock
        (back to the derived pre-pass)."""
        project, scene_id = payload.get("project"), payload.get("scene_id")
        if not (project and scene_id):
            raise HTTPException(status_code=400,
                                detail="project and scene_id are required")
        treatment = payload.get("treatment") or None
        from nolan.still_motion import STILL_TREATMENTS
        if treatment is not None and treatment not in STILL_TREATMENTS:
            raise HTTPException(
                status_code=400,
                detail=f"treatment must be one of {list(STILL_TREATMENTS)}")
        plan_path, data = _plan_for(project)
        from nolan import iterate
        scene = iterate.find_scene(data, scene_id)
        if scene is None:
            raise HTTPException(status_code=404,
                                detail=f"scene '{scene_id}' not found")
        if treatment:
            scene["still_treatment"] = treatment
        else:
            scene.pop("still_treatment", None)
        iterate.save_plan_raw(plan_path, data)
        return {"scene_id": scene_id, "still_treatment": treatment}

    _MIN_SCENE_S = 1.0

    @app.post("/api/timeline/scene-window")
    async def timeline_scene_window(payload: dict = Body(...)):
        """Roll edit: move a scene's start/end on the timeline. Neighbors
        within the same section absorb the change (their shared boundary
        moves with it); section boundaries are LOCKED (narration owns
        duration). Guards: >= 1s for the scene AND its neighbors."""
        project, scene_id = payload.get("project"), payload.get("scene_id")
        if not (project and scene_id):
            raise HTTPException(status_code=400,
                                detail="project and scene_id are required")
        plan_path, data = _plan_for(project)
        # locate the scene + its section list
        section_scenes, idx = None, None
        for scenes in (data.get("sections") or {}).values():
            if not isinstance(scenes, list):
                continue
            for i, s in enumerate(scenes):
                if isinstance(s, dict) and s.get("id") == scene_id:
                    section_scenes, idx = scenes, i
                    break
            if idx is not None:
                break
        if idx is None:
            raise HTTPException(status_code=404,
                                detail=f"scene '{scene_id}' not found")
        s = section_scenes[idx]
        prev_s = section_scenes[idx - 1] if idx > 0 else None
        next_s = section_scenes[idx + 1] if idx + 1 < len(section_scenes) else None

        changed = {}
        if payload.get("start") is not None:
            start = float(payload["start"])
            lo = (float(prev_s["start_seconds"]) + _MIN_SCENE_S) if prev_s else \
                 float(s.get("start_seconds") or 0.0)   # section head: locked
            hi = float(s.get("end_seconds") or start) - _MIN_SCENE_S
            if prev_s is None:
                start = float(s.get("start_seconds") or 0.0)  # locked head
            start = max(lo, min(hi, start))
            s["start_seconds"] = round(start, 3)
            if prev_s is not None:
                prev_s["end_seconds"] = round(start, 3)
            changed["start"] = s["start_seconds"]
        if payload.get("end") is not None:
            end = float(payload["end"])
            lo = float(s.get("start_seconds") or 0.0) + _MIN_SCENE_S
            hi = (float(next_s["end_seconds"]) - _MIN_SCENE_S) if next_s else \
                 float(s.get("end_seconds") or end)     # section tail: locked
            if next_s is None:
                end = float(s.get("end_seconds") or end)      # locked tail
            end = max(lo, min(hi, end))
            s["end_seconds"] = round(end, 3)
            if next_s is not None:
                next_s["start_seconds"] = round(end, 3)
            changed["end"] = s["end_seconds"]
        if not changed:
            raise HTTPException(status_code=400,
                                detail="start and/or end required")
        from nolan import iterate
        iterate.save_plan_raw(plan_path, data)
        return {"scene_id": scene_id, "applied": changed,
                "neighbors": {"prev": prev_s.get("id") if prev_s else None,
                              "next": next_s.get("id") if next_s else None}}

    @app.post("/api/timeline/note")
    async def timeline_note_add(payload: dict = Body(...)):
        """Add a timeline range note (ScenePlan.meta.timeline_notes): the
        beefed-up comment — {t0, t1, text, scene_id?, asset?, motion?}.
        Structured halves apply deterministically via /note/apply; free text
        routes to the existing revise/agent lane."""
        project = payload.get("project")
        if not project:
            raise HTTPException(status_code=400, detail="project is required")
        try:
            t0, t1 = float(payload["t0"]), float(payload["t1"])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=400, detail="t0 and t1 (seconds) required")
        note = {
            "id": uuid.uuid4().hex[:8],
            "t0": round(min(t0, t1), 3), "t1": round(max(t0, t1), 3),
            "text": (payload.get("text") or "").strip(),
            "scene_id": payload.get("scene_id"),
            "asset": payload.get("asset"),        # path to pin
            "motion": payload.get("motion"),      # STILL_TREATMENTS value
            "status": "open",
        }
        if not (note["text"] or note["asset"] or note["motion"]):
            raise HTTPException(status_code=400,
                                detail="a note needs text, an asset or a motion")
        plan_path, data = _plan_for(project)
        data.setdefault("meta", {}).setdefault("timeline_notes", []).append(note)
        from nolan import iterate
        iterate.save_plan_raw(plan_path, data)
        return note

    def _note_scene(data: dict, note: dict):
        """The scene a note targets: explicit scene_id, else the window
        containing the note's midpoint."""
        from nolan import iterate
        if note.get("scene_id"):
            return iterate.find_scene(data, note["scene_id"])
        mid = (float(note["t0"]) + float(note["t1"])) / 2
        for scenes in (data.get("sections") or {}).values():
            if not isinstance(scenes, list):
                continue
            for s in scenes:
                if not isinstance(s, dict):
                    continue
                a, b = s.get("start_seconds"), s.get("end_seconds")
                if a is not None and b is not None and a <= mid < b:
                    return s
        return None

    @app.post("/api/timeline/note/apply")
    async def timeline_note_apply(payload: dict = Body(...)):
        """Deterministic apply of a note's STRUCTURED half: asset -> pin,
        motion -> still_treatment lock. Free text is NOT interpreted here —
        if text remains, the response says route='agent' so the UI sends it
        down the existing revise lane (status becomes 'dispatched' there)."""
        project, note_id = payload.get("project"), payload.get("note_id")
        if not (project and note_id):
            raise HTTPException(status_code=400,
                                detail="project and note_id are required")
        plan_path, data = _plan_for(project)
        notes = (data.get("meta") or {}).get("timeline_notes") or []
        note = next((n for n in notes if n.get("id") == note_id), None)
        if note is None:
            raise HTTPException(status_code=404, detail=f"note '{note_id}' not found")
        scene = _note_scene(data, note)
        if scene is None:
            raise HTTPException(status_code=422,
                                detail="no scene under the note's window")
        applied = []
        if note.get("asset"):
            src = str(note["asset"])
            if not Path(src).exists():
                raise HTTPException(status_code=422,
                                    detail=f"asset not found: {src}")
            scene["pinned_asset"] = {"src": src, "kind": "image", "by": "human",
                                     **({"note": note["text"]} if note.get("text") else {})}
            applied.append(f"pinned {Path(src).name}")
        if note.get("motion"):
            from nolan.still_motion import STILL_TREATMENTS
            if note["motion"] not in STILL_TREATMENTS:
                raise HTTPException(
                    status_code=422,
                    detail=f"motion must be one of {list(STILL_TREATMENTS)}")
            scene["still_treatment"] = note["motion"]
            applied.append(f"locked {note['motion']}")
        route = "agent" if (note.get("text") and not applied) else None
        note["status"] = "applied" if applied else "open"
        note["scene_id"] = scene.get("id")
        from nolan import iterate
        iterate.save_plan_raw(plan_path, data)
        return {"note": note, "applied": applied, "route": route,
                "scene_id": scene.get("id")}

    @app.post("/api/timeline/note/update")
    async def timeline_note_update(payload: dict = Body(...)):
        """Update a note's status (e.g. 'dispatched' after the UI routes its
        free text to the agent lane) or delete it (status='deleted')."""
        project, note_id = payload.get("project"), payload.get("note_id")
        if not (project and note_id):
            raise HTTPException(status_code=400,
                                detail="project and note_id are required")
        plan_path, data = _plan_for(project)
        meta = data.setdefault("meta", {})
        notes = meta.get("timeline_notes") or []
        note = next((n for n in notes if n.get("id") == note_id), None)
        if note is None:
            raise HTTPException(status_code=404, detail=f"note '{note_id}' not found")
        status = payload.get("status")
        if status == "deleted":
            meta["timeline_notes"] = [n for n in notes if n.get("id") != note_id]
        elif status in ("open", "applied", "dispatched"):
            note["status"] = status
        else:
            raise HTTPException(status_code=400, detail="bad status")
        from nolan import iterate
        iterate.save_plan_raw(plan_path, data)
        return {"ok": True, "note_id": note_id, "status": status}

    @app.get("/api/scenes/audio-info")
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

    @app.post("/api/scenes/scene/revise")
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
        motion_warnings = []
        if patch and patch.get("motion_spec"):
            # normalize against the registry NOW (unknown effect = hard refuse;
            # soft issues surface as warnings but the normalized spec applies —
            # same semantics the render gate uses).
            from nolan.motion import spec as motion_spec_mod
            normalized, errs = motion_spec_mod.validate(patch["motion_spec"])
            if any(e.startswith("unknown effect") for e in errs):
                raise HTTPException(status_code=400, detail="; ".join(errs))
            patch["motion_spec"] = normalized
            motion_warnings = errs
        client = None
        words = None
        unresolved = []
        if note:
            from nolan.config import load_config
            from nolan.llm import create_text_llm
            client = create_text_llm(load_config())
            # VO word-timing for {cue:"..."} in a photo_brief (cached after first call)
            words = await asyncio.to_thread(iterate.scene_words, scene_plan_path)
            # typed @[scope]token mentions -> explicit references for the LLM
            note, unresolved = await asyncio.to_thread(
                _resolve_note_mentions, note, project, project_path,
                scene_plan_path, [scene_id])
        try:
            applied = await iterate.apply_edit(scene_plan_path, scene_id, patch=patch,
                                               note=note, client=client, pipeline=pipeline,
                                               transcript_words=words)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return {"applied": applied, "pipeline": pipeline,
                "unresolved_mentions": unresolved,
                "motion_warnings": motion_warnings}

    @app.post("/api/asset-review")
    async def api_asset_review(body: dict = Body(...)):
        """Run beat-by-beat asset acquisition review across brains (engine/plan/agent) → gallery."""
        from nolan.config import load_config
        from nolan.webui import operations
        project = (body.get("project") or "").strip()
        if not project:
            raise HTTPException(status_code=400, detail="project is required")
        brains = body.get("brains") if isinstance(body.get("brains"), list) and body.get("brains") else ["engine"]
        job = job_manager.start(
            "asset-review", operations.asset_review_job, config=load_config(),
            project=project, brains=brains, beats=body.get("beats"),
            media=(body.get("media") if isinstance(body.get("media"), list) else None),
            agent=(body.get("agent") or "nolan4"))
        return {"job_id": job.id, "type": "asset-review",
                "gallery": f"/broll-gen/asset_review_{project}.html"}

    @app.post("/api/scenes/scene/super-search")
    async def scenes_super_search(body: dict = Body(...)):
        """Per-beat super search from the Scene Plan Viewer — the /broll pairing engine WITH the
        loaded project as context and the scene's beat auto-located. Returns a job."""
        from nolan.config import load_config
        from nolan.webui import operations
        project = (body.get("project") or "").strip()
        line = (body.get("line") or "").strip()
        if not (project and line):
            raise HTTPException(status_code=400, detail="project and line are required")
        med = body.get("media")
        job = job_manager.start(
            "super-search", operations.evoke_broll, config=load_config(),
            line=line, operator=(body.get("operator") or "auto"), mode=(body.get("mode") or "stock"),
            project=project, media=(med if isinstance(med, list) and med else None))
        return {"job_id": job.id, "type": "super-search"}

    @app.post("/api/scenes/scene/attach")
    async def scenes_scene_attach(body: dict = Body(...)):
        """Attach a super-search pick to a scene (download image → matched_asset, or video ref)."""
        from nolan.config import load_config
        from nolan.webui import operations
        project = (body.get("project") or "").strip()
        scene_id = (body.get("scene_id") or "").strip()
        url = (body.get("url") or "").strip()
        if not (project and scene_id and url):
            raise HTTPException(status_code=400, detail="project, scene_id, url are required")
        job = job_manager.start(
            "attach-asset", operations.attach_scene_asset, config=load_config(),
            project_name=project, scene_id=scene_id, url=url, kind=(body.get("kind") or "image"),
            source=(body.get("source") or ""), title=(body.get("title") or ""))
        return {"job_id": job.id, "type": "attach-asset"}

    @app.post("/api/scenes/scene/assets")
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
                asset["thumb"] = (f"/api/scenes/frame-thumb?project={project}"
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
        elif op == "pin":
            # Human PIN: THIS asset for THIS beat. The asset engine returns
            # "pinned:human" for the scene and never re-resolves it; premium
            # renders it ahead of matched/auto assets. Pin a tray asset by id,
            # or pass src/kind directly.
            a = _find(payload.get("asset_id")) if payload.get("asset_id") else None
            src = (a or {}).get("src") or payload.get("src")
            if not src:
                raise HTTPException(status_code=400, detail="asset_id or src required")
            pin = {"src": str(src),
                   "kind": (a or {}).get("kind") or payload.get("kind", "image"),
                   "by": "human"}
            for key in ("clip_start",):
                v = (a or {}).get(key, payload.get(key))
                if v is not None:
                    pin[key] = float(v)
            note = (payload.get("note") or "").strip()
            if note:
                pin["note"] = note
                scene["human_note"] = note
            scene["pinned_asset"] = pin
        elif op == "unpin":
            scene.pop("pinned_asset", None)
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

    @app.post("/api/scenes/flow/refine")
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

    @app.post("/api/scenes/flow/accept")
    async def scenes_flow_accept(payload: dict = Body(...)):
        """Authoring mode (Gate A → accepted): promote the refined draft to flow.spec.json."""
        project = payload.get("project")
        if not project:
            raise HTTPException(status_code=400, detail="project required")
        pp = _flow_project_path(project)
        from nolan.flows.authoring import accept_draft
        plan = await asyncio.to_thread(accept_draft, pp)
        return {"accepted": True, "scene_plan": str(plan)}

    @app.get("/api/scenes/frame-thumb")
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
        cands.append(ctx.repo_root / src)
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

    @app.get("/api/scenes/source-video")
    async def scenes_source_video(src: str, project: str = None):
        """Stream an original source video (HTTP range-enabled) for clip preview.

        FileResponse honours the Range header, so the picker's preview player can
        seek straight to a clip's in-point without materializing the clip.
        """
        cands = [Path(src)]
        if project:
            pr = _get_project_dir(project)
            if pr:
                cands.append(pr[0] / src)
        cands.append(ctx.repo_root / src)
        path = next((c for c in cands if c.exists()), None)
        if not path:
            raise HTTPException(status_code=404, detail="video not found")
        mt = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
              ".mkv": "video/x-matroska", ".m4v": "video/mp4"}.get(path.suffix.lower(), "video/mp4")
        return FileResponse(str(path), media_type=mt)

    @app.post("/api/scenes/scene/upload")
    async def scenes_scene_upload(project: str = Form(...), file: UploadFile = File(...)):
        """Save a dropped local image/video into the project; returns a path to attach.

        The drag-and-drop handler in the Scenes page calls this, then attaches the
        returned path via the existing `op=add, source=path` asset flow.
        """
        import re as _re, shutil
        result = _get_project_dir(project)
        if not result:
            raise HTTPException(status_code=404, detail=f"Project '{project}' not found")
        project_path, _ = result
        name = _re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file.filename or "upload").name) or "upload"
        dest_dir = project_path / "assets" / "uploads"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / name
        i = 1
        while dest.exists():
            dest = dest_dir / f"{Path(name).stem}_{i}{Path(name).suffix}"
            i += 1
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        ext = dest.suffix.lower()
        kind = "clip" if ext in (".mp4", ".webm", ".mov", ".mkv", ".m4v") else "image"
        rel = str(dest.relative_to(project_path)).replace("\\", "/")
        return {"path": rel, "kind": kind, "label": Path(name).stem}

    # ComfyUI model -> (workflow file, prompt node) for generated scenes.
    _COMFY_WF = {"flux-dev": ("workflows/image/flux-dev-fp8.json", "6"),
                 "z-image": ("workflows/image/basic-z-image.json", "27")}

    @app.post("/api/scenes/rerender")
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

    @app.get("/api/scenes/fleet")
    async def scenes_fleet():
        """Live scene-edit agents (nolan* tmux sessions) joined with their status files."""
        from nolan import fleet
        return {"agents": fleet.fleet()}

    @app.post("/api/scenes/dispatch")
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
        project_path, scene_plan_path = result
        # typed @[scope]token mentions -> explicit references for the agent
        note, unresolved = await asyncio.to_thread(
            _resolve_note_mentions, note, project, project_path,
            scene_plan_path, scene_ids)
        try:
            status = fleet.dispatch(agent, str(scene_plan_path), project, scene_ids, note)
        except Exception as e:  # noqa: BLE001 - surface tmux/dispatch failures to the UI
            raise HTTPException(status_code=502, detail=f"dispatch failed: {e}")
        return {"dispatched": True, "agent": agent, "status": status,
                "unresolved_mentions": unresolved}
