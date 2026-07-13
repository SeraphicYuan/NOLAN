"""Honesty tests for the composer-native scene-edit engine (nolan.hyperframes.edit).

Covers the Phase-1 direct-edit surface end-to-end THROUGH the real author.py gate: discover, list,
patch+gate, atomic reject-and-revert, add/remove/retime, the within-frame transition planner, and the
lossless spec round-trip. Snapshot/render (npx + headless Chrome) are integration-verified separately.
"""
import asyncio
import json
import shutil
from pathlib import Path

import pytest


class StubLLM:
    """A deterministic stand-in for the text LLM: returns canned `generate` responses in order."""
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    async def generate(self, prompt, system_prompt=None):
        r = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return r

import sys
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from nolan import hyperframes as hf  # noqa: E402

SRC_COMP = REPO / "render-service" / "_lab_hyperframes" / "videos" / "faceless-demo"
VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"
TEST_COMP = "_hf_edit_pytest"
FRAME = "01-power"

pytestmark = pytest.mark.skipif(
    not (SRC_COMP / "compositions" / "frames" / f"{FRAME}.spec.json").exists(),
    reason="lab faceless-demo composition not present",
)


@pytest.fixture()
def comp():
    """A throwaway copy of faceless-demo under videos/ (so discovery finds it), torn down after."""
    dst = VIDEOS / TEST_COMP
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(SRC_COMP / "compositions", dst / "compositions")
    try:
        yield TEST_COMP
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def _spec_path(comp_name):
    return VIDEOS / comp_name / "compositions" / "frames" / f"{FRAME}.spec.json"


def test_discover_and_list(comp):
    assert comp in {c["name"] for c in hf.discover_compositions()}
    frames = hf.list_frames(comp)
    assert len(frames) == 1
    fr = frames[0]
    assert fr["id"] == FRAME and fr["dur"] == 14
    assert [(s["id"], s["type"]) for s in fr["scenes"]] == [("s1", "stat"), ("s2", "geo"), ("s3", "statement")]


def test_apply_scene_edit_valid(comp):
    r = hf.apply_scene_edit(comp, FRAME, "s1",
                            patch={"data.items.0.to": 30, "data.kicker": "PYTEST KICKER"})
    assert r["applied"], r
    # the edit landed in the spec ...
    spec = json.loads(_spec_path(comp).read_text(encoding="utf-8"))
    s1 = spec["frames"][0]["scenes"][0]
    assert s1["data"]["kicker"] == "PYTEST KICKER" and s1["data"]["items"][0]["to"] == 30
    # ... and in the recomposed HTML
    html = Path(r["html"]).read_text(encoding="utf-8")
    assert "PYTEST KICKER" in html and "30" in html


def test_invalid_edit_rejected_and_reverted(comp):
    before = _spec_path(comp).read_text(encoding="utf-8")
    r = hf.apply_scene_edit(comp, FRAME, "s2", patch={"data.kind": "moon"})  # geo.kind must be us|world
    assert r["applied"] is False
    assert "SPEC REJECTED" in r["errors"]
    assert _spec_path(comp).read_text(encoding="utf-8") == before, "rejected edit must revert byte-identically"


def test_add_remove_retime_scene(comp):
    r = hf.add_scene(comp, FRAME, {"id": "s4", "type": "statement", "start": 14.0, "dur": 3.0,
                                   "data": {"lines": ["Added."], "operative": "Added"}})
    assert r["applied"], r
    assert len(hf.list_frames(comp)[0]["scenes"]) == 4

    r = hf.retime_scene(comp, FRAME, "s4", start=15.0, dur=2.0)
    assert r["applied"], r
    s4 = next(s for s in hf.list_frames(comp)[0]["scenes"] if s["id"] == "s4")
    assert s4["start"] == 15.0 and s4["dur"] == 2.0

    r = hf.remove_scene(comp, FRAME, "s4")
    assert r["applied"], r
    assert len(hf.list_frames(comp)[0]["scenes"]) == 3


def test_add_scene_missing_required_field_rejected(comp):
    before = _spec_path(comp).read_text(encoding="utf-8")
    # statement requires non-empty `lines`; the gate must reject and the frame must be unchanged
    r = hf.add_scene(comp, FRAME, {"id": "sX", "type": "statement", "start": 14.0, "dur": 2.0, "data": {}})
    assert r["applied"] is False
    assert _spec_path(comp).read_text(encoding="utf-8") == before


def test_transition_planner(comp):
    dry = hf.beat_boundary_planner(comp, FRAME, apply=False)
    assert dry["applied"] is False
    kinds = {(p["scene_id"], p["kind"]) for p in dry["proposals"]}
    # stat->geo and geo->statement are type changes (scale_out); no proposal for the last scene
    assert ("s1", "scale_out") in kinds and ("s2", "scale_out") in kinds
    assert len(dry["proposals"]) == 2

    applied = hf.beat_boundary_planner(comp, FRAME, apply=True)
    assert applied["applied"], applied
    tos = [(s["transition_out"]) for s in hf.list_frames(comp)[0]["scenes"]]
    assert tos[0] == "scale_out" and tos[-1] is None


