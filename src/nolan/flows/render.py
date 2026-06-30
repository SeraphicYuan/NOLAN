"""chapter-block render mechanism — render each beat to its own clip, concat to final.

This is what makes per-beat re-render real: a beat renders as a single-step `_lab_chapter`
job, so it's an independent clip — and because its duration is pinned to its voiceover
segment, editing a beat's visuals never reflows the timeline. art/explainer/book all share
this mechanism (dispatched via Flow.render_mechanism). See web-video-lab/flows/EDITOR.md.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .base import FFMPEG, RS, _win, render_chapter


def _beat_job(job: dict, i: int, out_name: str) -> dict:
    """A single-step job for beat i (keeps theme/fx/captions; one step)."""
    step = job["props"]["steps"][i]
    return {**{k: v for k, v in job.items() if k != "props"},
            "out": out_name,
            "props": {**{k: v for k, v in job["props"].items() if k != "steps"}, "steps": [step]}}


def render_beat(job_path, i: int, work_dir) -> Path:
    """Render beat i of a flow job to its own clip. Returns the clip path."""
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    work_dir = Path(work_dir); work_dir.mkdir(parents=True, exist_ok=True)
    out_name = f"beat_{i:02d}.mp4"
    bjp = work_dir / f"_beat_{i:02d}.job.json"
    bjp.write_text(json.dumps(_beat_job(job, i, out_name)), encoding="utf-8")
    clip = render_chapter(bjp)                      # -> _lab_chapter/output/beat_<i>.mp4
    dest = work_dir / out_name
    dest.write_bytes(Path(clip).read_bytes())       # collect into the work dir
    return dest


def render_beats(job_path, work_dir, only=None) -> dict:
    """Render selected beats (or all) to clips. Returns {beat_index: clip_path}."""
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    idxs = list(only) if only is not None else range(len(job["props"]["steps"]))
    out = {}
    for i in idxs:
        print(f"[chapter-block] render beat {i}")
        out[i] = render_beat(job_path, i, work_dir)
    return out


def concat_beats(clip_paths, out_path) -> Path:
    """Concat ordered beat clips into the final video (hard-cut; same codec -> stream copy).

    Beats hard-cut today (same as the whole-composition Series render); cross-fade at the
    boundary is a documented refinement (ffmpeg xfade/acrossfade).
    """
    out_path = Path(out_path); out_path.parent.mkdir(parents=True, exist_ok=True)
    lst = out_path.parent / "_concat.txt"
    lst.write_text("".join(f"file '{_win(c)}'\n" for c in clip_paths), encoding="utf-8")
    r = subprocess.run([str(FFMPEG), "-y", "-f", "concat", "-safe", "0", "-i", _win(lst),
                        "-c", "copy", _win(out_path)], cwd=str(RS), capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:])
        raise RuntimeError(f"concat failed -> {out_path}")
    return out_path


def render_flow(job_path, work_dir, out_path) -> Path:
    """Full chapter-block render: all beats -> clips -> concat. Returns the final video."""
    clips = render_beats(job_path, work_dir)
    ordered = [clips[i] for i in sorted(clips)]
    return concat_beats(ordered, out_path)
