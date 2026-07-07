"""Shortlist→pipeline wiring (quality program step 4).

Pins: human pin outranks everything (incl. motion_spec) and is never
re-resolved; shortlist tier-0 runs before search with no-reuse; a winning
item's note lands as scene.human_note; clip items match on curated label;
record_candidates skips pinned scenes; human directives reach the
motion_design prompt; the shortlist note store round-trips.
"""

import json
from types import SimpleNamespace

from nolan.asset_engine import AssetEngine, EngineConfig
from nolan.scenes import Scene


def _engine(**kw):
    cfg = kw.pop("config", EngineConfig(enable_generation=False,
                                        enable_library=False,
                                        enable_bridge=False,
                                        enable_search=False))
    return AssetEngine(cfg, **kw)


# --- human pin ---------------------------------------------------------------

def test_pin_outranks_everything():
    s = Scene(id="s1", visual_type="b-roll",
              motion_spec={"effect": "stat-over", "content": {}})
    s.extra["pinned_asset"] = {"src": "D:/x/vase.jpg", "kind": "image", "by": "human"}
    eng = _engine(search_fn=lambda sc: (_ for _ in ()).throw(AssertionError("searched!")))
    assert eng.resolve(s) == "pinned:human"
    assert s.matched_asset == "D:/x/vase.jpg"


def test_pin_clip_sets_matched_clip():
    s = Scene(id="s1", visual_type="b-roll")
    s.extra["pinned_asset"] = {"src": "lib/v.mp4", "kind": "clip", "clip_start": 3.5}
    assert _engine().resolve(s) == "pinned:human"
    assert s.matched_clip["video_path"] == "lib/v.mp4"
    assert s.matched_clip["clip_start"] == 3.5 and s.matched_clip["pinned"]


# --- shortlist tier 0 --------------------------------------------------------

def test_shortlist_runs_before_search_with_no_reuse():
    def fake_shortlist(scene):
        scene.matched_asset = "D:/lib/amphora.jpg"
        return "image(0.44)"

    eng = _engine(shortlist_fn=fake_shortlist,
                  search_fn=lambda sc: {"video_path": "v.mp4", "clip_start": 0,
                                        "similarity_score": 0.9},
                  config=EngineConfig(enable_generation=False,
                                      enable_library=False, enable_bridge=False))
    s1 = Scene(id="s1", visual_type="b-roll", search_query="amphora")
    s2 = Scene(id="s2", visual_type="b-roll", search_query="amphora")
    assert eng.resolve(s1) == "shortlist:image(0.44)"
    # same item again -> claimed -> falls through to search
    assert eng.resolve(s2).startswith("search")
    assert s2.matched_asset is None and s2.matched_clip


def test_shortlist_clip_label_match_and_note(tmp_path, monkeypatch):
    from nolan import shortlist
    shortlist.save(tmp_path, [{
        "key": "clip:lib/siren.mp4@12.0", "kind": "clip",
        "label": "Siren Vase Odysseus mast detail", "note": "hold on the mast",
        "payload": {"op": "add", "source": "clip",
                    "source_video_path": "lib/siren.mp4", "clip_start": 12.0},
    }])
    fn = AssetEngine._default_shortlist_fn(EngineConfig(), tmp_path)
    s = Scene(id="s1", visual_type="b-roll",
              search_query="Odysseus mast siren vase")
    assert fn(s) == "clip:label"
    assert s.matched_clip["video_path"] == "lib/siren.mp4"
    assert s.matched_clip["clip_start"] == 12.0
    assert s.extra["human_note"] == "hold on the mast"


def test_shortlist_unrelated_clip_label_misses(tmp_path):
    from nolan import shortlist
    shortlist.save(tmp_path, [{
        "key": "clip:lib/x.mp4@0", "kind": "clip", "label": "Venice canal gondola",
        "payload": {"op": "add", "source": "clip",
                    "source_video_path": "lib/x.mp4", "clip_start": 0},
    }])
    fn = AssetEngine._default_shortlist_fn(EngineConfig(), tmp_path)
    s = Scene(id="s1", visual_type="b-roll", search_query="bronze age shipwreck")
    assert fn(s) is None and s.matched_clip is None


# --- review-tray candidates --------------------------------------------------

def test_record_candidates_skips_pinned(monkeypatch):
    s_pinned = Scene(id="s1", visual_type="b-roll", search_query="q",
                     matched_asset="a.jpg")
    s_pinned.extra["pinned_asset"] = {"src": "a.jpg"}
    s_plain = Scene(id="s2", visual_type="b-roll", search_query="q",
                    matched_asset="b.jpg")

    class _Hit:
        def __init__(self, i):
            self.score = 0.5 - i * 0.1
            self.asset = SimpleNamespace(id=i, source="test")

    class _Lib:
        scope = "global"
        def search_hybrid(self, q, k=5):
            return [_Hit(1), _Hit(2)]
        def abs_path(self, a):
            return f"D:/lib/{a.id}.jpg"

    import nolan.imagelib as il
    monkeypatch.setattr(il, "ImageLibrary", lambda *a, **k: _Lib())
    done = AssetEngine.record_candidates([s_pinned, s_plain])
    assert done == 1
    assert "asset_candidates" not in s_pinned.extra
    assert [c["src"] for c in s_plain.extra["asset_candidates"]] == \
        ["D:/lib/1.jpg", "D:/lib/2.jpg"]


