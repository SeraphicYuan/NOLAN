"""Test: video-style visual_stats (deterministic) + VideoStyleStore (no LLM).

Generates a tiny synthetic clip (mostly-red with a blue tail and a hard cut),
then asserts the computed format / palette / temperature / motion / pacing.

Usage:
    D:/env/nolan/python.exe scripts/test_video_style.py
"""

import os
import shutil
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
from src.nolan.video_style import visual_stats
from src.nolan.video_style.store import VideoStyleStore

TMP = "scripts/_vs_tmp"


def make_clip(path, w=64, h=48, fps=10):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(path, fourcc, fps, (w, h))
    red = np.full((h, w, 3), (40, 40, 220), np.uint8)   # BGR red
    blue = np.full((h, w, 3), (220, 40, 40), np.uint8)  # BGR blue
    for _ in range(30): vw.write(red)
    for _ in range(10): vw.write(blue)
    vw.release()


def main():
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(TMP, exist_ok=True)
    clip = os.path.join(TMP, "clip.mp4")
    make_clip(clip)

    stats = visual_stats.analyze_video(clip, segments=None, max_frames=24)
    print("format:", stats["format"])
    print("color:", {k: stats["color"][k] for k in ("temperature", "warm_ratio", "saturation")})
    print("palette top2:", stats["color"]["palette"][:2])
    print("motion:", stats["motion"], "graphics:", stats["graphics"])

    f = stats["format"]
    assert f["width"] == 64 and f["height"] == 48, f
    assert f["aspect_ratio"] == "4:3" and f["orientation"] == "landscape", f
    assert abs(f["duration"] - 4.0) < 0.5, f
    assert stats["color"]["temperature"] == "warm", stats["color"]  # mostly red
    assert stats["color"]["warm_ratio"] > 0.6, stats["color"]
    assert len(stats["color"]["palette"]) >= 2, "expected red + blue clusters"
    assert stats["motion"] > 0.0, "a hard cut should register motion"
    print("visual_stats OK")

    # pacing from synthetic segments
    segs = [{"timestamp_start": 0, "timestamp_end": 2},
            {"timestamp_start": 2, "timestamp_end": 2.5},
            {"timestamp_start": 2.5, "timestamp_end": 4}]
    pac = visual_stats.pacing_from_segments(segs, duration=4.0)
    print("pacing:", pac)
    assert pac["available"] and pac["segment_count"] == 3 and pac["cuts_per_min"] == 45.0, pac
    print("pacing OK")

    # store CRUD
    store = VideoStyleStore(TMP + "/store")
    sid = store.create("Cold Data Explainer")
    e1 = store.add_video(sid, video_path="projects/x/source/a.mp4", title="Ref A", duration=4.0)
    e2 = store.add_video(sid, video_path="projects/x/source/a.mp4")  # dup
    assert e1["skipped"] is False and e2["skipped"] is True, "dedup by video_path"
    store.pair_script_style(sid, "art-stories")
    store.write_extract(sid, e1["slug"], {"format": f, "color": stats["color"]})
    assert store.read_extract(sid, e1["slug"])["color"]["temperature"] == "warm"
    store.mark_analyzed(sid, e1["slug"])
    g = store.get(sid)
    assert g["source_count"] == 1 and g["script_style_id"] == "art-stories"
    assert store.remove_source(sid, e1["slug"]) and store.get(sid)["source_count"] == 0
    assert store.delete(sid)
    print("store OK")

    shutil.rmtree(TMP, ignore_errors=True)
    print("\nOK - video_style visual_stats + store verified.")


if __name__ == "__main__":
    main()
