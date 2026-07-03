"""Shared ffmpeg helpers for the render paths (pipeline consolidation P1).

One place for the subclip-extraction, silent-audio, and normalize filtergraph
that the segment and orchestrator renderers had each implemented separately.
Always uses the **bundled** ffmpeg (imageio_ffmpeg) — the orchestrator previously
shelled out to a bare ``ffmpeg`` on PATH, which on the Windows/WSL setup risks a
cp1252 decode crash and an absent/incompatible binary.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def normalize_vf(width: int, height: int, fps: int,
                 fade: float = 0.0, duration: float = 0.0) -> str:
    """Filtergraph: fit-and-pad to width×height, set fps, optional in/out fade."""
    vf = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
          f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,fps={fps}")
    if fade and fade > 0 and duration > 0:
        vf += (f",fade=t=in:st=0:d={fade},"
               f"fade=t=out:st={max(0.0, duration - fade):.3f}:d={fade}")
    return vf


def extract_subclip(src, start, duration, out, *, width: int = 1920,
                    height: int = 1080, fps: int = 30, fade: float = 0.0) -> Path:
    """Extract ``[start, start+duration)`` of ``src`` to a normalized mp4 clip.

    Output is fit-and-padded to width×height@fps (so ``nolan assemble`` can concat
    heterogeneous sources), audio dropped.
    """
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    dur = float(duration)
    cmd = [FFMPEG, "-y", "-ss", str(start), "-i", str(src), "-t", f"{dur:.3f}",
           "-vf", normalize_vf(width, height, fps, fade, dur),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", "-r", str(fps),
           "-loglevel", "error", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"ffmpeg subclip failed: {r.stderr[-300:]}")
    return out


def extract_poster(src, t, out, *, width: int = 360) -> Path:
    """Extract a single frame at time ``t`` (seconds) of ``src`` to a jpg thumbnail.

    Input-seeking (``-ss`` before ``-i``) so it stays fast even on large files.
    """
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [FFMPEG, "-y", "-ss", f"{max(0.0, float(t)):.3f}", "-i", str(src),
           "-frames:v", "1", "-vf", f"scale={int(width)}:-2", "-q:v", "3",
           "-loglevel", "error", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"ffmpeg poster failed: {r.stderr[-300:]}")
    return out


def silent_audio(duration: float, out) -> Path:
    """Produce a silent stereo WAV of the given duration (lavfi anullsrc)."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [FFMPEG, "-y", "-f", "lavfi",
           "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
           "-t", f"{float(duration):.3f}", "-c:a", "pcm_s16le",
           "-loglevel", "error", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"silent audio failed: {r.stderr[-300:]}")
    return out
