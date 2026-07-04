"""Test: per-shot visual facts (Tier 1 of video deconstruction) — no LLM/vision.

Verifies:
  1. Optical-flow classifier: pan / push-in / pull-out / static / subject
     motion on synthetic frames, and the treatment-hint mapping.
  2. Shot detection + E2E ensure_visual_facts on a generated 3-scene video:
     shots persisted to the library `shots` table, pan detected, idempotent.
  3. Schema v8: shots roundtrip + v7→v8 upgrade path.

Usage:
    D:/env/nolan/python.exe -X utf8 scripts/test_visual_facts.py
"""

import asyncio
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from src.nolan.indexer import VideoIndex
from src.nolan.visual_facts import (FLOW_SIZE, classify_flow, _camera_label,
                                    _subject_label, detect_shots,
                                    ensure_visual_facts, facts_current,
                                    treatment_hint)


def _base(rng):
    b = (rng.random((FLOW_SIZE[1] * 2, FLOW_SIZE[0] * 2)) * 255).astype(np.uint8)
    b = cv2.GaussianBlur(b, (31, 31), 0)
    return cv2.normalize(b, None, 0, 255, cv2.NORM_MINMAX)


def test_classifier():
    rng = np.random.default_rng(7)
    base = _base(rng)

    def crop(x=0, zoom=1.0):
        h, w = FLOW_SIZE[1], FLOW_SIZE[0]
        ch, cw = int(h / zoom), int(w / zoom)
        cy, cx = base.shape[0] // 2, base.shape[1] // 2 + x
        return cv2.resize(base[cy - ch // 2:cy + ch // 2, cx - cw // 2:cx + cw // 2], FLOW_SIZE)

    dt = 0.4
    m = classify_flow(crop(), crop(12), dt)
    assert _camera_label(m) == "pan-right", m
    m = classify_flow(crop(zoom=1.0), crop(zoom=1.12), dt)
    assert _camera_label(m) == "push-in", m
    m = classify_flow(crop(zoom=1.12), crop(zoom=1.0), dt)
    assert _camera_label(m) == "pull-out", m
    m = classify_flow(crop(), crop(), dt)
    assert _camera_label(m) == "static" and _subject_label(m["subject"]) == "none", m

    patch = (rng.random((80, 120)) * 255).astype(np.uint8)
    patch = cv2.normalize(cv2.GaussianBlur(patch, (15, 15), 0), None, 0, 255, cv2.NORM_MINMAX)
    a, b = crop().copy(), crop().copy()
    a[40:120, 60:180] = patch
    b[40:120, 68:188] = patch
    m = classify_flow(a, b, dt)
    assert _subject_label(m["subject"]) in ("medium", "high"), m["subject"]

    assert treatment_hint("push-in", "none") == "ken-burns-in"
    assert treatment_hint("pull-out", "low") == "ken-burns-out"
    assert treatment_hint("pan-left", "none") == "ken-burns-pan"
    assert treatment_hint("static", "none") == "hold"
    assert treatment_hint("static", "high") == "as-is"
    print("classifier OK — pan/zoom/static/subject + treatment mapping")


def make_test_video(path: Path):
    w, h, fps = 320, 180, 24

    def scene(seed, frames, tint, pan=0):
        r = np.random.default_rng(seed)
        big = (r.random((h * 2, w * 2, 3)) * 255).astype(np.uint8)
        big = cv2.GaussianBlur(big, (31, 31), 0)
        big = cv2.normalize(big, None, 0, 255, cv2.NORM_MINMAX)
        big = (big * np.array(tint).reshape(1, 1, 3)).astype(np.uint8)
        return [big[h // 2:h // 2 + h, w // 2 + int(pan * i):w // 2 + int(pan * i) + w].copy()
                for i in range(frames)]

    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for f in (scene(1, 72, (1.0, 0.4, 0.3)) + scene(2, 72, (0.3, 1.0, 0.4), pan=1)
              + scene(3, 72, (0.4, 0.3, 1.0))):
        vw.write(f)
    vw.release()


def test_e2e(td: Path):
    vp = td / "test.mp4"
    make_test_video(vp)
    shots = detect_shots(vp)
    assert len(shots) == 3, [s["timestamp_start"] for s in shots]

    idx = VideoIndex(td / "t.db")
    idx.add_video(path=str(vp), duration=9.0, checksum="c", fingerprint="fp-e2e")
    rows = asyncio.run(ensure_visual_facts(str(vp), idx))
    assert rows[1]["camera_motion"].startswith("pan"), rows[1]["camera_motion"]
    assert rows[1]["treatment_hint"] == "ken-burns-pan"
    assert rows[0]["camera_motion"] == "static" and rows[0]["treatment_hint"] == "hold"
    assert facts_current(idx, str(vp))
    rows2 = asyncio.run(ensure_visual_facts(str(vp), idx))
    assert [r["id"] for r in rows2] == [r["id"] for r in rows], "should be idempotent"
    print("e2e OK — 3 shots, pan detected + persisted, idempotent")


def test_schema(td: Path):
    p = td / "mig.db"
    VideoIndex(p)
    conn = sqlite3.connect(p)
    conn.execute("DROP TABLE shots")
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version VALUES (7)")
    conn.commit()
    conn.close()
    VideoIndex(p)   # reopen → migrate
    conn = sqlite3.connect(p)
    v = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    t = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='shots'").fetchone()
    assert v == 8 and t, (v, t)
    conn.close()

    idx = VideoIndex(td / "rt.db")
    vid = idx.add_video(path="x.mp4", duration=10.0, checksum="c", fingerprint="fp1")
    idx.add_shots_bulk(vid, [{"shot_index": 0, "timestamp_start": 0.0, "timestamp_end": 3.0,
                              "camera_motion": "push-in", "treatment_hint": "ken-burns-in",
                              "rep_timestamp": 1.5, "facts_version": 1}])
    s = idx.get_shots("x.mp4")[0]
    idx.update_shot_vision_facts(s["id"], asset_type="painting", identity_hint="Danse Macabre")
    s = idx.get_shots_by_video_id(vid)[0]
    assert s["asset_type"] == "painting" and s["identity_hint"] == "Danse Macabre"
    idx.clear_shots(vid)
    assert idx.get_shots("x.mp4") == []
    print("schema OK — v7->v8 migration + shots roundtrip + vision-facts update")


class FakeVision:
    """Concurrency-aware fake provider: canned JSON, one designated failure."""

    def __init__(self, fail_index=None):
        self.fail_index = fail_index
        self.calls = 0
        self.in_flight = 0
        self.max_in_flight = 0

    async def describe_image(self, image_path, prompt):
        import asyncio
        import json as _json
        self.calls += 1
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0.05)          # let the semaphore overlap calls
        self.in_flight -= 1
        idx = int(Path(image_path).stem.split("_")[1])
        if idx == self.fail_index:
            raise RuntimeError("simulated vision failure")
        return _json.dumps({"asset_type": "painting", "framing": "wide",
                            "on_screen_text": "", "identity_hint": f"Artwork {idx}",
                            "confidence": "high"})


def test_vision_concurrent_and_backfill(td: Path):
    vp = td / "vtest.mp4"
    make_test_video(vp)
    idx = VideoIndex(td / "v.db")
    idx.add_video(path=str(vp), duration=9.0, checksum="c", fingerprint="fp-vis")

    # 1) motion-only first (no provider) → rows persisted without vision facts
    rows = asyncio.run(ensure_visual_facts(str(vp), idx))
    assert rows and all(r["asset_type"] is None for r in rows)

    # 2) re-run with provider → INCREMENTAL vision backfill (ids unchanged),
    #    concurrent calls, one simulated failure isolated
    fake = FakeVision(fail_index=rows[1]["shot_index"])
    rows2 = asyncio.run(ensure_visual_facts(str(vp), idx, vision_provider=fake))
    assert [r["id"] for r in rows2] == [r["id"] for r in rows], "backfill must not replace rows"
    assert fake.calls == 3 and fake.max_in_flight >= 2, \
        (fake.calls, fake.max_in_flight)
    ok = [r for r in rows2 if r["asset_type"] == "painting"]
    failed = [r for r in rows2 if r["asset_type"] is None]
    assert len(ok) == 2 and len(failed) == 1, "failure must be isolated, not fatal"
    assert ok[0]["identity_hint"].startswith("Artwork")

    # 3) third run: vision present → returned as-is, no new calls
    fake2 = FakeVision()
    rows3 = asyncio.run(ensure_visual_facts(str(vp), idx, vision_provider=fake2))
    assert fake2.calls == 0 and [r["id"] for r in rows3] == [r["id"] for r in rows]
    print("vision OK — concurrent (overlap observed), write-through backfill, failure isolated")


def main():
    test_classifier()
    # ignore_cleanup_errors: sqlite conns opened via `with connect()` inside
    # VideoIndex._init_db commit-but-don't-close, which locks files on Windows.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        test_e2e(Path(td))
        test_schema(Path(td))
        test_vision_concurrent_and_backfill(Path(td))
    print("\nOK - visual facts verified.")


if __name__ == "__main__":
    main()
