"""Reusable voiceover stage for the build pipelines (segment builder, orchestrator).

Synchronous (CLI-safe) — produces real TTS audio, captions, and audio-accurate
scene timing from the shared primitives (tts.py / captions.py / aligner.py /
whisper.py). The interactive webui path (operations.generate_voiceover /
generate_captions) covers the studio; this module covers automated builds.

Pipeline ordering for accurate timing:
    synthesize VO  ->  caption (word timeline)  ->  align scenes  ->  render  ->  assemble
TTS runs (and frees VRAM) before ComfyUI render, so they never contend on the GPU.
"""

from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _wav_duration(p: Path) -> float:
    try:
        with wave.open(str(p), "rb") as w:
            return round(w.getnframes() / float(w.getframerate()), 3)
    except Exception:
        return 0.0


def _run(cmd: list) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {(r.stderr or r.stdout or '')[:400]}")


def _section_body(s: Any) -> str:
    """Clean spoken text from a ScriptSection (or dict with body/narration)."""
    from nolan.script import clean_tts_text
    if isinstance(s, dict):
        return clean_tts_text(s.get("body") or s.get("narration") or "")
    return clean_tts_text(getattr(s, "narration", "") or "")


def _section_title(s: Any, i: int) -> str:
    if isinstance(s, dict):
        return s.get("title") or f"section {i+1}"
    return getattr(s, "title", None) or f"section {i+1}"


def resolve_voice_ref(project_dir: Path, config, voice_id_override: Optional[str] = None):
    """Resolve the build voice: --voice override → project.yaml voice_id →
    config.tts.default_voice → None (OmniVoice auto). Returns (ref_audio, ref_text, voice_id).
    """
    from nolan.voice_library import VoiceLibrary
    vid = (voice_id_override or "").strip() or None
    if not vid:
        py = Path(project_dir) / "project.yaml"
        if py.exists():
            try:
                import yaml
                data = yaml.safe_load(py.read_text(encoding="utf-8")) or {}
                vid = (data.get("voice_id") or (data.get("tts") or {}).get("voice_id") or "").strip() or None
            except Exception:
                vid = None
    if not vid:
        vid = (getattr(config.tts, "default_voice", "") or "").strip() or None
    if not vid:
        return None, None, None
    v = VoiceLibrary(Path("voices")).get(vid)
    if not v:
        return None, None, None  # unknown voice → fall back to auto
    return str(VoiceLibrary(Path("voices")).sample_path(vid)), v.get("ref_text"), vid


def produce_voiceover(out_dir: Path, sections: List[Any], provider, *,
                      ref_audio: Optional[str] = None, ref_text: Optional[str] = None,
                      instruct: Optional[str] = None, num_step: Optional[int] = None,
                      tempo: float = 1.0, progress=None) -> Dict[str, Any]:
    """Synthesize per-section audio (one consistent voice), pace, and concat to mp3.

    Returns {voiceover, sections:[{index,title,body,wav,duration}], total}.
    Per-section wavs are tempo-adjusted so they match the final mp3 (captions align).
    """
    out_dir = Path(out_dir)
    vo_dir = out_dir / "assets" / "voiceover"
    work = vo_dir / "_work"
    work.mkdir(parents=True, exist_ok=True)

    bodies = [(_section_title(s, i), _section_body(s)) for i, s in enumerate(sections)]
    bodies = [(t, b) for (t, b) in bodies if b.strip()]
    if not bodies:
        raise RuntimeError("no narration to synthesize")

    items = []
    for i, (_t, body) in enumerate(bodies):
        it = {"id": f"sec_{i:04d}", "text": body}
        if ref_audio:
            it["ref_audio"] = ref_audio
        if ref_text:
            it["ref_text"] = ref_text
        if instruct:
            it["instruct"] = instruct
        items.append(it)

    if progress:
        progress(0.2, f"Synthesizing {len(items)} sections")
    produced = provider.synthesize_batch(items, work, num_step=num_step)
    if not produced:
        raise RuntimeError("TTS produced no audio")

    apply_tempo = abs(float(tempo) - 1.0) > 0.01
    out_sections, ordered = [], []
    for i, (title, body) in enumerate(bodies):
        src = produced.get(f"sec_{i:04d}")
        if not src:
            continue
        wav = work / f"sec_{i:04d}.wav"
        if apply_tempo:
            paced = work / f"sec_{i:04d}_p.wav"
            _run([_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
                  "-filter:a", f"atempo={float(tempo):.3f}", str(paced)])
            paced.replace(wav)
        elif Path(src) != wav:
            Path(src).replace(wav)
        dur = _wav_duration(wav)
        out_sections.append({"index": i, "title": title, "body": body,
                             "wav": str(wav), "duration": dur})
        ordered.append(wav)

    if progress:
        progress(0.7, "Concatenating voiceover")
    list_file = work / "_concat.txt"
    list_file.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in ordered),
                         encoding="utf-8")
    mp3 = vo_dir / "voiceover.mp3"
    _run([_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-f", "concat",
          "-safe", "0", "-i", str(list_file), "-ar", "44100", str(mp3)])

    return {"voiceover": str(mp3), "sections": out_sections,
            "total": round(sum(s["duration"] for s in out_sections), 3)}