# --- directives reach motion_design -------------------------------------------

def test_human_directives_section(tmp_path):
    from nolan.orchestrator.director import Director
    plan = {"schema_version": 2, "sections": {"a": [
        {"id": "s1", "visual_type": "b-roll", "human_note": "slow pan over the letter"},
        {"id": "s2", "visual_type": "b-roll",
         "pinned_asset": {"src": "x.jpg", "note": "keep it full-frame"}},
        {"id": "s3", "visual_type": "b-roll"},
    ]}}
    (tmp_path / "scene_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    text = Director._human_directives(SimpleNamespace(project_path=tmp_path))
    assert "s1: slow pan over the letter" in text
    assert "s2: keep it full-frame" in text
    assert "s3" not in text and "FOLLOW" in text


def test_human_directives_empty_without_notes(tmp_path):
    from nolan.orchestrator.director import Director
    (tmp_path / "scene_plan.json").write_text(
        json.dumps({"schema_version": 2, "sections": {"a": [{"id": "s1"}]}}),
        encoding="utf-8")
    assert Director._human_directives(SimpleNamespace(project_path=tmp_path)) == ""


# --- premium honors a pin directly (post-match, no re-resolve) ---------------

def test_premium_scene_step_honors_image_pin(tmp_path):
    from PIL import Image
    from nolan.premium_render import _scene_step
    img = tmp_path / "vase.jpg"
    Image.new("RGB", (800, 600), (120, 100, 90)).save(img)
    scene = {"id": "s1", "visual_type": "b-roll",
             "matched_asset": "some/other.jpg",          # pin must outrank it
             "pinned_asset": {"src": str(img), "kind": "image", "by": "human"}}
    block, props = _scene_step(scene, tmp_path, 30, 4.0)
    assert block == "ArtworkStage" and props["src"] == str(img)


def test_premium_scene_step_honors_clip_pin(tmp_path):
    from nolan.premium_render import _scene_step
    clip = tmp_path / "v.mp4"
    clip.write_bytes(b"x")
    scene = {"id": "s1", "visual_type": "b-roll",
             "pinned_asset": {"src": str(clip), "kind": "clip",
                              "clip_start": 2.0, "by": "human"}}
    block, props = _scene_step(scene, tmp_path, 30, 4.0)
    assert block == "Video" and props["src"] == str(clip)
    assert props["startFromFrames"] == 60


# --- pin/unpin API op ---------------------------------------------------------

def test_scene_assets_pin_and_unpin_ops(tmp_path):
    from fastapi.testclient import TestClient
    from nolan.hub import create_hub_app

    proj = tmp_path / "pin-test"
    proj.mkdir()
    (proj / "scene_plan.json").write_text(json.dumps({
        "schema_version": 2,
        "sections": {"a": [{"id": "s1", "visual_type": "b-roll",
                            "assets": [{"id": "a1", "kind": "image",
                                        "src": "D:/lib/x.jpg"}]}]},
    }), encoding="utf-8")
    client = TestClient(create_hub_app(db_path=None, projects_dir=tmp_path))

    r = client.post("/api/scenes/scene/assets", json={
        "project": "pin-test", "scene_id": "s1", "op": "pin",
        "asset_id": "a1", "note": "hold full-frame"})
    assert r.status_code == 200
    plan = json.loads((proj / "scene_plan.json").read_text(encoding="utf-8"))
    s = plan["sections"]["a"][0]
    assert s["pinned_asset"]["src"] == "D:/lib/x.jpg"
    assert s["pinned_asset"]["note"] == "hold full-frame"
    assert s["human_note"] == "hold full-frame"

    r = client.post("/api/scenes/scene/assets", json={
        "project": "pin-test", "scene_id": "s1", "op": "unpin"})
    assert r.status_code == 200
    plan = json.loads((proj / "scene_plan.json").read_text(encoding="utf-8"))
    assert "pinned_asset" not in plan["sections"]["a"][0]

    # direct-src pin (the review-tray "use this" path)
    r = client.post("/api/scenes/scene/assets", json={
        "project": "pin-test", "scene_id": "s1", "op": "pin",
        "src": "D:/lib/cand.jpg", "kind": "image"})
    assert r.status_code == 200
    plan = json.loads((proj / "scene_plan.json").read_text(encoding="utf-8"))
    assert plan["sections"]["a"][0]["pinned_asset"]["src"] == "D:/lib/cand.jpg"


# --- shortlist note store ------------------------------------------------------

def test_shortlist_set_note_roundtrip(tmp_path):
    from nolan import shortlist
    shortlist.save(tmp_path, [{"key": "img:1:global", "kind": "image"}])
    items = shortlist.set_note(tmp_path, "img:1:global", "prefer tight crop")
    assert items[0]["note"] == "prefer tight crop"
    items = shortlist.set_note(tmp_path, "img:1:global", "")
    assert "note" not in items[0]
