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


# --- shortlist note store ------------------------------------------------------

def test_shortlist_set_note_roundtrip(tmp_path):
    from nolan import shortlist
    shortlist.save(tmp_path, [{"key": "img:1:global", "kind": "image"}])
    items = shortlist.set_note(tmp_path, "img:1:global", "prefer tight crop")
    assert items[0]["note"] == "prefer tight crop"
    items = shortlist.set_note(tmp_path, "img:1:global", "")
    assert "note" not in items[0]
