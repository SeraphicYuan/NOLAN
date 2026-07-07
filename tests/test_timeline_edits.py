"""Timeline edits (P3): the authored still_treatment camera lock, roll-edit
scene windows (neighbors absorb, section bounds locked), and range notes
whose STRUCTURED half applies deterministically (asset -> pin, motion ->
treatment lock) while free text routes to the agent lane.
"""

import json
from pathlib import Path

import pytest

from nolan.still_motion import STILL_TREATMENTS, assign_still_treatments


# --- authored still_treatment lock (module contract) ---------------------------

def _still(id, **kw):
    return {"id": id, "matched_asset": f"assets/art/{id}.jpg",
            "narration_excerpt": "from the harbor through the strait", **kw}


def test_lock_wins_over_cues_and_counts_as_prev():
    plan = {"sections": {"a": [
        _still("s1", still_treatment="drift"),      # cue says pan; lock says drift
        _still("s2"),                               # pan cue -> pan (prev=drift ok)
    ]}}
    assign_still_treatments(plan)
    assert plan["sections"]["a"][0]["_still_treatment"] == "drift"
    assert plan["sections"]["a"][1]["_still_treatment"] == "kenburns-pan"


def test_lock_wins_over_drift_close_and_bad_lock_ignored():
    plan = {"sections": {"a": [
        _still("s1", still_treatment="wobble-o-matic"),      # not in vocab
        _still("s2", energy=0.1, still_treatment="kenburns-in"),  # last low-energy
    ]}}
    assign_still_treatments(plan)
    assert plan["sections"]["a"][0]["_still_treatment"] in STILL_TREATMENTS
    assert plan["sections"]["a"][0]["_still_treatment"] != "wobble-o-matic"
    # the drift quiet-close rule yields to the human lock
    assert plan["sections"]["a"][1]["_still_treatment"] == "kenburns-in"


def test_timeline_badge_authored_when_locked(tmp_path):
    from nolan.timeline_view import build_timeline
    (tmp_path / "scene_plan.json").write_text(json.dumps({"sections": {"a": [
        {"id": "s1", "start_seconds": 0.0, "end_seconds": 2.0,
         "matched_asset": "x.jpg", "still_treatment": "kenburns-out"},
    ]}}), encoding="utf-8")
    tl = build_timeline(tmp_path)
    assert tl["units"][0]["motion"] == {"badge": "kenburns-out",
                                        "source": "authored"}


# --- API: lock / roll edit / notes ---------------------------------------------

@pytest.fixture()
def client_proj(tmp_path):
    from fastapi.testclient import TestClient
    from nolan.hub import create_hub_app
    proj = tmp_path / "tl-test"
    proj.mkdir()
    art = proj / "assets" / "art"
    art.mkdir(parents=True)
    (art / "pinme.jpg").write_bytes(b"x")
    (proj / "scene_plan.json").write_text(json.dumps({
        "schema_version": 2,
        "sections": {"a": [
            {"id": "s1", "visual_type": "b-roll", "matched_asset": "assets/art/a.jpg",
             "start_seconds": 0.0, "end_seconds": 5.0},
            {"id": "s2", "visual_type": "b-roll", "matched_asset": "assets/art/b.jpg",
             "start_seconds": 5.0, "end_seconds": 10.0},
            {"id": "s3", "visual_type": "b-roll", "matched_asset": "assets/art/c.jpg",
             "start_seconds": 10.0, "end_seconds": 15.0},
        ]},
    }), encoding="utf-8")
    client = TestClient(create_hub_app(db_path=None, projects_dir=tmp_path))
    return client, proj


def _plan(proj):
    return json.loads((proj / "scene_plan.json").read_text(encoding="utf-8"))


def test_treatment_lock_set_validate_clear(client_proj):
    client, proj = client_proj
    r = client.post("/api/timeline/treatment", json={
        "project": "tl-test", "scene_id": "s1", "treatment": "kenburns-pan"})
    assert r.status_code == 200
    assert _plan(proj)["sections"]["a"][0]["still_treatment"] == "kenburns-pan"
    # invalid vocab is refused loudly
    r = client.post("/api/timeline/treatment", json={
        "project": "tl-test", "scene_id": "s1", "treatment": "spin"})
    assert r.status_code == 400
    # null clears the lock
    r = client.post("/api/timeline/treatment", json={
        "project": "tl-test", "scene_id": "s1", "treatment": None})
    assert r.status_code == 200
    assert "still_treatment" not in _plan(proj)["sections"]["a"][0]


