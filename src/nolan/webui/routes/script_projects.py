"""Script Projects routes for the NOLAN hub.

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
    projects_dir = ctx.projects_dir
    job_manager = ctx.job_manager
    style_store = ctx.style_store

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

    @app.get("/api/script-registries")
    async def script_registries():
        """Static rubric + spine-structure registries — for the create-form preset dropdowns
        (which have no project yet to query per-slug)."""
        from nolan.scriptwriter.rubrics import ARCHETYPES
        from nolan.scriptwriter.spine_structures import STRUCTURES
        return {
            "archetypes": [{"id": a.id, "title": a.title, "when_to_use": a.when_to_use}
                           for a in ARCHETYPES.values()],
            "spine_structures": [{"id": s.id, "title": s.title, "when_to_use": s.when_to_use,
                                  "min_threads": s.min_threads, "max_threads": s.max_threads}
                                 for s in STRUCTURES.values()],
        }

    @app.post("/api/script-projects")
    async def script_projects_create(body: dict = Body(...)):
        name = (body.get("name") or "").strip()
        subject = (body.get("subject") or "").strip()
        style_id = (body.get("style_id") or "").strip()
        if not subject or not style_id:
            raise HTTPException(status_code=400, detail="subject and style_id are required")
        if not style_store.exists(style_id):
            raise HTTPException(status_code=400, detail=f"unknown style_id: {style_id}")
        spine = body.get("composite_spine") or {}
        try:
            slug = script_project_store.create(
                name or subject, subject=subject, style_id=style_id,
                angle=(body.get("angle") or "").strip(),
                pivot=(body.get("pivot") or "").strip(),
                target_minutes=float(body.get("target_minutes") or 8.0),
                description=(body.get("description") or "").strip(),
                mode=(body.get("mode") or "semi").strip(),
                composite_spine=spine if isinstance(spine, dict) else {},
                review_archetype=(body.get("review_archetype") or "").strip(),
                ad_hoc_questions=body.get("ad_hoc_questions") or [],
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
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
        title = (body.get("title") or "").strip()
        allowed = ("url", "paste", "file", "reference", "youtube", "library-video", "mineru-book")
        if kind not in allowed:
            raise HTTPException(status_code=400, detail=f"kind must be one of {allowed}")

        if kind == "youtube":
            # Fetch subtitles only (no video) at add-time → source text is 'fetched'.
            if not url:
                raise HTTPException(status_code=400, detail="url required for kind=youtube")
            try:
                from nolan.youtube import YouTubeClient
                res = await asyncio.to_thread(YouTubeClient().fetch_transcript, url)
            except Exception as e:
                raise HTTPException(status_code=502,
                                    detail=f"could not fetch YouTube subtitles: {e}")
            text = res.get("text")
            if not (text or "").strip():
                raise HTTPException(status_code=502, detail="no subtitles found for that video")
            title = title or res.get("title") or url
            entry = script_project_store.add_source(
                slug, kind="youtube", title=title, url=url, text=text)
            return {"source": entry}

        if kind == "library-video":
            # Use an already-ingested library video's transcript (concatenated segments).
            video_path = (body.get("video_path") or url or "").strip()
            if not video_path:
                raise HTTPException(status_code=400, detail="video_path required for kind=library-video")
            if not (db_path and db_path.exists()):
                raise HTTPException(status_code=400, detail="library index not available")
            from nolan.indexer import VideoIndex
            segs = await asyncio.to_thread(VideoIndex(db_path).get_segments, video_path)
            transcript = "\n".join(s.transcript for s in segs
                                   if getattr(s, "transcript", None))
            if not transcript.strip():
                raise HTTPException(status_code=400, detail="that video has no transcript indexed")
            title = title or Path(video_path).name
            entry = script_project_store.add_source(
                slug, kind="library-video", title=title, url=video_path, text=transcript)
            return {"source": entry}

        # text-carrying kinds: url (pending) / paste / file / reference / mineru-book
        if kind == "url" and not url:
            raise HTTPException(status_code=400, detail="url required for kind=url")
        if kind in ("paste", "file", "mineru-book") and not text:
            raise HTTPException(status_code=400, detail=f"text required for kind={kind}")
        entry = script_project_store.add_source(slug, kind=kind, title=title, url=url, text=text)
        return {"source": entry}

    @app.post("/api/script-projects/{slug}/upload-file")
    async def script_projects_upload_file(slug: str, file: UploadFile = File(...),
                                          kind: str = Form("file")):
        """Add an uploaded source (.txt/.md/.srt/.vtt, or a MinerU book .md) to a project.

        `kind` = 'file' (default) or 'mineru-book'. No length cap — long books are stored
        whole; grounding chunk-reads them.
        """
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
        k = kind if kind in ("file", "mineru-book") else "file"
        entry = script_project_store.add_source(slug, kind=k, title=title, text=text)
        return {"source": entry}

    @app.post("/api/script-projects/{slug}/mode")
    async def script_projects_set_mode(slug: str, body: dict = Body(...)):
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        m = script_project_store.set_mode(slug, (body.get("mode") or "semi").strip())
        return {"mode": m.get("mode")}

    @app.post("/api/script-projects/{slug}/style")
    async def script_projects_set_style(slug: str, body: dict = Body(...)):
        """Change the narrative style (voice guide) on an existing project."""
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        style_id = (body.get("style_id") or "").strip()
        if not style_store.exists(style_id):
            raise HTTPException(status_code=400, detail=f"unknown style_id: {style_id}")
        m = script_project_store.set_style(slug, style_id)
        return {"style_id": m.get("style_id")}

    @app.get("/api/script-projects/{slug}/review-config")
    async def script_projects_review_config(slug: str):
        """Archetype (resolved + override), ad-hoc questions, composite spine, and the static
        archetype + spine-structure registries — everything the Review UI needs to render."""
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        from nolan.scriptwriter.rubrics import ARCHETYPES
        from nolan.scriptwriter.spine_structures import STRUCTURES
        meta = script_project_store.get(slug)
        return {
            "archetype": script_project_store.resolve_archetype(slug),
            "archetype_override": meta.get("review_archetype") or "",
            "ad_hoc_questions": meta.get("ad_hoc_questions") or [],
            "composite_spine": meta.get("composite_spine") or {},
            "archetypes": [{"id": a.id, "title": a.title, "when_to_use": a.when_to_use}
                           for a in ARCHETYPES.values()],
            "spine_structures": [{"id": s.id, "title": s.title, "when_to_use": s.when_to_use,
                                  "min_threads": s.min_threads, "max_threads": s.max_threads}
                                 for s in STRUCTURES.values()],
        }

    @app.post("/api/script-projects/{slug}/review-config")
    async def script_projects_set_review_config(slug: str, body: dict = Body(...)):
        """Set the review archetype override and/or the ad-hoc questions."""
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        if "archetype" in body:
            script_project_store.set_review_archetype(slug, (body.get("archetype") or "").strip())
        if "ad_hoc_questions" in body:
            script_project_store.set_ad_hoc_questions(slug, body.get("ad_hoc_questions") or [])
        return {"ok": True, "archetype": script_project_store.resolve_archetype(slug)}

    @app.get("/api/script-projects/{slug}/gate")
    async def script_projects_gate(slug: str, draft: Optional[str] = None):
        """Run the deterministic script gate on the current (or named) draft."""
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        from nolan.scriptwriter.gate import run_gate
        rep = await asyncio.to_thread(run_gate, slug, script_project_store, draft)
        return {"ok": rep.ok,
                "checks": [{"id": c.id, "level": c.level, "message": c.message} for c in rep.checks]}

    @app.get("/api/script-projects/{slug}/review/{n}")
    async def script_projects_review(slug: str, n: int):
        """A review's markdown + parsed findings + which finding ids are currently approved."""
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        md = script_project_store.read_review(slug, n)
        if md is None:
            raise HTTPException(status_code=404, detail=f"no review-{n:02d}")
        findings, approved_ids = [], []
        fp = script_project_store.review_findings_path(slug, n)
        if fp.exists():
            try:
                findings = json.loads(fp.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                findings = []
        ap = script_project_store.review_approved_path(slug, n)
        if ap.exists():
            try:
                approved_ids = [f.get("id") for f in json.loads(ap.read_text(encoding="utf-8"))]
            except (OSError, json.JSONDecodeError):
                approved_ids = []
        return {"n": n, "md": md, "findings": findings, "approved_ids": approved_ids}

    @app.post("/api/script-projects/{slug}/review/{n}/approve")
    async def script_projects_review_approve(slug: str, n: int, body: dict = Body(...)):
        """Write the approved-findings subset (the critique gate) → review-NN.approved.json."""
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        fp = script_project_store.review_findings_path(slug, n)
        if not fp.exists():
            raise HTTPException(status_code=404, detail="no findings to approve")
        try:
            findings = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise HTTPException(status_code=500, detail="findings unreadable")
        ids = set(body.get("ids") or [])
        approved = [f for f in findings if f.get("id") in ids]
        ap = script_project_store.review_approved_path(slug, n)
        ap.parent.mkdir(parents=True, exist_ok=True)
        ap.write_text(json.dumps(approved, indent=2, ensure_ascii=False), encoding="utf-8")
        # Learning loop: record which findings the producer kept vs dropped (best-effort).
        from nolan.scriptwriter import ledger
        ledger.record_review_decision(slug, script_project_store, n, list(ids))
        return {"approved": len(approved), "of": len(findings)}

    @app.post("/api/script-projects/{slug}/spine")
    async def script_projects_set_spine(slug: str, body: dict = Body(...)):
        """Set the composite spine (Phase 2): structure + threads + binding."""
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        try:
            m = script_project_store.set_composite_spine(
                slug, (body.get("structure") or "single").strip(),
                body.get("threads") or [], (body.get("binding") or "").strip())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"composite_spine": m.get("composite_spine")}

    @app.post("/api/script-projects/{slug}/length")
    async def script_projects_set_length(slug: str, body: dict = Body(...)):
        """Change the target length (minutes) after creation."""
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        try:
            m = script_project_store.set_target_minutes(slug, body.get("minutes"))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"target_minutes": m.get("target_minutes")}

    @app.post("/api/script-projects/{slug}/choose-angle")
    async def script_projects_choose_angle(slug: str, body: dict = Body(...)):
        """Semi-auto gate: record the human-picked angle before drafting."""
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        m = script_project_store.set_chosen_angle(slug, body.get("angle") or "")
        return {"chosen_angle": m.get("chosen_angle")}

    @app.post("/api/script-projects/{slug}/run")
    async def script_projects_run(slug: str, body: dict = Body(default={})):
        """Dispatch a script pipeline phase: prep | draft | v3 (auto). v3 is default."""
        from nolan.webui import operations
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        phase = (body.get("phase") or "v3").strip()   # v3 is the default pipeline
        if phase not in ("prep", "draft", "v3", "review", "revise"):
            raise HTTPException(status_code=400,
                                detail="phase must be prep/draft/v3/review/revise")
        session = (body.get("session") or "auto").strip() or "auto"
        job = job_manager.start(
            "script-phase", operations.run_script_phase,
            meta={"slug": slug, "phase": phase, "session": session},
            store_root="projects", slug=slug, session=session, phase=phase,
        )
        return {"job_id": job.id, "type": "script-phase", "phase": phase}

    @app.post("/api/script-projects/{slug}/auto")
    async def script_projects_auto(slug: str, body: dict = Body(default={})):
        """Full-auto: draft (v3, respecting any preset angle/spine) → gate → review →
        auto-approve → revise → gate → verify, in one unattended job."""
        from nolan.webui import operations
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        session = (body.get("session") or "auto").strip() or "auto"
        job = job_manager.start(
            "script-auto", operations.run_full_auto,
            meta={"slug": slug, "session": session},
            store_root="projects", slug=slug, session=session)
        return {"job_id": job.id, "type": "script-auto"}

    @app.get("/api/script-projects/{slug}/angle-candidates")
    async def script_projects_angle_candidates(slug: str):
        """Parsed candidate angles from angles.md (for the click-to-pick angle cards)."""
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        return {"candidates": script_project_store.angle_candidates(slug)}

    @app.get("/api/script-projects/{slug}/verify/{n}")
    async def script_projects_verify(slug: str, n: int):
        """Heuristic check that the revise (draft-N → draft-(N+1)) actually touched review-N's
        approved findings."""
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        from nolan.scriptwriter.gate import verify_revision
        return await asyncio.to_thread(verify_revision, script_project_store, slug, n)

    @app.post("/api/script-projects/{slug}/review/{n}/add-finding")
    async def script_projects_add_finding(slug: str, n: int, body: dict = Body(...)):
        """Append a PRODUCER-authored finding to review-N (the human 'add a critique' at the gate)."""
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        problem = (body.get("problem") or "").strip()
        fix = (body.get("fix") or "").strip()
        if not problem and not fix:
            raise HTTPException(status_code=400, detail="a finding needs a problem or a fix")
        fp = script_project_store.review_findings_path(slug, n)
        findings = []
        if fp.exists():
            try:
                findings = json.loads(fp.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                findings = []
        ids = {f.get("id") for f in findings}
        i = 1
        while f"h{i}" in ids:
            i += 1
        nf = {"id": f"h{i}", "dim": (body.get("dim") or "producer-note").strip(),
              "severity": (body.get("severity") or "med").strip(),
              "beat": (body.get("beat") or "").strip(), "quote": (body.get("quote") or "").strip(),
              "problem": problem, "fix": fix, "source": "human"}
        findings.append(nf)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(findings, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"finding": nf, "total": len(findings)}

    @app.get("/api/script-projects/{slug}/drafts")
    async def script_projects_drafts(slug: str):
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        return {"drafts": script_project_store.list_drafts(slug)}

    @app.get("/api/script-projects/{slug}/draft/{name}")
    async def script_projects_draft(slug: str, name: str):
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        content = script_project_store.read_draft(slug, name)
        if content is None:
            raise HTTPException(status_code=404, detail="draft not found")
        return {"slug": slug, "name": name, "content": content}

    @app.post("/api/script-projects/{slug}/promote-draft/{name}")
    async def script_projects_promote_draft(slug: str, name: str):
        """Promote a draft to the Director-ready script.md (the A/B winner)."""
        if not script_project_store.exists(slug):
            raise HTTPException(status_code=404, detail="project not found")
        if not script_project_store.promote_draft(slug, name):
            raise HTTPException(status_code=404, detail="draft not found")
        return {"promoted": name}

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
        session = (body.get("session") or "auto").strip() or "auto"
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

    ctx.script_project_store = script_project_store
