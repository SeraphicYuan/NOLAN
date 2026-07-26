"""Targeting: saliency, the VLM relevance lane, the sidecar cache, and failing soft.

The rule these pin down: a camera may lose its aim, never the render. Every path here has to survive
a missing file, a missing dependency, a read-only directory and a model that returns garbage.
"""
import json

import pytest

from nolan.camera import target


@pytest.fixture()
def img(tmp_path):
    from PIL import Image
    p = tmp_path / "shot.jpg"
    im = Image.new("RGB", (1600, 900), (200, 200, 200))
    for x in range(1100, 1400):                          # a "subject" right of centre
        for y in range(300, 700):
            im.putpixel((x, y), (20, 20, 30))
    im.save(p)
    target._MEM.clear()
    return p


def test_image_size_is_read_and_cached(img):
    assert target.image_size(img) == (1600, 900)
    assert json.loads((img.parent / (img.name + ".camera.json")).read_text())["size"] == [1600, 900]
    img.unlink()                                         # cached — no second read of the file
    target._MEM.clear()
    assert target.image_size(img) == (1600, 900)


def test_everything_fails_soft_on_a_missing_file(tmp_path):
    missing = tmp_path / "nope.jpg"
    assert target.image_size(missing) is None
    assert target.subject_point(missing) is None
    assert target.cutout_path(missing) is None
    assert target.subject_box(missing, "anything", enabled=True) is None
    assert target.capabilities(missing) == {"target"}


def test_capabilities_always_offer_a_target(img):
    """The centre is a legitimate target, so every targeting move has a floor to degrade onto."""
    assert "target" in target.capabilities(img)
    assert "target" in target.capabilities(None)


def test_the_vlm_lane_is_off_unless_asked(img, monkeypatch):
    """A model call per still to re-confirm a subject saliency already found is spend with no decision
    attached — so it is opt-in, and OFF is not an error."""
    monkeypatch.delenv("NOLAN_CAMERA_VLM", raising=False)
    assert target.subject_box(img, "the man on the right") is None
    assert "box" not in target.capabilities(img, narration="the man", want=("box",))


def test_the_vlm_lane_turns_on_by_env(img, monkeypatch):
    monkeypatch.setenv("NOLAN_CAMERA_VLM", "1")
    calls = []

    class _P:
        async def describe_image(self, path, prompt):
            calls.append(prompt)
            return '```json\n{"box": [0.6, 0.3, 0.25, 0.4], "label": "the man", "confident": true}\n```'

    monkeypatch.setattr("nolan.vision.create_vision_provider", lambda cfg: _P())
    got = target.subject_box(img, "the man on the right")
    assert got and got["box"][0] == 0.6 and got["label"] == "the man"
    assert "the man on the right" in calls[0], "the narration must reach the model — that IS the lane"


def test_a_box_result_is_cached_per_narration(img, monkeypatch):
    monkeypatch.setenv("NOLAN_CAMERA_VLM", "1")
    n = {"calls": 0}

    class _P:
        async def describe_image(self, path, prompt):
            n["calls"] += 1
            return '{"box": [0.1, 0.1, 0.3, 0.3], "confident": true}'

    monkeypatch.setattr("nolan.vision.create_vision_provider", lambda cfg: _P())
    target.subject_box(img, "same sentence")
    target.subject_box(img, "same sentence")
    assert n["calls"] == 1, "a re-render must not re-run the model"
    target.subject_box(img, "a DIFFERENT sentence")
    assert n["calls"] == 2, "a different narration is a different question"


def test_model_garbage_is_rejected_not_rendered(img, monkeypatch):
    """Every one of these would produce a broken framing if it were trusted."""
    monkeypatch.setenv("NOLAN_CAMERA_VLM", "1")
    for raw in ('not json at all',
                '{"box": [0.1, 0.1]}',                       # wrong arity
                '{"box": [0.1, 0.1, 0, 0.3], "confident": true}',   # zero area
                '{"box": [0.1, 0.1, 0.001, 0.001], "confident": true}',  # a sliver
                '{"box": ["a", "b", "c", "d"], "confident": true}',
                '{"box": [0.1, 0.1, 0.3, 0.3], "confident": false}'):   # model says it is unsure
        target._MEM.clear()
        (img.parent / (img.name + ".camera.json")).unlink(missing_ok=True)

        class _P:
            async def describe_image(self, path, prompt, _r=raw):
                return _r

        monkeypatch.setattr("nolan.vision.create_vision_provider", lambda cfg: _P())
        assert target.subject_box(img, "x") is None, raw


def test_a_provider_that_raises_costs_the_aim_not_the_render(img, monkeypatch):
    monkeypatch.setenv("NOLAN_CAMERA_VLM", "1")

    class _P:
        async def describe_image(self, path, prompt):
            raise RuntimeError("model is down")

    monkeypatch.setattr("nolan.vision.create_vision_provider", lambda cfg: _P())
    assert target.subject_box(img, "x") is None


def test_the_box_is_clamped_into_the_frame(img, monkeypatch):
    monkeypatch.setenv("NOLAN_CAMERA_VLM", "1")

    class _P:
        async def describe_image(self, path, prompt):
            return '{"box": [0.8, 0.8, 0.9, 0.9], "confident": true}'   # runs off the edge

    monkeypatch.setattr("nolan.vision.create_vision_provider", lambda cfg: _P())
    got = target.subject_box(img, "x")
    x, y, w, h = got["box"]
    assert x + w <= 1.0001 and y + h <= 1.0001


def test_a_read_only_sidecar_does_not_break_targeting(img, monkeypatch):
    monkeypatch.setattr(target, "_save", lambda *a, **k: (_ for _ in ()).throw(OSError("read-only")))
    with pytest.raises(OSError):
        target._save(img, {})
    monkeypatch.setattr(target, "_save", lambda *a, **k: None)
    assert target.image_size(img) == (1600, 900)
