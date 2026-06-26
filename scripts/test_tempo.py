"""Test: video-measured tempo — cut detection + curve + motion (synthetic clip).

Clip: 3s red, 3s blue, 3s green (hard cuts at 3s/6s), then 3s of a small white
square moving on black (a cut into black at 9s, then intra-shot motion, no cuts).

Usage:
    D:/env/nolan/python.exe scripts/test_tempo.py
"""

import os
import shutil
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
from src.nolan.video_style import tempo

TMP = "scripts/_tempo_tmp"


def make_clip(path, w=64, h=48, fps=10):
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    colors = [(40, 40, 220), (220, 40, 40), (40, 200, 40)]  # red, blue, green (BGR)
    for c in colors:
        block = np.full((h, w, 3), c, np.uint8)
        for _ in range(30):
            vw.write(block)
    # moving white square on black (intra-shot motion, no cuts)
    for k in range(30):
        fr = np.zeros((h, w, 3), np.uint8)
        x = (k * 2) % (w - 10)
        fr[20:28, x:x + 8] = (255, 255, 255)
        vw.write(fr)
    vw.release()


def main():
    shutil.rmtree(TMP, ignore_errors=True); os.makedirs(TMP, exist_ok=True)
    clip = os.path.join(TMP, "clip.mp4")
    make_clip(clip)

    res = tempo.analyze_tempo(clip, sample_fps=4.0, window=3.0)
    print("available:", res["available"], "| cut_count:", res["cut_count"], "| cpm:", res["cuts_per_min"])
    print("shot_len mean/median/stdev:", res["shot_len_mean"], res["shot_len_median"], res["shot_len_stdev"])
    print("intra_shot_motion:", res["intra_shot_motion"], "| energy:", res["energy"], "| tempo:", res["tempo"], "| trend:", res["trend"])
    for w in res["curve"]:
        print(f"  window t={w['t']:>4}  cuts/min={w['cuts_per_min']:>5}  motion={w['motion']}")

    assert res["available"]
    assert 2 <= res["cut_count"] <= 4, f"expected ~3 cuts, got {res['cut_count']}"
    assert res["cuts_per_min"] > 0 and res["energy"] > 0
    assert len(res["curve"]) == 4, f"expected 4 windows, got {len(res['curve'])}"
    # the moving-square window (last) should have more intra-shot motion than a static colour window (first)
    assert res["curve"][-1]["motion"] > res["curve"][0]["motion"], \
        f"moving window motion {res['curve'][-1]['motion']} should exceed static {res['curve'][0]['motion']}"
    assert res["tempo"] in ("slow", "moderate", "fast")
    print("\ncut detection + curve + motion-weighting OK")

    # guard: unreadable path
    g = tempo.analyze_tempo(os.path.join(TMP, "nope.mp4"))
    assert g["available"] is False
    print("unreadable-video guard OK")

    shutil.rmtree(TMP, ignore_errors=True)
    print("\nOK - tempo analysis verified.")


if __name__ == "__main__":
    main()
