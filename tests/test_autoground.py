"""S3: autoground fills long ungrounded holds (text AND data) from the pool — image or video — with the
correct `kb` ground shape, honors the 5s threshold + never-ground blocks, and leaves clean when nothing fits."""
import json
from pathlib import Path

from nolan.hyperframes.autoground import ground_data_scenes, _needs_ground, _pool_assets


def _mk(comp: Path):
    (comp / "capture" / "assets" / "videos").mkdir(parents=True)
    (comp / "capture" / "assets" / "mine.jpg").write_bytes(b"i")
    (comp / "capture" / "assets" / "videos" / "lock.mp4").write_bytes(b"v")
    (comp / "capture" / "assets" / "random.jpg").write_bytes(b"i")
    (comp / "pool.json").write_text(json.dumps([
        {"file": "mine.jpg", "media_type": "image", "caption": "kimberley big hole diamond mine", "usable": 9},
        {"file": "lock.mp4", "media_type": "video", "caption": "padlock antitrust court lock", "usable": 8},
        {"file": "random.jpg", "media_type": "image", "caption": "fluffy clouds sky meadow", "usable": 7},
    ]), encoding="utf-8")
    frames = comp / "compositions" / "frames"; frames.mkdir(parents=True)
    frames.joinpath("01.spec.json").write_text(json.dumps({"frames": [{"id": "01", "scenes": [
        {"id": "s1", "type": "statement", "dur": 7, "data": {"kicker": "the ground kept giving at the mine"}},
        {"id": "s2", "type": "statement", "dur": 7, "data": {"kicker": "under antitrust law the lock"}},
        {"id": "s3", "type": "statement", "dur": 7, "data": {"kicker": "quux frobnicate wibble plugh"}},
        {"id": "s4", "type": "statement", "dur": 3, "data": {"kicker": "the ground kept giving at the mine"}},
        {"id": "s5", "type": "document", "dur": 10, "data": {"kicker": "the mine ground"}},
    ]}]}), encoding="utf-8")


def test_autoground_fills_text_and_video_leaves_clean(tmp_path):
    _mk(tmp_path)
    rep = ground_data_scenes(tmp_path, apply=True, min_dur=5.0, use_llm=False, recompose=False)
    g = {x["scene"]: x for x in rep["grounded"]}
    clean = {x["scene"] for x in rep["left_clean"]}

    assert set(g) == {"s1", "s2"}                              # statements grounded (not just data-viz)
    assert g["s1"]["kind"] == "image" and g["s2"]["kind"] == "video"
    assert clean == {"s3"}                                     # no keyword overlap → left clean (not forced)
    # s4 (3s < 5) and s5 (document = never-ground) are not candidates at all
    assert "s4" not in g and "s4" not in clean
    assert "s5" not in g and "s5" not in clean

    # the written spec carries the CORRECT ground shape (kb for image — the key compose reads — video by kind)
    spec = json.loads((tmp_path / "compositions" / "frames" / "01.spec.json").read_text(encoding="utf-8"))
    scenes = {s["id"]: s for s in spec["frames"][0]["scenes"]}
    assert scenes["s1"]["data"]["ground"] == {"kind": "image", "src": "assets/mine.jpg", "kb": [1.0, 1.08]}
    assert scenes["s2"]["data"]["ground"] == {"kind": "video", "src": "assets/videos/lock.mp4"}
    assert "ground" not in scenes["s3"]["data"]               # left clean, no phantom ground


def test_needs_ground_threshold_and_never_ground():
    assert _needs_ground({"type": "statement", "dur": 6, "data": {}}, 5.0)
    assert not _needs_ground({"type": "statement", "dur": 4, "data": {}}, 5.0)        # below threshold
    assert not _needs_ground({"type": "document", "dur": 20, "data": {}}, 5.0)        # self-visual block
    assert not _needs_ground({"type": "statement", "dur": 20,                          # already grounded
                              "data": {"ground": {"kind": "image", "src": "x"}}}, 5.0)


def test_pool_assets_resolves_capture_and_flags_media_type(tmp_path):
    _mk(tmp_path)
    a = _pool_assets(tmp_path)
    assert a["mine.jpg"]["media_type"] == "image" and a["mine.jpg"]["src"] == "assets/mine.jpg"
    assert a["lock.mp4"]["media_type"] == "video" and a["lock.mp4"]["src"] == "assets/videos/lock.mp4"
