"""Per-video extract assembler — the input the synthesis agent reads.

Combines the deterministic visual stats, the script↔visual pairing profile, and
the (optional) style vision pass into one ``per_video/<slug>.json`` bundle, and
caches the sampled frames so the synthesis agent can look at them.

Samples the video ONCE and feeds those frames to every dimension.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import cv2

from . import pairing as pairing_mod
from . import tempo as tempo_mod
from . import vision_pass as vision_pass_mod
from . import visual_stats


def _save_frames(frames: List, timestamps: List[float], out_dir: Path) -> List[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    names = []
    for i, fr in enumerate(frames):
        name = f"frame_{i:03d}.jpg"
        # cv2.imwrite silently fails on non-ASCII paths on Windows; encode in
        # memory and write with numpy.tofile, which handles Unicode paths.
        ok, buf = cv2.imencode(".jpg", fr)
        if ok:
            buf.tofile(str(out_dir / name))
            names.append(name)
    return names


async def build_extract(video_path: Path, *, segments: Optional[List[Dict[str, Any]]] = None,
                        frames_dir: Optional[Path] = None,
                        embed: Optional[Callable] = None,
                        vision_provider=None,
                        max_frames: int = 24, vision_max_frames: int = 6,
                        measure_tempo: bool = True, tempo_sample_fps: float = 4.0) -> Dict[str, Any]:
    """Assemble the full per-video visual-style extract.

    - visual stats (format/color/motion/graphics) from the sampled frames
    - pacing from the indexed ``segments`` (if any)
    - pairing (said↔shown) from ``segments`` (needs transcript+description); uses
      ``embed`` (defaults to the BGE embedder)
    - cinematography from ``vision_provider`` (skipped if None)
    """
    sampled = visual_stats.sample_frames(Path(video_path), max_frames=max_frames)
    frames, fmt = sampled["frames"], sampled["format"]

    frame_files: List[str] = []
    frame_paths: List[Path] = []
    if frames_dir is not None and frames:
        frame_files = _save_frames(frames, sampled["timestamps"], Path(frames_dir))
        frame_paths = [Path(frames_dir) / n for n in frame_files]

    extract: Dict[str, Any] = {
        "video_path": str(video_path),
        "format": fmt,
        "color": visual_stats.color_stats(frames),
        "motion": visual_stats.motion_score(frames),
        "graphics": visual_stats.graphics_stats(frames),
        "pacing": visual_stats.pacing_from_segments(segments or [], fmt.get("duration", 0.0)),
        "frames_analyzed": len(frames),
        "frame_files": frame_files,
    }

    # Tempo measured from the video itself (true cuts + curve + motion) — the
    # primary pacing signal; ``pacing`` above (index-derived) is the cheap fallback.
    if measure_tempo:
        try:
            extract["tempo"] = tempo_mod.analyze_tempo(Path(video_path), sample_fps=tempo_sample_fps)
        except Exception as e:
            extract["tempo"] = {"available": False, "reason": str(e)}
    else:
        extract["tempo"] = {"available": False, "reason": "tempo measurement disabled"}

    # Script↔visual pairing (only meaningful for indexed videos).
    if segments:
        extract["pairing"] = pairing_mod.analyze_pairing(
            segments, duration=fmt.get("duration", 0.0), embed=embed)
    else:
        extract["pairing"] = {"available": False, "reason": "video not indexed (no segments)"}

    # Style vision pass (optional; needs saved frames + a provider).
    if vision_provider is not None and frame_paths:
        extract["cinematography"] = await vision_pass_mod.analyze_style_frames(
            vision_provider, frame_paths, max_frames=vision_max_frames)
    else:
        extract["cinematography"] = {"available": False,
                                     "reason": "no vision provider or no frames"}

    return extract
