"""NOLAN -> HyperFrames VOICEOVER bridge.

Translates a NOLAN `voice_pipeline` voiceover into the `audio_meta.json` shape the
faceless-explainer HyperFrames chain ALREADY consumes — so `audio.mjs sync-durations`
(frame `dur` = section duration; *narration owns duration*) and `assemble-index.mjs`
(root `<audio data-track-index="10">` per frame) both run on the NOLAN-cloned voice,
with NO second TTS pass. The only faceless step we replace is `audio.mjs generate`.

Reads a NOLAN VO from `<project>/assets/voiceover/`:
  - `segments/segments.json` (mode='segments': index/title/file/duration + optional
    `<file>.words.json`), OR
  - `_work/sec_NNNN.wav` (mode='full') + `voiceover.mp3`.

Writes into the HyperFrames comp:
  - `assets/voice/0N.wav`  (one per section, 1-based, the per-frame voice)
  - `assets/voice/voiceover.mp3`  (audition copy, if present)
  - `audio_meta.json`  `{bgm, voices:[{frame,path,duration_s,words}], sfx}`

  python vo_bridge.py --comp <hf_comp_dir> --vo <nolan_project_or_voiceover_dir>

Section i (0-based) maps to HyperFrames frame i+1 (1:1). The author writes exactly one
frame per section; `sync-durations` then sets each frame's dur from these voices.
"""
import argparse
import json
import shutil
import wave
from pathlib import Path


def _wav_dur(p: Path) -> float:
    with wave.open(str(p)) as w:
        return w.getnframes() / float(w.getframerate())


def _resolve_vo_dir(vo: Path) -> Path:
    """Accept a NOLAN project dir, its assets/voiceover dir, or a voiceover dir directly."""
    for cand in (vo, vo / "assets" / "voiceover", vo / "voiceover"):
        if (cand / "_work").is_dir() or (cand / "segments").is_dir() or (cand / "voiceover.mp3").exists():
            return cand
    raise FileNotFoundError(
        f"no NOLAN voiceover under {vo} (expected assets/voiceover/ with _work/ or segments/)")


def _sections_from_segments(seg_dir: Path):
    """mode='segments' — segments.json carries title/file/duration; words.json is optional."""
    data = json.loads((seg_dir / "segments.json").read_text(encoding="utf-8"))
    if isinstance(data, dict):                     # voice_pipeline emits {project, voice_id, segments:[...]}
        data = data.get("segments") or []
    out = []
    for s in data:
        wav = seg_dir / s["file"]
        words = []
        wj = seg_dir / (Path(s["file"]).stem + ".words.json")
        if wj.exists():
            try:
                words = json.loads(wj.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                words = []
        out.append({"title": s.get("title"), "wav": wav,
                    "dur": float(s.get("duration") or _wav_dur(wav)), "words": words})
    return out


def _sections_from_work(vo_dir: Path):
    """mode='full' — per-section anchors in _work/sec_NNNN.wav (section order), durations measured."""
    wavs = sorted((vo_dir / "_work").glob("sec_*.wav"))
    return [{"title": None, "wav": w, "dur": _wav_dur(w), "words": []} for w in wavs]


def translate(comp_dir: Path, vo_source: Path) -> dict:
    """Translate a NOLAN VO into `<comp>/audio_meta.json` + `<comp>/assets/voice/*.wav`."""
    comp_dir = Path(comp_dir)
    vo_dir = _resolve_vo_dir(Path(vo_source))
    seg = vo_dir / "segments"
    sections = (_sections_from_segments(seg) if (seg / "segments.json").exists()
                else _sections_from_work(vo_dir))
    if not sections:
        raise FileNotFoundError(
            f"no per-section wavs under {vo_dir} (segments/segments.json or _work/sec_*.wav)")

    voice_dir = comp_dir / "assets" / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)
    voices, total = [], 0.0
    for i, s in enumerate(sections):
        n = i + 1                                   # HyperFrames frames are 1-based
        rel = f"assets/voice/{n:02d}.wav"
        shutil.copyfile(s["wav"], comp_dir / rel)
        voices.append({"frame": n, "path": rel, "duration_s": round(s["dur"], 3),
                       "title": s.get("title"), "words": s.get("words") or []})
        total += s["dur"]

    mp3 = vo_dir / "voiceover.mp3"                   # audition copy (optional)
    if mp3.exists():
        shutil.copyfile(mp3, voice_dir / "voiceover.mp3")

    meta = {"bgm": None, "voices": voices, "sfx": [],
            "source": str(vo_dir), "total_s": round(total, 3)}
    (comp_dir / "audio_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"comp_dir": str(comp_dir), "sections": len(voices), "total_s": round(total, 3),
            "frames_expected": len(voices), "audio_meta": str(comp_dir / "audio_meta.json")}


def main():
    ap = argparse.ArgumentParser(description="NOLAN voiceover -> HyperFrames audio_meta.json bridge")
    ap.add_argument("--comp", required=True, help="HyperFrames composition dir (videos/<slug>/)")
    ap.add_argument("--vo", required=True, help="NOLAN project dir OR its assets/voiceover dir")
    a = ap.parse_args()
    res = translate(Path(a.comp), Path(a.vo))
    print(json.dumps(res, indent=2))
    print(f"\n  {res['sections']} section(s) -> {res['frames_expected']} frame(s), "
          f"{res['total_s']:.1f}s total. Author one frame per section, then "
          f"`audio.mjs sync-durations` + `assemble-index` + `hyperframes render`.")


if __name__ == "__main__":
    main()
