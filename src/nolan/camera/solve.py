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
            clamped.append(f"target ({tx:.2f},{ty:.2f}) unreachable at scale {s:.3f}")
        return {"scale": round(s, 4), "x": round(gx, 1), "y": round(gy, 1)}

    return {"mode": "cover", "from": _kf(s0), "to": _kf(s1), "clamped": sorted(set(clamped))}


def solve_pan(*, dur: float, direction: str = "right", amount: Optional[float] = None,
              img: Optional[Tuple[int, int]] = None, canvas=(CANVAS_W, CANVAS_H),
              cap: float = SCALE_CAP) -> Dict:
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
            full_h = w * ih / iw                      # the element is sized to the FULL image width-fit
            overflow = full_h - h
            travel = min(overflow, overflow * max(0.2, min(1.0, frac / 0.14)))
            y0, y1 = 0.0, -travel
            if direction == "up":
                y0, y1 = -overflow, -overflow + travel
            return {"mode": "long-axis", "element_height": round(full_h, 1),
                    "from": {"scale": 1.0, "x": 0.0, "y": round(y0, 1)},
                    "to": {"scale": 1.0, "x": 0.0, "y": round(y1, 1)},
                    "clamped": []}

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


UPSCALE_TOLERANCE = 1.18     # a modest upscale on a still is normal practice; 3x is mush


def resolution_floor(img: Optional[Tuple[int, int]], scale: float, canvas=(CANVAS_W, CANVAS_H),
                     tolerance: float = UPSCALE_TOLERANCE) -> Optional[str]:
    """A reason string if this move would upscale the source past what a still can carry, else None.

    Directly relevant: ~10 library sources are still 360p. Pushing 1.3x into one is a soft, mushy shot
    and the honest answer is to hold. But the tolerance matters as much as the rule: at 2%, a
    1920x1080 stock image — the single most common asset shape we have — could not take ANY push, and
    the feature would switch itself off across most of a real pool. 18% is the band where a still still
    holds up, and it still catches the 360p sources by a wide margin (they need ~3x).
    """
    if not img:
        return None
    iw, ih = img
    if iw <= 0 or ih <= 0:
        return None
    need_w, need_h = canvas[0] * scale, canvas[1] * scale
    cover = max(need_w / iw, need_h / ih)
    if cover > tolerance:
        return (f"source {iw}x{ih} would upscale {cover:.2f}x at scale {scale:.2f} "
                f"(canvas {canvas[0]}x{canvas[1]}, tolerance {tolerance:.2f})")
    return None
