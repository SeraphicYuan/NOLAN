"""Test: per-video extract assembler (synthetic clip + fake embedder + fake vision).

Usage:
    D:/env/nolan/python.exe scripts/test_extract.py
"""

import asyncio
import os
import re
import shutil
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
from src.nolan.video_style import extract

TMP = "scripts/_ex_tmp"


def make_clip(path, w=80, h=60, fps=10):
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    red = np.full((h, w, 3), (40, 40, 220), np.uint8)
    blue = np.full((h, w, 3), (220, 40, 40), np.uint8)
    for _ in range(30): vw.write(red)
    for _ in range(20): vw.write(blue)
    vw.release()


def fake_embedder(texts):
    toks = [re.findall(r"[a-z]+", t.lower()) for t in texts]
    vocab = sorted({w for ts in toks for w in ts})
    idx = {w: i for i, w in enumerate(vocab)}
    out = []
    for ts in toks:
        v = np.zeros(len(vocab))
        for w in ts:
            v[idx[w]] += 1
        out.append(v.tolist())
    return out


class FakeVision:
    async def describe_image(self, path, prompt):
        return "medium shot, cool grade, clean lower-third overlay"


def main():
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(TMP, exist_ok=True)
    clip = os.path.join(TMP, "clip.mp4")
    make_clip(clip)
    frames_dir = os.path.join(TMP, "frames")

    segments = [
        {"timestamp_start": 0, "timestamp_end": 2,
         "transcript": "a red signal flashed across the screen",
         "combined_summary": "a red signal flashing across the screen"},
        {"timestamp_start": 3, "timestamp_end": 5,
         "transcript": "markets fell sharply that morning",
         "combined_summary": "a calm blue ocean horizon at dawn"},
    ]

    ex = asyncio.run(extract.build_extract(
        clip, segments=segments, frames_dir=frames_dir,
        embed=fake_embedder, vision_provider=FakeVision(), max_frames=12, vision_max_frames=4))

    for key in ("format", "color", "motion", "graphics", "pacing", "pairing", "cinematography"):
        assert key in ex, f"missing {key}"
    print("format:", ex["format"]["aspect_ratio"], ex["format"]["orientation"])
    print("color.temp:", ex["color"]["temperature"], "| pacing.tempo:", ex["pacing"].get("tempo"))
    print("pairing:", ex["pairing"]["available"], ex["pairing"].get("literalness"),
          ex["pairing"].get("distribution"))
    print("cinematography frames_read:", ex["cinematography"]["frames_read"])
    print("frames saved:", len(ex["frame_files"]))

    assert ex["format"]["aspect_ratio"] == "4:3"
    assert ex["pacing"]["available"] and ex["pacing"]["segment_count"] == 2
    assert ex["pairing"]["available"] and ex["pairing"]["segment_count"] == 2
    assert ex["cinematography"]["frames_read"] == 4
    assert len(ex["frame_files"]) == ex["frames_analyzed"] > 0
    assert all(os.path.exists(os.path.join(frames_dir, n)) for n in ex["frame_files"]), "frames not written"
    print("extract assembly OK")

    # no segments -> pairing gracefully unavailable; no provider -> no cinematography
    ex2 = asyncio.run(extract.build_extract(clip, segments=None, frames_dir=None,
                                            embed=fake_embedder, max_frames=8))
    assert ex2["pairing"]["available"] is False
    assert ex2["cinematography"]["available"] is False
    print("graceful-degrade (no segments / no vision) OK")

    shutil.rmtree(TMP, ignore_errors=True)
    print("\nOK - per-video extract verified.")


if __name__ == "__main__":
    main()
