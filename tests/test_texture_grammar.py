"""P1 of the meta-style program: the texture grammar (scene.texture ->
Chapter step jitter/edge), the cutout-collage effect + rembg pre-pass, the
PostFX paper layer plumbing, and graphical foley. Wiring-honesty greps
included: an authored field with no executor is a bug.
"""

import json
from pathlib import Path

import pytest

from nolan.texture import TEXTURE_EDGES, stamp_step, validate_texture

REPO = Path(__file__).resolve().parents[1]


# --- texture vocabulary -----------------------------------------------------------

def test_validate_texture_happy_and_defaults():
    tex, errs = validate_texture({"jitter": {"fps": 12, "amp": 5}, "edge": "rough"})
    assert errs == []
    assert tex == {"jitter": {"fps": 12, "amp": 5.0}, "edge": "rough"}
    tex, errs = validate_texture({"jitter": {}})     # defaults fill
    assert errs == [] and tex["jitter"] == {"fps": 12, "amp": 4.0}
    assert validate_texture(None) == ({}, [])


def test_validate_texture_is_loud():
    _, errs = validate_texture({"jitter": {"fps": 60}})
    assert any("outside" in e for e in errs)
    _, errs = validate_texture({"edge": "wobbly"})
    assert any("wobbly" in e for e in errs)
    _, errs = validate_texture({"jiter": {}})        # typo'd key named, not dropped
    assert any("unknown keys" in e for e in errs)


def test_stamp_step_copies_and_raises():
    step = {}
    stamp_step(step, {"id": "s1", "texture": {"jitter": {"fps": 8, "amp": 6},
                                              "edge": "boil"}})
    assert step == {"jitter": {"fps": 8, "amp": 6.0}, "edge": "boil"}
    with pytest.raises(ValueError):
        stamp_step({}, {"id": "s1", "texture": {"edge": "nope"}})


# --- cutout-collage: registry + executor pre-pass ----------------------------------

def test_cutout_collage_registered_and_hostable():
    from nolan.motion.registry import get_effect
    eff = get_effect("cutout-collage")
    assert eff and eff.target == "CutoutCollage" and eff.backend == "remotion"
    assert any(p.name == "image" and p.required for p in eff.content)


def test_cutout_prepass_generates_sidecar(tmp_path, monkeypatch):
    from nolan.motion.executor import chapter_step_for_spec
    img = tmp_path / "server.jpg"
    img.write_bytes(b"x")
    made = []

    def _fake_salient(p, want_cutout, out_dir):
        fg = Path(out_dir) / (Path(p).stem + ".fg.png")
        fg.write_bytes(b"png")
        made.append(str(p))
        return {"x": 0.5, "y": 0.5}, fg

    import nolan.still_motion as sm
    monkeypatch.setattr(sm, "_salient", _fake_salient)
    block, props = chapter_step_for_spec(
        {"effect": "cutout-collage", "content": {"image": str(img)},
         "style": {"bg": "paper"}}, tmp_path)
    assert block == "CutoutCollage"
    assert props["cutoutSrc"].endswith("server.fg.png") and made == [str(img)]

    # sidecar cache: second call must NOT re-run rembg
    made.clear()
    chapter_step_for_spec({"effect": "cutout-collage",
                           "content": {"image": str(img)}}, tmp_path)
    assert made == []


def test_cutout_prepass_is_loud_on_missing_or_subjectless(tmp_path, monkeypatch):
    from nolan.motion.executor import chapter_step_for_spec
    with pytest.raises(ValueError, match="not found"):
        chapter_step_for_spec({"effect": "cutout-collage",
                               "content": {"image": "gone.jpg"}}, tmp_path)
    img = tmp_path / "sky.jpg"
    img.write_bytes(b"x")
    import nolan.still_motion as sm
    monkeypatch.setattr(sm, "_salient", lambda p, want_cutout, out_dir: ({"x": .5, "y": .5}, None))
    with pytest.raises(ValueError, match="no salient subject"):
        chapter_step_for_spec({"effect": "cutout-collage",
                               "content": {"image": str(img)}}, tmp_path)


# --- graphical foley ----------------------------------------------------------------

def test_graphical_foley_stamps_without_overwriting():
    from nolan.audio_mix import FOLEY_CUES, stamp_graphical_foley
    plan = {"sections": {"a": [
        {"id": "s1", "motion_spec": {"effect": "kinetic-text"}},
        {"id": "s2", "layout_spec": {"template": "statistic"}},
        {"id": "s3", "motion_spec": {"effect": "kinetic-text"},
         "sfx": {"query": "authored", "at": 1.0}},               # never clobbered
        {"id": "s4", "matched_asset": "a.jpg"},                   # no graphic kind
    ]}}
    assert stamp_graphical_foley(plan) == 2
    a = plan["sections"]["a"]
    assert a[0]["sfx"]["query"] == FOLEY_CUES["kinetic-text"]["query"]
    assert a[1]["sfx"]["query"] == FOLEY_CUES["statistic"]["query"]
    assert a[2]["sfx"]["query"] == "authored"
    assert "sfx" not in a[3]


def test_foley_kinds_exist_in_their_registries():
    """Catalog honesty: every foley key is a real effect id or block template."""
    from nolan.audio_mix import FOLEY_CUES
    from nolan.layout_blocks import ADAPTERS
    from nolan.motion.registry import get_effect
    for kind in FOLEY_CUES:
        assert get_effect(kind) or kind in ADAPTERS, kind


# --- wiring honesty (docs claim, tests enforce) -------------------------------------

def test_texture_field_is_consumed_end_to_end():
    from nolan.scenes import PLAN_FIELD_CONSUMERS
    assert PLAN_FIELD_CONSUMERS["texture"] == "src/nolan/texture.py"
    # premium stamps it onto steps...
    pr = (REPO / "src/nolan/premium_render.py").read_text(encoding="utf-8")
    assert "stamp_step" in pr and "texture" in pr
    # ...and the Chapter driver executes jitter + edge with audio OUTSIDE
    ch = (REPO / "render-service/remotion-lib/src/Chapter.tsx").read_text(encoding="utf-8")
    for needle in ("jitter?", "edge?", "<Freeze", "feDisplacementMap"):
        assert needle in ch, needle
    assert ch.index("s.audioSrc") < ch.index("<Jitter"), "audio must stay outside the jitter wrapper"
    # edge vocabulary: one owner, client mirrors it
    for e in TEXTURE_EDGES:
        assert f'"{e}"' in ch


def test_paper_layer_wired():
    fx = (REPO / "render-service/remotion-lib/src/Effects.tsx").read_text(encoding="utf-8")
    assert "paper?: number" in fx and "-paper" in fx
    # comps registry hosts the collage
    comps = (REPO / "render-service/remotion-lib/src/comps.ts").read_text(encoding="utf-8")
    assert "CutoutCollage" in comps


def test_texture_editable_from_the_ui():
    from nolan.iterate.revise import editable_fields
    assert "texture" in editable_fields("segment")
    assert "texture" in editable_fields("orchestrator")
