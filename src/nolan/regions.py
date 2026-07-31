"""Where the subject IS — labelled boxes, produced by a DETECTOR, never by prose.

`imagelib.catalog.regions` has shipped as an unpopulated column since the discovery tier landed.
It was consumer-blocked; the camera umbrella un-blocked it by landing
`camera.solve.solve_push(target=(x, y))`, which frames both keyframes on the same point so a push
holds its subject instead of drifting off it. **The missing half was the producer, and this is
it.**

## Why this is not a vision-model field

It was tried. A 50-row validation asked a VLM for `focal_zone` — one cell of a 3x3 grid — and it
answered `mc` (middle-centre) on **50 of 50**. Not occasionally wrong: constant. `open_zones`
behaved the same way, returning one of two templates for 38 of 50 images. A language model can
say *what* is in a picture; it cannot say *where*, because it is not measuring.

    The model NAMES. A detector LOCALISES. Never raw coordinates from prose.

So the producer is a matting/saliency detector, and the label vocabulary stays closed.

## Two tiers, because accuracy costs a model load

* **`matting`** — `rembg` (U2Net). Accurate, and the right answer for a portrait, but it loads a
  ~170 MB model and runs in the high hundreds of milliseconds. Used when asked for.
* **`energy`** — the fallback and the default: subject mass estimated from gradient energy inside
  the measured content box (`nolan.pixels`). No model, ~2 ms, and good enough for the FIRST
  payoff, which is crop safety rather than the zoom: knowing that the subject sits left-of-centre
  is what stops a 16:9 `cover` decapitating a portrait.

Both report `conf`, and a caller that needs certainty can require the matting tier. A region with
low confidence is still better than a hardcoded centre — but it says so.

## Characterised on 24 real museum rows spanning every image_kind

17 located, 7 declined. The boxes are tight (a carved Veranda Post at conf 0.87, a seated Buddha,
a pastel portrait), and every decline is a genuinely full-bleed composition — Caillebotte's
*Paris Street; Rain*, Van Gogh's *Bedroom*, a landscape photograph — where detail covers the
frame and there is no single thing to push into. Declining there is the answer, not a failure.

**One honest limitation.** On a `panel_count: pair` row — a coin photographed showing both faces
— the box correctly spans BOTH faces, which puts its centre in the empty ground between them. A
push on that point closes on nothing. The fix is not more precision here; it is that a caller
holding `caption.panel_count == "pair"` should target one panel rather than the pair's centroid.
Recorded rather than silently shipped, because a focal point that is confidently in the gap is
worse than none.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Closed vocabulary. `subject` is what this module produces today; the others are reserved for
# the passes that will fill them, and naming them here keeps a future detector from inventing a
# parallel spelling (checklist class 3).
REGION_LABELS = ("subject", "face", "text", "watermark", "negative_space")
REGION_KINDS = ("matting", "energy", "vlm-named")

# A "subject" box covering more than this share of the frame is not a subject — it is a picture
# with detail everywhere. Returning None there is more useful than asserting a box that means
# "all of it".
_NO_SUBJECT_AREA = 0.70


@dataclass
class Region:
    label: str
    kind: str
    box: Tuple[float, float, float, float]      # (x0, y0, x1, y1) as FRACTIONS of the frame
    conf: float

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def centre(self) -> Tuple[float, float]:
        x0, y0, x1, y1 = self.box
        return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


def _energy_subject(path) -> Optional[Region]:
    """Subject mass from gradient energy inside the content box. No model.

    Dead margin is excluded first (via `nolan.pixels`), which matters more than it sounds: on a
    coin photograph 31% content, the energy centroid of the FULL frame is dragged toward the
    middle of a grey field that contains nothing.
    """
    import numpy as np
    from PIL import Image

    from nolan.pixels import measure

    facts = measure(path)
    if facts is None:
        return None
    try:
        with Image.open(path) as im:
            im = im.convert("L")
            im.thumbnail((512, 512))
            g = np.asarray(im, dtype=np.float32) / 255.0
    except Exception:
        return None
    if g.shape[0] < 8 or g.shape[1] < 8:
        return None

    h, w = g.shape
    # content box is in full-res pixels; rescale to this working array
    cx0, cy0, cx1, cy1 = facts.content_box
    sx, sy = w / max(1, facts.width), h / max(1, facts.height)
    x0, y0 = int(cx0 * sx), int(cy0 * sy)
    x1, y1 = max(x0 + 2, int(cx1 * sx)), max(y0 + 2, int(cy1 * sy))
    inner = g[y0:y1, x0:x1]
    if inner.size < 16:
        return None

    gy, gx = np.gradient(inner)
    e = np.hypot(gx, gy)
    if float(e.sum()) <= 1e-6:
        return None
    # Keep the energetic part: everything above the 70th percentile of local detail.
    thr = float(np.percentile(e, 70))
    mask = e >= thr
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return None

    # Trim the extreme 5% each way so a single bright speck cannot define the box.
    bx0, bx1 = np.percentile(xs, [5, 95])
    by0, by1 = np.percentile(ys, [5, 95])
    box = ((x0 + bx0) / w, (y0 + by0) / h, (x0 + bx1) / w, (y0 + by1) / h)

    # CONFIDENCE = how much of the frame the located box does NOT cover.
    #
    # The first version used the share of above-threshold pixels, which is a constant by
    # construction: the threshold IS the 70th percentile, so that share is always ~0.30 and the
    # confidence was always 0.24 — exactly the dead-field failure this module exists to replace,
    # reproduced inside the replacement. Caught by the test that asserts a busy full-bleed image
    # yields nothing.
    #
    # Box area is a real measurement: a compact subject leaves most of the frame empty, while a
    # picture with detail everywhere produces a box that fills it.
    area = max(0.0, (box[2] - box[0])) * max(0.0, (box[3] - box[1]))
    if area > _NO_SUBJECT_AREA:
        return None          # detail everywhere: nothing to push into, and saying so is useful
    return Region(label="subject", kind="energy",
                  box=tuple(round(float(v), 4) for v in box),
                  conf=round(float(max(0.0, min(1.0, 1.0 - area))), 3))


def _matting_subject(path) -> Optional[Region]:
    """Subject box from `rembg`'s alpha matte. Accurate; loads a ~170 MB model."""
    import numpy as np
    from PIL import Image

    try:
        from rembg import remove
    except Exception:
        return None
    try:
        with Image.open(path) as im:
            cut = remove(im.convert("RGBA"))
        alpha = np.asarray(cut.split()[-1], dtype=np.float32) / 255.0
    except Exception:
        return None
    if alpha.size == 0:
        return None
    h, w = alpha.shape
    mask = alpha > 0.5
    ys, xs = np.nonzero(mask)
    if ys.size == 0 or float(mask.mean()) > 0.98:
        return None                       # nothing removed = no separable subject
    box = (xs.min() / w, ys.min() / h, (xs.max() + 1) / w, (ys.max() + 1) / h)
    return Region(label="subject", kind="matting",
                  box=tuple(round(float(v), 4) for v in box),
                  conf=round(float(min(1.0, mask.mean() * 3)), 3))


