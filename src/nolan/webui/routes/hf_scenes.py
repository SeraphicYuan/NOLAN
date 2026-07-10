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
