"""Where to aim the camera — saliency first, relevance only when it is worth a model call.

TWO LANES, and the difference is the whole design.

`subject_point()` is a CONTRAST centroid on a 64px thumbnail by default — no model, ~10ms — because a
target point exists to aim a push, not to cut a matte. (`precise=True` uses rembg's foreground centroid
instead, the signal `still_motion.subject_center` uses on the legacy path.) Either way it is a saliency
answer: for TWO people it aims at the GAP BETWEEN THEM, and for any image it cannot tell you which
subject the SENTENCE is about — a logo in the corner, one face in a crowd, the clause in a contract.

The default matters for a reason that only showed up under measurement: rembg took ~20s on a cold call,
and the camera wants a target for nearly every image ground, so a 35-asset comp would have added minutes
to a compose that takes seconds — for a decision a contrast centroid answers just as well.

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


BORDER_MIN = 0.015          # below this a "border" is a dark edge in the picture, not a surround
BORDER_MAX = 0.30           # above this we are cropping the subject, not a border — distrust it
_PURITY = 0.95              # a border strip is ~entirely surround; a dark photo edge is not
_TOL = 16.0                 # grey levels from the corner colour still counted as "the surround"


def content_box(path) -> Optional[Tuple[float, float, float, float]]:
    """The picture INSIDE the file: (x0, y0, x1, y1) as fractions, cropping a flat surround.

    Why the camera needs this. `ka_a_diamond_is_forever_document_2.jpg` is not the 1947 ad — it is a
    PHOTOGRAPH of the ad, lying on black, shot slightly askew. Measured: a black margin of 7.7% on the
    left and 11.8% on the right (p90 11.3% / 18.8%, asymmetric because of the tilt). Long-axis panning
    it width-fits the FILE, so the pan travels across that black and the module's own rule — never
    expose an edge — breaks on the axis it is not moving along. The first attempt at this was a
    symmetric 6% overscan, which is the right instinct with a made-up number: it cannot remove 11.8%
    on one side and 7.7% on the other, and on an unbordered source it silently crops real picture.

    So measure instead of guess. Rows/columns are scanned from each edge inward while they stay flat
    (low spread) and close to the corner colour, which catches a black photo surround, a white scan
    margin and a letterboxed still alike. Bounded on both ends: under `BORDER_MIN` there is nothing
    worth cropping, and over `BORDER_MAX` the "border" is more likely the picture (a dark vignette, a
    night sky) — in both cases the full frame is returned and the camera behaves exactly as before.
    A strip counts as surround only if it is ~entirely surround (`_PURITY`), which is what separates a
    real border from a dark edge in a photograph: across the diamond-v2 pool that gate takes the
    false-positive rate from "nearly every asset" (a naive percentile fires on 40 of 47) to the 14 that
    genuinely carry one. The price is that the box is CONSERVATIVE on a TILTED source — a strip stops
    being pure the moment one row's page corner enters it — so on that ad it removes ~3% of the ~8-12%
    black. The rest is a wedge that no axis-aligned crop can take; deskewing the asset is the fix, and
    it belongs to asset cleanup, not to the camera.

    (A residual measure was tried here and removed: "how much of the kept edge is still surround-
    coloured" reads 0.42 on the tilted black ad and 0.87 on a white document whose page is simply
    white. A warning that fires on every clean scan is worse than no warning.)

    Cached in the sidecar; ~15ms on a 128px thumbnail. None if the file can't be read."""
    p = Path(path)
    cached = _load(p).get("content_box")
    if cached:
        return tuple(cached)
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        return None
    try:
        with Image.open(p) as im:
            a = np.asarray(im.convert("L").resize((128, 128), Image.BILINEAR), dtype=float)
    except (OSError, ValueError):
        return None

    n = 128
    ref = float(np.median([a[:3, :3], a[:3, -3:], a[-3:, :3], a[-3:, -3:]]))
    m = np.abs(a - ref) <= _TOL                                   # True where the pixel IS the surround
    if m.mean() > 0.9:
        # The whole file matches the "surround" colour — a flat card, a near-empty scan, a solid plate.
        # Every strip then passes the purity gate and the scan runs to BORDER_MAX, "finding" a 30%
        # border on all four sides of an image that has none. There is no picture to distinguish from
        # a border here, so there is no crop to make.
        _save(p, dict(_load(p), content_box=[0.0, 0.0, 1.0, 1.0]))
        return (0.0, 0.0, 1.0, 1.0)

    def _depth(mask) -> float:
        """Deepest leading strip of `mask` (columns) that is at least `_PURITY` surround."""
        best = 0
        for d in range(1, int(n * BORDER_MAX) + 1):
            if mask[:, :d].mean() >= _PURITY:
                best = d
            else:
                break
        return best / n

    left, right = _depth(m), _depth(m[:, ::-1])
    top, bottom = _depth(m.T), _depth(m.T[:, ::-1])
    left, right, top, bottom = (0.0 if v < BORDER_MIN else v for v in (left, right, top, bottom))
    box = (left, top, 1.0 - right, 1.0 - bottom)
    _save(p, dict(_load(p), content_box=list(box)))
    return box


