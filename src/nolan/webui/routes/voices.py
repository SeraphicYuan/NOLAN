"""Voices routes for the NOLAN hub.

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
        if script_project:                       # B1: never voice a scaffold placeholder
            from pathlib import Path as _P
            from nolan.scriptwriter import ScriptProjectStore
            _st = ScriptProjectStore(_P("projects"))
            if not _st.exists(script_project):
                raise HTTPException(status_code=404,
                                    detail=f"script project not found: {script_project}")
            if not _st.vo_readiness(script_project)["written"]:
                raise HTTPException(
                    status_code=409,
                    detail="script not written yet — promote a draft to script.md "
                           "before generating a voiceover")
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

    @app.post("/api/generate-voiceover/{slug}/retake/{index}")
    async def api_voiceover_retake(slug: str, index: int, body: dict = Body(default={})):
        """B2: re-synthesize ONE section of a Script Project's voiceover (fresh take,
        gated + spliced). Runs as a background job."""
        from nolan.config import load_config
        from nolan.webui import operations
        ref_audio = None
        voice_id = (body.get("voice_id") or "").strip() or None
        sample_token = (body.get("sample_token") or "").strip()
        ref_text = None
        if sample_token:
            sp = voice_lib.temp_sample_path(sample_token)
            if not sp.exists():
                raise HTTPException(status_code=404, detail="sample not found")
            ref_audio = str(sp)
            ref_text = body.get("ref_text") or None
            voice_id = None
        job = job_manager.start(
            "voiceover-retake", operations.generate_voiceover_retake,
            meta={"slug": slug, "index": index},
            config=load_config(), script_project=slug, index=int(index),
            voice_id=voice_id, ref_audio=ref_audio, ref_text=ref_text,
            text=(body.get("text") or None),
            num_step=(int(body["num_step"]) if body.get("num_step") else None))
        return {"job_id": job.id, "type": "voiceover-retake"}

    @app.get("/api/voiceover-takes/{slug}")
    async def api_voiceover_takes(slug: str):
        """List archived full-VO takes for a Script Project (B3)."""
        from nolan.voice_pipeline import list_takes
        from pathlib import Path as _P
        return {"takes": list_takes(_P("projects") / slug / "assets" / "voiceover")}

    @app.post("/api/voiceover-takes/{slug}/restore")
    async def api_voiceover_restore(slug: str, body: dict = Body(...)):
        """Restore a previously-archived take (B3)."""
        from nolan.voice_pipeline import restore_take
        from pathlib import Path as _P
        take_id = (body.get("take_id") or "").strip()
        if not take_id:
            raise HTTPException(status_code=400, detail="take_id is required")
        ok = restore_take(_P("projects") / slug / "assets" / "voiceover", take_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"take not found: {take_id}")
        return {"restored": take_id}

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

    @app.get("/api/voiceover-index")
    async def api_voiceover_index():
        """Every existing voiceover on disk — pipeline PROJECTS and hybrid HF COMPS — so the page can
        browse/play VO it didn't itself create. Read-only scan; nothing here synthesizes."""
        items = []
        proot = Path("projects")
        if proot.is_dir():
            for pdir in sorted(p for p in proot.iterdir() if p.is_dir()):
                vo = pdir / "assets" / "voiceover"
                if not vo.is_dir():
                    continue
                full = (vo / "voiceover.mp3").exists()
                nsec = len(list((vo / "_work").glob("sec_*.wav"))) if (vo / "_work").is_dir() else 0
                segj = vo / "segments" / "segments.json"
                if not nsec and segj.exists():
                    try:
                        nsec = len((json.loads(segj.read_text(encoding="utf-8")) or {}).get("segments", []))
                    except Exception:
                        nsec = 0
                if not (full or nsec):
                    continue
                items.append({"kind": "project", "name": pdir.name, "sections": nsec,
                              "has_mp3": full, "captions": (vo / "voiceover.srt").exists(),
                              "mp3_url": f"/api/voiceover/{quote(pdir.name)}/voiceover.mp3" if full else None})
        from nolan.hyperframes import edit as hfedit
        seen = set()
        for root in (hfedit.LAB_VIDEOS, hfedit.PROJECTS):
            if not Path(root).is_dir():
                continue
            for comp in sorted(p for p in Path(root).iterdir() if p.is_dir()):
                am = comp / "audio_meta.json"
                if not am.is_file() or comp.name in seen:
                    continue
                try:
                    meta = json.loads(am.read_text(encoding="utf-8"))
                except Exception:
                    continue
                voices = meta.get("voices", []) or []
                if not voices:
                    continue
                seen.add(comp.name)
                items.append({"kind": "hf", "name": comp.name, "sections": len(voices),
                              "total_s": meta.get("total_s"), "has_mp3": False,
                              "voices": [{"title": v.get("title", ""), "duration_s": v.get("duration_s"),
                                          "url": f"/api/hf-voice/{quote(comp.name)}/{quote(v.get('path', ''))}"}
                                         for v in voices]})
        return {"items": items}

    @app.get("/api/hf-voice/{comp}/{path:path}")
    async def api_hf_voice_file(comp: str, path: str):
        """Serve a hybrid-HF comp's voiceover wav (assets/voice/*.wav) — the sibling of /api/voiceover
        that reaches render-service/_lab_hyperframes/videos/<comp>/, which the projects-scoped one can't."""
        from urllib.parse import unquote
        from nolan.hyperframes import edit as hfedit
        safe = unquote(path).replace("\\", "/")
        if ".." in safe:
            raise HTTPException(status_code=400, detail="bad path")
        base = next((Path(root) / comp for root in (hfedit.LAB_VIDEOS, hfedit.PROJECTS)
                     if (Path(root) / comp).is_dir()), None)
        if base is None:
            raise HTTPException(status_code=404, detail="comp not found")
        p = (base / safe).resolve()
        if base.resolve() not in p.parents or not p.is_file():
            raise HTTPException(status_code=404, detail="not found")
        mt = {".wav": "audio/wav", ".mp3": "audio/mpeg"}.get(p.suffix.lower(), "application/octet-stream")
        return FileResponse(p, media_type=mt)

    # (TTS Studio merged into this page; the /tts transition alias was
    #  removed once nothing referenced it — deferred item #9.)

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
