"""Test D asset prep: pool JPGs -> collage-ready transparent cutouts, with a matte-quality gate.

The pool holds JPGs; `collage` needs transparent PNG cutouts. rembg does the cut, but it FAILS
SILENTLY on some subjects and a bad matte would ship a broken collage that no gate can see.

Measured on the five props (2026-08-04):

    asset              cover   blobs>=1%  largest-blob
    cash_stack         55.0%       1        100.0%   clean
    gavel              27.1%       1        100.0%   clean (low cover is HONEST — a thin diagonal
                                                     object legitimately fills little of its bbox)
    gpu_card           85.5%       1        100.0%   clean
    water_glass        84.6%       1        100.0%   clean
    smart_meter        56.8%       3         41.0%   MULTI-OBJECT — five meters in a row
    electric_bill      12.7%      10         24.2%   BROKEN — white paper on a light ground; rembg
                                                     kept only the blue header bars and loose text

So coverage alone does not discriminate: `gavel` (27%) is fine and `electric_bill` (12.7%) is not.
FRAGMENTATION does — but it cannot AUTO-REJECT, because `smart_meter` is legitimately fragmented.
Hence: a low largest-blob fraction FLAGS for review; only an explicit decision resolves it.
`crop_to_subject` is that decision for a multi-object source.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from nolan.cutout import cutout_file  # noqa: E402

SRC = REPO / "render-service/_lab_hyperframes/videos/data-center-economics-final/assets/props"
OUT = Path(__file__).resolve().parent / "_testD" / "assets"

# A coherent single subject holds essentially all of its own alpha in one blob. Below this the
# matte is either shattered or genuinely multi-object — either way a human decides, not the script.
COHERENT = 0.85

SUBJECTS = [
    # (source stem, noun it lands on, crop_to_subject)
    ("smart_meter_00", "meter", True),    # five meters in a row -> keep the largest
    ("water_glass_00", "water", False),
    ("gavel_01",       "zoning", False),
    ("gpu_card_00",    "chips", False),
    ("cash_stack_00",  "back", False),
]


def matte_stats(png: Path) -> tuple[float, int, float]:
    a = np.array(Image.open(png).convert("RGBA"))[:, :, 3] > 16
    lab, n = ndimage.label(a)
    if n == 0:
        return 0.0, 0, 0.0
    sizes = ndimage.sum(a, lab, range(1, n + 1))
    tot = float(sizes.sum())
    return float(a.mean()), int((sizes >= 0.01 * tot).sum()), float(sizes.max() / tot)


def crop_largest(png: Path) -> tuple[int, int]:
    """Keep only the largest connected component, cropped to its bbox."""
    im = Image.open(png).convert("RGBA")
    a = np.array(im)
    mask = a[:, :, 3] > 16
    lab, n = ndimage.label(mask)
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    keep = int(np.argmax(sizes)) + 1
    a[:, :, 3] = np.where(lab == keep, a[:, :, 3], 0)
    ys, xs = np.where(lab == keep)
    im2 = Image.fromarray(a).crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    im2.save(png)
    return im2.size


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    flagged = []
    print(f'{"asset":18} {"noun":8} {"size":>13} {"cover":>7} {"blobs":>6} {"largest":>8}  verdict')
    for stem, noun, crop in SUBJECTS:
        dst = OUT / f"{stem}.cutout.png"
        if not dst.exists():
            cutout_file(SRC / f"{stem}.jpg", dst, trim=True, trim_pad=4)
        cover, blobs, largest = matte_stats(dst)
        note = ""
        if largest < COHERENT:
            if crop:
                w, h = crop_largest(dst)
                cover, blobs, largest = matte_stats(dst)
                note = f"cropped to largest subject ({w}x{h})"
            else:
                flagged.append(stem)
                note = "FLAG — matte is fragmented; review before use"
        size = Image.open(dst).size
        print(f"{stem:18} {noun:8} {size[0]:5}x{size[1]:<7} {cover:6.1%} {blobs:6d} {largest:7.1%}  {note or 'ok'}")

    if flagged:
        print(f"\n{len(flagged)} matte(s) need review: {', '.join(flagged)}")
        return 1
    print(f"\n{len(SUBJECTS)} subjects ready in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