def test_roll_edit_neighbor_absorbs(client_proj):
    client, proj = client_proj
    r = client.post("/api/timeline/scene-window", json={
        "project": "tl-test", "scene_id": "s2", "start": 3.0})
    assert r.status_code == 200
    scenes = _plan(proj)["sections"]["a"]
    assert scenes[1]["start_seconds"] == 3.0
    assert scenes[0]["end_seconds"] == 3.0          # neighbor absorbed
    assert scenes[2]["start_seconds"] == 10.0       # untouched


def test_roll_edit_guards(client_proj):
    client, proj = client_proj
    # min duration: dragging s2.start past s2.end-1 clamps
    r = client.post("/api/timeline/scene-window", json={
        "project": "tl-test", "scene_id": "s2", "start": 9.9})
    assert r.status_code == 200
    assert r.json()["applied"]["start"] == 9.0      # clamped to end-1
    # section head is LOCKED (narration owns duration)
    r = client.post("/api/timeline/scene-window", json={
        "project": "tl-test", "scene_id": "s1", "start": 2.0})
    assert r.status_code == 200
    assert _plan(proj)["sections"]["a"][0]["start_seconds"] == 0.0
    # section tail is LOCKED
    r = client.post("/api/timeline/scene-window", json={
        "project": "tl-test", "scene_id": "s3", "end": 20.0})
    assert r.status_code == 200
    assert _plan(proj)["sections"]["a"][2]["end_seconds"] == 15.0


def test_note_structured_apply_and_freetext_route(client_proj):
    client, proj = client_proj
    pin_path = str(proj / "assets" / "art" / "pinme.jpg")
    # structured note: asset + motion -> deterministic apply on the mid scene
    r = client.post("/api/timeline/note", json={
        "project": "tl-test", "t0": 6.0, "t1": 9.0,
        "text": "the storm painting, slow reveal",
        "asset": pin_path, "motion": "kenburns-out"})
    assert r.status_code == 200
    nid = r.json()["id"]
    r = client.post("/api/timeline/note/apply", json={
        "project": "tl-test", "note_id": nid})
    assert r.status_code == 200
    body = r.json()
    assert body["scene_id"] == "s2"                  # midpoint 7.5 -> s2
    assert body["route"] is None                     # structured -> no agent
    s2 = _plan(proj)["sections"]["a"][1]
    assert s2["pinned_asset"]["src"] == pin_path
    assert s2["pinned_asset"]["note"] == "the storm painting, slow reveal"
    assert s2["still_treatment"] == "kenburns-out"
    notes = _plan(proj)["meta"]["timeline_notes"]
    assert notes[0]["status"] == "applied"

    # free-text-only note: apply changes nothing, routes to the agent lane
    r = client.post("/api/timeline/note", json={
        "project": "tl-test", "t0": 1.0, "t1": 2.0, "text": "more menace here"})
    nid2 = r.json()["id"]
    r = client.post("/api/timeline/note/apply", json={
        "project": "tl-test", "note_id": nid2})
    assert r.json()["route"] == "agent"
    assert r.json()["scene_id"] == "s1"
    # UI then marks it dispatched
    r = client.post("/api/timeline/note/update", json={
        "project": "tl-test", "note_id": nid2, "status": "dispatched"})
    assert r.status_code == 200
    # delete removes it
    r = client.post("/api/timeline/note/update", json={
        "project": "tl-test", "note_id": nid2, "status": "deleted"})
    ids = [n["id"] for n in _plan(proj)["meta"]["timeline_notes"]]
    assert nid2 not in ids and nid in ids


def test_note_missing_asset_is_loud(client_proj):
    client, proj = client_proj
    r = client.post("/api/timeline/note", json={
        "project": "tl-test", "t0": 1.0, "t1": 2.0,
        "asset": "D:/nope/gone.jpg"})
    nid = r.json()["id"]
    r = client.post("/api/timeline/note/apply", json={
        "project": "tl-test", "note_id": nid})
    assert r.status_code == 422


def test_notes_survive_in_meta_roundtrip(client_proj):
    """timeline_notes ride ScenePlan.meta — the lossless contract."""
    client, proj = client_proj
    client.post("/api/timeline/note", json={
        "project": "tl-test", "t0": 0.0, "t1": 1.0, "text": "keep me"})
    from nolan.scenes import ScenePlan
    plan = ScenePlan.load(proj / "scene_plan.json")
    out = proj / "roundtrip.json"
    plan.save(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["meta"]["timeline_notes"][0]["text"] == "keep me"
