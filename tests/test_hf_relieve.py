"""Long-hold reliever (nolan.hyperframes.relieve) — POST_MORTEM #9.

Turns the advisory LONG-HOLD flag into concrete remedies. Locks the pure parts: ground-asset matching
and the per-scene remedy proposal (ground when a pool image relates, split for multi-line, cadence
fallback).
"""
import json
from pathlib import Path

from nolan.hyperframes import relieve


def test_best_ground_picks_related_image():
    pool = [
        {"file": "candle.jpg", "media_type": "image", "caption": "a candle flame flickering in the dark"},
        {"file": "plough.jpg", "media_type": "image", "caption": "a skeleton guiding a ploughman and horses in a field"},
        {"file": "clip.mp4", "media_type": "video", "caption": "a ploughman ploughing a field"},   # video ignored
    ]
    g = relieve.best_ground("the ploughman toils in his field until death", pool)
    assert g and g["file"] == "plough.jpg"                # the related IMAGE, not the candle, not the video
    # no relation -> None (author picks / generates rather than a bad literal match)
    assert relieve.best_ground("quantum entanglement in superconductors", pool) is None


def _comp(tmp_path, scenes, frame_dur, pool):
    comp = tmp_path / "comp"
    (comp / "compositions" / "frames").mkdir(parents=True)
    words = [{"word": f"w{i}", "start": round(i, 2), "end": round(i + 0.9, 2)} for i in range(int(frame_dur) + 2)]
    (comp / "audio_meta.json").write_text(json.dumps(
        {"voices": [{"frame": 1, "duration_s": frame_dur, "words": words}]}), encoding="utf-8")
    (comp / "compositions" / "frames" / "01.spec.json").write_text(
        json.dumps({"frames": [{"id": "01", "dur": frame_dur, "scenes": scenes}]}), encoding="utf-8")
    (comp / "pool.json").write_text(json.dumps(pool), encoding="utf-8")
    return comp


def test_propose_emits_ground_split_and_cadence(tmp_path):
    # one ungrounded 2-line statement spanning ~20s -> LONG-HOLD; a related pool image exists
    scenes = [{"id": "s1", "type": "statement", "start": 0, "dur": 10,
               "data": {"anchor": "w0 w1", "lines": ["death comes for the ploughman", "in his own field"]}},
              {"id": "s2", "type": "statement", "start": 10, "dur": 10, "data": {"anchor": "w10 w11", "lines": ["and none escape"]}}]
    pool = [{"file": "plough.jpg", "media_type": "image",
             "caption": "a skeleton guiding a ploughman and horses through a field"}]
    comp = _comp(tmp_path, scenes, 20.0, pool)

    props = relieve.propose(comp)
    assert props, "expected at least one long-hold proposal"
    p = next(p for p in props if p["scene"] == "s1")
    kinds = [r["kind"] for r in p["remedies"]]
    assert "ground" in kinds and "split" in kinds and "cadence" in kinds     # all three offered
    ground = next(r for r in p["remedies"] if r["kind"] == "ground")
    assert ground["asset"] == "plough.jpg"
    assert ground["patch"]["data.ground"]["src"] == "assets/plough.jpg"       # gate-ready patch
    assert ground["patch"]["data.ground"]["kb"] == [1.0, 1.12]


def test_no_long_holds_no_proposals(tmp_path):
    # short, readable scenes -> nothing to relieve
    scenes = [{"id": "s1", "type": "statement", "start": 0, "dur": 3, "data": {"anchor": "w0", "lines": ["a"]}},
              {"id": "s2", "type": "statement", "start": 3, "dur": 3, "data": {"anchor": "w3", "lines": ["b"]}}]
    comp = _comp(tmp_path, scenes, 6.0, [])
    assert relieve.propose(comp) == []
