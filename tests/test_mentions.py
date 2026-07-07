"""Typed @-mentions (`@[scope]token`): the server resolver that expands UI
autocomplete tokens into explicit references at the revise/dispatch doors,
plus the /api/motion/registry mirror and the client/server vocabulary
honesty checks (pitfall #4: two dialects for one decision).
"""

import json
import re
from pathlib import Path

import pytest

from nolan.mentions import MENTION_RE, SCOPES, resolve_mentions

REPO = Path(__file__).resolve().parents[1]


# --- resolver unit tests --------------------------------------------------------

def test_untyped_note_passes_through():
    note = "make it grimmer, keep @a1 as-is"
    out, unresolved = resolve_mentions(note)
    assert out == note and unresolved == []


def test_asset_scope_resolves_across_scenes():
    scenes = [{"id": "s1", "assets": [
        {"id": "a1", "kind": "clip", "src": "D:/x/battle.mp4",
         "label": "battle", "clip_start": 3.0, "clip_end": 9.5}]}]
    out, unresolved = resolve_mentions("zoom @[asset]a1 harder", scenes=scenes)
    assert '[asset a1 "battle" (clip, 3.0-9.5s)]' in out
    assert unresolved == []


def test_motion_scope_treatment_and_registry_effect():
    out, unresolved = resolve_mentions("use @[motion]kenburns-pan then @[motion]kinetic-text")
    assert "[motion kenburns-pan — still-camera treatment" in out
    assert "[motion kinetic-text —" in out and "params:" in out
    assert unresolved == []


def test_unknown_tokens_stay_verbatim_and_are_reported():
    out, unresolved = resolve_mentions("try @[motion]wobble-o-matic and @[vid]nope")
    assert "@[motion]wobble-o-matic" in out
    assert unresolved == ["@[motion]wobble-o-matic", "@[vid]nope"]


def test_vid_scope_resolves_from_clips():
    clips = [{"id": "clip_ab12", "label": "storm surge",
              "source_video_path": "D:/lib/odyssey.mp4",
              "clip_start": 12.0, "clip_end": 18.5}]
    out, unresolved = resolve_mentions("open on @[vid]clip_ab12", clips=clips)
    assert '[clip clip_ab12 "storm surge" source: D:/lib/odyssey.mp4 @ 12.0-18.5s]' in out
    assert unresolved == []


def test_pool_scope_resolves_by_basename(tmp_path):
    art = tmp_path / "assets" / "art"
    art.mkdir(parents=True)
    (art / "trireme.jpg").write_bytes(b"x")
    (tmp_path / "scene_plan.json").write_text("{}", encoding="utf-8")
    out, unresolved = resolve_mentions("pin @[pool]trireme.jpg here",
                                       project_dir=tmp_path)
    assert '[pool asset "trireme.jpg" (image, status unused)' in out
    assert unresolved == []


def test_pic_scope_uses_imagelib(monkeypatch):
    class _Asset:
        title = "Parthenon frieze"
        path = "img/42.jpg"

    class _FakeLib:
        base = Path("D:/lib/images")
        def __init__(self, scope="global", project=None):
            self.catalog = self
        def get(self, pic_id):
            return _Asset() if pic_id == 42 else None

    import nolan.imagelib as imagelib
    monkeypatch.setattr(imagelib, "ImageLibrary", _FakeLib)
    out, unresolved = resolve_mentions("show @[pic]42 full frame")
    assert '[picture #42 "Parthenon frieze" (imagelib global)' in out
    assert unresolved == []


# --- wiring honesty (docs claim, tests enforce) ---------------------------------

SCENES_HTML = (REPO / "src/nolan/templates/scenes.html").read_text(encoding="utf-8")


def test_popover_scopes_match_server_vocabulary():
    """The scenes.html autocomplete SCOPES list and nolan.mentions.SCOPES are
    the same vocabulary — a scope added to one side only is a silent rot."""
    m = re.search(r"const SCOPES = \[(.*?)\];", SCENES_HTML, re.DOTALL)
    assert m, "scenes.html mention popover SCOPES table missing"
    client = set(re.findall(r"\['(\w+)',", m.group(1)))
    assert client == set(SCOPES)


def test_client_treatments_match_still_treatments():
    from nolan.still_motion import STILL_TREATMENTS
    m = re.search(r"const TL_TREATMENTS = \[(.*?)\];", SCENES_HTML, re.DOTALL)
    assert m, "scenes.html TL_TREATMENTS missing"
    client = re.findall(r"'([\w-]+)'", m.group(1))
    assert tuple(client) == tuple(STILL_TREATMENTS)


def test_both_note_doors_resolve_mentions():
    """Every door a human note passes through (revise + dispatch) must call
    the one resolver — a door that skips it hands raw tokens to the LLM."""
    src = (REPO / "src/nolan/webui/routes/scenes.py").read_text(encoding="utf-8")
    refs = src.count("_resolve_note_mentions")   # def + to_thread call sites
    assert refs >= 3, f"expected def + 2 call sites, found {refs}"
    for door in ("scenes_revise", "scenes_dispatch"):
        body = src.split(f"async def {door}", 1)[1].split("\n    @app.", 1)[0]
        assert "_resolve_note_mentions" in body, f"{door} skips mention resolution"


# --- /api/motion/registry + motion_spec patch validation ------------------------

@pytest.fixture()
def client_proj(tmp_path):
    from fastapi.testclient import TestClient
    from nolan.hub import create_hub_app
    proj = tmp_path / "mo-test"
    proj.mkdir()
    (proj / "scene_plan.json").write_text(json.dumps({
        "schema_version": 2,
        "sections": {"a": [
            {"id": "s1", "visual_type": "b-roll", "matched_asset": "a.jpg",
             "start_seconds": 0.0, "end_seconds": 5.0},
        ]},
    }), encoding="utf-8")
    return TestClient(create_hub_app(db_path=None, projects_dir=tmp_path)), proj


def test_motion_registry_endpoint(client_proj):
    client, _ = client_proj
    r = client.get("/api/motion/registry")
    assert r.status_code == 200
    j = r.json()
    from nolan.still_motion import STILL_TREATMENTS
    assert j["treatments"] == list(STILL_TREATMENTS)
    kinetic = next(e for e in j["effects"] if e["id"] == "kinetic-text")
    assert any(p["name"] == "text" and p["required"] for p in kinetic["content"])
    assert "position" in j["shared"]


def test_motion_spec_patch_validated_at_the_door(client_proj):
    client, proj = client_proj
    # unknown effect: refused loudly, nothing written
    r = client.post("/api/scenes/scene/revise", json={
        "project": "mo-test", "scene_id": "s1",
        "patch": {"motion_spec": {"effect": "spin-o-rama"}}})
    assert r.status_code == 400
    plan = json.loads((proj / "scene_plan.json").read_text(encoding="utf-8"))
    assert "motion_spec" not in plan["sections"]["a"][0]

    # valid effect: normalized (backend/target/duration filled) before saving
    r = client.post("/api/scenes/scene/revise", json={
        "project": "mo-test", "scene_id": "s1",
        "patch": {"motion_spec": {"effect": "kinetic-text",
                                  "content": {"text": "THE FALL"}}}})
    assert r.status_code == 200
    spec = json.loads((proj / "scene_plan.json").read_text(
        encoding="utf-8"))["sections"]["a"][0]["motion_spec"]
    assert spec["backend"] == "remotion" and spec["target"] == "Kinetic"
    assert spec["content"]["text"] == "THE FALL"
    assert spec["duration"] == pytest.approx(4.0)
