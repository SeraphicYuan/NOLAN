"""S3: autoground fills long ungrounded holds (text AND data) from the pool — image or video — with the
correct `kb` ground shape, honors the 5s threshold + never-ground blocks, and leaves clean when nothing fits."""
import json
from pathlib import Path

from nolan.hyperframes.autoground import (_GROUND_BLOCKS, _needs_ground, _pool_assets, ground_data_scenes)


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
    # blocks that IGNORE data.ground are not candidates: writing one there is a silent no-op that also
    # burns a pool asset (observed live on the diamond comp — 7 of 20 picks landed on hero/chart/cycle)
    for blk in ("hero", "chart", "cycle", "diagram", "gallery"):
        assert not _needs_ground({"type": blk, "dur": 20, "data": {}}, 5.0), blk


def test_ground_blocks_matches_the_composer():
    """HONESTY: `_GROUND_BLOCKS` must be exactly the composer templates whose fn calls media_ground().
    If a new block starts (or stops) rendering a ground, this fails until autoground is updated."""
    import re
    root = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"
    consuming, registry = set(), {}
    for name in ("compose.py", "compose_extension.py"):
        src = (root / name).read_text(encoding="utf-8")
        bounds = [(m.start(), m.group(1)) for m in re.finditer(r"^def (\w+)\(", src, re.M)] + [(len(src), "")]
        for i in range(len(bounds) - 1):
            fn = bounds[i][1]
            if fn != "media_ground" and "media_ground(" in src[bounds[i][0]:bounds[i + 1][0]]:
                consuming.add(fn)
        reg = re.search(r"^(?:BLOCKS|EXT_BLOCKS) = \{(.*?)\n?\}", src, re.S | re.M)
        assert reg, f"{name}: block registry not found"
        registry.update(dict(re.findall(r'"(\w+)":\s*(\w+)', reg.group(1))))
    assert len(registry) >= 45, f"only parsed {len(registry)} templates — the registry regex drifted"
    assert {t for t, fn in registry.items() if fn in consuming} == _GROUND_BLOCKS


def test_pool_assets_resolves_capture_and_flags_media_type(tmp_path):
    _mk(tmp_path)
    a = _pool_assets(tmp_path)
    assert a["mine.jpg"]["media_type"] == "image" and a["mine.jpg"]["src"] == "assets/mine.jpg"
    assert a["lock.mp4"]["media_type"] == "video" and a["lock.mp4"]["src"] == "assets/videos/lock.mp4"


def test_ground_src_is_derived_from_where_the_file_resolves(tmp_path):
    """REGRESSION: `src` must never be GUESSED from media_type. `file` is sometimes bare and sometimes
    already carries its subdir, and a manually-clipped video lands in assets/ not assets/videos/ — guessing
    produced dead links both ways, and a dead ground is SILENT (freeze-heal skips it, the root mount finds
    nothing). Every case here was a real entry in the diamond comp's pool."""
    (tmp_path / "capture" / "assets" / "videos").mkdir(parents=True)
    (tmp_path / "capture" / "assets" / "generated").mkdir(parents=True)
    (tmp_path / "assets").mkdir(parents=True)
    (tmp_path / "capture" / "assets" / "videos" / "a21_03.mp4").write_bytes(b"v")   # pool clip, subdir in `file`
    (tmp_path / "capture" / "assets" / "generated" / "a3_gen.png").write_bytes(b"i")  # generated, subdir
    (tmp_path / "capture" / "assets" / "a1_00.jpg").write_bytes(b"i")               # pool still, bare
    (tmp_path / "assets" / "clip_1125_1133.mp4").write_bytes(b"v")                  # MANUAL clip: bare + assets/
    (tmp_path / "pool.json").write_text(json.dumps([
        {"file": "videos/a21_03.mp4", "media_type": "video", "caption": "vault", "usable": 8},
        {"file": "generated/a3_gen.png", "media_type": "image", "caption": "gen", "usable": 8},
        {"file": "a1_00.jpg", "media_type": "image", "caption": "still", "usable": 8},
        {"file": "clip_1125_1133.mp4", "media_type": "video", "caption": "manual", "usable": 8},
    ]), encoding="utf-8")
    a = _pool_assets(tmp_path)
    assert a["videos/a21_03.mp4"]["src"] == "assets/videos/a21_03.mp4"       # not assets/videos/videos/…
    assert a["generated/a3_gen.png"]["src"] == "assets/generated/a3_gen.png"
    assert a["a1_00.jpg"]["src"] == "assets/a1_00.jpg"
    assert a["clip_1125_1133.mp4"]["src"] == "assets/clip_1125_1133.mp4"     # not assets/videos/…
    for v in a.values():                                                     # every emitted src resolves
        assert (tmp_path / v["src"]).exists() or (tmp_path / "capture" / v["src"]).exists(), v["src"]
