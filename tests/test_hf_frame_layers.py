"""Layer-lanes map (edit.frame_layers): a frame's timeline broken into bg/overlay/text/fx lanes, one element
per asset / text / motion, each carrying the inspector control it edits (`target`) so the lanes UI can jump
straight to the right field. Derived from the SPEC (fields = layers)."""
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"

from nolan.hyperframes import edit as hfedit  # noqa: E402


@pytest.fixture()
def comp():
    name = "_hf_layers_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    fdir = dst / "compositions" / "frames"
    fdir.mkdir(parents=True)
    # one frame, two scenes: a statement with a VIDEO ground + reveal + a transition, and a newshead with an image
    (fdir / "f1.spec.json").write_text(json.dumps({"frames": [{"id": "f1", "dur": 12.0, "scenes": [
        {"id": "s1", "type": "statement", "start": 0, "dur": 6,
         "data": {"lines": ["hello there"], "reveal": "scramble", "ground": {"kind": "video", "src": "assets/x.mp4"}},
         "transition_out": {"kind": "wipe", "dur": 0.5}},
        {"id": "s2", "type": "newshead", "start": 6, "dur": 6,
         "data": {"headline": "Big news", "image": "assets/pic.png"}},
    ]}]}), encoding="utf-8")
    (dst / "hyperframes.json").write_text('{"theme":"highlighter-editorial"}', encoding="utf-8")
    try:
        yield name
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def _by(els, sid, lane=None, kind=None):
    return [e for e in els if e["scene_id"] == sid and (lane is None or e["lane"] == lane) and (kind is None or e["kind"] == kind)]


def test_lanes_and_targets(comp):
    m = hfedit.frame_layers(comp, "f1")
    assert m["lanes"] == ["bg", "overlay", "text", "fx"] and m["dur"] == 12.0
    els = m["elements"]

    # s1: a VIDEO ground → bg lane, targets the `ground` field, carries its src as the thumb + its time window
    g = _by(els, "s1", "bg", "asset")
    assert len(g) == 1 and g[0]["target"] == "ground" and g[0]["thumb"] == "assets/x.mp4"
    assert g[0]["start"] == 0 and g[0]["dur"] == 6
    # s1 text → text lane targeting the block's text field; its reveal → a motion chip targeting `reveal`
    assert _by(els, "s1", "text", "text")[0]["target"] == "lines"
    assert _by(els, "s1", "text", "motion")[0]["target"] == "reveal"
    # s1 transition → fx lane targeting `transition`
    assert _by(els, "s1", "fx", "motion")[0]["target"] == "transition"

    # s2: an IMAGE overlay → overlay lane targeting `image`; no ground, no transition
    ov = _by(els, "s2", "overlay", "asset")
    assert len(ov) == 1 and ov[0]["target"] == "image" and ov[0]["thumb"] == "assets/pic.png"
    assert not _by(els, "s2", "bg") and not _by(els, "s2", "fx")


@pytest.fixture()
def usage_comp():
    name = "_hf_usage_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    fdir = dst / "compositions" / "frames"
    fdir.mkdir(parents=True)
    (fdir / "f1.spec.json").write_text(json.dumps({"frames": [{"id": "f1", "dur": 10, "scenes": [
        {"id": "f1s1", "type": "statement", "start": 0, "dur": 5,
         "data": {"lines": ["a"], "ground": {"kind": "video", "src": "assets/videos/shared.mp4"}}},
        {"id": "f1s2", "type": "newshead", "start": 5, "dur": 5,
         "data": {"headline": "b", "image": "assets\\pic1.png"}},                       # backslash + no subdir
    ]}]}), encoding="utf-8")
    (fdir / "f2.spec.json").write_text(json.dumps({"frames": [{"id": "f2", "dur": 8, "scenes": [
        {"id": "f2s1", "type": "statement", "start": 0, "dur": 5,
         "data": {"lines": ["c"], "ground": {"kind": "video", "src": "capture/assets/videos/shared.mp4"}}},  # same file, other prefix
        {"id": "f2s2", "type": "statement", "start": 5, "dur": 3, "data": {"lines": ["text only"]}},          # no media
    ]}]}), encoding="utf-8")
    (dst / "hyperframes.json").write_text('{"theme":"highlighter-editorial"}', encoding="utf-8")
    try:
        yield name
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def test_asset_scene_usage_reverse_index(usage_comp):
    """The /pool HF by-scene index: file -> [scene_id], normalized across assets/ + capture/assets/ prefixes
    (backslashes tolerated); a file used in N scenes lists N; text-only scenes contribute nothing."""
    u = hfedit.asset_scene_usage(usage_comp)
    bf, order = u["by_file"], u["scene_order"]
    assert bf["videos/shared.mp4"] == ["f1s1", "f2s1"]        # same file, two scenes, two frames, two prefixes
    assert bf["pic1.png"] == ["f1s2"]                          # backslash + bare-name normalization
    assert order == ["f1s1", "f1s2", "f2s1", "f2s2"]           # frame/scene order preserved
    assert "capture/assets/videos/shared.mp4" not in bf and "assets/videos/shared.mp4" not in bf  # prefixes stripped


def test_no_media_field_no_asset_chip(comp):
    # a scene whose ground is a non-media kind (paper) contributes NO bg asset chip (nothing to target)
    sf = (VIDEOS / comp / "compositions" / "frames" / "f1.spec.json")
    spec = json.loads(sf.read_text())
    spec["frames"][0]["scenes"][0]["data"]["ground"] = {"kind": "paper"}
    sf.write_text(json.dumps(spec), encoding="utf-8")
    els = hfedit.frame_layers(comp, "f1")["elements"]
    assert not _by(els, "s1", "bg")            # paper ground has no src → no asset chip
    assert _by(els, "s1", "text", "text")      # text is still there


def test_frame_transcripts_sliced_by_scene_window():
    """Each scene's narration = the VO words whose timing overlaps its window (audio_meta word timings)."""
    name = "_hf_transcripts_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "compositions" / "frames").mkdir(parents=True)
    (dst / "compositions" / "frames" / "01-x.spec.json").write_text(json.dumps({"frames": [{"id": "01-x", "dur": 10.0, "scenes": [
        {"id": "s1", "type": "statement", "start": 0, "dur": 4, "data": {"lines": ["a"]}},
        {"id": "s2", "type": "statement", "start": 4, "dur": 6, "data": {"lines": ["b"]}},
    ]}]}), encoding="utf-8")
    (dst / "hyperframes.json").write_text('{"theme":"highlighter-editorial"}', encoding="utf-8")
    (dst / "audio_meta.json").write_text(json.dumps({"voices": [{"frame": "1", "words": [
        {"word": "hello", "start": 0.0, "end": 1.0}, {"word": "there", "start": 1.0, "end": 2.0},
        {"word": "world", "start": 4.5, "end": 5.5}, {"word": "again", "start": 8.0, "end": 9.0},
    ]}]}), encoding="utf-8")
    try:
        t = hfedit.frame_transcripts(name, "01-x")
        assert t["s1"] == "hello there" and t["s2"] == "world again"
    finally:
        shutil.rmtree(dst, ignore_errors=True)
