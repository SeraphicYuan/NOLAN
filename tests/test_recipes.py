"""Recipes + exemplar briefs (quality program step 7).

Pins: shipped recipes validate against the motion registry, plan validation
is loud (unknown recipe/role, missing slots), materialization maps slots/
scene fields and never overrides an explicit spec, the materialized specs
are premium-hostable, the catalog is generated, exemplar guidance is
measured (and loud when an exemplar isn't deconstructed), and candidate
drafting writes reviewable files without touching the registry.
"""

import json
from pathlib import Path

from nolan.recipes import (
    draft_recipe_candidates, load_recipes, recipes_catalog,
    resolve_plan_recipes, validate_plan_recipes, validate_recipe,
)

REPO = Path(__file__).resolve().parents[1]


def _plan(scenes):
    return {"schema_version": 2, "sections": {"a": scenes}}


# --- registry ------------------------------------------------------------------

def test_shipped_recipes_validate():
    recipes = load_recipes()
    assert {"map-journey", "quote-reveal", "stat-impact"} <= set(recipes)
    for rid, r in recipes.items():
        assert validate_recipe(r) == [], f"recipe {rid} fails validation"


def test_validate_recipe_catches_bad_roles():
    errs = "\n".join(validate_recipe({
        "id": "x", "roles": [
            {"role": "a", "motion": {"effect": "no-such"}},
            {"role": "a", "motion": None}]}))
    assert "unknown motion effect" in errs
    assert "duplicate role" in errs
    assert "when_to_use" in errs


# --- plan validation --------------------------------------------------------------

def test_plan_validation_is_loud():
    plan = _plan([
        {"id": "s1", "recipe": {"id": "no-such", "role": "map"}},
        {"id": "s2", "recipe": {"id": "map-journey", "role": "no-role"}},
        {"id": "s3", "recipe": {"id": "map-journey", "role": "map",
                                "slots": {"title": "x"}}},   # pins missing
        {"id": "s4", "recipe": "map-journey"},
    ])
    text = "\n".join(validate_plan_recipes(plan))
    assert "unknown recipe" in text
    assert "no role" in text
    assert "missing slot 'pins'" in text
    assert "must be {id, key, role}" in text


# --- materialization ---------------------------------------------------------------

def test_materialization_maps_slots_and_scene_fields():
    scenes = [
        {"id": "s1", "recipe": {"id": "map-journey", "key": "v1", "role": "map",
                                "slots": {"title": "The long way home",
                                          "pins": [{"x": 0.2, "y": 0.4,
                                                    "label": "Troy"}]}}},
        {"id": "s2", "recipe": {"id": "map-journey", "key": "v1",
                                "role": "arrival"}},
        {"id": "s3", "matched_asset": "D:/x/turner.jpg",
         "recipe": {"id": "stat-impact", "key": "y1", "role": "referent",
                    "slots": {"value": 2700, "suffix": " yrs",
                              "caption": "the story survived"}}},
    ]
    plan = _plan(scenes)
    assert validate_plan_recipes(plan) == []
    n = resolve_plan_recipes(plan)
    assert n == 2                                    # arrival role is motionless
    ms1 = scenes[0]["motion_spec"]
    assert ms1["effect"] == "route-map"
    assert ms1["content"]["pins"][0]["label"] == "Troy"
    assert ms1["_from_recipe"] == "map-journey:v1"
    assert scenes[1].get("motion_spec") is None
    ms3 = scenes[2]["motion_spec"]
    assert ms3["content"]["image"] == "D:/x/turner.jpg"   # scene-field mapping
    assert ms3["content"]["value"] == 2700


def test_explicit_spec_wins():
    scenes = [{"id": "s1",
               "motion_spec": {"effect": "kinetic-text", "content": {"text": "x"}},
               "recipe": {"id": "quote-reveal", "key": "q", "role": "quote",
                          "slots": {"quote": "...", "attribution": "...",
                                    "source": "..."}}}]
    assert resolve_plan_recipes(_plan(scenes)) == 0
    assert scenes[0]["motion_spec"]["effect"] == "kinetic-text"


def test_materialized_recipe_is_premium_hostable(tmp_path):
    from nolan.motion import chapter_step_for_spec
    scenes = [{"id": "s1", "recipe": {
        "id": "quote-reveal", "key": "q", "role": "quote",
        "slots": {"quote": "Sing in me, Muse", "attribution": "HOMER",
                  "source": "Odyssey, Book I"}}}]
    plan = _plan(scenes)
    resolve_plan_recipes(plan)
    hosted = chapter_step_for_spec(scenes[0]["motion_spec"], tmp_path)
    assert hosted is not None and hosted[0] == "PremiumCard"
    assert hosted[1]["title"] == "Sing in me, Muse"


def test_catalog_is_generated():
    cat = recipes_catalog()
    for rid in ("map-journey", "quote-reveal", "stat-impact"):
        assert rid in cat
    assert "map → arrival" in cat


# --- exemplar guidance ----------------------------------------------------------------

def test_exemplar_guidance_measured_and_loud(tmp_path):
    from nolan.exemplars import exemplar_guidance, summarize_extract
    # no exemplars declared -> silent
    (tmp_path / "project.yaml").write_text("name: x\n", encoding="utf-8")
    assert exemplar_guidance(tmp_path) == ""
    # declared but not deconstructed -> loud line, not silence
    (tmp_path / "project.yaml").write_text(
        "exemplars:\n  - definitely-not-deconstructed\n", encoding="utf-8")
    g = exemplar_guidance(tmp_path)
    assert "NOT DECONSTRUCTED" in g

    s = summarize_extract({
        "duration": 600.0,
        "beats": [{"function": "hook", "t0": 0, "t1": 22},
                  {"function": "context", "t0": 22, "t1": 200}],
        "shots": [{"asset_type": "live-footage", "camera_motion": "static"},
                  {"asset_type": "archival", "camera_motion": "pan"}]})
    assert s["beats"] == 2 and s["hook_s"] == 22
    assert s["texture_mix"]["live-footage"] == 50
    assert s["static_share"] == 50


# --- candidate drafting -----------------------------------------------------------------

def test_draft_candidates_writes_reviewable_files(tmp_path, monkeypatch):
    import nolan.recipes as rc

    class _Store:
        def read_extract(self, slug):
            return {"duration": 100.0, "beats": [
                {"title": "Intro Montage", "function": "hook",
                 "first_shot": 0, "last_shot": 3, "t0": 0, "t1": 12,
                 "shown": "opens on a bubble then archival maps"}],
                "shots": [
                    {"shot_index": 0, "asset_type": "live-footage",
                     "treatment_hint": "hold"},
                    {"shot_index": 1, "asset_type": "live-footage",
                     "treatment_hint": "push"},
                    {"shot_index": 2, "asset_type": "archival",
                     "treatment_hint": "pan"},
                    {"shot_index": 3, "asset_type": "archival",
                     "treatment_hint": "pan"}]}

    import nolan.deconstruct.store as ds
    monkeypatch.setattr(ds, "DeconstructionStore", lambda: _Store())
    written = draft_recipe_candidates("some-slug", out_dir=tmp_path)
    assert len(written) == 1
    draft = json.loads(written[0].read_text(encoding="utf-8"))
    assert draft["status"] == "candidate"
    assert draft["id"].startswith("CANDIDATE--")
    assert [r["role"] for r in draft["roles"]] == ["live-footage-1", "archival-2"]
    # candidates never enter the live registry
    assert draft["id"] not in load_recipes()
