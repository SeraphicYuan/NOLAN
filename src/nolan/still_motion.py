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


def render_split(left_img, right_img, out_path, duration: float = 4.0,
                 left_label: str = "", right_label: str = "", fps: int = 30) -> Path:
    """Render two stills as a SplitScreen 'collision' clip (the relational operator's payoff)."""
    from nolan import remotion_source
    out_path = Path(out_path)
    frames = max(30, int(round(duration * fps)))
    produced = remotion_source.render(
        "SplitScreen", {"leftLabel": left_label or "", "rightLabel": right_label or ""},
        out_path.name, duration_frames=frames,
        background=str(Path(left_img).resolve()), foreground=str(Path(right_img).resolve()))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if Path(produced).resolve() != out_path.resolve():
        import shutil
        shutil.copy(produced, out_path)
    return out_path


def render_stat_over(media_path, value, out_path, *, prefix: str = "", suffix: str = "",
                     caption: str = "", decimals: int = 0, theme=None, accent: str = "",
                     kind: str = "image", duration: float = 5.0, fps: int = 30) -> Path:
    """Render the SCALE count-up (StatOver) over a tangible-referent still or clip.

    Number + caption styling comes entirely from `theme` (resolveTheme in the composition),
    so the stat matches the rest of the video. kind='video' uses live footage as the backdrop.
    """
    from nolan import remotion_source
    out_path = Path(out_path)
    frames = max(30, int(round(duration * fps)))
    props = {"value": value, "prefix": prefix or "", "suffix": suffix or "",
             "caption": caption or "", "decimals": int(decimals or 0)}
    if theme:
        props["theme"] = theme
    if accent:
        props["accent"] = accent
    media = str(Path(media_path).resolve())
    kw = {"video": media} if kind == "video" else {"background": media}
    produced = remotion_source.render("StatOver", props, out_path.name, duration_frames=frames, **kw)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if Path(produced).resolve() != out_path.resolve():
        import shutil
        shutil.copy(produced, out_path)
    return out_path


def render_clip_montage(clips, out_path, transition: str = "fade", trans_frames: int = 16, fps: int = 30) -> Path:
    """Assemble b-roll clips/stills into one video with shot-to-shot transitions (ClipMontage).

    clips: list of {"path", "kind": "video"|"image", "duration": seconds}. transition applies
    between every pair (fade|slide|wipe|clockWipe|cut). Uses @remotion/transitions (no ffmpeg xfade).
    """
    from nolan import remotion_source
    out_path = Path(out_path)
    cards = [{"src": str(Path(c["path"]).resolve()), "kind": c.get("kind", "video"),
              "durationInFrames": max(1, int(round(c.get("duration", 3.0) * fps)))} for c in clips]
    n_trans = max(0, len(cards) - 1)
    transitions = [{"type": transition, "durationInFrames": trans_frames}] * n_trans
    overlap = 0 if transition == "cut" else trans_frames * n_trans
    total = max(30, sum(c["durationInFrames"] for c in cards) - overlap)
    produced = remotion_source.render("ClipMontage", {"transitions": transitions},
                                      out_path.name, duration_frames=total, cards=cards)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if Path(produced).resolve() != out_path.resolve():
        import shutil
        shutil.copy(produced, out_path)
    return out_path