def build_captions(out_dir: Path, vo_sections: List[Dict[str, Any]], *,
                   model_size: str = "base", progress=None) -> List[Dict[str, Any]]:
    """Caption each section (hybrid: known body words + Whisper timing), stitch a
    global word timeline, and write voiceover.srt/.vtt/.words.json. Returns the words."""
    from nolan import captions as _cap
    from nolan.whisper import WhisperTranscriber, WhisperConfig, WHISPER_AVAILABLE
    if not WHISPER_AVAILABLE:
        raise RuntimeError("captions need Whisper (pip install faster-whisper)")

    vo_dir = Path(out_dir) / "assets" / "voiceover"
    transcriber = WhisperTranscriber(WhisperConfig(
        model_size=model_size, device="cpu", compute_type="int8"))
    global_words: List[Dict[str, Any]] = []
    offset = 0.0
    total = len(vo_sections)
    for n, s in enumerate(vo_sections):
        if progress:
            progress(0.05 + 0.9 * (n / total if total else 0), f"Captioning [{n+1}/{total}]")
        wav = Path(s["wav"])
        wt = transcriber.transcribe_words(wav)
        words = _cap.align_words(s["body"].split(), wt)
        global_words.extend(_cap.shift_words(words, offset))
        offset += float(s.get("duration") or _wav_duration(wav))

    (vo_dir / "voiceover.srt").write_text(_cap.words_to_srt(global_words), encoding="utf-8")
    (vo_dir / "voiceover.vtt").write_text(_cap.words_to_vtt(global_words), encoding="utf-8")
    (vo_dir / "voiceover.words.json").write_text(
        json.dumps(global_words, ensure_ascii=False), encoding="utf-8")
    return global_words


def align_scenes_from_words(scenes: List[Any], words: List[Dict[str, Any]]) -> int:
    """Set each scene's start_seconds/end_seconds from a word timeline (no re-transcribe).

    Matches scene.narration_excerpt against the words via the existing aligner.
    Returns the count of confidently-matched scenes.
    """
    from nolan.aligner import align_scenes_to_audio
    from nolan.whisper import WordTimestamp
    if not scenes or not words:
        return 0
    wt = [WordTimestamp(w["word"], float(w["start"]), float(w["end"])) for w in words]
    scene_dicts = [{"id": getattr(s, "id", str(i)),
                    "narration_excerpt": getattr(s, "narration_excerpt", "") or ""}
                   for i, s in enumerate(scenes)]
    results, _unmatched = align_scenes_to_audio(scene_dicts, wt)
    by_id = {r.scene_id: r for r in results}
    matched = 0
    for i, s in enumerate(scenes):
        r = by_id.get(getattr(s, "id", str(i)))
        if r is not None:
            s.start_seconds = round(r.start_seconds, 3)
            s.end_seconds = round(r.end_seconds, 3)
            if getattr(r, "confidence", 0) > 0:
                matched += 1
    return matched
