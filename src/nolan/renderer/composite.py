"""Composite an overlay renderer on top of a b-roll clip.

This is the piece that turns NOLAN from a "cut sequence of full-frame cards"
into layered video-essay grammar: a counter / lower-third / caption animating
*over* moving b-roll, instead of cutting away to a black card.

Design: keep `nolan assemble` a dumb concatenator. Each composite scene is
rendered here into a single self-contained mp4 (b-roll background + alpha
overlay), which assemble then concatenates like any other clip.

The overlay renderer must expose `render_frame_rgba(t) -> HxWx4 uint8` (every
`BaseRenderer` subclass does). Compositing is done with ffmpeg's `overlay`
filter over a PNG sequence, so it does not depend on MoviePy's mask API.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image


def _ffmpeg_exe(ffmpeg: Optional[str]) -> str:
    if ffmpeg:
        return ffmpeg
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def composite_over_broll(
    overlay_renderer,
    broll_path: str,
    output_path: str,
    duration: float,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    fade: float = 0.0,
    scrim: float = 0.0,
    ffmpeg: Optional[str] = None,
) -> str:
    """Render `overlay_renderer` over the b-roll at `broll_path` -> `output_path`.

    Args:
        overlay_renderer: a BaseRenderer; its background is made transparent.
        broll_path: background video (any size; scaled+cropped to width x height).
        duration: scene duration in seconds (overlay + trimmed background).
        fade: optional fade in/out (seconds) applied to the *background* b-roll.
        scrim: 0..1 black overlay on the b-roll to keep overlaid text legible.
    """
    ff = _ffmpeg_exe(ffmpeg)
    overlay_renderer.timeline.duration = duration
    n_frames = max(1, int(round(duration * fps)))

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for i in range(n_frames):
            rgba = overlay_renderer.render_frame_rgba(i / fps)
            Image.fromarray(rgba.astype(np.uint8), "RGBA").save(td / f"ov_{i:05d}.png")

        # Background: scale to cover, center-crop to exact WxH, normalize fps.
        bg_chain = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps={fps}"
        )
        if scrim and scrim > 0:
            bg_chain += f",drawbox=x=0:y=0:w={width}:h={height}:color=black@{min(1.0, scrim)}:t=fill"
        if fade and fade > 0:
            bg_chain += f",fade=t=in:st=0:d={fade},fade=t=out:st={max(0.0, duration - fade)}:d={fade}"

        cmd = [
            ff, "-y",
            "-i", str(broll_path),
            "-framerate", str(fps), "-i", str(td / "ov_%05d.png"),
            "-filter_complex",
            f"[0:v]{bg_chain}[bg];[bg][1:v]overlay=0:0:format=auto[v]",
            "-map", "[v]",
            "-t", str(duration),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
            "-loglevel", "error", str(output_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"composite ffmpeg failed: {r.stderr[-800:]}")
    return str(output_path)
