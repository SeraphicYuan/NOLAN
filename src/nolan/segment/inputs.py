"""Stage 0/1 — resolve any input into a common SegmentInput.

Three input kinds (all roads lead to: script sections + VO + duration + timing):
  1. indexed-source span  -> extract VO from the span, slice the SRT for script+timing
  2. script text (+ optional VO)
  3. VO audio (+ optional script; transcribe if absent)
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import imageio_ffmpeg

from nolan.scenes import ScriptSection

FF = imageio_ffmpeg.get_ffmpeg_exe()
LineTiming = List[Tuple[str, float, float]]   # (text, start, end) seconds, span-relative


@dataclass
class SegmentInput:
    sections: List[ScriptSection]
    duration: float
    vo_path: Optional[Path] = None
    source_video: Optional[Path] = None        # for segment-search b-roll
    project_id: Optional[str] = None
    index_db: Optional[Path] = None
    line_timing: Optional[LineTiming] = None


# --- SRT ---------------------------------------------------------------------
def _ts(t: str) -> float:
    h, m, rest = t.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt(path: Path) -> LineTiming:
    out: LineTiming = []
    blocks = re.split(r"\n\s*\n", Path(path).read_text(encoding="utf-8", errors="ignore"))
    for b in blocks:
        m = re.search(r"(\d\d:\d\d:\d\d,\d+)\s*-->\s*(\d\d:\d\d:\d\d,\d+)(.*)", b, re.DOTALL)
        if not m:
            continue
        text = " ".join(line.strip() for line in m.group(3).strip().splitlines() if line.strip())
        text = re.sub(r"<[^>]+>", "", text).strip()
        if text:
            out.append((text, _ts(m.group(1)), _ts(m.group(2))))
    return out


def _ffprobe_duration(path: Path) -> float:
    import json
    pr = subprocess.run([FF, "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", pr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def _extract_audio(src: Path, start: float, dur: float, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([FF, "-y", "-ss", str(start), "-t", str(dur), "-i", str(src),
                    "-vn", "-c:a", "aac", "-b:a", "192k", "-loglevel", "error", str(out)], check=True)
    return out


def _section(title: str, narration: str, start: float, end: float) -> ScriptSection:
    return ScriptSection(title=title, narration=narration, start_time=start, end_time=end,
                         word_count=len(narration.split()))


# --- resolvers ---------------------------------------------------------------
def from_indexed_span(source_video: Path, srt_path: Path, start: float, end: float,
                      work_dir: Path, index_db: Optional[Path] = None,
                      project_id: Optional[str] = None) -> SegmentInput:
    dur = end - start
    vo = _extract_audio(Path(source_video), start, dur, Path(work_dir) / "vo.m4a")
    lines = [(t, s - start, e - start) for (t, s, e) in parse_srt(Path(srt_path))
             if e > start and s < end]
    script = " ".join(t for (t, _s, _e) in lines)
    return SegmentInput(
        sections=[_section("Segment", script, 0.0, dur)], duration=dur, vo_path=vo,
        source_video=Path(source_video), project_id=project_id,
        index_db=Path(index_db) if index_db else None, line_timing=lines or None)


def from_script(script_text: str, work_dir: Path, vo_path: Optional[Path] = None,
                wpm: float = 150.0, source_video: Optional[Path] = None,
                index_db: Optional[Path] = None, project_id: Optional[str] = None) -> SegmentInput:
    paras = [p.strip() for p in re.split(r"\n\s*\n", script_text.strip()) if p.strip()] or [script_text.strip()]
    if vo_path:
        dur = _ffprobe_duration(Path(vo_path))
    else:
        words = sum(len(p.split()) for p in paras)
        dur = max(2.0, words / wpm * 60.0)
    sections = [_section(f"Section {i+1}", p, 0.0, dur) for i, p in enumerate(paras)]
    return SegmentInput(sections=sections, duration=dur, vo_path=Path(vo_path) if vo_path else None,
                        source_video=Path(source_video) if source_video else None,
                        index_db=Path(index_db) if index_db else None, project_id=project_id)


def from_vo(vo_path: Path, work_dir: Path, script_text: Optional[str] = None,
            whisper_model: str = "base", **kw) -> SegmentInput:
    dur = _ffprobe_duration(Path(vo_path))
    if script_text:
        return from_script(script_text, work_dir, vo_path=Path(vo_path), **kw)
    # transcribe
    from nolan.whisper import WhisperTranscriber, WhisperConfig
    tr = WhisperTranscriber(WhisperConfig(model_size=whisper_model, device="cpu", compute_type="int8"))
    segs = tr.transcribe(str(vo_path))
    lines = [(s.get("text", "").strip(), float(s.get("start", 0)), float(s.get("end", 0)))
             for s in (segs if isinstance(segs, list) else segs.get("segments", []))]
    script = " ".join(t for (t, _s, _e) in lines if t)
    return SegmentInput(sections=[_section("Segment", script, 0.0, dur)], duration=dur,
                        vo_path=Path(vo_path), line_timing=lines or None, **{
                            k: v for k, v in kw.items() if k in ("project_id",)})


# --- timing ------------------------------------------------------------------
def assign_timing(scenes, total_duration: float) -> None:
    """Tile [0, total_duration] across scenes in order, proportional to narration length.
    (Precise per-line SRT/word alignment is a later refinement.)"""
    weights = [max(1, len((s.narration_excerpt or "").split())) for s in scenes]
    wsum = sum(weights) or 1
    t = 0.0
    for s, w in zip(scenes, weights):
        s.start_seconds = round(t, 3)
        t += total_duration * w / wsum
        s.end_seconds = round(t, 3)
    if scenes:
        scenes[-1].end_seconds = round(total_duration, 3)