def _energy_point(path) -> Optional[Tuple[float, float]]:
    """Attention centroid from local CONTRAST on a 64px thumbnail — no model, ~10ms.

    This is the default because of what a target point is FOR: aiming a push, not cutting a matte. A
    matte is pixel-accurate and costs a rembg pass; a point needs to land on the interesting half of
    the frame. Measured: rembg took ~20s on a first call, and the camera wants a target for nearly
    every image ground — that is minutes added to a compose that took seconds, on a decision that a
    contrast centroid answers just as well. rembg stays where the matte IS the product (parallax,
    rack-focus) and as an explicit upgrade.
    """
    try:
        from PIL import Image, ImageFilter
        with Image.open(path) as im:
            g = im.convert("L").resize((64, 64), Image.BOX)
        edges = g.filter(ImageFilter.FIND_EDGES)
        px = list(edges.getdata())
        tot = sum(px)
        if tot <= 0:
            return None
        sx = sum(v * (i % 64) for i, v in enumerate(px)) / tot / 63.0
        sy = sum(v * (i // 64) for i, v in enumerate(px)) / tot / 63.0
        return (round(min(max(sx, 0.15), 0.85), 4), round(min(max(sy, 0.15), 0.85), 4))
    except Exception as e:
        logger.debug("_energy_point(%s) unavailable: %s", path, e)
        return None


def subject_point(path, cache: bool = True, precise: bool = False) -> Optional[Tuple[float, float]]:
    """Salient subject centroid (x, y in 0..1), or None.

    `precise=True` uses the rembg matte's centroid (slower, exact); the default is the contrast
    centroid above. Clamped away from the extreme edges either way: a centroid at 0.02 asks for a
    framing the solver would only have to clamp back, and a subject that close to the border reads as a
    crop rather than a composition.
    """
    p = Path(path)
    key = "point_precise" if precise else "point"
    d = _load(p) if cache else {}
    if key in d:
        pt = d[key]
        return tuple(pt) if pt else None
    point = None
    if precise:
        try:
            import numpy as np
            from nolan.cutout import remove_background
            rgba = remove_background(p)
            alpha = np.asarray(rgba.split()[-1])
            ys, xs = np.where(alpha > 40)
            if xs.size >= 50:
                cx, cy = float(xs.mean()) / rgba.width, float(ys.mean()) / rgba.height
                point = (round(min(max(cx, 0.15), 0.85), 4), round(min(max(cy, 0.15), 0.85), 4))
        except Exception as e:                          # rembg missing, weights absent, decode error…
            logger.debug("subject_point(%s, precise) unavailable: %s", p, e)
    if point is None:
        point = _energy_point(p)
    if cache:
        d = _load(p)
        d[key] = list(point) if point else None
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
