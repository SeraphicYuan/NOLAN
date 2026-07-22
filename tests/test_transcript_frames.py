"""Transcript visual tier — CLIP-embed frames (tagged with video_id + timestamp) into an isolated
ImageLibrary and retrieve them by text→image search, resolving each hit back to a video + a YouTube
&t= deep-link. Frame FETCHING (ranged ffmpeg / storyboard sprites) is network-bound and validated live;
here we test the embed→search round-trip + metadata plumbing deterministically with synthetic frames."""
from pathlib import Path


def test_parse_tags():
    from nolan.transcript_frames import _parse_tags
    assert _parse_tags("video_id=abc;t=125.5;kind=keyframe") == {"video_id": "abc", "t": "125.5", "kind": "keyframe"}
    assert _parse_tags("") == {}


def test_embed_and_visual_search_roundtrip(tmp_path):
    from PIL import Image

    from nolan import transcript_frames as tf
    store = tmp_path / "store"
    fdir = tmp_path / "frames"
    fdir.mkdir()
    red = fdir / "r.jpg"
    Image.new("RGB", (80, 60), (200, 30, 30)).save(red)
    blue = fdir / "b.jpg"
    Image.new("RGB", (80, 60), (30, 30, 200)).save(blue)

    n = tf.embed_frames([(120.0, red)], "vidREDxxxxx", "https://www.youtube.com/watch?v=vidREDxxxxx",
                        kind="keyframe", base_dir=store)
    n += tf.embed_frames([(300.0, blue)], "vidBLUxxxxx", "https://www.youtube.com/watch?v=vidBLUxxxxx",
                         kind="storyboard", base_dir=store)
    assert n == 2

    res = tf.visual_search("a colorful frame", n=10, base_dir=store)
    assert len(res) == 2                                      # both embedded frames come back
    by_vid = {r["video_id"]: r for r in res}
    assert set(by_vid) == {"vidREDxxxxx", "vidBLUxxxxx"}
    r = by_vid["vidREDxxxxx"]
    assert r["start"] == 120.0 and r["kind"] == "keyframe"    # tags round-tripped off the Asset row
    assert r["watch_url"].endswith("&t=120s")                # timestamp deep-link
    assert r["score"] >= 0.0 and Path(r["thumb"]).exists()   # a real thumbnail path
