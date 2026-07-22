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


def build_tts_items(bodies, *, ref_audio=None, ref_text=None, instruct=None,
                    speed=None, language_id=None, normalize: bool = True) -> list:
    """The per-section synthesis batch, one consistent voice across sections.

    Shared by the async project core (synthesize_voiceover) and the sync
    segment-builder core (nolan.voiceover.produce_voiceover) — the SAME item
    schema OmniVoice's synthesize_batch consumes (ids sec_0000…).

    ``normalize`` (A1) expands numbers/currency/percent/years to spoken words in
    the SYNTHESIS text only — the caller's stored section bodies are untouched.
    """
    from nolan.tts_normalize import normalize_for_speech
    items = []
    for i, body in enumerate(bodies):
        text = normalize_for_speech(body) if normalize else body
        it = {"id": f"sec_{i:04d}", "text": text}
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
    return items


def _audio_filter(tempo: float, loudnorm: bool) -> Optional[str]:
    """Compose the ffmpeg -filter:a chain: optional atempo (pace) + optional
    loudnorm (A3, EBU R128 to -16 LUFS so the /voices preview matches the mix)."""
    parts = []
    if _tempo_on(tempo):
        parts.append(f"atempo={float(tempo):.3f}")
    if loudnorm:
        parts.append("loudnorm=I=-16:TP=-2:LRA=11")
    return ",".join(parts) if parts else None


