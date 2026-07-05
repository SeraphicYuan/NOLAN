"""Shared voiceover core — one TTS pipeline for webUI ops and the Director.

Extracted from ``nolan.webui.operations.generate_voiceover`` (Phase 1 of the
architecture consolidation) so the orchestrator's ``voiceover`` step and the
Voices page run the SAME code: per-section synthesis (beat anchors land in
``assets/voiceover/_work/sec_NNNN.wav``), voice cloning from the voice
library, GPU-lock serialization with ComfyUI, and full/segments packaging.

Callers pass ``log``/``progress`` callbacks instead of a webui job object.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable, Optional


def _ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _wav_duration(path) -> float:
    import wave
    try:
        with wave.open(str(path), "rb") as w:
            return round(w.getnframes() / float(w.getframerate()), 3)
    except Exception:
        return 0.0


def _tempo_on(tempo) -> bool:
    return tempo is not None and abs(float(tempo) - 1.0) > 0.01


async def _atempo(src, dst, tempo: float) -> None:
    """Time-stretch audio by `tempo` (>1 faster) without changing pitch (ffmpeg atempo)."""
    proc = await asyncio.create_subprocess_exec(
        _ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src), "-filter:a", f"atempo={float(tempo):.3f}", str(dst),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"atempo failed: {(err or b'').decode(errors='replace')[:300]}")


async def _free_comfyui_vram(config) -> None:
    """Best-effort: ask ComfyUI to unload models so a TTS job has VRAM headroom."""
    import httpx
    base = f"http://{config.comfyui.host}:{config.comfyui.port}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            await c.post(f"{base}/free", json={"unload_models": True, "free_memory": True})
    except Exception:
        pass  # ComfyUI not running / no /free — fine, we proceed anyway


async def synthesize_voiceover(*, config, project: str = None, script_project: str = None,
                               project_dir: Path = None,
                               mode: str = "full", voice_id: str = None,
                               store_root: str = "voices",
                               ref_audio: str = None, ref_text: str = None,
                               instruct: str = None, num_step: int = None,
                               speed: float = None, language_id: str = None,
                               tempo: float = 1.0,
                               log: Optional[Callable[[str], None]] = None,
                               progress: Optional[Callable[[float, str], None]] = None):
    """Generate a project's voiceover with local TTS.

    Source: a render project's script.json (``project``) OR a Script Project's
    script.md (``script_project``, split on ## headings). Only section *bodies* are
    spoken — headings/metadata are never read aloud (both modes).
    ``project_dir`` overrides the ``projects/<name>`` base-path convention (the
    Director passes its absolute project path; webUI callers rely on CWD).

    mode='full'     -> concatenated voiceover.mp3 + per-section anchors in
                       ``_work/sec_NNNN.wav`` (run `nolan align` after — it
                       beat-anchors on those wavs automatically).
    mode='segments' -> per-section wavs + segments.json under assets/voiceover/segments/.

    Runs under the shared GPU lock so it never overlaps ComfyUI.
    """
    from nolan.tts import create_tts_provider
    from nolan.voice_library import VoiceLibrary
    from nolan.webui.jobs import get_gpu_lock

    log = log or (lambda msg: None)
    progress = progress or (lambda pct, msg: None)

    if not config.tts.enabled:
        raise RuntimeError("TTS is disabled — set tts.enabled: true in nolan.yaml "
                           "(see docs/OMNIVOICE_SETUP.md)")

    # --- resolve sections [{title, timecode, body}] + the project base dir ----
    if script_project:
        from nolan.script import parse_script_sections
        base = Path(project_dir) if project_dir else Path("projects") / script_project
        md_path = base / "script.md"
        if not md_path.exists():
            raise RuntimeError(f"no script.md for script project '{script_project}'")
        sections = parse_script_sections(md_path.read_text(encoding="utf-8"))
        label = script_project
    elif project:
        from nolan.script import Script, clean_tts_text
        base = Path(project_dir) if project_dir else Path("projects") / project
        sp = base / "script.json"
        if not sp.exists():
            raise RuntimeError(f"no script.json for project '{project}'")
        sc = Script.load_json(str(sp))
        sections = [{"title": s.title, "timecode": None, "body": clean_tts_text(s.narration)}
                    for s in sc.sections if (s.narration or "").strip()]
        label = project
    else:
        raise RuntimeError("provide project or script_project")
    sections = [s for s in sections if (s["body"] or "").strip()]
    if not sections:
        raise RuntimeError("script has no narration to synthesize")

    # --- resolve cloning voice: explicit ref_audio wins; else a saved voice_id.
    # The SAME ref is applied to every section so the voice stays consistent.
    if not ref_audio and voice_id:
        lib = VoiceLibrary(Path(store_root))
        voice = lib.get(voice_id)
        if not voice:
            raise RuntimeError(f"voice not found: {voice_id}")
        ref_audio = str(lib.sample_path(voice_id))
        ref_text = voice.get("ref_text")
        log(f"Cloning voice: {voice.get('name')} ({voice_id})")
    if not ref_audio and not instruct:
        log("No voice reference/instruct — OmniVoice will auto-pick a voice "
            "PER SECTION, so sections may not match. Pick/clone a voice for consistency.")

    items = []
    for i, s in enumerate(sections):
        it = {"id": f"sec_{i:04d}", "text": s["body"]}
        if ref_audio:
            it["ref_audio"] = ref_audio
        if ref_text:
            it["ref_text"] = ref_text
        if instruct:
            it["instruct"] = instruct
        if speed is not None:
            it["speed"] = speed
        if language_id:
            it["language_id"] = language_id
        items.append(it)

    vo_dir = base / "assets" / "voiceover"
    work = vo_dir / "_work"
    work.mkdir(parents=True, exist_ok=True)
    provider = create_tts_provider(config.tts)
    loop = asyncio.get_event_loop()

    progress(0.1, f"Synthesizing {len(items)} sections (waiting for GPU)…")
    async with get_gpu_lock():
        if config.tts.omnivoice.free_comfyui_vram:
            progress(0.15, "Freeing ComfyUI VRAM…")
            await _free_comfyui_vram(config)
        progress(0.25, f"Running OmniVoice on {len(items)} sections…")
        produced = await loop.run_in_executor(
            None, lambda: provider.synthesize_batch(items, work, num_step=num_step))

    if not produced:
        raise RuntimeError("TTS produced no audio (check the omnivoice env / logs)")
    missing = [it["id"] for it in items if it["id"] not in produced]
    if missing:
        log(f"warning: {len(missing)} sections produced no audio: {missing[:5]}")

    import json as _json
    import shutil as _shutil
    from nolan.script_style import slugify

    if mode == "segments":
        progress(0.9, "Packaging segments…")
        seg_dir = vo_dir / "segments"
        _shutil.rmtree(seg_dir, ignore_errors=True)
        seg_dir.mkdir(parents=True, exist_ok=True)
        manifest = []
        apply_tempo = _tempo_on(tempo)
        for i, s in enumerate(sections):
            src = produced.get(f"sec_{i:04d}")
            if not src:
                continue
            name = f"{i:02d}_{slugify(s['title'] or 'section')}.wav"
            dest = seg_dir / name
            if apply_tempo:
                await _atempo(src, dest, tempo)
                Path(src).unlink(missing_ok=True)
            else:
                Path(src).replace(dest)
            manifest.append({"index": i, "title": s["title"], "timecode": s["timecode"],
                             "file": name, "duration": _wav_duration(dest)})
        (seg_dir / "segments.json").write_text(
            _json.dumps({"project": label, "voice_id": voice_id, "segments": manifest},
                        indent=2, ensure_ascii=False), encoding="utf-8")
        _shutil.rmtree(work, ignore_errors=True)
        total = round(sum(m["duration"] for m in manifest), 1)
        progress(1.0, f"{len(manifest)} segments ({total}s) → {seg_dir}")
        return {"mode": "segments", "project": label, "segments": manifest,
                "count": len(manifest), "dir": str(seg_dir), "missing": missing}

    # full mode: concat -> voiceover.mp3
    progress(0.9, "Concatenating voiceover…")
    ordered = [produced[it["id"]] for it in items if it["id"] in produced]
    list_file = work / "_concat.txt"
    list_file.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in ordered),
                         encoding="utf-8")
    out_mp3 = vo_dir / "voiceover.mp3"
    cmd = [_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-f", "concat",
           "-safe", "0", "-i", str(list_file)]
    if _tempo_on(tempo):
        cmd += ["-filter:a", f"atempo={float(tempo):.3f}"]
    cmd += ["-ar", "44100", str(out_mp3)]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"voiceover concat failed: {(err or b'').decode(errors='replace')[:400]}")

    progress(1.0, f"Voiceover ready ({len(ordered)} sections) → {out_mp3}")
    return {"mode": "full", "project": label, "voiceover": str(out_mp3),
            "sections": len(ordered), "missing": missing,
            "next": "run `nolan align` to set audio-accurate scene timings"}
