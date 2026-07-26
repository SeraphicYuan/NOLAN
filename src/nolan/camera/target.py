"""Where to aim the camera — saliency first, relevance only when it is worth a model call.

TWO LANES, and the difference is the whole design.

`subject_point()` is rembg's foreground CENTROID (the same signal `still_motion.subject_center`
already pushes into on the legacy path). For one clear subject it is exactly right, free of any model
API, and deterministic. For TWO people it aims at the GAP BETWEEN THEM, and for any image it cannot
tell you which subject the SENTENCE is about — a logo in the corner, one face in a crowd, the clause
in a contract.

`subject_box()` is the VLM lane, and it buys RELEVANCE, not detection. Given the beat's narration it
returns a box for the thing being talked about. That is the only reason to spend a model call here,
and it is why the lane is opt-in rather than default: a push at the salient subject is usually right,
and paying a VLM call per still to confirm it would be waste.

Everything is cached in a `<image>.camera.json` sidecar (the pattern `subject_center` established) so
a re-render never re-runs a model, and everything is fail-soft: a missing file, a missing dependency
or a model that returns nonsense costs you the targeting, never the render.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

SIDECAR_SUFFIX = ".camera.json"
_MEM: Dict[str, dict] = {}


# --- the sidecar ------------------------------------------------------------------------------------

def _sidecar(path: Path) -> Path:
    return path.parent / (path.name + SIDECAR_SUFFIX)


def _load(path: Path) -> dict:
    key = str(path)
    if key in _MEM:
        return _MEM[key]
    data = {}
    sc = _sidecar(path)
    if sc.exists():
        try:
            data = json.loads(sc.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    _MEM[key] = data
    return data


def _save(path: Path, data: dict) -> None:
    _MEM[str(path)] = data
    try:
        _sidecar(path).write_text(json.dumps(data, indent=1), encoding="utf-8")
    except OSError:
        pass                                            # a read-only pool must not break a render


# --- lane 1: saliency (deterministic, no model) -------------------------------------------------------

def image_size(path) -> Optional[Tuple[int, int]]:
    """(w, h) — the camera needs it for the long-axis decision and the resolution floor."""
    p = Path(path)
    cached = _load(p).get("size")
    if cached:
        return tuple(cached)
    try:
        from PIL import Image
        with Image.open(p) as im:
            size = (int(im.width), int(im.height))
    except Exception:
        return None
    d = _load(p)
    d["size"] = list(size)
    _save(p, d)
    return size


def subject_point(path, cache: bool = True) -> Optional[Tuple[float, float]]:
    """Salient subject centroid (x, y in 0..1), or None.

    Clamped away from the extreme edges: a centroid at 0.02 asks for a framing the solver would have to
    clamp anyway, and a subject that close to the border reads as a crop, not a composition.
    """
    p = Path(path)
    d = _load(p) if cache else {}
    if "point" in d:
        pt = d["point"]
        return tuple(pt) if pt else None
    point = None
    try:
        import numpy as np
        from nolan.cutout import remove_background
        rgba = remove_background(p)
        alpha = np.asarray(rgba.split()[-1])
        ys, xs = np.where(alpha > 40)
        if xs.size >= 50:
            cx, cy = float(xs.mean()) / rgba.width, float(ys.mean()) / rgba.height
            point = (round(min(max(cx, 0.15), 0.85), 4), round(min(max(cy, 0.15), 0.85), 4))
    except Exception as e:                              # rembg missing, weights absent, decode error…
        logger.debug("subject_point(%s) unavailable: %s", p, e)
    if cache:
        d = _load(p)
        d["point"] = list(point) if point else None
        _save(p, d)
    return point


def cutout_path(path, cache: bool = True) -> Optional[Path]:
    """An RGBA cutout of the subject on disk (for `parallax`), or None.

    Written next to the source as `<stem>.fg.png`, so the composer can reference it like any other
    asset and the assemble step stages it with everything else.
    """
    p = Path(path)
    d = _load(p) if cache else {}
    if "cutout" in d:
        fg = d["cutout"]
        return (p.parent / fg) if fg and (p.parent / fg).exists() else None
    out = None
    try:
        from nolan.cutout import remove_background
        rgba = remove_background(p)
        import numpy as np
        alpha = np.asarray(rgba.split()[-1])
        if (alpha > 40).sum() >= 50:
            fg = p.parent / (p.stem + ".fg.png")
            rgba.save(fg)
            out = fg
    except Exception as e:
        logger.debug("cutout(%s) unavailable: %s", p, e)
    if cache:
        d = _load(p)
        d["cutout"] = out.name if out else None
        _save(p, d)
    return out


# --- lane 2: relevance (a model call, opt-in) ---------------------------------------------------------

_BOX_PROMPT = (
    "You are framing a camera move on this image for a documentary narration.\n"
    "The narrator says: \"{narration}\"\n"
    "Return STRICT JSON only:\n"
    '{{"box": [x, y, w, h], "label": "<what is in the box>", "confident": true|false}}\n'
    "x,y,w,h are fractions of the image (0..1), x,y = top-left corner of the region the narration is "
    "about. If the narration is not about any specific visible region, set confident=false and return "
    "the whole frame."
)


def _parse_box(raw: str) -> Optional[dict]:
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    box = d.get("box")
    if not (isinstance(box, (list, tuple)) and len(box) == 4):
        return None
    try:
        x, y, w, h = (float(v) for v in box)
    except (TypeError, ValueError):
        return None
    if not (0 <= x <= 1 and 0 <= y <= 1) or w <= 0 or h <= 0:
        return None
    w, h = min(w, 1 - x), min(h, 1 - y)
    if w < 0.02 or h < 0.02:                            # a sliver is a parse artefact, not a subject
        return None
    return {"box": [round(x, 4), round(y, 4), round(w, 4), round(h, 4)],
            "label": str(d.get("label") or "")[:120], "confident": bool(d.get("confident", True))}


def subject_box(path, narration: str = "", *, enabled: Optional[bool] = None,
                cache: bool = True) -> Optional[dict]:
    """{box, label, confident} for what the NARRATION is about, or None.

    Off unless asked (`NOLAN_CAMERA_VLM=1` or `enabled=True`): the deterministic lane covers the common
    case, and a model call per still to re-confirm a subject we already found is spend without a
    decision attached. Cached per (image, narration) so a re-render is free.
    """
    if enabled is None:
        enabled = os.environ.get("NOLAN_CAMERA_VLM", "").strip() in ("1", "true", "yes")
    p = Path(path)
    key = "box:" + re.sub(r"\s+", " ", (narration or "").strip().lower())[:160]
    d = _load(p) if cache else {}
    if key in d:
        return d[key]
    if not enabled:
        return None
    out = None
    try:
        import asyncio

        from nolan.vision import VisionConfig, create_vision_provider
        provider = create_vision_provider(VisionConfig())
        raw = asyncio.run(provider.describe_image(p, _BOX_PROMPT.format(narration=narration or "")))
        out = _parse_box(raw)
        if out and not out.get("confident"):
            out = None                                  # an unconfident box is worse than none
    except Exception as e:
        logger.debug("subject_box(%s) unavailable: %s", p, e)
    if cache:
        d = _load(p)
        d[key] = out
        _save(p, d)
    return out


# --- what the camera may actually ask for --------------------------------------------------------

def capabilities(path=None, *, narration: str = "", want: Sequence[str] = ()) -> set:
    """The `needs` the registry may treat as available for this asset.

    `target` is always available — the centre is a legitimate target and every move that needs one can
    fall back to it. `cutout` and `box` are probed ONLY when a move actually wants them, so selecting a
    push never pays for a matte it will not use.
    """
    avail = {"target"}
    if path is None:
        return avail
    p = Path(path)
    if not p.exists():
        return avail
    if "cutout" in want and cutout_path(p):
        avail.add("cutout")
    if "box" in want:
        got = subject_box(p, narration)
        if got:
            avail.add("box")
            avail.add("detection")
    return avail
