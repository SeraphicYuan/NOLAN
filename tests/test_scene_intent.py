"""resolve_scene_intent — the premium ladder's dry-run behind the Inspector
strip, the timeline conflict markers and the pre-render plan.

The critical property is AGREEMENT: the intent's winning rung must match what
_scene_step/_expand_shots actually do for the same scene (pitfall #4 — the
dry-run must not become a second dialect of the ladder).
"""

import json
from pathlib import Path

import pytest

from nolan.premium_render import (PremiumIneligible, _expand_shots,
                                  _scene_step, resolve_scene_intent)


@pytest.fixture()
def proj(tmp_path):
    art = tmp_path / "assets" / "art"
    art.mkdir(parents=True)
    for n in ("a.jpg", "b.jpg", "c.jpg"):
        (art / n).write_bytes(b"x")
    (tmp_path / "clip.mp4").write_bytes(b"x")
    return tmp_path


def _intent_rung(scene, proj):
    return resolve_scene_intent(scene, proj)["winner"]["rung"]


def _step_block(scene, proj):
    return _scene_step(scene, proj, 30, 5.0)[0]


# --- ladder agreement: dry-run rung <-> real render behavior --------------------

def test_pin_still_agrees(proj):
    s = {"id": "s", "pinned_asset": {"src": "assets/art/a.jpg", "kind": "image"},
         "motion_spec": {"effect": "kinetic-text", "content": {"text": "X"}},
         "matched_asset": "assets/art/b.jpg"}
    assert _intent_rung(s, proj) == "pin"
    block, props = _scene_step(s, proj, 30, 5.0)
    assert block == "ArtworkStage" and props["src"].endswith("a.jpg")


def test_pin_clip_agrees(proj):
    s = {"id": "s", "pinned_asset": {"src": "clip.mp4", "kind": "clip",
                                     "clip_start": 2.0}}
    assert _intent_rung(s, proj) == "pin"
    assert _step_block(s, proj) == "Video"


def test_layout_beats_motion_and_agrees(proj):
    s = {"id": "s",
         "layout_spec": {"template": "title", "params": {"title": "ROME"}},
         "motion_spec": {"effect": "kinetic-text", "content": {"text": "X"}}}
    it = resolve_scene_intent(s, proj)
    assert it["winner"]["rung"] == "layout"
    assert any(c["id"] == "layout-overrides-motion" for c in it["conflicts"])
    assert any(o["rung"] == "motion" for o in it["overridden"])
    assert _step_block(s, proj) != "Kinetic"      # motion did not win


def test_motion_agrees(proj):
    s = {"id": "s", "motion_spec": {"effect": "kinetic-text",
                                    "content": {"text": "X"}},
         "matched_asset": "assets/art/a.jpg"}
    assert _intent_rung(s, proj) == "motion"
    assert _step_block(s, proj) == "Kinetic"


def test_placements_and_plain_still_agree(proj):
    two = {"id": "s", "assets": [
        {"id": "a1", "kind": "image", "src": "assets/art/a.jpg", "place": [0.2, 0.5]},
        {"id": "a2", "kind": "image", "src": "assets/art/b.jpg", "place": [0.8, 0.5]}]}
    assert _intent_rung(two, proj) == "placements"
    assert _step_block(two, proj) == "PhotoMontage"
    still = {"id": "s", "matched_asset": "assets/art/a.jpg"}
    assert _intent_rung(still, proj) == "still"
    assert _step_block(still, proj) == "ArtworkStage"


def test_human_shots_beat_motion_and_agree(proj):
    s = {"id": "s", "shots": [{"src": "assets/art/a.jpg"},
                              {"src": "assets/art/b.jpg"}],
         "motion_spec": {"effect": "kinetic-text", "content": {"text": "X"}},
         "matched_asset": "assets/art/c.jpg"}
    it = resolve_scene_intent(s, proj)
    assert it["winner"]["rung"] == "shots"
    assert any(c["id"] == "shots-override-motion" for c in it["conflicts"])
    units = _expand_shots(s, proj, 30, 300, 0)
    assert len(units) == 2                          # the shot list rendered

    s["shots_auto"] = True                          # auto list yields to motion
    it = resolve_scene_intent(s, proj)
    assert it["winner"]["rung"] == "motion"
    assert any(c["id"] == "auto-shots-yield-to-motion" for c in it["conflicts"])
    units = _expand_shots(s, proj, 30, 300, 0)
    assert len(units) == 1 and units[0][0] == "Kinetic"


def test_ineligible_agrees(proj):
    s = {"id": "s", "visual_type": "b-roll"}
    assert _intent_rung(s, proj) == "ineligible"
    with pytest.raises(PremiumIneligible):
        _scene_step(s, proj, 30, 5.0)


# --- collision flags: silent losers made loud -----------------------------------

