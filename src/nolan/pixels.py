"""Deterministic pixel measurement — every NUMBER about an image, and no model.

This module exists because a 50-row validation pass measured the alternative and it lost.
A VLM was asked, among other things, whether an image had a dead border. It agreed with pixel
measurement on **16 of 50** — worse than chance — and said "no border" on ten rows where the
margin was 15%+ of the frame, one at 32%. It was not lying; it was answering a different
question (a decorative border *inside* the artwork, not dead margin *around* it). The same pass
killed `focal_zone` (returned the centre cell on 50/50) and `open_zones` (7 distinct answers for
50 images, 38 of them one of two templates).

So the split this module enforces:

    **The model NAMES. A detector LOCALISES. Nothing numeric is ever asked of a model.**

Border percentages, colour, bounding boxes, dimensions, aspect — all of it arrives here, free,
exactly right, and identically on every run. What a caption may still contribute is what is
*depicted*, which no amount of arithmetic recovers (measured: 93.2% of caption tokens appear
nowhere in the catalog record).

The measurement that pays for the module on its own is `content_box`. Museum object photography
is an object on a plain sweep, and 20 of 50 sampled rows carry >=5% dead margin — coins run
29-32%, because a coin photo is two coins on a wide grey field. Two consequences, both live:

  * `asset_gate`'s resolution floor was measuring the FILE. A 1686px coin photo that is 31%
    content is really a ~940px asset, so the gate was admitting things it believed were
    archival-grade and were not. `effective_dims` is the honest number.
  * A ken-burns move computed on the file pans across empty grey. That is the "A Diamond Is
    Forever" defect — a photograph of a 1947 page, 7.7% black one side and 11.8% the other,
    with a long-axis pan travelling over the source's own edge.

Everything here runs on a 512px working copy, costs ~16ms a row, needs no network and no key,
and is therefore affordable on every row at harvest time rather than on demand.

It lives at the TOP level, beside `asset_gate` and `editing`, rather than inside `imagelib`,
because four umbrellas need the same numbers — the gate's resolution floor, `hyperframes/
cleanup`'s crop, the discovery tier's harvest, and the caption pass — and one measurement with
four callers is the checklist's "one registry per decision". The practical forcing function is
narrower: `nolan.imagelib.__init__` imports CLIP and Chroma, so a gate that reached into
imagelib for a border measurement would drag a model loader into every acquisition call.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Working resolution. The measurements are shares and ratios, so they are resolution-independent;
# 512 is the thumbnail size the discovery tier already stores, which makes this free on a
# not-held row (no second decode of a full-size file).
_WORK_PX = 512

# Per-pixel channel deviation, 0-255, still considered "the background colour". Sized for JPEG
# ringing around a hard matte edge rather than for gradient sweeps: a genuine gradient is part of
# the photograph and must NOT be eaten as dead margin.
_BG_TOL = 16.0

# A row/column counts as dead when its 99th-percentile deviation is within tolerance — i.e. all
# but ~1% of it is background. The percentile rather than the max is what makes this survive
# dust, a stray hot pixel and JPEG ringing; the mean would be far too permissive and would eat
# into a dark painting's own edge.
_DEAD_PCTL = 99.0

# Maximum saturation of an edge colour still treated as GROUND rather than picture. Sweeps,
# letterbox bars, mats and page edges are achromatic; a painted sky is not. See `_scan_side`.
_GROUND_MAX_SAT = 0.18

# A single side may not be declared more than this share of dead margin. Nothing in the corpus
# comes close (the worst real row is a 35% coin field), so this is a backstop against a
# pathological eat on an image that is genuinely one flat colour for most of its extent.
_MAX_SIDE_MARGIN = 0.45

# Border band sampled for `uniform_background`, as a share of the short edge. Measured separation
# on the validation sample: object-photos 81% uniform, flat artworks 12%.
_RING_FRAC = 0.05

# Saturation below this reads as a greyscale reproduction rather than a colour one.
_GREY_SAT = 0.05

# A 3x3 cell is quiet enough to carry text when its mean gradient magnitude is below this
# (0-1 scale). The honest replacement for the VLM's `open_zones`, which was a template.
# CALIBRATED over 9,819 cells of the live corpus: the distribution runs p25=0.016, p50=0.028,
# p75=0.043. The first guess of 0.045 called 78% of all cells quiet — a field that answers
# "where can type go" with "anywhere" is as useless as the VLM template it replaced. 0.015
# selects the genuinely calm ~22%, i.e. about two cells of nine on a typical row.
_QUIET_GRAD = 0.015

_CELLS = ("tl", "tc", "tr", "ml", "mc", "mr", "bl", "bc", "br")


@dataclass
class PixelFacts:
    """Deterministic measurements of one image file. Every field is reproducible."""

    # --- the file as stored ---
    width: int
    height: int
    aspect: float                                  # w/h of the FILE

    # --- content box: the picture with its dead margin removed ---
    # (x0, y0, x1, y1) in FULL-RESOLUTION pixels, right/bottom exclusive.
    content_box: Tuple[int, int, int, int]
    # Dead margin per side as a share of that side's extent.
    margin: Dict[str, float]
    content_fraction: float                        # content box area / file area
    # What the resolution floor must judge — the content box in full-res pixels. THE number
    # `asset_gate` was getting wrong.
    effective_width: int
    effective_height: int
    content_aspect: float                          # w/h of the CONTENT, which is what gets framed

    # --- what kind of file this is, measured rather than asked ---
    uniform_background: float                      # share of the border band that is one colour
    object_on_sweep: bool                          # object photographed on a plain ground
    shape: str                                     # 'rect' | 'round' | 'blank'
    edge_contact: List[str]                        # sides the content actually touches

    # --- tone ---
    luminance: float                               # 0-1 mean
    contrast: float                                # 0-1, p95-p5 of luma
    saturation: float                              # 0-1 mean HSV S
    greyscale: bool

    # --- where text can go (the honest `open_zones`) ---
    quiet_cells: List[str]                         # 3x3 cells calm enough to carry type
    quiet_map: List[float]                         # the 9 raw gradient means, same order

    schema: int = 1

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def effective_dims(self) -> Tuple[int, int]:
        return (self.effective_width, self.effective_height)


def _open_rgb(path: Path):
    """Load as a float32 RGB array at working resolution, plus the true file size."""
    import numpy as np
    from PIL import Image

    with Image.open(path) as im:
        full_w, full_h = im.size
        im = im.convert("RGB")
        im.thumbnail((_WORK_PX, _WORK_PX))
        arr = np.asarray(im, dtype=np.float32)
    return arr, full_w, full_h


def _dead_runs(dead: "list") -> Tuple[int, int]:
    """Length of the leading and trailing True runs in a boolean 1-D array."""
    import numpy as np

    n = int(dead.shape[0])
    idx = np.flatnonzero(~dead)
    if idx.size == 0:                       # every row/column is background: a blank image
        return n, 0
    return int(idx[0]), int(n - 1 - idx[-1])


def _scan_side(lines) -> int:
    """How many leading lines are dead, given lines ordered from the edge inward.

    Each side is judged against ITS OWN outermost line rather than against one background colour
    sampled from the whole border. That matters because margins are often asymmetric — the defect
    that motivated this module was a photographed page with 7.7% dead on one side and 11.8% on
    the other — and a one-sided margin is outvoted in a whole-border sample, so it measured zero.
    Judging per side also self-limits: an edge that is real picture has a non-uniform outermost
    line, so its 99th-percentile deviation blows the tolerance immediately and nothing is eaten.

    THE CHROMATIC GUARD, and why it is not optional: uniformity alone does not distinguish a
    mount from a sky. Horace Pippin's "Cabin in the Cotton" (`artic:111617`) has a flat painted
    blue sky across the top 17.8% of the panel, and the first version of this trimmed it — which
    would have handed the gate a painting 18% shorter than it is. A studio sweep, a letterbox
    bar, a paper mat and a scanned page edge are all ACHROMATIC; a sky is not. So a side is only
    eligible to be trimmed when its own edge colour is near-neutral. The cost is that a genuinely
    coloured backdrop goes unmeasured, which is the safe direction: the content box may be a
    superset of the content, never a subset.
    """
    import numpy as np

    ref = np.median(lines[0], axis=0)
    hi, lo = float(ref.max()), float(ref.min())
    if hi > 0 and (hi - lo) / hi > _GROUND_MAX_SAT:
        return 0
    n = 0
    limit = int(lines.shape[0] * _MAX_SIDE_MARGIN)
    for i in range(min(lines.shape[0], limit)):
        dev = np.abs(lines[i] - ref).max(axis=1)
        if np.percentile(dev, _DEAD_PCTL) > _BG_TOL:
            break
        n += 1
    return n


def _content_box(arr) -> Tuple[Tuple[int, int, int, int], bool]:
    """Bounding box of the non-background content, in WORKING-resolution pixels.

    Background is measured, never assumed black or white: the margin that actually shows up in a
    museum corpus is mid-grey studio sweep at least as often as it is letterbox black.
    """
    h, w, _ = arr.shape

    top = _scan_side(arr)                                   # rows, downward
    bottom = _scan_side(arr[::-1])                          # rows, upward
    left = _scan_side(arr.transpose(1, 0, 2))               # cols, rightward
    right = _scan_side(arr.transpose(1, 0, 2)[::-1])        # cols, leftward

    if top + bottom >= h or left + right >= w:              # nothing survived: a blank image
        return (0, 0, w, h), True
    return (left, top, w - right, h - bottom), False


def _uniform_background(arr, box) -> float:
    """Share of the outer border band within tolerance of the band's own median colour.

    High for an object on a sweep, low for a painting that fills its frame — measured 81% vs 12%
    on the validation sample, which separates the two with no vision call at all.
    """
    import numpy as np

    h, w, _ = arr.shape
    band = max(2, int(round(min(h, w) * _RING_FRAC)))
    mask = np.zeros((h, w), dtype=bool)
    mask[:band, :] = True
    mask[h - band:, :] = True
    mask[:, :band] = True
    mask[:, w - band:] = True

    px = arr[mask]
    if px.size == 0:
        return 0.0
    bg = np.median(px, axis=0)
    dev = np.abs(px - bg).max(axis=1)
    return float((dev <= _BG_TOL).mean())


def _shape(arr, box, blank: bool) -> str:
    """`round` = the content is a DISC, not a rectangle — so cover-fitting it into a 16:9 frame
    either crops into the picture or leaves ground showing. Decided by circularity.

    Two corrections came out of looking at the output, and both are worth keeping:

    * The first version asked whether the four corners were background and the centre was not —
      true of ANY object photographed on a plain ground, so it called an engraving, a dalmatic
      and three Greek kraters round (12 of 19 hits wrong). The honest test compares the content
      mask against the inscribed circle: a disc fills the circle and leaves the corners empty,
      a krater's rim fills the top corners, an engraving fills all four. 19 hits → 10, of which
      8 are unambiguous.
    * The value is `round`, not `tondo`. The survivors are a mix of round PICTURES (a Botticelli-
      school tondo, circular portrait miniatures) and round OBJECTS shot from above (a
      paperweight, a basin, a scarab). Naming it `tondo` would claim an art-historical judgement
      the pixels cannot support — and the consumer does not care which it is, because the framing
      consequence is identical.
    """
    import numpy as np

    if blank:
        return "blank"
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    if bw < 24 or bh < 24:
        return "rect"
    if not (0.9 <= (bw / bh) <= 1.11):          # a tondo sits on a square field
        return "rect"

    inner = arr[y0:y1, x0:x1, :]
    ring = np.concatenate([inner[0, :, :], inner[-1, :, :],
                           inner[:, 0, :], inner[:, -1, :]], axis=0)
    bg = np.median(ring, axis=0)
    content = np.abs(inner - bg).max(axis=2) > _BG_TOL

    yy = np.arange(bh).reshape(-1, 1)
    xx = np.arange(bw).reshape(1, -1)
    cy, cx = (bh - 1) / 2.0, (bw - 1) / 2.0
    r = min(bw, bh) / 2.0
    dist = np.sqrt(((yy - cy) / r) ** 2 + ((xx - cx) / r) ** 2)

    inside = dist <= 0.92                        # comfortably within the disc
    outside = dist >= 1.02                       # the corners the disc cannot reach
    if not inside.any() or not outside.any():
        return "rect"
    if float(content[inside].mean()) >= 0.90 and float(content[outside].mean()) <= 0.12:
        return "round"
    return "rect"


def _tone(arr) -> Tuple[float, float, float]:
    import numpy as np

    luma = (0.2126 * arr[:, :, 0] + 0.7152 * arr[:, :, 1] + 0.0722 * arr[:, :, 2]) / 255.0
    p5, p95 = np.percentile(luma, [5, 95])
    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    return float(luma.mean()), float(p95 - p5), float(sat.mean())


def _quiet(arr, box) -> Tuple[List[str], List[float]]:
    """Mean gradient magnitude per 3x3 cell OF THE CONTENT BOX — the measured answer to "where
    can type go", replacing a VLM field that returned one of two templates 38 times in 50."""
    import numpy as np

    x0, y0, x1, y1 = box
    inner = arr[y0:y1, x0:x1, :]
    if inner.shape[0] < 6 or inner.shape[1] < 6:
        return [], [0.0] * 9
    luma = (0.2126 * inner[:, :, 0] + 0.7152 * inner[:, :, 1]
            + 0.0722 * inner[:, :, 2]) / 255.0
    gy, gx = np.gradient(luma)
    grad = np.hypot(gx, gy)

    h, w = grad.shape
    ys = [0, h // 3, 2 * h // 3, h]
    xs = [0, w // 3, 2 * w // 3, w]
    cells, raw = [], []
    for r in range(3):
        for c in range(3):
            cell = grad[ys[r]:ys[r + 1], xs[c]:xs[c + 1]]
            m = float(cell.mean()) if cell.size else 1.0
            raw.append(m)
            if m <= _QUIET_GRAD:
                cells.append(_CELLS[r * 3 + c])
    return cells, raw


def measure(path) -> Optional[PixelFacts]:
    """Measure one image file. Returns None if it cannot be read — a measurement that failed
    must be absent, never silently zero, or the gate would read an unreadable file as flawless.
    """
    p = Path(path)
    try:
        arr, full_w, full_h = _open_rgb(p)
    except Exception:
        return None
    if arr.size == 0 or arr.shape[0] < 2 or arr.shape[1] < 2:
        return None

    h, w, _ = arr.shape
    box, blank = _content_box(arr)
    x0, y0, x1, y1 = box

    sx, sy = full_w / w, full_h / h
    fbox = (int(round(x0 * sx)), int(round(y0 * sy)),
            int(round(x1 * sx)), int(round(y1 * sy)))
    eff_w = max(1, fbox[2] - fbox[0])
    eff_h = max(1, fbox[3] - fbox[1])

    margin = {
        "left": x0 / w,
        "right": (w - x1) / w,
        "top": y0 / h,
        "bottom": (h - y1) / h,
    }
    content_fraction = ((x1 - x0) * (y1 - y0)) / float(w * h)
    uniform = _uniform_background(arr, box)
    lum, contrast, sat = _tone(arr)
    quiet_cells, quiet_map = _quiet(arr, box)

    touch = [side for side, m in margin.items() if m < 0.005]

    return PixelFacts(
        width=full_w,
        height=full_h,
        aspect=full_w / max(1, full_h),
        content_box=fbox,
        margin={k: round(v, 4) for k, v in margin.items()},
        content_fraction=round(content_fraction, 4),
        effective_width=eff_w,
        effective_height=eff_h,
        content_aspect=eff_w / max(1, eff_h),
        uniform_background=round(uniform, 4),
        # Both halves matter: a plain ground AND the content not filling the frame. A flat
        # artwork shot edge-to-edge on a white wall has a uniform border but ~99% content, and
        # calling it an object photo is what made `banner_suspect` refuse 4 of 4 museum rows.
        object_on_sweep=bool(uniform >= 0.5 and content_fraction <= 0.92),
        shape=_shape(arr, box, blank),
        edge_contact=sorted(touch),
        luminance=round(lum, 4),
        contrast=round(contrast, 4),
        saturation=round(sat, 4),
        greyscale=bool(sat < _GREY_SAT),
        quiet_cells=quiet_cells,
        quiet_map=[round(v, 5) for v in quiet_map],
    )


def effective_dims(path, declared: Optional[Tuple[int, int]] = None
                   ) -> Optional[Tuple[int, int]]:
    """The dimensions a resolution floor should judge: the CONTENT, in full-image pixels.

    `declared` lets a caller measure a 512px thumbnail but scale the answer to the full image the
    catalog knows the size of — the discovery tier's exact case, where the thumbnail is local and
    the full file is still at the institution.
    """
    facts = measure(path)
    if facts is None:
        return None
    if declared and declared[0] and declared[1]:
        dw, dh = declared
        return (max(1, int(round(dw * facts.effective_width / max(1, facts.width)))),
                max(1, int(round(dh * facts.effective_height / max(1, facts.height)))))
    return facts.effective_dims
