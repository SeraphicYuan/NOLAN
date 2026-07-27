"""Camera geometry: the amplitude law, and a transform pair that can never expose an edge.

THE AMPLITUDE LAW. The eye judges apparent SPEED, not scale delta, so hold speed roughly constant and
derive the size of the move from the beat. Today every ground gets a flat `1.02 -> 1.12` no matter
whether the beat is 4s or 17s — which is exactly why long holds read as dead and short ones read as
jumpy. A 4s beat gets ~5% of travel; a 16s beat gets ~11%, capped so a very long hold does not turn
into a zoom.

THE SOLVER. A ground is a canvas-sized div with a cover-fit background; `scale` creates overscan and
`x/y` move inside it. The one hard constraint is that a translate may only consume overscan that
exists: |x| <= W*(s-1)/2. Break it and you get a black edge in a finished video — the bug class this
module exists to make unrepresentable. When a requested move cannot fit, we raise the scale to afford
it (to a cap, beyond which a 1080p source visibly softens), then CLAMP and report. Reporting is the
point: a silent clamp is the "no silent caps" violation, and a camera that quietly does less than it
was asked is indistinguishable from one that is broken.

LONG-AXIS MODE. Cover-fit already crops a tall source to a centre band, so panning inside the overscan
can never reveal the top of a poster. For a source much taller than the canvas, the ground is instead
sized to the FULL image (`background-size: 100% auto`) and translated across the real overflow — the
difference between a pan that reveals a document and one that just slides a crop around.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

CANVAS_W, CANVAS_H = 1920, 1080
SCALE_CAP = 1.35            # beyond this a 1080p source visibly softens
MIN_SCALE = 1.01          # never exactly 1.0: at 1.0 a sub-pixel rounding seam can show
TALL_RATIO = 1.35           # img_h/img_w vs canvas_h/canvas_w beyond which long-axis is the honest pan
LONG_AXIS_BLEED = 1.01      # a hair wider than the canvas on a long-axis pan — sub-pixel seams only


def scale_amplitude(dur: float, lo: float = 0.05, hi: float = 0.16) -> float:
    """Total scale travel for a beat of `dur` seconds — constant apparent speed, clamped both ends."""
    return round(max(lo, min(hi, 0.035 + 0.0045 * max(0.0, float(dur)))), 4)


def pan_amplitude(dur: float, lo: float = 0.03, hi: float = 0.14) -> float:
    """Total translate travel as a fraction of the frame, same law."""
    return round(max(lo, min(hi, 0.02 + 0.004 * max(0.0, float(dur)))), 4)


def _overscan(scale: float, w: float, h: float) -> Tuple[float, float]:
    """Half-width / half-height of travel available at this scale, in px."""
    return (w * (scale - 1.0) / 2.0, h * (scale - 1.0) / 2.0)


def _clamp_to_target(target, side):
    """A target point in 0..1, clamped so the framing it implies stays inside the image."""
    tx = 0.5 if target is None else float(target[0])
    ty = 0.5 if target is None else float(target[1])
    half = side / 2.0
    return (min(max(tx, half), 1.0 - half), min(max(ty, half), 1.0 - half))


def solve_push(*, dur: float, target=None, scale_from: float = MIN_SCALE, amount: Optional[float] = None,
               reverse: bool = False, canvas=(CANVAS_W, CANVAS_H), cap: float = SCALE_CAP) -> Dict:
    """A push (or pull, `reverse=True`) about `target` (x,y in 0..1; None = centre).

    Both keyframes are framed on the SAME point, so the target stays put while the frame closes on it.
    That is what separates a push-in on a subject from a zoom that drifts off it.
    """
    w, h = canvas
    amt = scale_amplitude(dur) if amount is None else float(amount)
    s0 = max(MIN_SCALE, float(scale_from))
    s1 = min(cap, s0 + amt)
    clamped: List[str] = []
    if s0 + amt > cap:
        clamped.append(f"scale {s0 + amt:.3f} -> cap {cap}")
    if reverse:
        s0, s1 = s1, s0

    def _kf(s):
        # translate so `target` sits at frame centre at scale s, then clamp into the overscan
        tx, ty = (0.5, 0.5) if target is None else (float(target[0]), float(target[1]))
        ox, oy = _overscan(s, w, h)
        want_x = (0.5 - tx) * w * s
        want_y = (0.5 - ty) * h * s
        gx = min(max(want_x, -ox), ox)
        gy = min(max(want_y, -oy), oy)
        if abs(gx - want_x) > 0.5 or abs(gy - want_y) > 0.5:
            # Not a failure: at scale 1.10 the overscan is 5% of the frame, so a target at 0.33 cannot
            # be CENTRED by any amount of translation — the framing is biased as far toward it as the
            # scale affords. Said plainly, because this line lands in every run log.
            bias = min(1.0, (abs(gx) + abs(gy)) / (abs(want_x) + abs(want_y) + 1e-6))
            clamped.append(f"target ({tx:.2f},{ty:.2f}) can only be approached {bias * 100:.0f}% at "
                           f"scale {s:.3f} — framing biased toward it, not centred on it")
        return {"scale": round(s, 4), "x": round(gx, 1), "y": round(gy, 1)}

    return {"mode": "cover", "from": _kf(s0), "to": _kf(s1), "clamped": sorted(set(clamped))}


def solve_pan(*, dur: float, direction: str = "right", amount: Optional[float] = None,
              img: Optional[Tuple[int, int]] = None, canvas=(CANVAS_W, CANVAS_H),
              cap: float = SCALE_CAP, content=None) -> Dict:
    """A lateral or vertical pan.

    Horizontal + a normal source: overscan from a scale that is RAISED to afford the requested travel.
    Vertical + a tall source: long-axis mode, which pans the real image instead of a crop.
    """
    w, h = canvas
    frac = pan_amplitude(dur) if amount is None else float(amount)
    clamped: List[str] = []
    vertical = direction in ("down", "up")

    if vertical and img:
        iw, ih = img
        if iw > 0 and (ih / iw) > (h / w) * TALL_RATIO:
            # Width-fit to the PICTURE, not to the file. A bare 100%-width fit shows the source's full
            # width — which on a scanned page or a photographed ad means showing the dark surround the
            # file carries, the very thing cover-fit was hiding. The rendered f09 pan exposed exactly
            # that, and it is this module's own rule ("never expose an edge") broken on the axis it is
            # not moving along.
            #
            # The first attempt was a symmetric 6% overscan — the right instinct with an invented
            # number. That ad's surround is 7.7% left and 11.8% right (asymmetric: the page is
            # photographed askew), so 6% could not remove it, and on a source with no border at all the
            # same 6% quietly cropped real picture. So the caller measures it (`target.content_box`)
            # and the geometry is solved against the content box. `bleed` is the only fudge left, and
            # it is there for sub-pixel seams, not for borders.
            cx0, cy0, cx1, cy1 = content or (0.0, 0.0, 1.0, 1.0)
            fw, fh = max(0.05, cx1 - cx0), max(0.05, cy1 - cy0)
            ew = w * LONG_AXIS_BLEED / fw             # the CONTENT spans the canvas width
            full_h = ew * ih / iw                     # element sized to the whole file at that width
            left = w * (1.0 - LONG_AXIS_BLEED) / 2.0 - cx0 * ew
            top = cy0 * full_h                        # where the picture starts inside the element
            overflow = fh * full_h - h                # travel available ACROSS THE PICTURE
            if overflow <= 1.0:
                clamped.append(f"content box {fw:.2f}x{fh:.2f} leaves no long-axis travel — cover push")
            else:
                travel = min(overflow, overflow * max(0.2, min(1.0, frac / 0.14)))
                y0, y1 = -top, -top - travel
                if direction == "up":
                    y0, y1 = -top - overflow, -top - overflow + travel
                notes = []
                if (cx0 or cy0 or cx1 < 1.0 or cy1 < 1.0):
                    notes.append(f"cropped the source's own surround "
                                 f"(l{cx0 * 100:.1f}% r{(1 - cx1) * 100:.1f}% "
                                 f"t{cy0 * 100:.1f}% b{(1 - cy1) * 100:.1f}%)")
                return {"mode": "long-axis", "element_height": round(full_h, 1),
                        "element_width": round(ew, 1), "element_left": round(left, 1),
                        "from": {"scale": 1.0, "x": 0.0, "y": round(y0, 1)},
                        "to": {"scale": 1.0, "x": 0.0, "y": round(y1, 1)},
                        "clamped": notes}

    span = (h if vertical else w) * frac              # px of travel we want
    need = 1.0 + (2.0 * span) / (h if vertical else w)
    s = min(cap, max(1.02, need))
    if need > cap:
        span = (h if vertical else w) * (cap - 1.0) / 2.0
        clamped.append(f"pan {frac:.3f} needs scale {need:.3f} > cap {cap} — travel clamped")
    ox, oy = _overscan(s, w, h)
    half = min(span / 2.0, oy if vertical else ox)
    sign = -1.0 if direction in ("left", "up") else 1.0
    if vertical:
        kf0 = {"scale": round(s, 4), "x": 0.0, "y": round(+half * sign, 1)}
        kf1 = {"scale": round(s, 4), "x": 0.0, "y": round(-half * sign, 1)}
    else:
        kf0 = {"scale": round(s, 4), "x": round(+half * sign, 1), "y": 0.0}
        kf1 = {"scale": round(s, 4), "x": round(-half * sign, 1), "y": 0.0}
    return {"mode": "cover", "from": kf0, "to": kf1, "clamped": sorted(set(clamped))}


def solve_box(*, dur: float, box, fill: float = 0.7, canvas=(CANVAS_W, CANVAS_H),
              cap: float = SCALE_CAP, reverse: bool = False) -> Dict:
    """Push into a REGION (x, y, w, h in 0..1) until it fills `fill` of the frame.

    The scale is DERIVED from the box, which is the whole reason a box beats a point: a logo in the
    corner and a face filling half the frame want completely different pushes toward the same spot.
    """
    bx, by, bw, bh = (float(v) for v in box)
    bw, bh = max(1e-3, bw), max(1e-3, bh)
    want = min(fill / bw, fill / bh)
    s1 = min(cap, max(1.0 + scale_amplitude(dur) * 0.5, want))
    out = solve_push(dur=dur, target=(bx + bw / 2.0, by + bh / 2.0), scale_from=1.0,
                     amount=s1 - 1.0, reverse=reverse, canvas=canvas, cap=cap)
    if want > cap:
        out["clamped"] = sorted(set(out["clamped"] + [f"box needs scale {want:.2f} > cap {cap}"]))
    return out


MUSH_FACTOR = 2.6            # total upscale past which MOTION starts advertising the softness


def cover_scale(img: Tuple[int, int], canvas=(CANVAS_W, CANVAS_H)) -> float:
    """The upscale a STATIC ground already pays to fill the frame (`background-size: cover`)."""
    iw, ih = img
    return max(canvas[0] / max(1, iw), canvas[1] / max(1, ih))


def resolution_floor(img: Optional[Tuple[int, int]], scale: float, canvas=(CANVAS_W, CANVAS_H),
                     mush: float = MUSH_FACTOR) -> Optional[str]:
    """A reason string if MOVING this source would advertise its softness, else None.

    THE FIRST TWO VERSIONS OF THIS FUNCTION ASKED THE WRONG QUESTION, and the frames test on a real
    project is what showed it. They compared the total upscale against a small tolerance (2%, then 18%)
    and attributed all of it to the camera — but a ground is ALREADY scaled to cover the frame whether
    or not a camera exists. Measured on the diamond-v2 pool: 30 of 47 image assets are narrower than the
    canvas, median width 1179px, and the static ground already pays a median 1.82x (max 5.68x). THIRTY
    ONE of 47 were over the 18% "tolerance" while completely still. So the floor switched the camera off
    on most of a real project to avoid a softness that was already on screen.

    What the camera actually adds is `scale` — at most 35%. The honest question is whether the TOTAL is
    soft enough that moving it draws the eye to the mush, so that is what this measures. A 1024px-wide
    still already at 1.88x can take a push (2.06x total, no worse than what is showing); a 360p source at
    3.0x cannot, and no camera decision rescues it — that is an asset problem.
    """
    if not img:
        return None
    iw, ih = img
    if iw <= 0 or ih <= 0:
        return None
    total = cover_scale(img, canvas) * float(scale)
    if total > mush:
        return (f"source {iw}x{ih} sits at {total:.2f}x total upscale at scale {scale:.2f} "
                f"(cover alone is {cover_scale(img, canvas):.2f}x; mush floor {mush:.2f}x)")
    return None