def test_lossless_unknown_key_survives(comp):
    """The spec round-trip must preserve keys the engine doesn't know (the extra/meta invariant)."""
    spec, info = hf.load_frame_spec(comp, FRAME)
    spec["frames"][0]["scenes"][0]["_producer_note"] = "keep me"
    spec["frames"][0]["_beat_ref"] = "sec_0000"
    hf.save_frame_spec(Path(info["spec_file"]), spec)
    # a subsequent field edit must not drop the unknown keys
    hf.apply_scene_edit(comp, FRAME, "s3", patch={"data.cue": 2.0})
    spec2 = json.loads(_spec_path(comp).read_text(encoding="utf-8"))
    assert spec2["frames"][0]["scenes"][0]["_producer_note"] == "keep me"
    assert spec2["frames"][0]["_beat_ref"] == "sec_0000"


# ---- Phase 2: note edit (comment → LLM ops → gate) ----

def test_note_prompt_and_mentions(comp):
    spec, info = hf.load_frame_spec(comp, FRAME)
    fr = spec["frames"][info["i"]]
    system, prompt = hf.build_note_prompt(fr, "apply @reveal:scramble to @s1", "s1",
                                          ["assets/a.png"], hf.catalog())
    assert "BLOCK TYPES" in system and "TRANSITIONS" in system and "REVEALS" in system
    assert "@s1 = scene s1" in prompt and "reveal 'scramble'" in prompt
    assert "assets/a.png" in prompt


def test_revise_note_valid(comp):
    plan = json.dumps({"ops": [
        {"op": "patch", "scene_id": "s1", "patch": {"data.kicker": "NOTE EDIT"}},
        {"op": "transition", "scene_id": "s1", "kind": "crossfade", "dur": 0.6},
    ]})
    r = asyncio.run(hf.revise_frame_note(comp, FRAME, "change kicker + dissolve",
                                         scene_id="s1", client=StubLLM(plan)))
    assert r["applied"], r
    spec = json.loads(_spec_path(comp).read_text(encoding="utf-8"))
    s1 = spec["frames"][0]["scenes"][0]
    assert s1["data"]["kicker"] == "NOTE EDIT" and s1["transition_out"]["kind"] == "crossfade"


def test_revise_note_add_then_retime(comp):
    plan = json.dumps({"ops": [
        {"op": "add", "scene": {"id": "s5", "type": "statement", "start": 14, "dur": 2,
                                "data": {"lines": ["Woven in."], "operative": "Woven"}}},
        {"op": "retime", "scene_id": "s5", "start": 15, "dur": 1.5},
    ]})
    r = asyncio.run(hf.revise_frame_note(comp, FRAME, "add a shot", client=StubLLM(plan)))
    assert r["applied"], r
    s5 = next(s for s in hf.list_frames(comp)[0]["scenes"] if s["id"] == "s5")
    assert s5["start"] == 15 and s5["dur"] == 1.5


def test_revise_note_self_corrects_on_reject(comp):
    """A rejected first plan, corrected on the retry (the gate feeds the error back)."""
    bad = json.dumps({"ops": [{"op": "patch", "scene_id": "s2", "patch": {"data.kind": "moon"}}]})
    good = json.dumps({"ops": [{"op": "patch", "scene_id": "s2", "patch": {"data.kind": "world"}}]})
    stub = StubLLM(bad, good)
    r = asyncio.run(hf.revise_frame_note(comp, FRAME, "fix geo", scene_id="s2", client=stub, retry=1))
    assert r["applied"] and stub.calls == 2, r
    assert json.loads(_spec_path(comp).read_text())["frames"][0]["scenes"][1]["data"]["kind"] == "world"


def test_revise_note_rejected_and_reverted(comp):
    before = _spec_path(comp).read_text(encoding="utf-8")
    bad = json.dumps({"ops": [{"op": "patch", "scene_id": "s2", "patch": {"data.kind": "moon"}}]})
    r = asyncio.run(hf.revise_frame_note(comp, FRAME, "x", scene_id="s2",
                                         client=StubLLM(bad, bad), retry=1))
    assert r["applied"] is False
    assert _spec_path(comp).read_text(encoding="utf-8") == before


def test_revise_note_no_ops(comp):
    r = asyncio.run(hf.revise_frame_note(comp, FRAME, "do nothing", client=StubLLM('{"ops":[]}')))
    assert r["applied"] is False and "no ops" in r["errors"].lower()


# ---- asset picker target ----

