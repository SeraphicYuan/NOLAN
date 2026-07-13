"""HyperFrames scene edit-mode routes — the composer-native `/hyperframes` page + its edit APIs.

Thin wrappers over ``nolan.hyperframes`` (the editing bridge): discover compositions, list the
frame->scene tree, patch/add/remove/retime a scene through the author.py gate, plan within-frame
transitions, snapshot-preview a frame, and background-render a full frame clip. Edit per scene,
re-render per frame (see kb/frame-vs-scene.md, kb/edit-mode-plan.md).
"""
import asyncio
from pathlib import Path

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

    @app.get("/api/hf/frame-spec")
    async def hf_frame_spec(comp: str = Query(...), frame_id: str = Query(...)):
        spec, info = _guard(hfedit.load_frame_spec, comp, frame_id)
        return {"comp": comp, "frame": spec["frames"][info["i"]]}

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
        """Serve a frame's rendered preview clip (from render_frame) — playable in the edit page."""
        fdir = (_guard(hfedit.comp_dir, comp) / "compositions" / "frames").resolve()
        mp4 = (fdir / f"{frame_id}.preview.mp4").resolve()
        if fdir not in mp4.parents or not mp4.is_file():
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

    # ---- render one or more frame clips (background job)

    @app.post("/api/hf/frame/rerender")
    async def hf_frame_rerender(payload: dict = Body(...)):
        comp = payload.get("comp")
        frame_ids = payload.get("frame_ids") or []
        if not (comp and frame_ids):
            raise HTTPException(status_code=400, detail="comp and frame_ids required")

        async def worker(job, comp, frame_ids):
            results = []
            for i, fid in enumerate(frame_ids):
                job.message = f"Rendering frame {i + 1}/{len(frame_ids)}: {fid}…"
                res = await asyncio.to_thread(hfedit.render_frame, comp, fid)
                results.append({"frame_id": fid, "ok": res.get("ok"), "mp4": res.get("mp4")})
            done = sum(1 for r in results if r["ok"])
            job.message = f"Rendered {done}/{len(frame_ids)} frame(s)"
            return {"results": results}

        job = job_manager.start("hf_render", worker,
                                meta={"comp": comp, "frames": frame_ids},
                                comp=comp, frame_ids=frame_ids)
        return {"job_id": job.id, "frames": frame_ids}

    # ---- assemble the full video (INCREMENTAL: window the assembled index per-frame + concat, cached)

    @app.post("/api/hf/assemble")
    async def hf_assemble(payload: dict = Body(...)):
        """Fast full-video assemble: re-render only changed frames (content-hash cache) + concat →
        renders/<comp>.mp4. Requires a prior assemble-index (index.html); run hf-finish once first."""
        comp = (payload.get("comp") or "").strip()
        if not comp:
            raise HTTPException(status_code=400, detail="comp required")

        async def worker(job, comp):
            job.message = "Assembling (incremental — only changed frames re-render)…"
            from nolan.hyperframes.incremental import render_incremental
            r = await asyncio.to_thread(render_incremental, comp, captions=False)
            job.message = (f"Assembled: {r.get('rendered', 0)} rendered, {r.get('reused', 0)} reused → "
                           f"{r.get('mp4')}") if r.get("ok") else "Assemble failed (is index.html built? run hf-finish once)."
            return r

        job = job_manager.start("hf_assemble", worker, meta={"comp": comp}, comp=comp)
        return {"job_id": job.id, "comp": comp}

    @app.get("/api/hf/assembled-video")
    async def hf_assembled_video(comp: str = Query(...)):
        """Serve the incrementally-assembled full video (renders/<comp>.mp4)."""
        cdir = _guard(hfedit.comp_dir, comp).resolve()
        mp4 = (cdir / "renders" / f"{comp}.mp4").resolve()
        if cdir not in mp4.parents or not mp4.is_file():
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
                                                  assets=payload.get("assets"), client=client)
        except (FileNotFoundError, KeyError) as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ---- per-frame comments / batch changeset (#4 — STAGED, not applied; feeds the #5 batch dispatch)

    @app.post("/api/hf/frame/comment")
    async def hf_stage_comment(payload: dict = Body(...)):
        comp, fid = payload.get("comp"), payload.get("frame_id")
        text = payload.get("text") or payload.get("note")
        if not (comp and fid and text):
            raise HTTPException(status_code=400, detail="comp, frame_id, text required")
        return await asyncio.to_thread(_guard, hfedit.stage_comment, comp, fid, text, payload.get("scene_id"))

    @app.get("/api/hf/changeset")
    async def hf_changeset(comp: str = Query(...)):
        """All OPEN per-frame comments across the comp — the pending batch-edit changeset."""
        return {"comp": comp, "comments": _guard(hfedit.list_changeset, comp)}

    @app.post("/api/hf/comment/resolve")
    async def hf_resolve_comment(payload: dict = Body(...)):
        comp, fid = payload.get("comp"), payload.get("frame_id")
        if not (comp and fid):
            raise HTTPException(status_code=400, detail="comp, frame_id required")
        return await asyncio.to_thread(_guard, hfedit.resolve_comment, comp, fid, payload.get("comment_id"))

    # ---- batch-agent mode (#5): compile the changeset into ONE brief, dispatch to a fleet agent

    @app.get("/api/hf/batch/brief")
    async def hf_batch_brief(comp: str = Query(...)):
        """Preview the compiled batch-edit brief (project + per-frame context + the staged comments)."""
        from nolan.hyperframes.batch import compile_batch_brief
        brief, changeset = _guard(compile_batch_brief, comp)
        return {"comp": comp, "brief": brief, "comments": len(changeset)}

    @app.post("/api/hf/batch/dispatch")
    async def hf_batch_dispatch(payload: dict = Body(...)):
        """Compile the changeset into a kickoff brief (with provenance) and dispatch it to a tmux fleet agent."""
        comp = (payload.get("comp") or "").strip()
        if not comp:
            raise HTTPException(status_code=400, detail="comp required")
        from nolan.hyperframes.batch import dispatch_batch
        return await asyncio.to_thread(_guard, dispatch_batch, comp, payload.get("session"))

    # ---- asset picker target (land an asset in <comp>/assets/, referenced by scene data)

    @app.get("/api/hf/assets")
    async def hf_assets(comp: str = Query(...)):
        return {"comp": comp, "assets": _guard(hfedit.list_assets, comp)}

    @app.get("/api/hf/asset-file")
    async def hf_asset_file(comp: str = Query(...), path: str = Query(...)):
        """Serve a comp asset for the picker's thumbnails — confined to <comp>/assets/."""
        root = _guard(hfedit.comp_dir, comp).resolve()
        target = (root / path).resolve()
        assets_root = (root / "assets").resolve()
        if assets_root not in target.parents or not target.is_file():
            raise HTTPException(status_code=404, detail="asset not found")
        return FileResponse(str(target))

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

    # ---- new essay (scaffold script/assets -> dispatch the faceless-explainer agent)

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
        res = _guard(hfedit.new_essay, name, script, payload.get("style"),
                     bool(payload.get("acquire_pool", True)), payload.get("voiceover") or None,
                     payload.get("asset_density") or "balanced", payload.get("theme") or None,
                     payload.get("motion") or None)
        if res.get("acquire_pool"):        # acquire the asset pool first (from the script), before authoring
            pjob = job_manager.start("hf_pool", _pool_job, meta={"comp": res["comp"]},
                                     comp=res["comp"], needs=None, script=script,
                                     per=int(payload.get("per", 8)), gen=bool(payload.get("gen", True)),
                                     cull=bool(payload.get("cull", True)))
            res["pool_job"] = pjob.id
        if session:                        # dispatch to a live agent; else caller runs the prompt manually
            from nolan.webui import operations
            try:
                await asyncio.to_thread(operations._dispatch_to_tmux, session, res["prompt"])
                res["dispatched"] = session
            except Exception as e:
                res["dispatch_error"] = str(e)
        return res