def detect_subject(path, *, prefer: str = "energy") -> Optional[Region]:
    """Locate the subject. `prefer='matting'` pays for the model; otherwise it is free.

    Returns None when there is no separable subject — a full-bleed textile has detail everywhere
    and no single thing to push into, and saying None is more useful than asserting the centre.
    """
    if prefer == "matting":
        r = _matting_subject(path)
        if r is not None:
            return r
    return _energy_subject(path)


def focal_point(path, *, prefer: str = "energy",
                min_conf: float = 0.15) -> Optional[Tuple[float, float]]:
    """The (x, y) for `camera.solve.solve_push(target=...)`, or None to leave it centred.

    THE SEAM this module exists to close. Below `min_conf` it returns None on purpose: pushing on
    a badly-located target is worse than pushing on the centre, because the move looks deliberate
    either way and only one of them is.
    """
    r = detect_subject(path, prefer=prefer)
    if r is None or r.conf < min_conf:
        return None
    return r.centre


def crop_safe(path, aspect: float, *, prefer: str = "energy") -> bool:
    """Would a `cover` crop to `aspect` cut into the subject? The FIRST payoff — crop safety, not
    the zoom. A 16:9 cover on a tall portrait is how you decapitate someone."""
    r = detect_subject(path, prefer=prefer)
    if r is None:
        return True                       # nothing located: no basis to refuse
    from nolan.pixels import measure
    facts = measure(path)
    if facts is None:
        return True
    src = facts.width / max(1, facts.height)
    x0, y0, x1, y1 = r.box
    if aspect > src:                      # target is wider: the crop eats TOP and BOTTOM
        keep = src / aspect
        margin = (1.0 - keep) / 2.0
        return y0 >= margin - 1e-6 and y1 <= 1.0 - margin + 1e-6
    keep = aspect / src                   # target is taller: the crop eats LEFT and RIGHT
    margin = (1.0 - keep) / 2.0
    return x0 >= margin - 1e-6 and x1 <= 1.0 - margin + 1e-6


def regions_json(regions: List[Region]) -> str:
    import json
    return json.dumps([r.to_dict() for r in regions], ensure_ascii=False)