def test_missing_pin_file_is_flagged_and_falls_through(proj):
    s = {"id": "s", "pinned_asset": {"src": "assets/art/GONE.jpg"},
         "matched_asset": "assets/art/a.jpg"}
    it = resolve_scene_intent(s, proj)
    assert it["winner"]["rung"] == "still"          # today's silent fall-through
    assert any(c["id"] == "pin-missing-file" and c["severity"] == "error"
               for c in it["conflicts"])


def test_pin_overrides_motion_flag(proj):
    s = {"id": "s", "pinned_asset": {"src": "assets/art/a.jpg"},
         "motion_spec": {"effect": "kinetic-text", "content": {"text": "X"}}}
    it = resolve_scene_intent(s, proj)
    assert any(c["id"] == "pin-overrides-motion" and c["severity"] == "warn"
               for c in it["conflicts"])


def test_camera_lock_inert_only_off_stills(proj):
    locked = {"id": "s", "still_treatment": "kenburns-pan",
              "motion_spec": {"effect": "kinetic-text", "content": {"text": "X"}}}
    it = resolve_scene_intent(locked, proj)
    assert any(c["id"] == "camera-lock-inert" for c in it["conflicts"])
    fine = {"id": "s", "still_treatment": "kenburns-pan",
            "matched_asset": "assets/art/a.jpg"}
    it = resolve_scene_intent(fine, proj)
    assert not any(c["id"] == "camera-lock-inert" for c in it["conflicts"])


def test_invalid_motion_spec_is_an_error_flag(proj):
    s = {"id": "s", "motion_spec": {"effect": "kinetic-text", "content": {}},
         "matched_asset": "assets/art/a.jpg"}    # missing required text
    it = resolve_scene_intent(s, proj)
    assert any(c["id"] == "motion-spec-invalid" and c["severity"] == "error"
               for c in it["conflicts"])


# --- surfaces: timeline units + the two endpoints --------------------------------

def test_timeline_units_carry_intent(proj):
    (proj / "scene_plan.json").write_text(json.dumps({"sections": {"a": [
        {"id": "s1", "start_seconds": 0.0, "end_seconds": 2.0,
         "pinned_asset": {"src": "assets/art/a.jpg"},
         "motion_spec": {"effect": "kinetic-text", "content": {"text": "X"}}},
    ]}}), encoding="utf-8")
    from nolan.timeline_view import build_timeline
    tl = build_timeline(proj)
    u = tl["units"][0]
    assert u["intent"]["winner"] == "pin"
    assert any(c["id"] == "pin-overrides-motion" for c in u["intent"]["conflicts"])
    assert tl["scenes"][0]["dirty"] is True         # no rendered_clip yet


@pytest.fixture()
def client_proj(tmp_path):
    from fastapi.testclient import TestClient
    from nolan.hub import create_hub_app
    proj = tmp_path / "it-test"
    art = proj / "assets" / "art"
    art.mkdir(parents=True)
    (art / "a.jpg").write_bytes(b"x")
    (proj / "scene_plan.json").write_text(json.dumps({
        "schema_version": 2,
        "sections": {"a": [
            {"id": "s1", "visual_type": "b-roll", "search_query": "roman forum",
             "matched_asset": "assets/art/a.jpg",
             "pinned_asset": {"src": "assets/art/a.jpg"},
             "motion_spec": {"effect": "kinetic-text", "content": {"text": "X"}},
             "start_seconds": 0.0, "end_seconds": 5.0},
            {"id": "s2", "visual_type": "b-roll", "search_query": "roman coin",
             "matched_asset": "assets/art/a.jpg", "resolved_source": "library",
             "start_seconds": 5.0, "end_seconds": 10.0},
        ]},
    }), encoding="utf-8")
    return TestClient(create_hub_app(db_path=None, projects_dir=tmp_path)), proj


def test_intent_endpoint(client_proj):
    client, _ = client_proj
    r = client.get("/api/scenes/intent",
                   params={"project": "it-test", "scene_id": "s1"})
    assert r.status_code == 200
    j = r.json()
    assert j["winner"]["rung"] == "pin"
    assert any(c["id"] == "pin-overrides-motion" for c in j["conflicts"])
    assert client.get("/api/scenes/intent",
                      params={"project": "it-test", "scene_id": "nope"}
                      ).status_code == 404


def test_rerender_plan_endpoint(client_proj):
    client, _ = client_proj
    r = client.post("/api/scenes/rerender/plan", json={
        "project": "it-test", "scene_ids": ["s1", "s2"]})
    assert r.status_code == 200
    plans = {p["id"]: p for p in r.json()["scenes"]}
    # s1: resolved_source empty + query present -> matching re-runs
    assert plans["s1"]["re_match"] is True
    assert plans["s1"]["winner"]["rung"] == "pin"
    assert plans["s1"]["duration"] == 5.0
    # s2: match intact -> render only
    assert plans["s2"]["re_match"] is False
    # unknown scene ids are refused loudly
    assert client.post("/api/scenes/rerender/plan", json={
        "project": "it-test", "scene_ids": ["ghost"]}).status_code == 404
