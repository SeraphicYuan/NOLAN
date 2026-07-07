"""The five 2026-07-07 pipeline-flag fixes: premium-lane routing for
manifest-carrying projects, loud card fallback, camera-lock honoring in the
orchestrator lane (in-memory only), manifest v2 scene stamps, and the
lane-aware pre-render plan.
"""

import json
from pathlib import Path

import pytest

from nolan.still_motion import STILL_TREATMENTS, to_still_motion_treatment


# --- lane routing ----------------------------------------------------------------

def _proj(tmp_path, with_manifest: bool):
    proj = tmp_path / "p"
    (proj / "output").mkdir(parents=True)
    (proj / "scene_plan.json").write_text(json.dumps({
        "schema_version": 2,
        "sections": {"a": [{"id": "s1", "visual_type": "b-roll",
                            "matched_asset": "a.jpg",
                            "start_seconds": 0.0, "end_seconds": 5.0}]},
    }), encoding="utf-8")
    if with_manifest:
        (proj / "output" / "render_manifest.json").write_text(
            json.dumps({"version": 2, "written_by": "render", "scenes": {}}),
            encoding="utf-8")
    return proj


def test_manifest_project_rerenders_on_the_premium_lane(tmp_path, monkeypatch):
    """A premium-rendered project (manifest present) must NOT go through the
    orchestrator assemble — the 2026-07-07 aeneid incident swapped the premium
    final for title cards and static stills."""
    from nolan.iterate import engine
    proj = _proj(tmp_path, with_manifest=True)
    calls = []
    monkeypatch.setattr("nolan.premium_render.render_premium",
                        lambda p, **kw: calls.append(Path(p)) or proj / "output" / "final.mp4")
    monkeypatch.setattr(engine, "_rerender_orchestrator",
                        lambda *a, **k: pytest.fail("orchestrator lane used on a premium project"))
    out = engine.rerender_scenes(proj / "scene_plan.json", ["s1"],
                                 pipeline="orchestrator")
    assert calls == [proj]
    assert out == proj / "output" / "final.mp4"


def test_no_manifest_keeps_the_orchestrator_lane(tmp_path, monkeypatch):
    from nolan.iterate import engine
    proj = _proj(tmp_path, with_manifest=False)
    called = []
    monkeypatch.setattr(engine, "_rerender_orchestrator",
                        lambda plan_path, ids, **kw: called.append(sorted(ids)) or None)
    engine.rerender_scenes(proj / "scene_plan.json", ["s1"], pipeline="orchestrator")
    assert called == [["s1"]]


# --- loud card fallback ------------------------------------------------------------

def test_card_fallback_stamps_provenance(tmp_path, monkeypatch):
    from nolan import render_dispatch
    monkeypatch.setattr(render_dispatch, "render_card", lambda *a, **k: None)
    scene = {"id": "s1", "visual_type": "generated-image",
             "comfyui_prompt": "a burning scroll"}
    kind = render_dispatch.render_one(scene, tmp_path / "out.mp4", duration=3.0)
    assert kind == "card"
    assert scene["resolved_source"].startswith("fallback:card(")
    assert "no generator" in scene["resolved_source"]

    def _boom(scene, out):
        raise RuntimeError("comfyui unreachable")
    scene2 = {"id": "s2", "visual_type": "generated-image",
              "comfyui_prompt": "x"}
    kind = render_dispatch.render_one(scene2, tmp_path / "out2.mp4",
                                      duration=3.0, gen_fn=_boom)
    assert kind == "card"
    assert "comfyui unreachable" in scene2["resolved_source"]


# --- camera lock in the orchestrator lane ------------------------------------------

def test_lock_mapping_stays_inside_the_registry_enum():
    """Every authored camera lock maps into the still-motion effect's
    treatment vocabulary — the one-bridge rule (pitfall #4)."""
    from nolan.motion.registry import get_effect
    eff = get_effect("still-motion")
    allowed = next(p.values for p in eff.content if p.name == "treatment")
    for t in STILL_TREATMENTS:
        assert to_still_motion_treatment(t) in allowed, t


def test_stamp_tempo_motions_honors_the_lock(tmp_path):
    from nolan.orchestrator.render import stamp_tempo_motions
    (tmp_path / "a.jpg").write_bytes(b"x")
    plan = {"sections": {"a": [
        {"id": "s1", "matched_asset": "a.jpg", "energy": 0.2,
         "still_treatment": "kenburns-out",
         "start_seconds": 0.0, "end_seconds": 4.0},
        {"id": "s2", "matched_asset": "a.jpg", "energy": 0.2,
         "start_seconds": 4.0, "end_seconds": 8.0},
        {"id": "s3", "matched_asset": "a.jpg",              # no energy: lock still stamps
         "still_treatment": "drift",
         "start_seconds": 8.0, "end_seconds": 12.0},
    ]}}
    n = stamp_tempo_motions(plan, tmp_path)
    assert n == 3
    s1, s2, s3 = plan["sections"]["a"]
    assert s1["motion_spec"]["content"]["treatment"] == "ken-burns-out"   # lock wins
    assert s2["motion_spec"]["content"]["treatment"] == "hold"           # tempo pick (e=0.2)
    assert s3["motion_spec"]["content"]["treatment"] == "atmospheric"    # drift lock, no energy


