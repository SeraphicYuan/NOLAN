"""HyperFrames scene edit-mode routes — the composer-native `/hyperframes` page + its edit APIs.

Thin wrappers over ``nolan.hyperframes`` (the editing bridge): discover compositions, list the
frame->scene tree, patch/add/remove/retime a scene through the author.py gate, plan within-frame
transitions, snapshot-preview a frame, and background-render a full frame clip. Edit per scene,
re-render per frame (see kb/frame-vs-scene.md, kb/edit-mode-plan.md).
"""
import asyncio
import json
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import Body, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from nolan import hyperframes as hfedit


def register(app, ctx):
    templates_dir = ctx.templates_dir
    job_manager = ctx.job_manager
    hf_template = templates_dir / "hf_scenes.html"

    def _guard(fn, *a, **k):
        """Map engine exceptions to HTTP status: missing comp/frame/scene -> 404, bad arg -> 400."""
        try:
            return fn(*a, **k)
        except (FileNotFoundError, KeyError) as e:
            raise HTTPException(status_code=404, detail=str(e))
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ---- page

    @app.get("/hyperframes", response_class=HTMLResponse)
    async def hyperframes_home():
        if hf_template.exists():
            return hf_template.read_text(encoding="utf-8")
        return "<h1>HyperFrames edit template not found</h1>"

    # ---- read

    @app.get("/api/hf/compositions")
    async def hf_compositions():
        return {"compositions": hfedit.discover_compositions()}

    @app.get("/api/hf/frames")
    async def hf_frames(comp: str = Query(...)):
        return {"comp": comp, "frames": _guard(hfedit.list_frames, comp)}

    @app.get("/api/hf/catalog")
    async def hf_catalog():
        return hfedit.catalog()

    @app.get("/api/hf/frame-layers")
    async def hf_frame_layers(comp: str = Query(...), frame_id: str = Query(...)):
        """The frame's layer map (bg/overlay/text/fx lanes) for the layer-lanes view — each element carries its
        time window + the inspector control it edits, so a lane chip click jumps straight to that control."""
        return _guard(hfedit.frame_layers, comp, frame_id)

    # ---- ✨ Replace: per-scene asset replacement (context-derived prompt → stock + ComfyUI gen) --------------

    @app.get("/api/hf/replace/brief")
    async def hf_replace_brief(comp: str = Query(...), frame_id: str = Query(...), scene_id: str = Query(...)):
        """The editable starting point for a replace — which asset field, its current src, modality, and a
        prompt/query DERIVED from the scene (old gen_prompt if any, else the narration) + the theme."""
        from nolan.hyperframes import replace as rep
        return _guard(rep.brief, comp, frame_id, scene_id)

    @app.post("/api/hf/replace/search")
    async def hf_replace_search(payload: dict = Body(...)):
        """Stock search (background job — download takes a few seconds, esp. video). Result = the candidates,
        which ALSO land in the pool tagged to the scene."""
        comp, fid, sid = payload.get("comp"), payload.get("frame_id"), payload.get("scene_id")
        query, modality, n = payload.get("query", ""), payload.get("modality", "image"), int(payload.get("n", 6))
        if not (comp and fid and sid):
            raise HTTPException(status_code=400, detail="comp, frame_id, scene_id required")

        async def worker(job, comp, fid, sid, query, modality, n):
            from nolan.hyperframes import replace as rep
            job.message = f"Searching stock for “{query[:40]}”…"
            job.log(f"stock search: {query!r} ({modality}, up to {n})")
            cands = await asyncio.to_thread(rep.search, comp, fid, sid, query, n, modality)
            job.message = f"Found {len(cands)} stock candidate(s)"
            job.log(f"landed {len(cands)}")
            return {"candidates": cands}

        job = job_manager.start("hf_replace_search", worker, meta={"comp": comp, "scene": sid},
                                comp=comp, fid=fid, sid=sid, query=query, modality=modality, n=n)
        return {"job_id": job.id}

    @app.get("/api/hf/style-presets")
    async def hf_style_presets():
        """The text-to-image style presets for the gen dropdown (prepended to the prompt)."""
        from nolan.hyperframes import replace as rep
        return {"presets": rep.style_presets()}

    @app.post("/api/hf/replace/enhance")
    async def hf_replace_enhance(payload: dict = Body(...)):
        """Two-step gen STEP 1: art-direct the raw prompt (LLM subject + project brief) + prepend the style
        preset → the final ComfyUI prompt the user then tweaks. Sync (~one LLM call)."""
        comp, fid, sid = payload.get("comp"), payload.get("frame_id"), payload.get("scene_id")
        prompt, style = payload.get("prompt", ""), payload.get("style", "")
        if not (comp and fid and sid and prompt.strip()):
            raise HTTPException(status_code=400, detail="comp, frame_id, scene_id, prompt required")
        from nolan.hyperframes import replace as rep
        return await asyncio.to_thread(_guard, rep.enhance, comp, fid, sid, prompt, style)

    @app.post("/api/hf/replace/generate")
    async def hf_replace_generate(payload: dict = Body(...)):
        """ComfyUI generate (background job, one-tap — GPU). Result = the candidates, tagged to the scene."""
        comp, fid, sid = payload.get("comp"), payload.get("frame_id"), payload.get("scene_id")
        prompt, n, neg = payload.get("prompt", ""), int(payload.get("n", 3)), payload.get("negative")
        if not (comp and fid and sid and prompt.strip()):
            raise HTTPException(status_code=400, detail="comp, frame_id, scene_id, prompt required")

        async def worker(job, comp, fid, sid, prompt, n, neg):
            from nolan.hyperframes import replace as rep
            job.message = f"Generating {n} image(s)…"
            cands = await asyncio.to_thread(rep.generate, comp, fid, sid, prompt, n, neg, job.log)
            job.message = f"Generated {len(cands)}/{n}"
            return {"candidates": cands}

        job = job_manager.start("hf_replace_gen", worker, meta={"comp": comp, "scene": sid},
                                comp=comp, fid=fid, sid=sid, prompt=prompt, n=n, neg=neg)
        return {"job_id": job.id}

    @app.get("/api/hf/frame-spec")
    async def hf_frame_spec(comp: str = Query(...), frame_id: str = Query(...)):
        spec, info = _guard(hfedit.load_frame_spec, comp, frame_id)
        return {"comp": comp, "frame": spec["frames"][info["i"]],
                "transcripts": _guard(hfedit.frame_transcripts, comp, frame_id)}

    @app.get("/api/hf/snapshot")
    async def hf_snapshot(comp: str = Query(...), frame_id: str = Query(...),
                          at: float = Query(None)):
        """Fast still preview of a frame at timecode `at` (default mid) — snapshot-first iteration."""
        res = await asyncio.to_thread(_guard, hfedit.snapshot_frame, comp, frame_id, at)
        if not res.get("ok") or not res.get("png") or not Path(res["png"]).exists():
            raise HTTPException(status_code=500, detail=f"snapshot failed: {res.get('output', '')[-300:]}")
        return FileResponse(res["png"], media_type="image/png")

    @app.get("/api/hf/frame-video")
    async def hf_frame_video(comp: str = Query(...), frame_id: str = Query(...)):
        """Serve a frame's rendered per-frame video — the newest of `<id>.preview.mp4` (render_frame)
        or `<id>.clip.mp4` (incremental render), so both surfaces are playable in the edit page."""
        fdir = (_guard(hfedit.comp_dir, comp) / "compositions" / "frames").resolve()
        mp4 = hfedit.frame_video_path(comp, frame_id)
        if mp4 is None or fdir not in mp4.resolve().parents or not mp4.is_file():
            raise HTTPException(status_code=404, detail="no rendered preview for this frame")
        return FileResponse(str(mp4), media_type="video/mp4")

    # ---- edit (each goes through the author.py gate; a rejected edit reverts, no partial state)

    @app.post("/api/hf/scene/revise")
    async def hf_scene_revise(payload: dict = Body(...)):
        comp, fid, sid = payload.get("comp"), payload.get("frame_id"), payload.get("scene_id")
        if not (comp and fid and sid):
            raise HTTPException(status_code=400, detail="comp, frame_id, scene_id required")
        return await asyncio.to_thread(_guard, hfedit.apply_scene_edit, comp, fid, sid,
                                       payload.get("patch"), payload.get("deletes"))

    @app.post("/api/hf/scene/add")
    async def hf_scene_add(payload: dict = Body(...)):
        comp, fid, scene = payload.get("comp"), payload.get("frame_id"), payload.get("scene")
        if not (comp and fid and isinstance(scene, dict)):
            raise HTTPException(status_code=400, detail="comp, frame_id, scene(object) required")
        return await asyncio.to_thread(_guard, hfedit.add_scene, comp, fid, scene, payload.get("index"))

    @app.post("/api/hf/scene/remove")
    async def hf_scene_remove(payload: dict = Body(...)):
        comp, fid, sid = payload.get("comp"), payload.get("frame_id"), payload.get("scene_id")
        if not (comp and fid and sid):
            raise HTTPException(status_code=400, detail="comp, frame_id, scene_id required")
        return await asyncio.to_thread(_guard, hfedit.remove_scene, comp, fid, sid)

    @app.post("/api/hf/scene/retime")
    async def hf_scene_retime(payload: dict = Body(...)):
        comp, fid, sid = payload.get("comp"), payload.get("frame_id"), payload.get("scene_id")
        if not (comp and fid and sid):
            raise HTTPException(status_code=400, detail="comp, frame_id, scene_id required")
        return await asyncio.to_thread(_guard, hfedit.retime_scene, comp, fid, sid,
                                       payload.get("start"), payload.get("dur"))

    @app.post("/api/hf/transitions/plan")
    async def hf_transitions_plan(payload: dict = Body(...)):
        comp, fid = payload.get("comp"), payload.get("frame_id")
        if not (comp and fid):
            raise HTTPException(status_code=400, detail="comp, frame_id required")
        return await asyncio.to_thread(_guard, hfedit.beat_boundary_planner, comp, fid,
                                       bool(payload.get("apply")))

    @app.post("/api/hf/frame/set-transition")
    async def hf_frame_set_transition(payload: dict = Body(...)):
        """Set/clear a FRAME-level clip transition INTO the next frame (frame.transition_out={kind,dur}) —
        the frame→frame matte/reveal wipe spliced at the concat seam. `kind` falsy clears it."""
        comp, fid = payload.get("comp"), payload.get("frame_id")
        if not (comp and fid):
            raise HTTPException(status_code=400, detail="comp, frame_id required")
        return await asyncio.to_thread(_guard, hfedit.set_frame_transition, comp, fid,
                                       payload.get("kind") or None, float(payload.get("dur") or 1.2))

    # ---- 🎬 Effect from a clip (Tier-1): dispatch the agent to clone a reference clip's effect as GSAP -----

    @app.post("/api/hf/effect/analyze")
    async def hf_effect_analyze(payload: dict = Body(...)):
        """Dispatch the effect agent (tmux) with a GSAP task brief to clone a reference clip's effect onto a
        scene. A Clips-page `clip_id` is resolved → sampled frames the agent can SEE (mirrors the Clips
        analyze flow) → a GSAP brief. The agent writes a proposal JSON; /api/hf/effect/apply lands it (gated).
        Runs as a background job (frame extraction). `clip_ref` (free text) is the fallback when no clip_id."""
        comp, fid, sid = payload.get("comp"), payload.get("frame_id"), payload.get("scene_id")
        clip_id = (payload.get("clip_id") or "").strip()
        clip_ref, comment = payload.get("clip_ref", ""), payload.get("comment", "")
        session = (payload.get("session") or "nolan2").strip()
        num_frames = int(payload.get("num_frames") or 8)
        if not (comp and fid and sid):
            raise HTTPException(status_code=400, detail="comp, frame_id, scene_id required")

        async def worker(job, comp, fid, sid, clip_id, clip_ref, comment, session, num_frames):
            from nolan.hyperframes import effect as eff
            from nolan.webui import operations
            frame_paths, clip_meta = [], None
            # Resolve a Clips-page clip_id → evenly-spaced frames the agent can inspect (same extractor the
            # Clips "Analyze effect" flow uses; cached under projects/_clips/<clip_id>/frames).
            if clip_id:
                if not (ctx.db_path and Path(ctx.db_path).exists()):
                    raise RuntimeError("no library DB configured — cannot resolve clip_id")
                job.message = f"Extracting {num_frames} frames from {clip_id}…"
                job.log(f"resolving clip {clip_id}; extracting {num_frames} frames")
                res = await operations.materialize_clip(job, db_path=Path(ctx.db_path), clip_id=clip_id,
                                                        form="frames", num_frames=num_frames)
                frame_paths = [Path(p).as_posix() for p in (res.get("frames") or [])]
                mc = res.get("matched_clip") or {}
                clip_meta = {"clip_id": clip_id, "video": mc.get("video_path"),
                             "start": mc.get("clip_start"), "end": mc.get("clip_end")}
                if not clip_ref:
                    clip_ref = (f"{clip_id} — {Path(str(mc.get('video_path') or '')).name} "
                                f"[{mc.get('clip_start')}–{mc.get('clip_end')}s]")
                job.log(f"extracted {len(frame_paths)} frames → {res.get('dir')}")
            brief = eff.effect_task_brief(comp, fid, sid, clip_ref=clip_ref, comment=comment,
                                          frame_paths=frame_paths, clip_meta=clip_meta)
            task_dir = hfedit.comp_dir(comp) / "compositions" / "_effects"
            task_dir.mkdir(parents=True, exist_ok=True)
            task_file, proposal = task_dir / f"{sid}_task.md", task_dir / f"{sid}.json"
            task_file.write_text(brief, encoding="utf-8")
            dispatched = False
            try:
                from nolan.webui.operations import _dispatch_to_tmux
                await asyncio.to_thread(_dispatch_to_tmux, session,
                                        f"New HyperFrames GSAP effect task — read {task_file.as_posix()} "
                                        f"and write your proposal to {proposal.as_posix()}")
                dispatched = True
            except Exception as e:
                job.log(f"dispatch to tmux '{session}' failed: {e}")
            job.message = (f"Effect agent {'dispatched to ' + session if dispatched else 'brief written (no live session)'}"
                           f" — {len(frame_paths)} frames")
            return {"dispatched": dispatched, "session": session, "frames": len(frame_paths),
                    "task": task_file.as_posix(), "proposal": proposal.as_posix()}

        job = job_manager.start("hf_effect_analyze", worker, meta={"comp": comp, "scene": sid},
                                comp=comp, fid=fid, sid=sid, clip_id=clip_id, clip_ref=clip_ref,
                                comment=comment, session=session, num_frames=num_frames)
        return {"job_id": job.id}

    @app.post("/api/hf/effect/apply")
    async def hf_effect_apply(payload: dict = Body(...)):
        """Land the agent's effect proposal onto the scene (through the author.py gate). Two proposal
        shapes: `{"block":{"type","data"}}` retargets the scene onto a REUSABLE catalog block (Tier-2,
        e.g. spotlight); `{"html":[...],"tl":[...]}` lands a bespoke `raw` GSAP effect (Tier-1)."""
        comp, fid, sid = payload.get("comp"), payload.get("frame_id"), payload.get("scene_id")
        if not (comp and fid and sid):
            raise HTTPException(status_code=400, detail="comp, frame_id, scene_id required")
        prop = _guard(hfedit.comp_dir, comp) / "compositions" / "_effects" / f"{sid}.json"
        if not prop.exists():
            raise HTTPException(status_code=404, detail="no effect proposal for this scene yet")
        try:
            data = json.loads(prop.read_text(encoding="utf-8"))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"unreadable proposal: {e}")
        from nolan.hyperframes import effect as eff
        block = data.get("block")
        if isinstance(block, dict) and block.get("type"):    # Tier-2: reusable block
            return await asyncio.to_thread(_guard, eff.apply_block, comp, fid, sid,
                                           block.get("type"), block.get("data") or {})
        return await asyncio.to_thread(_guard, eff.apply_effect, comp, fid, sid,   # Tier-1: raw
                                       data.get("html"), data.get("tl"))

    @app.get("/api/hf/effect/proposal")
    async def hf_effect_proposal(comp: str = Query(...), scene_id: str = Query(...)):
        """The agent's written proposal for a scene, so the UI can PREVIEW it before ✓ Apply
        (block type+data, or raw html/tl + rationale). 404 until the agent has written one."""
        prop = _guard(hfedit.comp_dir, comp) / "compositions" / "_effects" / f"{scene_id}.json"
        if not prop.exists():
            raise HTTPException(status_code=404, detail="no proposal yet")
        try:
            data = json.loads(prop.read_text(encoding="utf-8"))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"unreadable proposal: {e}")
        block = data.get("block") if isinstance(data.get("block"), dict) else None
        return {"kind": "block" if block else "raw",
                "block_type": (block or {}).get("type"),
                "data": (block or {}).get("data"),
                "html": data.get("html"), "tl": data.get("tl"),
                "dedup": data.get("dedup"), "rationale": data.get("rationale")}

    # ---- bespoke mode: hand SELECTED scene(s) to fleet agents for fully-custom `raw` authoring ----

    @app.post("/api/hf/bespoke/dispatch")
    async def hf_bespoke_dispatch(payload: dict = Body(...)):
        """Fan out ONE agent per selected scene (round-robin across fleet sessions), each with a rich
        context brief. Each agent authors a bespoke `raw` scene and submits it via propose_scene_edit —
        the proposals then appear in the SAME review panel as batch edits (accept → gate → render)."""
        comp = payload.get("comp")
        scene_ids = payload.get("scene_ids") or []
        if not (comp and scene_ids):
            raise HTTPException(status_code=400, detail="comp and scene_ids required")
        from nolan.hyperframes import bespoke as bsp
        return await asyncio.to_thread(_guard, bsp.dispatch_bespoke, comp, scene_ids,
                                       payload.get("direction", ""), payload.get("sessions"))

    @app.get("/api/hf/bespoke/brief")
    async def hf_bespoke_brief(comp: str = Query(...), frame_id: str = Query(...),
                               scene_id: str = Query(...), direction: str = Query("")):
        """Preview the exact context brief a bespoke agent would receive for a scene (transparency —
        so you can see WHAT the agent is told before dispatching)."""
        from nolan.hyperframes import bespoke as bsp
        return {"brief": _guard(bsp.bespoke_task_brief, comp, frame_id, scene_id, direction)}

    # ---- render one or more frame clips (background job)

    @app.post("/api/hf/frame/rerender")
    async def hf_frame_rerender(payload: dict = Body(...)):
        comp = payload.get("comp")
        frame_ids = payload.get("frame_ids") or []
        if not (comp and frame_ids):
            raise HTTPException(status_code=400, detail="comp and frame_ids required")

        async def worker(job, comp, frame_ids):
            # "This frame" renders through the SAME path as assemble (render_one → windows the assembled index):
            # it renders video grounds/comparison correctly, whereas the old render_frame preview left grounds
            # black AND tripped the coverage gate. DRAFT quality — this is a fast preview (a 93s frame at "high"
            # CRF15/slow takes minutes); the deliverable render (⚙ Render → All changed / Whole project) is "high".
            from nolan.hyperframes.incremental import render_one
            results = []
            for i, fid in enumerate(frame_ids):
                job.message = f"Rendering frame {i + 1}/{len(frame_ids)}: {fid}…"
                job.log(f"[{i + 1}/{len(frame_ids)}] rendering {fid} (draft preview)…")
                clip = await asyncio.to_thread(render_one, comp, fid, "draft", True)
                ok = clip is not None and Path(clip).exists()
                results.append({"frame_id": fid, "ok": ok, "mp4": str(clip) if clip else None})
                job.log(f"[{i + 1}/{len(frame_ids)}] {fid}: " + (f"ok → {clip}" if ok else "FAILED (see server log)"))
            done = sum(1 for r in results if r["ok"])
            job.message = f"Rendered {done}/{len(frame_ids)} frame(s)"
            job.log(f"done: {done}/{len(frame_ids)} rendered")
            return {"results": results}

        job = job_manager.start("hf_render", worker,
                                meta={"comp": comp, "frames": frame_ids},
                                comp=comp, frame_ids=frame_ids)
        return {"job_id": job.id, "frames": frame_ids}

    # ---- assemble the full video (INCREMENTAL: window the assembled index per-frame + concat, cached)

    @app.post("/api/hf/assemble")
    async def hf_assemble(payload: dict = Body(...)):
        """Fast full-video assemble: re-render only changed frames (content-hash cache) + concat →
        renders/<comp>.mp4. `force` re-renders EVERY frame (whole-project rebuild). Requires a prior
        assemble-index (index.html); run hf-finish once first."""
        comp = (payload.get("comp") or "").strip()
        if not comp:
            raise HTTPException(status_code=400, detail="comp required")
        force = bool(payload.get("force"))                 # whole project — re-render every frame
        scope_only = payload.get("only")                   # explicit frame ids (a single-frame / subset render)

        async def worker(job, comp, force, scope_only):
            from nolan.hyperframes.incremental import render_incremental
            if force:
                only = [f["id"] if isinstance(f, dict) else f for f in _guard(hfedit.list_frames, comp)]
                job.message = f"Rebuilding all {len(only)} frame(s)…"
            elif scope_only:
                only = list(scope_only)
                job.message = f"Rendering {len(only)} frame(s): {', '.join(only)}…"
            else:
                only = None
                job.message = "Assembling (incremental — only changed frames re-render)…"
            r = await asyncio.to_thread(
                lambda: render_incremental(comp, only, True, "high", False, log=job.log))
            job.message = (f"Assembled: {r.get('rendered', 0)} rendered, {r.get('reused', 0)} reused → "
                           f"{r.get('mp4')}") if r.get("ok") else "Assemble failed (is index.html built? run hf-finish once)."
            return r

        job = job_manager.start("hf_assemble", worker, meta={"comp": comp, "force": force, "only": scope_only},
                                comp=comp, force=force, scope_only=scope_only)
        return {"job_id": job.id, "comp": comp}

    @app.get("/api/hf/assembled-video")
    async def hf_assembled_video(comp: str = Query(...)):
        """Serve the assembled full video — the newest of `renders/<comp>.mp4` or `renders/video.mp4`
        (finish and the incremental render have historically used different names)."""
        cdir = _guard(hfedit.comp_dir, comp).resolve()
        cands = [p for p in ((cdir / "renders" / f"{comp}.mp4"), (cdir / "renders" / "video.mp4")) if p.is_file()]
        mp4 = max(cands, key=lambda p: p.stat().st_mtime) if cands else None
        if mp4 is None or cdir not in mp4.resolve().parents:
            raise HTTPException(status_code=404, detail="no assembled video yet — click Assemble")
        return FileResponse(str(mp4), media_type="video/mp4")

    # ---- Phase 2: note edit (comment → LLM ops → gate)

    @app.post("/api/hf/frame/revise-note")
    async def hf_revise_note(payload: dict = Body(...)):
        comp, fid, note = payload.get("comp"), payload.get("frame_id"), payload.get("note")
        if not (comp and fid and note):
            raise HTTPException(status_code=400, detail="comp, frame_id, note required")
        from nolan.config import load_config
        from nolan.llm import create_text_llm
        client = create_text_llm(load_config())
        try:
            return await hfedit.revise_frame_note(comp, fid, note, scene_id=payload.get("scene_id"),
                                                  assets=payload.get("assets"), client=client,
                                                  mentions=payload.get("mentions"))
        except (FileNotFoundError, KeyError) as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ---- per-frame comments / batch changeset (#4 — STAGED, not applied; feeds the #5 batch dispatch)

    @app.post("/api/hf/frame/comment")
    async def hf_stage_comment(payload: dict = Body(...)):
        comp, fid = payload.get("comp"), payload.get("frame_id")
        text = payload.get("text") or payload.get("note")
        if not (comp and fid and text):
            raise HTTPException(status_code=400, detail="comp, frame_id, text required")
        return await asyncio.to_thread(_guard, hfedit.stage_comment, comp, fid, text,
                                       payload.get("scene_id"), payload.get("mentions"))

    @app.get("/api/hf/changeset")
    async def hf_changeset(comp: str = Query(...)):
        """All OPEN per-frame comments across the comp — the pending batch-edit changeset."""
        return {"comp": comp, "comments": _guard(hfedit.list_changeset, comp)}

    @app.post("/api/hf/comment/resolve")
    async def hf_resolve_comment(payload: dict = Body(...)):
        comp, fid = payload.get("comp"), payload.get("frame_id")
        if not (comp and fid):
            raise HTTPException(status_code=400, detail="comp, frame_id required")
        # status defaults to 'applied'; the batch preview passes 'dropped' to UN-stage an edit before dispatch
        return await asyncio.to_thread(_guard, hfedit.resolve_comment, comp, fid,
                                       payload.get("comment_id"), payload.get("status") or "applied",
                                       payload.get("reason"))

    # ---- activity / feedback feed (every single + batch/agent edit's process, outcome, error)

    @app.get("/api/hf/activity")
    async def hf_activity(comp: str = Query(...)):
        """The per-comp activity feed + the open changeset — the /hyperframes 'Activity & feedback' panel."""
        return {"comp": comp, "activity": _guard(hfedit.list_activity, comp, 80),
                "changeset": _guard(hfedit.list_changeset, comp)}

    # ---- batch-agent mode (#5): compile the changeset into ONE brief, dispatch to a fleet agent

    @app.get("/api/hf/batch/brief")
    async def hf_batch_brief(comp: str = Query(...), frame_id: Optional[str] = Query(None)):
        """Preview the compiled batch-edit brief. `frame_id` scopes to one frame (the frame-level batch)."""
        from nolan.hyperframes.batch import compile_batch_brief
        brief, changeset = _guard(compile_batch_brief, comp, frame_id)
        return {"comp": comp, "brief": brief, "comments": len(changeset)}

    @app.post("/api/hf/batch/dispatch")
    async def hf_batch_dispatch(payload: dict = Body(...)):
        """Compile the changeset into a kickoff brief (with provenance) and dispatch it to a tmux fleet agent.
        `frame_id` (optional) scopes the dispatch to one frame; omit for the whole project."""
        comp = (payload.get("comp") or "").strip()
        if not comp:
            raise HTTPException(status_code=400, detail="comp required")
        from nolan.hyperframes.batch import dispatch_batch
        return await asyncio.to_thread(_guard, dispatch_batch, comp, payload.get("session"),
                                       None, None, payload.get("frame_id"))

    # ---- proposals (agent edit → human accept; the agent-contract review surface)

    @app.get("/api/hf/proposals")
    async def hf_proposals(comp: str = Query(...), status: Optional[str] = Query(None)):
        return {"comp": comp, "proposals": _guard(hfedit.list_proposals, comp, status)}

    @app.post("/api/hf/proposal/accept")
    async def hf_proposal_accept(payload: dict = Body(...)):
        comp, pid = payload.get("comp"), payload.get("proposal_id")
        if not (comp and pid):
            raise HTTPException(status_code=400, detail="comp, proposal_id required")
        return await asyncio.to_thread(_guard, hfedit.accept_proposal, comp, pid)

    @app.post("/api/hf/proposal/reject")
    async def hf_proposal_reject(payload: dict = Body(...)):
        comp, pid = payload.get("comp"), payload.get("proposal_id")
        if not (comp and pid):
            raise HTTPException(status_code=400, detail="comp, proposal_id required")
        return _guard(hfedit.reject_proposal, comp, pid, payload.get("reason", ""))

    @app.get("/api/hf/proposal/preview")
    async def hf_proposal_preview(comp: str = Query(...), proposal_id: str = Query(...),
                                  at: Optional[float] = Query(None)):
        """Render (lazily) a still preview of a proposal's result — so the human eyeballs the end result
        before accepting. Applies the ops to a COPY; canonical is untouched. Returns the PNG."""
        res = await asyncio.to_thread(_guard, hfedit.proposal_preview, comp, proposal_id, at)
        if not res.get("ok") or not res.get("png") or not Path(res["png"]).exists():
            raise HTTPException(status_code=422, detail=(res.get("output") or "preview render failed")[-300:])
        return FileResponse(res["png"], media_type="image/png")

    # ---- asset picker target (land an asset in <comp>/assets/, referenced by scene data)

    @app.get("/api/hf/assets")
    async def hf_assets(comp: str = Query(...)):
        return {"comp": comp, "assets": _guard(hfedit.list_assets, comp)}

    @app.get("/api/hf/asset-meta")
    async def hf_asset_meta(comp: str = Query(...)):
        # pool provenance keyed by file basename → the edit UI shows a generated scene's enhanced prompt
        return {"comp": comp, "meta": _guard(hfedit.asset_pool_meta, comp)}

    @app.get("/api/hf/asset-file")
    async def hf_asset_file(comp: str = Query(...), path: str = Query(...)):
        """Serve a comp asset (full file, Range-enabled) — for the crop modal + a field's real media.
        The GRIDS use /api/hf/asset-thumb instead (a tiny cached poster), so a 200-video pool doesn't
        mount 200 <video> elements."""
        root = _guard(hfedit.comp_dir, comp).resolve()
        target = (root / path).resolve()
        assets_root = (root / "assets").resolve()
        if assets_root not in target.parents or not target.is_file():
            raise HTTPException(status_code=404, detail="asset not found")
        return FileResponse(str(target))

    @app.get("/api/hf/asset-thumb")
    async def hf_asset_thumb(comp: str = Query(...), path: str = Query(...)):
        """A small CACHED JPEG poster for an asset (video frame @0.5s, or a downscaled image) — one tiny
        lazy-loaded <img> per grid cell instead of a full <video preload=metadata>. Keyed by path+mtime so
        an in-place edit (crop/cutout) invalidates it. This is THE fix for the slow asset pool / picker."""
        import hashlib
        import imageio_ffmpeg
        root = _guard(hfedit.comp_dir, comp).resolve()
        target = (root / path).resolve()
        assets_root = (root / "assets").resolve()
        if assets_root not in target.parents or not target.is_file():
            raise HTTPException(status_code=404, detail="asset not found")
        key = hashlib.md5(f"{target}|{int(target.stat().st_mtime)}".encode()).hexdigest()
        out = root / "compositions" / "_preview" / "_thumbs" / f"{key}.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        if not out.exists():
            ff = imageio_ffmpeg.get_ffmpeg_exe()
            is_video = target.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv", ".m4v")
            cmd = ([ff, "-y"] + (["-ss", "0.5"] if is_video else [])
                   + ["-i", str(target), "-frames:v", "1", "-vf", "scale=240:-1:force_original_aspect_ratio=decrease",
                      "-loglevel", "error", str(out)])
            await asyncio.to_thread(subprocess.run, cmd, timeout=20, capture_output=True)
        if out.exists():
            return FileResponse(str(out), media_type="image/jpeg")
        raise HTTPException(status_code=404, detail="could not make thumbnail")

    @app.get("/api/hf/asset-frame")
    async def hf_asset_frame(comp: str = Query(...), path: str = Query(...), t: float = Query(0.0)):
        """A small CACHED JPEG of a VIDEO frame at time `t` (seconds). Powers the cleanup review's
        ambiguous-trim preview — the two shots straddling a candidate cut, so the reviewer can SEE whether a
        head/tail is a stray before trimming it. Keyed by path+mtime+t (an in-place edit invalidates it)."""
        import hashlib
        import imageio_ffmpeg
        root = _guard(hfedit.comp_dir, comp).resolve()
        target = (root / path).resolve()
        assets_root = (root / "assets").resolve()
        if assets_root not in target.parents or not target.is_file():
            raise HTTPException(status_code=404, detail="asset not found")
        ts = max(0.0, float(t))
        key = hashlib.md5(f"{target}|{int(target.stat().st_mtime)}|{ts:.3f}".encode()).hexdigest()
        out = root / "compositions" / "_preview" / "_thumbs" / f"f{key}.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        if not out.exists():
            ff = imageio_ffmpeg.get_ffmpeg_exe()
            cmd = [ff, "-y", "-ss", f"{ts:.3f}", "-i", str(target), "-frames:v", "1",
                   "-vf", "scale=240:-1:force_original_aspect_ratio=decrease", "-loglevel", "error", str(out)]
            await asyncio.to_thread(subprocess.run, cmd, timeout=20, capture_output=True)
        if out.exists():
            return FileResponse(str(out), media_type="image/jpeg")
        raise HTTPException(status_code=404, detail="could not grab frame")

    @app.post("/api/hf/asset/resolve")
    async def hf_asset_resolve(payload: dict = Body(...)):
        comp, src = payload.get("comp"), payload.get("src")
        if not (comp and src):
            raise HTTPException(status_code=400, detail="comp, src required")
        return _guard(hfedit.resolve_asset, comp, src)

    @app.post("/api/hf/asset/upload")
    async def hf_asset_upload(comp: str = Form(...), file: UploadFile = File(...)):
        data = await file.read()
        return await asyncio.to_thread(_guard, hfedit.save_upload, comp, file.filename, data)

    @app.post("/api/hf/scene/add-asset")
    async def hf_scene_add_asset(comp: str = Form(...), frame_id: str = Form(...), scene_id: str = Form(...),
                                 file: UploadFile = File(...)):
        """Drag-drop an asset onto a scene (#5): validate → land in assets/ + pool (scene provenance) →
        add to the scene's shortlist named `{scene_id}_edit_{vid|pic}{N}`. Returns the shortlist entry."""
        data = await file.read()
        try:
            return await asyncio.to_thread(_guard, hfedit.add_scene_asset, comp, frame_id, scene_id,
                                           file.filename, data)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/hf/scene/remove-asset")
    async def hf_scene_remove_asset(payload: dict = Body(...)):
        comp, frame_id, scene_id, name = (payload.get(k) for k in ("comp", "frame_id", "scene_id", "name"))
        if not (comp and frame_id and scene_id and name):
            raise HTTPException(status_code=400, detail="comp, frame_id, scene_id, name required")
        return _guard(hfedit.remove_scene_asset, comp, frame_id, scene_id, name)

    @app.post("/api/hf/pool/add")
    async def hf_pool_add(comp: str = Form(...), file: UploadFile = File(...)):
        """Q1: drop an asset STRAIGHT into the pool — neutral, plain name, no scene/background. Referenceable anywhere."""
        data = await file.read()
        try:
            return await asyncio.to_thread(_guard, hfedit.add_pool_asset, comp, file.filename, data)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/hf/quickedit-ops")
    async def hf_quickedit_ops():
        return {"ops": hfedit.quick_edit_ops()}

    @app.post("/api/hf/asset-quickedit")
    async def hf_asset_quickedit(payload: dict = Body(...)):
        """Fast ffmpeg quick-edit (crop, …) on an asset. mode='inplace' (reversible backup) | 'new' (new pool asset)."""
        comp, path, op = payload.get("comp"), payload.get("path"), payload.get("op")
        if not (comp and path and op):
            raise HTTPException(status_code=400, detail="comp, path, op required")
        try:
            return await asyncio.to_thread(_guard, hfedit.quickedit_asset, comp, path, op,
                                           payload.get("params") or {}, payload.get("mode") or "new",
                                           payload.get("name"))
        except (ValueError, FileNotFoundError) as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/hf/asset/cleanup-analyze")
    async def hf_asset_cleanup_analyze(payload: dict = Body(...)):
        """Detect a corner logo / burned-in captions / (video) stray head-tail frames → a reviewable PLAN.
        Writes nothing. `confirm` (default true) runs the OpenRouter vision filter over the CV proposals."""
        comp, path = payload.get("comp"), payload.get("path")
        if not (comp and path):
            raise HTTPException(status_code=400, detail="comp, path required")
        return await asyncio.to_thread(_guard, hfedit.cleanup_analyze, comp, path,
                                       payload.get("confirm", True))

    @app.post("/api/hf/asset/cleanup-analyze-batch")
    async def hf_asset_cleanup_analyze_batch(payload: dict = Body(...)):
        """Analyze MANY pool assets → reviewable plans for the batch-cleanup UI (one shared vision provider)."""
        comp, paths = payload.get("comp"), payload.get("paths")
        if not (comp and isinstance(paths, list) and paths):
            raise HTTPException(status_code=400, detail="comp and a non-empty paths[] required")
        return await asyncio.to_thread(_guard, hfedit.cleanup_analyze_batch, comp, paths,
                                       payload.get("confirm", True))

    @app.post("/api/hf/asset/cleanup")
    async def hf_asset_cleanup(payload: dict = Body(...)):
        """Auto-clean an asset → a NEW pool asset (logo/caption crop + head/tail trim in one ffmpeg pass).
        Pass a reviewed `plan` to skip re-analysis. A no-op writes nothing."""
        comp, path = payload.get("comp"), payload.get("path")
        if not (comp and path):
            raise HTTPException(status_code=400, detail="comp, path required")
        return await asyncio.to_thread(_guard, hfedit.cleanup_asset, comp, path,
                                       payload.get("confirm", True), payload.get("plan"))

    @app.get("/api/hf/overlay-plate")
    async def hf_overlay_plate(tag: str = Query(...)):
        """Serve an effects-umbrella overlay PLATE clip (fire/rain/…) so the fx-modal preview can blend it live."""
        import os
        from nolan.effects.library import resolve_plate
        p = resolve_plate(tag)
        if not p or not os.path.exists(p):
            raise HTTPException(status_code=404, detail=f"no plate stocked for {tag!r}")
        return FileResponse(p, media_type="video/mp4")

    @app.post("/api/hf/asset-treat-preview")
    async def hf_asset_treat_preview(payload: dict = Body(...)):
        """Fast low-res REAL bake of the selected effects (NO pool entry) → the fx-modal 'Preview result'."""
        comp, path, effects = payload.get("comp"), payload.get("path"), payload.get("effects") or []
        if not (comp and path and effects):
            raise HTTPException(status_code=400, detail="comp, path, effects required")
        try:
            out = await asyncio.to_thread(_guard, hfedit.treat_preview, comp, path, effects)
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        low = str(out).lower()
        mt = ("video/mp4" if low.endswith((".mp4", ".mov", ".webm"))
              else "image/png" if low.endswith(".png") else "image/jpeg")
        return FileResponse(str(out), media_type=mt)

    @app.post("/api/hf/asset-revert")
    async def hf_asset_revert(payload: dict = Body(...)):
        comp, path = payload.get("comp"), payload.get("path")
        if not (comp and path):
            raise HTTPException(status_code=400, detail="comp, path required")
        try:
            return _guard(hfedit.revert_asset, comp, path)
        except FileNotFoundError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/hf/scene/fit-ground")
    async def hf_scene_fit_ground(payload: dict = Body(...)):
        """#5: retime a scene's video ground so it spans exactly the scene's duration (no-op if it already does)."""
        comp, fid, sid = payload.get("comp"), payload.get("frame_id"), payload.get("scene_id")
        if not (comp and fid and sid):
            raise HTTPException(status_code=400, detail="comp, frame_id, scene_id required")
        return await asyncio.to_thread(_guard, hfedit.fit_ground_to_scene, comp, fid, sid)

    @app.post("/api/hf/asset-removebg")
    async def hf_asset_removebg(payload: dict = Body(...)):
        """#3: remove-background (rembg cutout) — slower, so it runs as a BACKGROUND JOB. Returns a job id
        the UI polls via /api/jobs/{id}; the result is a new RGBA pool asset (the original is kept)."""
        comp, path = payload.get("comp"), payload.get("path")
        if not (comp and path):
            raise HTTPException(status_code=400, detail="comp, path required")
        from nolan.webui.jobs import get_job_manager

        async def _worker(job, comp=comp, path=path):
            job.set_progress(0.1, "removing background (rembg)…")
            res = await asyncio.to_thread(hfedit.quickedit_asset, comp, path, "remove_bg",
                                          {"model": payload.get("model") or "birefnet"}, "new")
            job.message = f"cutout → {res['name']}"
            return res

        job = get_job_manager().start("remove-bg", _worker, meta={"comp": comp, "path": path})
        return {"job_id": job.id}

    # ---- new essay (scaffold script/assets -> dispatch the hf-author agent)

    @app.get("/api/hf/agents")
    async def hf_agents():
        """Available tmux Claude-agent sessions (nolan1-6) to dispatch authoring to."""
        from nolan.webui import operations
        try:
            return {"sessions": operations.list_tmux_sessions()}
        except Exception:
            return {"sessions": []}

    async def _pool_job(job, comp, needs, script, per, gen=True, cull=True):
        """ACQUIRE->SCORE+CAPTION->INVENTORY via the NOLAN asset bridge (pool.py). needs given, else derived from script/SOURCE.md."""
        nds = needs
        if not nds:
            from nolan.hyperframes.edit import _project_script, _project_dir
            src = script or _project_script(_project_dir(comp))
            if not src:
                job.message = "No needs and no script to derive from."
                return {"ok": False, "detail": "provide `needs`, or a script/SOURCE.md to derive them"}
            job.message = "Planning asset needs from the script…"
            from nolan.config import load_config
            from nolan.llm import create_text_llm
            nds = await hfedit.derive_asset_needs(src, create_text_llm(load_config()))
        if not nds:
            job.message = "No asset needs derived."
            return {"ok": False, "detail": "no asset needs"}
        job.message = f"Acquiring {len(nds)} asset need(s) — multi-source + VLM cull + captions (a few minutes)…"
        res = await asyncio.to_thread(hfedit.run_pool, comp, nds, per, gen, cull)
        job.message = f"Asset pool: {res.get('count', 0)} asset(s) -> {comp}/capture/"
        return res

    async def _assets_job(job, comp, script, key_assets, acquire_pool, per, gen, cull):
        """Launch-time acquisition in order: key-assets HEROES (global/precision) → b-roll POOL (recall) →
        prepend the hero block onto the author's menu. Heroes-first; the agent decides where/whether to use
        them. 'curated' only builds the pull-list (human collects on /keyassets); 'auto' collects now."""
        ka = {}
        if key_assets and key_assets != "off":
            job.message = f"Key-assets ({key_assets}): building the hero pull-list…"
            ka = await asyncio.to_thread(hfedit.run_key_assets, comp, script, key_assets, False)  # stage after pool
        pool = {}
        if acquire_pool:
            pool = await _pool_job(job, comp, None, script, per, gen, cull)   # rewrites base asset-descriptions.md
        if key_assets == "auto" and ka.get("collected"):
            job.message = "Staging heroes into the author's menu…"
            from nolan.keyassets.inventory import write_hero_section
            await asyncio.to_thread(write_hero_section, hfedit._project_dir(comp))
        job.message = f"Assets ready — heroes: {ka.get('collected', 0)}, b-roll: {pool.get('count', 0)}"
        return {"ok": True, "key_assets": ka, "pool": pool}

    @app.post("/api/hf/pool")
    async def hf_pool(payload: dict = Body(...)):
        """Build an asset pool for a comp (existing or just-scaffolded) via the NOLAN bridge — background job."""
        comp = (payload.get("comp") or "").strip()
        if not comp:
            raise HTTPException(status_code=400, detail="comp required")
        job = job_manager.start("hf_pool", _pool_job, meta={"comp": comp}, comp=comp,
                                needs=payload.get("needs"), script=payload.get("script"),
                                per=int(payload.get("per", 8)), gen=bool(payload.get("gen", True)),
                                cull=bool(payload.get("cull", True)))
        return {"job_id": job.id, "comp": comp}

    @app.post("/api/hf/voiceover")
    async def hf_voiceover(payload: dict = Body(...)):
        """Bridge a NOLAN voiceover into a comp → audio_meta.json + assets/voice/*.wav (the cloned voice
        drives frame durations + mounts as the root voice track). vo_source = projects/<name> or a path."""
        comp = (payload.get("comp") or "").strip()
        vo = (payload.get("vo_source") or payload.get("source") or "").strip()
        if not (comp and vo):
            raise HTTPException(status_code=400, detail="comp and vo_source required")
        return await asyncio.to_thread(_guard, hfedit.attach_voiceover, comp, vo)

    @app.get("/api/hf/themes")
    async def hf_themes():
        """The selectable NOLAN themes (themes/ registry) for the new-essay picker."""
        return {"themes": hfedit.list_themes()}

    @app.post("/api/hf/theme-suggest")
    async def hf_theme_suggest(payload: dict = Body(...)):
        """Deterministic, explainable theme ranking for a script (select_theme.py) — seeds the picker."""
        return {"ranked": hfedit.suggest_theme(payload.get("script") or "", int(payload.get("top", 3)))}

    @app.post("/api/hf/new")
    async def hf_new(payload: dict = Body(...)):
        script = (payload.get("script") or "").strip()
        name = (payload.get("name") or "").strip()
        session = (payload.get("session") or "").strip()
        if not (script and name):
            raise HTTPException(status_code=400, detail="name and script are required")
        key_assets = (payload.get("key_assets") or "curated").strip()   # curated | auto | off
        res = _guard(hfedit.new_essay, name, script, payload.get("style"),
                     bool(payload.get("acquire_pool", True)), payload.get("voiceover") or None,
                     payload.get("asset_density") or "balanced", payload.get("theme") or None,
                     payload.get("motion") or None, gen_style=payload.get("gen_style") or None,
                     key_assets=key_assets)
        if res.get("acquire_pool") or key_assets != "off":   # heroes (global) then b-roll pool, before authoring
            ajob = job_manager.start("hf_assets", _assets_job, meta={"comp": res["comp"]},
                                     comp=res["comp"], script=script, key_assets=key_assets,
                                     acquire_pool=bool(res.get("acquire_pool")),
                                     per=int(payload.get("per", 8)), gen=bool(payload.get("gen", True)),
                                     cull=bool(payload.get("cull", True)))
            res["assets_job"] = ajob.id
        if session:                        # dispatch to a live agent; else caller runs the prompt manually
            from nolan.webui import operations
            try:
                await asyncio.to_thread(operations._dispatch_to_tmux, session, res["prompt"])
                res["dispatched"] = session
            except Exception as e:
                res["dispatch_error"] = str(e)
        return res
