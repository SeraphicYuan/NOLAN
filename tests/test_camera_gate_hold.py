"""A DELIBERATE hold is not a frozen frame — the camera's vocabulary reaching the temporal gate.

WIRING_CHECKLIST pitfall #7, and this time it was mine: the camera umbrella made `hold` a legitimate
choice (an iconic image at a climax, a beat too short for a move to read, a source too low-res to push
without turning to mush) while `temporal_gate` still treated any static scene as FROZEN. Left alone,
the first end-to-end run would have flagged every intentional hold — and a gate whose failures are
false positives is one people learn to skip, taking its true positives with it (pitfall #11).

The fix is not an exemption for static scenes. It is that the camera RECORDS its decision on the ground
element, so the gate can tell a choice from an accident.
"""
import json
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"
sys.path.insert(0, str(BRIDGE))
import compose  # noqa: E402

from nolan.hyperframes import temporal_gate as tg  # noqa: E402

FROZEN = dict(mean_motion=0.0005, tail_motion=0.0005, dur=12.0, grounded=True)


def test_a_deliberate_hold_is_not_flagged():
    assert tg.classify_motion(**FROZEN, camera="hold", camera_why="640x360 source would upscale 3.0x") is None


def test_a_frozen_scene_with_no_decision_behind_it_still_fails():
    """The case the gate exists for — a clip that froze, not a frame we chose to hold."""
    v = tg.classify_motion(**FROZEN)
    assert v and "FROZEN" in v


def test_a_moving_camera_does_not_excuse_a_frozen_render():
    """`camera="push-in"` and zero measured motion means the move did not reach the pixels — exactly
    the kind of silent breakage this gate is for, so it must still fail."""
    v = tg.classify_motion(**FROZEN, camera="push-in", camera_why="no cue — the default push")
    assert v and "FROZEN" in v


def test_the_composer_records_its_decision_on_the_ground():
    """The gate reads the HTML, so the decision has to be IN the HTML."""
    compose._CAMERA_PREV_FAMILY = None
    frag, _tl = compose.media_ground("s9", {"kind": "image", "src": "assets/x.jpg"}, 0.0, 11.0)
    gnd = next(f for f in frag if 'id="s9-gnd"' in f)
    assert 'data-camera="' in gnd and 'data-camera-why="' in gnd, gnd[:200]


def test_a_hold_records_WHY_it_held(tmp_path, monkeypatch):
    """'held' without a reason is a silent cap wearing a label."""
    from PIL import Image
    Image.new("RGB", (640, 360), (90, 90, 90)).save(tmp_path / "low.jpg")
    monkeypatch.setitem(compose.__dict__, "_ASSET_BASE", tmp_path)
    compose._CAMERA_PREV_FAMILY = None
    frag, tl = compose.media_ground("s1", {"kind": "image", "src": "low.jpg"}, 0.0, 12.0)
    gnd = next(f for f in frag if 'id="s1-gnd"' in f)
    assert 'data-camera="hold"' in gnd, gnd[:240]
    assert "upscale" in gnd, "the hold gave no reason"
    assert not [t for t in tl if "scale" in t]


def test_the_gate_reads_the_decision_out_of_a_real_frame_pair(tmp_path):
    """End to end through `scene_windows`: spec + composed HTML on disk, decision recovered."""
    fdir = tmp_path / "compositions" / "frames"
    fdir.mkdir(parents=True)
    scenes = [{"id": "s1", "type": "statement", "start": 0.0, "dur": 12.0,
               "data": {"kicker": "K", "lines": ["one"], "operative": "one",
                        "ground": {"kind": "image", "src": "assets/x.jpg", "camera": "hold"}}}]
    (fdir / "01-f.spec.json").write_text(
        json.dumps({"frames": [{"id": "01-f", "dur": 12.0, "scenes": scenes}]}), encoding="utf-8")
    compose._CAMERA_PREV_FAMILY = None
    (fdir / "01-f.html").write_text(compose.compose_frame("01-f", 12.0, scenes), encoding="utf-8")

    rows = tg.scene_windows(tmp_path)
    row = next(r for r in rows if r["scene"] == "s1")
    assert row["camera"] == "hold", row
    assert tg.classify_motion(**FROZEN, camera=row["camera"], camera_why=row["camera_why"]) is None


def test_a_missing_html_degrades_to_no_decision(tmp_path):
    """An un-composed frame must not crash the gate — it simply has no camera decision to read."""
    fdir = tmp_path / "compositions" / "frames"
    fdir.mkdir(parents=True)
    (fdir / "01-f.spec.json").write_text(json.dumps({"frames": [{"id": "01-f", "dur": 8.0, "scenes": [
        {"id": "s1", "type": "statement", "start": 0.0, "dur": 8.0, "data": {"lines": ["x"]}}]}]}),
        encoding="utf-8")
    rows = tg.scene_windows(tmp_path)
    assert rows and rows[0]["camera"] == ""
