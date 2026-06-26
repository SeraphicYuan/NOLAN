"""Test: PieCalloutRenderer 5-beat donut callout.

Verifies:
  1. The donut renders (non-background pixels after fade-in).
  2. The highlighted slice is drawn in the accent colour during reveal/explode.
  3. The slice size tracks the percentage (23% paints far more accent than 0.0017%).
  4. The info text block appears (dark pixels on the right half) late in the timeline.
  5. The pie location is controllable via pie_center.

Usage:
    D:/env/nolan/python.exe scripts/test_pie_callout.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.nolan.renderer.scenes.pie_callout import PieCalloutRenderer

W, H = 960, 540
DUR = 6.5
SLICE = (37, 99, 235)


def build(pct, pie_center=(0.30, 0.52)):
    r = PieCalloutRenderer(
        percentage=pct,
        info_title=f"{pct:g}%",
        info_text="of every 30 million people. A vanishingly small slice of the whole.",
        slice_label="Affected",
        width=W, height=H, pie_center=pie_center,
    )
    r.timeline.duration = DUR
    return r


def accent_pixels(frame):
    R, G, B = frame[..., 0], frame[..., 1], frame[..., 2]
    return int(((B > 150) & (R < 120) & (G < 170)).sum())


def dark_pixels_right(frame):
    half = frame[:, W // 2:, :]
    return int((half.max(axis=2) < 90).sum())


def nonbg_pixels(frame, bg=(244, 242, 237)):
    return int((np.abs(frame.astype(int) - np.array(bg)).sum(axis=2) > 24).sum())


def main():
    big = build(23.0)
    tiny = build(0.0017)

    # 1: donut visible after fade-in (t=1.0).
    f1 = big.render_frame(1.0)
    n1 = nonbg_pixels(f1)
    print(f"t=1.0 non-bg pixels (donut) = {n1}")
    assert n1 > 500, "donut did not render"

    # 2 + 3: accent slice present mid-explode, and size tracks percentage.
    fb = big.render_frame(4.2)
    ft = tiny.render_frame(4.2)
    ab, at = accent_pixels(fb), accent_pixels(ft)
    print(f"t=4.2 accent pixels  23%={ab}  0.0017%={at}")
    assert ab > 0, "slice was never coloured"
    assert ab > at * 1.5, f"slice size did not track percentage ({ab} vs {at})"

    # 4: info text block appears on the right late in the timeline.
    early = dark_pixels_right(big.render_frame(2.0))
    late = dark_pixels_right(big.render_frame(5.8))
    print(f"right-half dark pixels  early={early}  late={late}")
    assert late > early and late > 200, "info text block did not appear"

    # 5: pie location is controllable (slice centroid shifts with pie_center).
    left = build(40.0, pie_center=(0.25, 0.5)).render_frame(4.5)
    right = build(40.0, pie_center=(0.70, 0.5)).render_frame(4.5)

    def accent_centroid_x(frame):
        R, G, B = frame[..., 0], frame[..., 1], frame[..., 2]
        mask = (B > 150) & (R < 120) & (G < 170)
        xs = np.where(mask.any(axis=0))[0]
        return xs.mean() if len(xs) else 0

    cx_left, cx_right = accent_centroid_x(left), accent_centroid_x(right)
    print(f"accent centroid x  pie@0.25={cx_left:.0f}  pie@0.70={cx_right:.0f}")
    assert cx_right > cx_left + 50, "pie_center did not move the pie"

    print("\nOK - pie callout renders, slice tracks %, text appears, location controllable.")


if __name__ == "__main__":
    main()
