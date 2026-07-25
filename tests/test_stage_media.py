"""A1 (post-mortem): assemble_media.stage_referenced_media resolves referenced assets/x from capture/**."""
import json
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"
sys.path.insert(0, str(BRIDGE))
import assemble_media as AM  # noqa: E402


def _spec(frames_dir: Path, name: str, spec: dict):
    (frames_dir / name).write_text(json.dumps(spec), encoding="utf-8")


def test_stage_referenced_media_bridges_capture_to_assets(tmp_path):
    comp = tmp_path
    frames = comp / "compositions" / "frames"
    frames.mkdir(parents=True)
    # a video ground, an image ground (both physically in capture/, not assets/), and one truly-missing ref
    _spec(frames, "01.spec.json", {"frames": [{"scenes": [
        {"id": "s1", "data": {"ground": {"kind": "video", "src": "assets/vid.mp4"}}},
        {"id": "s2", "data": {"ground": {"kind": "image", "src": "assets/img.jpg"}}},
        {"id": "s3", "data": {"ground": {"kind": "video", "src": "assets/gone.mp4"}}},
    ]}]})
    (comp / "capture" / "keyassets" / "videos").mkdir(parents=True)
    (comp / "capture" / "assets").mkdir(parents=True)
    (comp / "capture" / "keyassets" / "videos" / "vid.mp4").write_bytes(b"v")   # lives under capture/
    (comp / "capture" / "assets" / "img.jpg").write_bytes(b"i")

    # A genuinely-absent ref is now FATAL, not a warning: it used to only print, the render went ahead,
    # and v2 died ~20 min later on a wall of HTTP404 (see tests/test_assemble_media_missing.py). Staging
    # still happens for everything that DOES resolve — that work is useful and idempotent — so exercise
    # the staging contract under the knowing-exception var, then assert the gate still bites without it.
    import os
    import pytest

    os.environ["HF_ALLOW_MISSING_MEDIA"] = "1"
    try:
        res = AM.stage_referenced_media(comp)
        assert set(res["staged"]) == {"assets/vid.mp4", "assets/img.jpg"}
        assert res["missing"] == ["assets/gone.mp4"]             # still reported, just no longer fatal
        assert (comp / "assets" / "vid.mp4").exists()            # copied in from capture/keyassets/videos
        assert (comp / "assets" / "img.jpg").exists()            # copied in from capture/assets
        assert not (comp / "assets" / "gone.mp4").exists()

        # idempotent: a second pass stages nothing (already present)
        assert AM.stage_referenced_media(comp)["staged"] == []
    finally:
        os.environ.pop("HF_ALLOW_MISSING_MEDIA", None)

    # …and the unresolvable ref is STILL fatal on a later run — staging what it could does not excuse it
    with pytest.raises(SystemExit, match="resolve to NOTHING"):
        AM.stage_referenced_media(comp)


def test_iter_media_srcs_finds_nested_srcs():
    spec = {"a": {"ground": {"src": "assets/g.mp4"}},
            "items": [{"src": "assets/i1.jpg"}, {"label": "no src"}],
            "b": {"annotations": [{"src": "assets/a.png"}]}, "http": {"src": "https://x/y.mp4"}}
    got = set(AM._iter_media_srcs(spec))
    # The walk now matches on the VALUE's shape (`assets/<name>.<media-ext>`) instead of the key NAME
    # `src` — that is what finally staged newshead.image / timeline events[].image / document.source /
    # bare-string gallery images / spotlight.subject. A remote URL is deliberately NOT yielded: the sole
    # consumer (stage_referenced_media) filters to `assets/` anyway, so a remote ref was never staged
    # and never could be. Contract is "local media refs", not "every value under a key called src".
    assert got == {"assets/g.mp4", "assets/i1.jpg", "assets/a.png"}
