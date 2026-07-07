"""Motif layer — stateful infographics (quality program step 5).

Pins: delta accumulation order and isNew stamping, per-scene keys, loud
validation (unknown id / non-stateful effect / missing base), in-memory
materialization through the SAME hostability gate, premium wiring, and the
registry/comps/gate wiring for the new timeline effect.
"""

import json
from pathlib import Path

from nolan.motion.motifs import (
    STATEFUL_EFFECTS, build_motif_content, resolve_plan_motifs,
    validate_plan_motifs,
)

REPO = Path(__file__).resolve().parents[1]

MOTIF = {"id": "eras", "effect": "timeline",
         "base": {"title": "Greek memory", "start": -800, "end": 1950,
                  "eras": [{"label": "Archaic", "from": -800, "to": -480}]}}


def _plan(scenes, motifs=None):
    return {"schema_version": 2, "motifs": motifs or [MOTIF],
            "sections": {"a": scenes}}


# --- accumulation --------------------------------------------------------------

def test_accumulation_and_isnew_stamping():
    d1 = {"markers": [{"year": -750, "label": "Homer composes"}]}
    d2 = {"markers": [{"year": -300, "label": "Alexandria edits"}],
          "focus": {"from": -400, "to": -200}}
    # first visit: its own delta is new
    c1 = build_motif_content(MOTIF, [], d1)
    assert [m["label"] for m in c1["markers"]] == ["Homer composes"]
    assert c1["markers"][0]["isNew"] is True
    # second visit: first delta settled, second stamped new; focus per-scene
    c2 = build_motif_content(MOTIF, [d1], d2)
    assert [m.get("isNew", False) for m in c2["markers"]] == [False, True]
    assert c2["focus"] == {"from": -400, "to": -200}
    assert c2["title"] == "Greek memory"          # base carries through
    # base itself must never be mutated by accumulation
    assert "markers" not in MOTIF["base"]


def test_resolve_plan_materializes_in_scene_order():
    scenes = [
        {"id": "s1", "motif": {"id": "eras", "delta": {
            "markers": [{"year": -750, "label": "Homer"}]}}},
        {"id": "s2", "visual_type": "b-roll"},
        {"id": "s3", "motif": {"id": "eras", "delta": {
            "markers": [{"year": 1488, "label": "First print"}]}}},
    ]
    plan = _plan(scenes)
    n = resolve_plan_motifs(plan)
    assert n == 2
    ms1 = scenes[0]["motion_spec"]
    ms3 = scenes[2]["motion_spec"]
    assert ms1["effect"] == "timeline" and ms1["target"] == "Timeline"
    assert len(ms1["content"]["markers"]) == 1
    assert [m.get("isNew", False) for m in ms3["content"]["markers"]] == [False, True]
    assert ms3["_from_motif"] == "eras"
    assert scenes[1].get("motion_spec") is None


def test_explicit_motion_spec_is_kept_but_delta_still_accumulates():
    scenes = [
        {"id": "s1", "motif": {"id": "eras", "delta": {
            "markers": [{"year": -750, "label": "Homer"}]}},
         "motion_spec": {"effect": "kinetic-text", "content": {"text": "x"}}},
        {"id": "s2", "motif": {"id": "eras", "delta": {
            "markers": [{"year": 1488, "label": "Print"}]}}},
    ]
    plan = _plan(scenes)
    assert resolve_plan_motifs(plan) == 1
    assert scenes[0]["motion_spec"]["effect"] == "kinetic-text"
    # s1's delta still counted as history for s2
    assert [m.get("isNew", False)
            for m in scenes[1]["motion_spec"]["content"]["markers"]] == [False, True]


# --- validation ----------------------------------------------------------------

def test_validation_catches_the_failure_modes():
    bad = _plan(
        [{"id": "s1", "motif": {"id": "nope"}},
         {"id": "s2", "motif": "eras"},
         {"id": "s3", "motif": {"id": "eras", "delta": [1, 2]}}],
        motifs=[MOTIF,
                {"id": "bad-effect", "effect": "kinetic-text", "base": {}},
                {"id": "no-base", "effect": "timeline"}])
    errors = validate_plan_motifs(bad)
    text = "\n".join(errors)
    assert "not stateful" in text          # kinetic-text can't be a motif
    assert "missing base" in text
    assert "unknown motif id" in text      # s1
    assert "must be {id, delta}" in text   # s2
    assert "delta must be an object" in text  # s3
    assert not validate_plan_motifs(_plan([]))


def test_route_map_is_stateful_too():
    assert "route-map" in STATEFUL_EFFECTS
    motif = {"id": "voyage", "effect": "route-map",
             "base": {"title": "The long way home",
                      "pins": [{"x": 0.2, "y": 0.4, "label": "Troy"}]}}
    c = build_motif_content(motif, [{"pins": [{"x": 0.5, "y": 0.6, "label": "Aeaea"}]}],
                            {"pins": [{"x": 0.8, "y": 0.3, "label": "Ithaca"}]})
    assert [p.get("isNew", False) for p in c["pins"]] == [False, False, True]


# --- gate + premium wiring -------------------------------------------------------

def test_materialized_motif_is_premium_hostable(tmp_path):
    from nolan.motion import chapter_step_for_spec
    plan = _plan([{"id": "s1", "motif": {"id": "eras", "delta": {
        "markers": [{"year": -750, "label": "Homer"}]}}}])
    resolve_plan_motifs(plan)
    hosted = chapter_step_for_spec(plan["sections"]["a"][0]["motion_spec"], tmp_path)
    assert hosted is not None
    block, props = hosted
    assert block == "TimelinePro"
    assert props["start"] == -800 and props["markers"][0]["isNew"]


def test_wiring_greps():
    """Registry → comps → gate → premium — the full chain exists."""
    comps = (REPO / "render-service/remotion-lib/src/comps.ts").read_text(encoding="utf-8")
    assert "TimelinePro: Timeline" in comps
    gate = (REPO / "src/nolan/flows/gate/contact.py").read_text(encoding="utf-8")
    assert "TimelinePro" in gate
    prem = (REPO / "src/nolan/premium_render.py").read_text(encoding="utf-8")
    assert "resolve_plan_motifs" in prem
    director = (REPO / "src/nolan/orchestrator/director.py").read_text(encoding="utf-8")
    assert "validate_plan_motifs" in director
    skill = (REPO / "skills/orchestrator/motion-designer.md").read_text(encoding="utf-8")
    assert "Motifs" in skill and '"motifs"' in skill