def concat_wavs_to_mp3(ordered, list_file, out_mp3, *, tempo: float = 1.0,
                       loudnorm: bool = True) -> None:
    """ffmpeg concat of section wavs -> voiceover.mp3 (optional atempo + loudnorm). Sync."""
    import subprocess
    Path(list_file).write_text(
        "".join(f"file '{Path(p).resolve().as_posix()}'\n" for p in ordered),
        encoding="utf-8")
    cmd = [_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-f", "concat",
           "-safe", "0", "-i", str(list_file)]
    filt = _audio_filter(tempo, loudnorm)
    if filt:
        cmd += ["-filter:a", filt]
    cmd += ["-ar", "44100", str(out_mp3)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(
            f"voiceover concat failed: {(r.stderr or r.stdout or '')[:400]}")


def finalize_sections(vo_dir, sections, wavs, *, wpm: float = 150.0, trim: bool = True):
    """A3 trim + A2 gate + measure sidecar. Trims each section wav IN PLACE (so the
    beat-anchor durations are honest), gates the result, writes
    ``<vo_dir>/voiceover.measure.json``, and returns the VoiceReport. The caller
    raises on ``not report.ok`` so a broken VO fails loudly (never ships silently)."""
    import json as _json
    from nolan.voice_audio import trim_silence
    from nolan.voice_gate import gate_voiceover
    if trim:
        for w in wavs:
            if w and Path(w).exists():
                try:
                    trim_silence(w)
                except Exception:  # noqa: BLE001 - a trim failure must not lose the take
                    pass
    report = gate_voiceover(sections, wavs, wpm=wpm)
    d = report.to_dict()
    d["total_s"] = round(sum(s.get("duration_s", 0.0) for s in d["sections"]
                            if s.get("present")), 2)
    try:
        Path(vo_dir).mkdir(parents=True, exist_ok=True)
        (Path(vo_dir) / "voiceover.measure.json").write_text(
            _json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return report


_CAPTION_FILES = ("voiceover.srt", "voiceover.vtt", "voiceover.words.json")


def _now_stamp() -> str:
    import datetime
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _unique_dir(parent: Path, base: str) -> Path:
    """A fresh child dir named `base` (or `base-2`, `-3`…) — collision-safe when two
    archives land in the same second (rapid retakes / tests)."""
    ts, n = base, 1
    while (parent / ts).exists():
        n += 1
        ts = f"{base}-{n}"
    d = parent / ts
    d.mkdir(parents=True, exist_ok=True)
    return d


def archive_current_take(vo_dir, *, keep: int = 3) -> Optional[str]:
    """B3: snapshot the existing VO (mp3 + measure + captions + per-section _work wavs) into
    ``_takes/full/<ts>/`` before a regenerate overwrites it, so a good take is never silently
    lost. Prunes to the most-recent ``keep``. Returns the take id, or None if nothing to save."""
    import shutil
    vo_dir = Path(vo_dir)
    if not (vo_dir / "voiceover.mp3").exists():
        return None
    dst = _unique_dir(vo_dir / "_takes" / "full", _now_stamp())
    ts = dst.name
    for name in ("voiceover.mp3", "voiceover.measure.json", *_CAPTION_FILES):
        p = vo_dir / name
        if p.exists():
            shutil.copy2(p, dst / name)
    if (vo_dir / "_work").exists():
        shutil.copytree(vo_dir / "_work", dst / "_work",
                        ignore=shutil.ignore_patterns("_concat.txt", "_batch.jsonl"),
                        dirs_exist_ok=True)
    takes = sorted((vo_dir / "_takes" / "full").glob("*/"))
    for old in takes[:-keep] if keep else []:
        shutil.rmtree(old, ignore_errors=True)
    return ts


def list_takes(vo_dir) -> list:
    """List archived full-VO takes (newest first) with their total duration."""
    import json as _json
    vo_dir = Path(vo_dir)
    root = vo_dir / "_takes" / "full"
    out = []
    if not root.exists():
        return out
    for d in sorted(root.glob("*/"), reverse=True):
        total = None
        mp = d / "voiceover.measure.json"
        if mp.exists():
            try:
                total = _json.loads(mp.read_text(encoding="utf-8")).get("total_s")
            except (OSError, ValueError):
                pass
        out.append({"id": d.name, "has_mp3": (d / "voiceover.mp3").exists(), "total_s": total})
    return out


def restore_take(vo_dir, take_id: str) -> bool:
    """Restore a previously-archived full-VO take (mp3 + measure + captions + _work anchors)."""
    import shutil
    vo_dir = Path(vo_dir)
    src = vo_dir / "_takes" / "full" / take_id
    if not (src / "voiceover.mp3").exists():
        return False
    # archive what's current first, so 'restore' is itself reversible
    archive_current_take(vo_dir)
    for name in ("voiceover.mp3", "voiceover.measure.json", *_CAPTION_FILES):
        p = src / name
        (vo_dir / name).unlink(missing_ok=True)
        if p.exists():
            shutil.copy2(p, vo_dir / name)
    if (src / "_work").exists():
        shutil.rmtree(vo_dir / "_work", ignore_errors=True)
        shutil.copytree(src / "_work", vo_dir / "_work", dirs_exist_ok=True)
    return True


async def retake_section(*, config, index: int, project: str = None, script_project: str = None,
                         project_dir: Path = None, text: str = None, voice_id: str = None,
                         store_root: str = "voices", ref_audio: str = None, ref_text: str = None,
                         instruct: str = None, num_step: int = None, speed: float = None,
                         language_id: str = None,
                         log: Optional[Callable[[str], None]] = None,
                         progress: Optional[Callable[[float, str], None]] = None) -> dict:
    """B2: re-synthesize ONE section (a fresh, non-deterministic take), gate it, and splice it
    back — preserving the section↔beat count invariant. The prior section wav is snapshotted to
    ``_takes/sec_NN/`` first (B3). A take that fails the A2 gate is REJECTED (the old audio is
    kept) so a retake can never make a project worse. Stale captions are invalidated (loud)."""
    from nolan.tts import create_tts_provider
    from nolan.voice_library import VoiceLibrary
    from nolan.voice_audio import trim_silence
    from nolan.voice_gate import gate_voiceover
    from nolan.webui.jobs import get_gpu_lock
    import shutil

    log = log or (lambda m: None)
    progress = progress or (lambda p, m: None)
    if not config.tts.enabled:
        raise RuntimeError("TTS is disabled — set tts.enabled: true in nolan.yaml")

    # resolve sections + base dir (same contract as synthesize_voiceover)
    if script_project:
        from nolan.script import parse_script_sections
        base = Path(project_dir) if project_dir else Path("projects") / script_project
        sections = parse_script_sections((base / "script.md").read_text(encoding="utf-8"))
    elif project:
        from nolan.script import Script, clean_tts_text
        base = Path(project_dir) if project_dir else Path("projects") / project
        sc = Script.load_json(str(base / "script.json"))
        sections = [{"title": s.title, "body": clean_tts_text(s.narration)}
                    for s in sc.sections if (s.narration or "").strip()]
    else:
        raise RuntimeError("provide project or script_project")
    sections = [s for s in sections if (s.get("body") or "").strip()]
    if not (0 <= index < len(sections)):
        raise RuntimeError(f"section index {index} out of range (0..{len(sections)-1})")

    vo_dir = base / "assets" / "voiceover"
    work = vo_dir / "_work"
    sec_path = work / f"sec_{index:04d}.wav"
    body = text if text is not None else sections[index]["body"]

    # resolve cloning voice (explicit ref wins, else the saved voice_id)
    if not ref_audio and voice_id:
        lib = VoiceLibrary(Path(store_root))
        v = lib.get(voice_id)
        if not v:
            raise RuntimeError(f"voice not found: {voice_id}")
        ref_audio, ref_text = str(lib.sample_path(voice_id)), v.get("ref_text")

    # snapshot the current take of THIS section (B3)
    if sec_path.exists():
        snap = vo_dir / "_takes" / f"sec_{index:02d}"
        snap.mkdir(parents=True, exist_ok=True)
        stamp, k = _now_stamp(), 1
        while (snap / f"{stamp}.wav").exists():
            k += 1
            stamp = f"{_now_stamp()}-{k}"
        shutil.copy2(sec_path, snap / f"{stamp}.wav")

    items = build_tts_items([body], ref_audio=ref_audio, ref_text=ref_text,
                            instruct=instruct, speed=speed, language_id=language_id)
    items[0]["id"] = "retake"
    provider = create_tts_provider(config.tts)
    loop = asyncio.get_event_loop()
    tmp = work / "_retake"
    tmp.mkdir(parents=True, exist_ok=True)
    progress(0.2, f"Re-synthesizing section {index} (waiting for GPU)…")
    async with get_gpu_lock():
        produced = await loop.run_in_executor(
            None, lambda: provider.synthesize_batch(items, tmp, num_step=num_step))
    new_wav = produced.get("retake")
    if not new_wav or not Path(new_wav).exists():
        raise RuntimeError(f"retake of section {index} produced no audio")

    trim_silence(new_wav)
    rep = gate_voiceover([sections[index]], [new_wav])
    if not rep.ok:                                   # reject a bad take; keep the old audio
        Path(new_wav).unlink(missing_ok=True)
        return {"index": index, "ok": False, "accepted": False,
                "gate": rep.to_dict(), "reason": rep.summary()}

    Path(new_wav).replace(sec_path)                  # splice the good take in place
    shutil.rmtree(tmp, ignore_errors=True)

    # re-concat the full mp3 from all (in-order) section wavs + refresh the measure sidecar
    ordered = sorted(work.glob("sec_*.wav"))
    await asyncio.to_thread(concat_wavs_to_mp3, ordered, work / "_concat.txt",
                            vo_dir / "voiceover.mp3")
    full_rep = finalize_sections(vo_dir, sections, [work / f"sec_{i:04d}.wav"
                                                    if (work / f"sec_{i:04d}.wav").exists() else None
                                                    for i in range(len(sections))], trim=False)
    # captions no longer match the new timings — invalidate loudly
    invalidated = False
    for name in _CAPTION_FILES:
        p = vo_dir / name
        if p.exists():
            p.unlink()
            invalidated = True
    log(f"section {index} retaken ✓ (durations changed; captions invalidated={invalidated})")
    return {"index": index, "ok": True, "accepted": True,
            "duration_s": _wav_duration(sec_path), "captions_invalidated": invalidated,
            "gate": full_rep.to_dict()}


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

    items = build_tts_items(
        [s["body"] for s in sections], ref_audio=ref_audio, ref_text=ref_text,
        instruct=instruct, speed=speed, language_id=language_id)

    vo_dir = base / "assets" / "voiceover"
    prior = archive_current_take(vo_dir)             # B3: never clobber a good take silently
    if prior:
        log(f"archived the previous voiceover as take {prior}")
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

    # A3 trim + A2 gate + measure sidecar (BEFORE packaging → honest beat durations).
    sec_wavs = [produced.get(f"sec_{i:04d}") for i in range(len(sections))]
    report = finalize_sections(vo_dir, sections, sec_wavs)
    gate = report.to_dict()
    if report.checks:
        log(report.summary())

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
        if not report.ok:
            raise RuntimeError("voiceover failed the quality gate — " + report.summary())
        progress(1.0, f"{len(manifest)} segments ({total}s) → {seg_dir}")
        return {"mode": "segments", "project": label, "segments": manifest,
                "count": len(manifest), "dir": str(seg_dir), "missing": missing, "gate": gate}

    # full mode: concat -> voiceover.mp3
    progress(0.9, "Concatenating voiceover…")
    ordered = [produced[it["id"]] for it in items if it["id"] in produced]
    out_mp3 = vo_dir / "voiceover.mp3"
    await asyncio.to_thread(concat_wavs_to_mp3, ordered, work / "_concat.txt",
                            out_mp3, tempo=tempo)

    if not report.ok:
        raise RuntimeError("voiceover failed the quality gate — " + report.summary())
    progress(1.0, f"Voiceover ready ({len(ordered)} sections) → {out_mp3}")
    return {"mode": "full", "project": label, "voiceover": str(out_mp3),
            "sections": len(ordered), "missing": missing, "gate": gate,
            "next": "run `nolan align` to set audio-accurate scene timings"}
