"""Temporal render gate (nolan.hyperframes.temporal_gate) — the deterministic motion check.

Locks the pure classifier + the frame-motion measurement (POST_MORTEM: the 'reads like a slide'
beats — a static/frozen/dead-air stretch nothing looked at because only midpoint stills were judged).
"""
from pathlib import Path

from nolan.hyperframes import temporal_gate as tg


def test_classify_frozen_static_deadair_and_ok():
    # frozen: ~0 motion over a long window
    assert "FROZEN" in tg.classify_motion(0.0005, 0.0005, 12.0, grounded=True)
    # static hold: low motion, ungrounded, long -> reads like a slide
    assert "STATIC-HOLD" in tg.classify_motion(0.01, 0.01, 10.0, grounded=False)
    # a grounded low-motion scene is NOT a static-hold (footage moves under it)
    assert tg.classify_motion(0.01, 0.05, 10.0, grounded=True) is None
    # dead-air tail: motion up front, dead tail
    assert "DEAD-AIR-TAIL" in tg.classify_motion(0.05, 0.0005, 10.0, grounded=True)
    # short holds are never flagged
    assert tg.classify_motion(0.0, 0.0, 3.0, grounded=False) is None
    # healthy motion -> None
    assert tg.classify_motion(0.08, 0.07, 10.0, grounded=False) is None


def test_frame_motion_on_synthetic_frames(tmp_path):
    import numpy as np
    from PIL import Image

    def _save(name, arr):
        p = tmp_path / name
        Image.fromarray((arr * 255).astype("uint8"), mode="L").save(p)
        return p

    # three identical frames -> ~0 motion
    flat = np.zeros((36, 64), dtype="float32")
    frozen = [_save(f"f{i}.png", flat) for i in range(3)]
    assert tg.frame_motion(frozen)["mean"] < 0.002

    # alternating black/white -> large motion
    black = np.zeros((36, 64), dtype="float32")
    white = np.ones((36, 64), dtype="float32")
    moving = [_save("m0.png", black), _save("m1.png", white), _save("m2.png", black)]
    fm = tg.frame_motion(moving)
    assert fm["mean"] > 0.5 and fm["pairs"] == 2


def test_scene_windows_offsets_and_grounded(tmp_path):
    import json
    comp = tmp_path / "comp"
    (comp / "compositions" / "frames").mkdir(parents=True)
    (comp / "audio_meta.json").write_text(json.dumps(
        {"voices": [{"frame": 1, "duration_s": 10.0}, {"frame": 2, "duration_s": 8.0}]}), encoding="utf-8")
    (comp / "compositions" / "frames" / "01.spec.json").write_text(json.dumps(
        {"frames": [{"id": "01", "dur": 10.0, "scenes": [
            {"id": "s1", "type": "statement", "start": 0, "dur": 10, "data": {}}]}]}), encoding="utf-8")
    (comp / "compositions" / "frames" / "02.spec.json").write_text(json.dumps(
        {"frames": [{"id": "02", "dur": 8.0, "scenes": [
            {"id": "s1", "type": "statement", "start": 0, "dur": 8,
             "data": {"ground": {"kind": "video", "src": "a.mp4"}}}]}]}), encoding="utf-8")
    wins = tg.scene_windows(comp)
    assert wins[0]["start"] == 0.0 and not wins[0]["grounded"]
    assert wins[1]["start"] == 10.0 and wins[1]["grounded"]     # 2nd frame offset by the 1st's VO duration
