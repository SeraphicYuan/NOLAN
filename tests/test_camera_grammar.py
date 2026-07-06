"""Camera grammar — one physics module for every virtual-camera comp.

Pins the Ken Burns "zip back" fix (homer-2beat-test: ArtworkStage always
pulled back to the whole in a fixed-length glide right before the cut) and
the saliency wiring (synthesized pushes aim at the subject, not a lane).
TS behavior itself is verified by the effect bench (frames get LOOKED at);
these tests keep the wiring from silently reverting.
"""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CAMERA = REPO / "render-service/remotion-lib/src/camera.ts"
STAGE = REPO / "render-service/remotion-lib/src/blocks/library/ArtworkStage.tsx"


def test_camera_module_exports_the_grammar():
    src = CAMERA.read_text(encoding="utf-8")
    for token in ("MIN_HOLD", "MIN_GLIDE", "MAX_GLIDE", "DRIFT_RATE",
                  "camDistance", "glideFor", "driftScale", "easeInOut"):
        assert f"export const {token}" in src or f"export type {token}" in src, token


def test_artwork_stage_uses_the_grammar():
    src = STAGE.read_text(encoding="utf-8")
    assert 'from "../../camera"' in src, "ArtworkStage no longer imports camera.ts"
    for call in ("glideFor(", "driftScale(", "MIN_HOLD"):
        assert call in src, f"ArtworkStage no longer uses {call}"


def test_no_pullback_keyframe():
    """The banned move: appending a return-to-whole camera keyframe near the
    end of the step (the fixed 36-frames-before-cut reset)."""
    src = STAGE.read_text(encoding="utf-8")
    assert "durationInFrames - 36" not in src, (
        "ArtworkStage regrew the pull-back-to-whole keyframe — the camera "
        "grammar bans resetting before a cut (cut on motion / ease to hold)")


def test_premium_aims_synthesized_pushes_at_the_subject():
    src = (REPO / "src/nolan/premium_render.py").read_text(encoding="utf-8")
    assert src.count("_subject_center(") >= 2, (
        "premium no longer passes saliency centers into camera_tour_props "
        "(single-still and shot-expansion paths)")


def test_subject_center_sidecar_cache(tmp_path, monkeypatch):
    import nolan.still_motion as sm

    calls = []

    def fake_salient(path, want_cutout, out_dir):
        calls.append(path)
        return {"x": 0.62, "y": 0.41}, None

    monkeypatch.setattr(sm, "_salient", fake_salient)
    img = tmp_path / "a.jpg"
    img.write_bytes(b"x")
    assert sm.subject_center(img) == (0.62, 0.41)
    assert sm.subject_center(img) == (0.62, 0.41)   # served from sidecar
    assert len(calls) == 1
    side = json.loads((tmp_path / "a.jpg.subject.json").read_text())
    assert side["ok"] is True

    # failure caches as a miss and returns None (fail-soft, no re-run storm)
    def broken(path, want_cutout, out_dir):
        calls.append(path)
        raise RuntimeError("no rembg")

    monkeypatch.setattr(sm, "_salient", broken)
    img2 = tmp_path / "b.jpg"
    img2.write_bytes(b"x")
    assert sm.subject_center(img2) is None
    assert sm.subject_center(img2) is None
    assert len(calls) == 2                           # broken ran once
