"""Render a single still into a moving shot via the `StillMotion` Remotion effect.

Turns a photo into video-essay b-roll with a MOTIVATED motion:
  ken-burns-in / -out / -pan  — camera zooms/pans with its origin on the salient subject
  parallax                    — sharp subject cutout (rembg) over a blurred, slower background

The salient target (and the parallax foreground) are derived from a rembg cutout, so a
push-in actually pushes *into the subject*. Pairs with `motion_select` (which picks the id)
and the pairing engine (which picks the asset).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

_TREATMENTS = {"ken-burns-in", "ken-burns-out", "ken-burns-pan", "parallax",
               "rack-focus", "blur-in", "atmospheric", "hold"}
_NEED_CUTOUT = {"parallax", "rack-focus"}


def _salient(image_path, want_cutout: bool, out_dir: Path):
    """Return ({x,y} salient target in 0..1, cutout_png_path|None) from a rembg mask."""
    import numpy as np
    from nolan.cutout import remove_background
    rgba = remove_background(image_path)                 # PIL RGBA (subject kept, bg transparent)
    alpha = np.asarray(rgba.split()[-1])
    ys, xs = np.where(alpha > 40)
    target = {"x": 0.5, "y": 0.5}
    if xs.size >= 50:
        cx, cy = float(xs.mean()) / rgba.width, float(ys.mean()) / rgba.height
        target = {"x": min(max(cx, 0.15), 0.85), "y": min(max(cy, 0.15), 0.85)}
    fg = None
    if want_cutout and xs.size >= 50:
        fg = out_dir / (Path(image_path).stem + ".fg.png")
        rgba.save(fg)
    return target, fg


def render_still(image_path, motion_id: str = "ken-burns-in", out_path=None,
                 duration: float = 4.0, direction: str = "right") -> Path:
    """Render `image_path` to an mp4 with the chosen motion. Returns the mp4 path."""
    from nolan import remotion_source
    image_path = Path(image_path)
    out_path = Path(out_path) if out_path else image_path.with_suffix(".motion.mp4")
    treatment = motion_id if motion_id in _TREATMENTS else "ken-burns-in"

    target, fg = {"x": 0.5, "y": 0.5}, None
    if treatment != "hold":
        try:
            target, fg = _salient(image_path, want_cutout=(treatment in _NEED_CUTOUT), out_dir=out_path.parent)
        except Exception:
            pass
    if treatment in _NEED_CUTOUT and not fg:
        treatment = "ken-burns-in"                       # no subject found → graceful fallback

    frames = max(30, int(round(duration * 30)))
    produced = remotion_source.render(
        "StillMotion", {"treatment": treatment, "target": target, "direction": direction},
        out_path.name, duration_frames=frames,
        background=str(image_path.resolve()), foreground=(str(Path(fg).resolve()) if fg else None),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if Path(produced).resolve() != out_path.resolve():
        import shutil
        shutil.copy(produced, out_path)
    return out_path