def test_assets_resolve_and_list(comp, tmp_path):
    src = tmp_path / "pic.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 40)
    r = hf.resolve_asset(comp, str(src))
    assert r["path"] == "assets/pic.png"
    listed = hf.list_assets(comp)
    pic = next(a for a in listed if a["name"] == "pic.png")
    assert pic["path"] == "assets/pic.png" and pic["kind"] == "image"


# ---- route layer: FastAPI TestClient over /hyperframes + /api/hf/* (added 2026-07-13) ----
# The Phase-1/2 status entries CLAIMED "TestClient over the full route surface" but no such
# tests existed. These are that coverage, for real: read routes, the gated edit route, the two
# path-traversal guards, and the page smoke.


@pytest.fixture()
def client(tmp_path):
    from fastapi.testclient import TestClient
    from nolan.hub import create_hub_app
    return TestClient(create_hub_app(db_path=None, projects_dir=tmp_path))


def test_route_page_smoke(client):
    r = client.get("/hyperframes")
    assert r.status_code == 200
    body = r.text
    assert "/api/hf/compositions" in body and 'id="comp"' in body
    # honesty: the mislabel is gone (the note edit is an LLM, not the tmux fleet)
    assert "Apply (agent)" not in body and "Apply (AI edit)" in body


def test_route_compositions_lists_comp(client, comp):
    r = client.get("/api/hf/compositions")
    assert r.status_code == 200
    assert comp in {c["name"] for c in r.json()["compositions"]}


def test_route_frames_and_spec(client, comp):
    r = client.get("/api/hf/frames", params={"comp": comp})
    assert r.status_code == 200
    frames = r.json()["frames"]
    assert len(frames) == 1 and frames[0]["id"] == FRAME
    r2 = client.get("/api/hf/frame-spec", params={"comp": comp, "frame_id": FRAME})
    assert r2.status_code == 200
    assert [s["id"] for s in r2.json()["frame"]["scenes"]] == ["s1", "s2", "s3"]


def test_route_catalog(client):
    cat = client.get("/api/hf/catalog").json()
    assert "scene_templates" in cat and "reveals" in cat and "transitions" in cat


def test_route_missing_comp_404(client):
    assert client.get("/api/hf/frames", params={"comp": "__nope__"}).status_code == 404


def test_route_scene_revise_gated(client, comp):
    r = client.post("/api/hf/scene/revise", json={
        "comp": comp, "frame_id": FRAME, "scene_id": "s1", "patch": {"data.kicker": "ROUTE EDIT"}})
    assert r.status_code == 200 and r.json()["applied"], r.text
    before = _spec_path(comp).read_text(encoding="utf-8")           # a rejected edit must revert
    r2 = client.post("/api/hf/scene/revise", json={
        "comp": comp, "frame_id": FRAME, "scene_id": "s2", "patch": {"data.kind": "moon"}})
    assert r2.status_code == 200 and r2.json()["applied"] is False
    assert _spec_path(comp).read_text(encoding="utf-8") == before


def test_route_themes_and_suggest(client):
    r = client.get("/api/hf/themes")
    assert r.status_code == 200 and len(r.json()["themes"]) > 0
    r2 = client.post("/api/hf/theme-suggest", json={"script": "A dark tale of war and gods.", "top": 3})
    assert r2.status_code == 200 and isinstance(r2.json()["ranked"], list)


def test_route_asset_file_confined_to_assets(client, comp, tmp_path):
    src = tmp_path / "pic.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 40)
    hf.resolve_asset(comp, str(src))
    assert client.get("/api/hf/asset-file", params={"comp": comp, "path": "assets/pic.png"}).status_code == 200
    # a real file OUTSIDE assets/ (the frame spec exists) + an absolute escape must both be refused
    for bad in (f"../compositions/frames/{FRAME}.spec.json", "../../../../etc/passwd", "assets/../hyperframes.json"):
        assert client.get("/api/hf/asset-file", params={"comp": comp, "path": bad}).status_code == 404, bad


def test_route_assemble_requires_comp(client):
    assert client.post("/api/hf/assemble", json={}).status_code == 400


def test_route_assembled_video_404_when_absent(client, comp):
    # no renders/<comp>.mp4 built yet for the fixture comp
    assert client.get("/api/hf/assembled-video", params={"comp": comp}).status_code == 404
    # traversal comp id must not escape the videos dir
    assert client.get("/api/hf/assembled-video",
                      params={"comp": "../../../../etc"}).status_code in (400, 404)


def test_route_frame_video_guard(client, comp):
    # the fixture frame ships a preview clip -> served; a missing frame + a traversal id -> 404 (not 500)
    assert client.get("/api/hf/frame-video", params={"comp": comp, "frame_id": FRAME}).status_code == 200
    assert client.get("/api/hf/frame-video", params={"comp": comp, "frame_id": "99-nope"}).status_code == 404
    assert client.get("/api/hf/frame-video",
                      params={"comp": comp, "frame_id": "../../../../etc/passwd"}).status_code == 404
