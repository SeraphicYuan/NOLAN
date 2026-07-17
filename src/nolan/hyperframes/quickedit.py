"""Fast asset "quick edits" for the /hyperframes edit page. A small REGISTRY so each new op is one entry.

An op is `{label, media, ui, cmd|fn, background?}`:
  - `cmd(ff, src, out, params, mt) -> [ffmpeg argv]`  — an ffmpeg op (crop / trim / fit). Runs synchronously
    (fast: a few-second clip is ~0.1-2s), so it's inline in the edit page.
  - `fn(src, out, params) -> None`                    — a non-ffmpeg op (remove_bg via rembg). Marked
    `background: True` → the route runs it as a job (it's the slow one).
  - `ui`: how the edit UI presents it — `crop` (drag a rect), `trim` (mark in/out on a scrubber),
    `auto` (applied automatically, no modal), `button` (one click).

Comp-level orchestration (in-place vs new-pool-asset, the reversible backup, jobs) lives in
`nolan.hyperframes.edit` (quickedit_asset / removebg_asset / fit_ground_to_scene).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List

_IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_VENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-movflags", "+faststart"]


def _ffmpeg() -> str:
    from nolan.hf_qa import _ffmpeg as ff
    return ff()


def media_type(path: Path) -> str:
    return "image" if Path(path).suffix.lower() in _IMG_EXT else "video"


# ---- ffmpeg command builders ------------------------------------------------------------------------
def _crop_cmd(ff, src, out, p, mt) -> List[str]:
    x, y, w, h = (int(round(float(p[k]))) for k in ("x", "y", "w", "h"))
    if w <= 0 or h <= 0:
        raise ValueError("crop width/height must be positive")
    if x < 0 or y < 0:
        raise ValueError("crop x/y must be >= 0")
    vf = f"crop={w}:{h}:{x}:{y}"
    if mt == "image":
        return [ff, "-y", "-i", str(src), "-vf", vf, "-frames:v", "1", "-update", "1", str(out)]
    return [ff, "-y", "-i", str(src), "-vf", vf, *_VENC, "-c:a", "copy", str(out)]


def _trim_cmd(ff, src, out, p, mt) -> List[str]:
    start, end = float(p["start"]), float(p["end"])
    if end <= start:
        raise ValueError("trim out point must be after the in point")
    # input-seek + re-encode → frame-accurate cut of [start, end]
    return [ff, "-y", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{end - start:.3f}", *_VENC, "-c:a", "aac", str(out)]


def _atempo_chain(speed: float) -> str:
    """audio tempo for a speed factor — the atempo filter clamps to [0.5, 2.0], so chain for extremes."""
    parts, s = [], speed
    while s > 2.0:
        parts.append("atempo=2.0"); s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5"); s *= 2.0
    parts.append(f"atempo={s:.6f}")
    return ",".join(parts)


def _fit_cmd(ff, src, out, p, mt) -> List[str]:
    """Retime a video so its WHOLE duration becomes `target` seconds (speed = src_dur/target; >1 faster)."""
    target, src_dur = float(p["target"]), float(p["src_dur"])
    if target <= 0 or src_dur <= 0:
        raise ValueError("fit needs positive target and source durations")
    speed = src_dur / target
    cmd = [ff, "-y", "-i", str(src), "-vf", f"setpts={1.0 / speed:.6f}*PTS", "-af", _atempo_chain(speed), *_VENC, str(out)]
    return cmd


# ---- non-ffmpeg ops ---------------------------------------------------------------------------------
def _removebg_fn(src: Path, out: Path, p: Dict) -> None:
    """rembg cutout → RGBA PNG. CPU (off the GPU lock); slower than the ffmpeg ops → run as a job."""
    from nolan.cutout import remove_background
    img = remove_background(str(src), model=p.get("model", "birefnet"))
    img.save(str(out))


# ---- registry (extend by adding one entry) ----------------------------------------------------------
QUICK_EDITS: Dict[str, Dict] = {
    "crop": {"label": "Crop", "media": ("image", "video"), "ui": "crop", "cmd": _crop_cmd},
    "trim": {"label": "Trim", "media": ("video",), "ui": "trim", "cmd": _trim_cmd},
    "fit": {"label": "Fit to scene", "media": ("video",), "ui": "auto", "cmd": _fit_cmd},
    "remove_bg": {"label": "Remove background", "media": ("image",), "ui": "button",
                  "background": True, "out_ext": ".png", "fn": _removebg_fn},
}


def apply_quick_edit(src: Path, op: str, params: Dict, out: Path) -> Path:
    """Run ONE quick-edit op `src -> out`. Dispatches to the op's ffmpeg `cmd` or its python `fn`."""
    if op not in QUICK_EDITS:
        raise ValueError(f"unknown quick-edit {op!r} (have: {', '.join(QUICK_EDITS)})")
    spec = QUICK_EDITS[op]
    mt = media_type(src)
    if mt not in spec["media"]:
        raise ValueError(f"'{op}' is not available for a {mt}")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if "fn" in spec:
        spec["fn"](Path(src), out, params)
    else:
        cmd = spec["cmd"](_ffmpeg(), Path(src), out, params, mt)
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        if r.returncode != 0 or not out.exists() or out.stat().st_size == 0:
            raise RuntimeError(f"{op} failed: {(r.stderr or '')[-240:]}")
    if not (out.exists() and out.stat().st_size > 0):
        raise RuntimeError(f"{op} produced no output")
    return out
