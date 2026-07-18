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
# CSS mix-blend-mode -> ffmpeg `blend=all_mode=` name (the baked path must match the render-time CSS blend).
_FF_BLEND = {"screen": "screen", "multiply": "multiply", "overlay": "overlay", "lighten": "lighten",
             "darken": "darken", "soft-light": "softlight", "hard-light": "hardlight",
             "color-dodge": "dodge", "color-burn": "burn", "normal": "normal"}


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


# ---- effects "treat" op (the baked per-asset path of the effects umbrella) --------------------------
def _treat_cmd(ff, src, out, p, mt) -> List[str]:
    """Bake effect TREATMENTS onto an asset (destructive-to-a-copy, like crop): colour/grain via a -vf
    chain, and element/damage effects by compositing their plate (screen blend, per-effect opacity).
    A plate overlay on an IMAGE yields a VIDEO (the still, animated under the looping plate)."""
    from nolan.effects.registry import normalize_treatments, FFMPEG_VF
    from nolan.effects.library import resolve_plate
    vf, plates = [], []
    for n in normalize_treatments(p.get("effects", [])):
        e = n["effect"]
        if e.id in FFMPEG_VF:                                   # colour / grain look
            vf.append(FFMPEG_VF[e.id])
        elif e.method == "blend_overlay" and e.plate:           # fire/rain/… → composite its plate
            pth = resolve_plate(e.plate)
            if pth:
                plates.append((pth, n["opacity"]))
    if not vf and not plates:
        raise ValueError("no bakeable effects selected (scanlines etc. are render-time only)")
    chain = ",".join(vf)
    is_img = mt == "image"
    pv = bool(p.get("preview"))                                # modal "Preview result" → a low-res, short REAL bake
    scale = "scale=480:-2" if pv else ""                       # cap width so the preview bake is fast
    if not plates:                                             # single-input colour/grain
        vfc = ",".join(x for x in (chain, scale) if x)
        if is_img:
            return [ff, "-y", "-i", str(src), "-vf", vfc, "-frames:v", "1", "-update", "1", str(out)]
        return [ff, "-y", "-i", str(src), "-vf", vfc, *_VENC, "-c:a", "copy", *(["-t", "1.5"] if pv else []), str(out)]
    cmd = [ff, "-y"]                                            # plate overlay(s) → video out
    cmd += (["-loop", "1", "-i", str(src)] if is_img else ["-i", str(src)])
    for pth, _o in plates:
        cmd += ["-stream_loop", "-1", "-i", pth]                # loop the plate under the base
    # blend in RGB (gbrp): `screen` is a per-channel op — screen-mixing YUV chroma planes casts colour (a
    # fire plate → magenta). Convert base + each plate to gbrp, blend, then back to yuv420p for the encoder.
    base_pre = ",".join(x for x in (chain, scale, "format=gbrp") if x)
    fc = [f"[0:v]{base_pre}[b0]"]
    base = "b0"
    for i, (pth, op) in enumerate(plates, start=1):             # scale plate to the base, screen-blend at opacity
        fc.append(f"[{i}:v]format=gbrp[pf{i}]")
        fc.append(f"[pf{i}][{base}]scale2ref[pp{i}][bb{i}]")
        fc.append(f"[bb{i}][pp{i}]blend=all_mode=screen:all_opacity={op:.3f}[b{i}]")
        base = f"b{i}"
    fc.append(f"[{base}]format=yuv420p[vout]")
    cmd += ["-filter_complex", ";".join(fc), "-map", "[vout]"]
    if not is_img:
        cmd += ["-map", "0:a?", "-c:a", "copy"]
    dur = "1.5" if pv else ("8" if is_img else None)           # preview: 1.5s; still+plate: 8s loop; video: its own length
    tail = ["-t", dur] if dur else ["-shortest"]
    return cmd + _VENC + tail + [str(out)]


def _treat_ext(src: Path, params: Dict):
    """A plate overlay turns an IMAGE into a video → .mp4; otherwise keep the source's own extension."""
    if media_type(src) != "image":
        return None
    from nolan.effects.registry import normalize_treatments
    for n in normalize_treatments((params or {}).get("effects", [])):
        e = n["effect"]
        if e.method == "blend_overlay" and e.plate:
            return ".mp4"
    return None


# ---- non-ffmpeg ops ---------------------------------------------------------------------------------
def _removebg_fn(src: Path, out: Path, p: Dict) -> None:
    """rembg cutout → RGBA PNG. CPU (off the GPU lock); slower than the ffmpeg ops → run as a job."""
    from nolan.cutout import remove_background
    img = remove_background(str(src), model=p.get("model", "birefnet"))
    img.save(str(out))


def _cleanup_cmd(ff, src, out, p, mt) -> List[str]:
    """Composite AUTO-cleanup: apply a precomputed PLAN (logo/caption crop + head/tail trim) in ONE ffmpeg
    pass. The plan comes from nolan.hyperframes.cleanup.analyze() (with the OpenRouter vision confirm) via
    params['plan'], so this stays a pure argv builder — image OR video."""
    from nolan.hyperframes.cleanup import build_cmd
    plan = p.get("plan")
    if not plan:
        raise ValueError("cleanup needs a precomputed plan — analyze the asset first")
    return build_cmd(ff, Path(src), Path(out), plan)


def _cleanup_ext(src: Path, params: Dict):
    return Path(src).suffix if (params.get("plan") or {}).get("kind") == "image" else ".mp4"


# ---- registry (extend by adding one entry) ----------------------------------------------------------
QUICK_EDITS: Dict[str, Dict] = {
    "crop": {"label": "Crop", "media": ("image", "video"), "ui": "crop", "cmd": _crop_cmd},
    "trim": {"label": "Trim", "media": ("video",), "ui": "trim", "cmd": _trim_cmd},
    "fit": {"label": "Fit to scene", "media": ("video",), "ui": "auto", "cmd": _fit_cmd},
    "remove_bg": {"label": "Remove background", "media": ("image",), "ui": "button",
                  "background": True, "out_ext": ".png", "fn": _removebg_fn},
    "treat": {"label": "Effects", "media": ("image", "video"), "ui": "treat",
              "cmd": _treat_cmd, "out_ext": _treat_ext},
    "cleanup": {"label": "Clean up (auto)", "media": ("image", "video"), "ui": "auto",
                "background": True, "cmd": _cleanup_cmd, "out_ext": _cleanup_ext},
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