def test_orchestrator_rerender_stamps_in_memory_only(tmp_path, monkeypatch):
    """The rerender lane animates stills via stamped motion_specs, but the
    plan on disk never gains the derived spec (derived-vs-authored contract);
    fallback provenance DOES travel back."""
    from nolan.iterate import engine
    from nolan.orchestrator import render as render_mod
    from nolan.orchestrator.render import RenderOutcome
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "a.jpg").write_bytes(b"x")
    (proj / "scene_plan.json").write_text(json.dumps({
        "schema_version": 2,
        "sections": {"a": [
            {"id": "s1", "visual_type": "archival-art", "matched_asset": "a.jpg",
             "energy": 0.2, "still_treatment": "kenburns-out",
             "start_seconds": 0.0, "end_seconds": 4.0}]},
    }), encoding="utf-8")

    seen = []

    def _fake_render_scene(scene, project_path, rendered_dir):
        seen.append(json.loads(json.dumps(scene)))
        return RenderOutcome(scene["id"], "assets/rendered/s1.mp4",
                             scene.get("visual_type", ""), None, None)

    monkeypatch.setattr(render_mod, "render_scene", _fake_render_scene)
    monkeypatch.setattr(render_mod, "call_assemble", lambda **kw: None)
    monkeypatch.setattr(render_mod, "generate_silent_audio", lambda *a, **k: None)
    engine.rerender_scenes(proj / "scene_plan.json", ["s1"], pipeline="orchestrator")

    assert seen and seen[0]["motion_spec"]["content"]["treatment"] == "ken-burns-out"
    saved = json.loads((proj / "scene_plan.json").read_text(encoding="utf-8"))
    s1 = saved["sections"]["a"][0]
    assert "motion_spec" not in s1 or not s1["motion_spec"]   # never persisted
    assert s1["rendered_clip"] == "assets/rendered/s1.mp4"    # annotate ran


# --- manifest v2 scene stamps + timeline dirty --------------------------------------

def test_manifest_stamps_and_timeline_dirty(tmp_path):
    from nolan.premium_render import _write_render_manifest, scene_stamp
    from nolan.timeline_view import build_timeline
    proj = tmp_path / "p"
    (proj / "output").mkdir(parents=True)
    plan = {"schema_version": 2, "sections": {"a": [
        {"id": "s1", "visual_type": "archival-art", "matched_asset": "a.jpg",
         "start_seconds": 0.0, "end_seconds": 4.0}]}}
    (proj / "scene_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    _write_render_manifest(proj, [], proj / "output" / "final.mp4")
    m = json.loads((proj / "output" / "render_manifest.json").read_text(encoding="utf-8"))
    assert m["version"] == 2
    assert m["scene_stamps"]["s1"] == scene_stamp(plan["sections"]["a"][0])

    tl = build_timeline(proj)
    assert tl["scenes"][0]["dirty"] is False        # rendered, untouched

    # a field edit flips the stamp -> dirty
    plan["sections"]["a"][0]["transition"] = "dissolve"
    (proj / "scene_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    tl = build_timeline(proj)
    assert tl["scenes"][0]["dirty"] is True


def test_underscore_keys_do_not_dirty_the_stamp():
    from nolan.premium_render import scene_stamp
    s = {"id": "s1", "matched_asset": "a.jpg"}
    base = scene_stamp(s)
    assert scene_stamp({**s, "_still_treatment": "drift"}) == base
    assert scene_stamp({**s, "transition": "fade"}) != base


# --- lane-aware plan endpoint --------------------------------------------------------

def test_plan_endpoint_reports_the_lane(tmp_path):
    from fastapi.testclient import TestClient
    from nolan.hub import create_hub_app
    proj = tmp_path / "lane-test"
    (proj / "output").mkdir(parents=True)
    (proj / "scene_plan.json").write_text(json.dumps({
        "schema_version": 2,
        "sections": {"a": [{"id": "s1", "visual_type": "b-roll",
                            "matched_asset": "a.jpg",
                            "start_seconds": 0.0, "end_seconds": 5.0}]},
    }), encoding="utf-8")
    client = TestClient(create_hub_app(db_path=None, projects_dir=tmp_path))

    r = client.post("/api/scenes/rerender/plan",
                    json={"project": "lane-test", "scene_ids": ["s1"]})
    assert r.status_code == 200
    assert r.json()["lane"] != "premium"            # no manifest yet

    (proj / "output" / "render_manifest.json").write_text(
        json.dumps({"version": 2, "written_by": "render", "scenes": {}}),
        encoding="utf-8")
    r = client.post("/api/scenes/rerender/plan",
                    json={"project": "lane-test", "scene_ids": ["s1"]})
    assert r.json()["lane"] == "premium"
    assert "beat cache" in r.json()["lane_note"]
