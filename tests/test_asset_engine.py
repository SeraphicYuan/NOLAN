"""Asset engine (Phase 2) — the unified ladder + the lossless dict adapter.

Tier functions are stubbed: these tests pin the LADDER (order, gates, field
writes, resolved_source audit) without models/network. Segment-builder parity
is covered by tests/test_segment_builder.py through the resolver shim.
"""

from nolan.asset_engine import ART_TYPES, AssetEngine, EngineConfig
from nolan.scenes import Scene


def scene(**kw) -> Scene:
    base = dict(id="s01", visual_type="b-roll", search_query="roman ships",
                visual_description="ancient fleet at sea", narration_excerpt="the fleet")
    base.update(kw)
    return Scene(**base)


def test_footage_search_hit_wins():
    e = AssetEngine(EngineConfig(),
                    search_fn=lambda s: {"similarity_score": 0.72, "video_path": "v.mp4"},
                    library_fn=lambda s: "/lib/should-not-be-used.jpg")
    s = scene()
    assert e.resolve(s) == "search(0.72)"
    assert s.matched_clip["video_path"] == "v.mp4"
    assert not s.matched_asset


def test_footage_below_gate_escalates_to_library():
    e = AssetEngine(EngineConfig(search_threshold=0.5),
                    search_fn=lambda s: {"similarity_score": 0.31},
                    library_fn=lambda s: "/lib/fleet.jpg")
    s = scene()
    assert e.resolve(s) == "library(search-miss)"
    assert s.matched_asset == "/lib/fleet.jpg"
    assert not s.matched_clip


def test_art_exact_title_first():
    def art_fn(s):
        s.matched_asset = "assets/art/nydia.jpg"
        return "exact:met"
    e = AssetEngine(EngineConfig(), art_fn=art_fn,
                    library_fn=lambda s: "/lib/wrong.jpg")
    s = scene(visual_type="archival-art", search_query="Nydia, the Blind Flower Girl")
    assert e.resolve(s) == "art:exact:met"
    assert s.matched_asset == "assets/art/nydia.jpg"


def test_art_miss_escalates():
    e = AssetEngine(EngineConfig(enable_generation=False),
                    art_fn=lambda s: None,
                    library_fn=lambda s: "/lib/statue.jpg")
    s = scene(visual_type="archival-art")
    assert e.resolve(s) == "library(art-miss)"


def test_art_fn_exception_is_contained():
    def art_fn(s):
        raise RuntimeError("museum API down")
    e = AssetEngine(EngineConfig(enable_generation=False, enable_library=False),
                    art_fn=art_fn)
    s = scene(visual_type="archival-art")
    assert e.resolve(s) == "none(art-miss)"


def test_generated_type_gets_prompt():
    e = AssetEngine(EngineConfig())
    s = scene(visual_type="generated-image", visual_description="a burning city")
    assert e.resolve(s) == "generated"
    assert s.comfyui_prompt == "a burning city"


def test_motion_authoring_for_graphic():
    e = AssetEngine(EngineConfig(),
                    motion_fn=lambda s: {"effect": "counter", "backend": "python"})
    s = scene(visual_type="graphic")
    assert e.resolve(s) == "motion:counter"
    assert s.motion_spec["effect"] == "counter"


def test_selection_only_config_reports_none():
    # The Director's select_clips profile: no generation tags, no motion.
    e = AssetEngine(EngineConfig(enable_generation=False, enable_motion=False),
                    search_fn=lambda s: None, library_fn=lambda s: None)
    s = scene()
    assert e.resolve(s) == "none(search-miss)"
    assert s.resolved_source == "none(search-miss)"


def test_resolved_source_always_written():
    e = AssetEngine(EngineConfig(enable_generation=False))
    scenes = [scene(id=f"s{i:02d}", visual_type=vt)
              for i, vt in enumerate(["b-roll", "graphic", "archival-art"])]
    e.resolve_all(scenes)
    assert all(s.resolved_source for s in scenes)


def test_resolve_dicts_is_lossless_and_in_place():
    e = AssetEngine(EngineConfig(),
                    search_fn=lambda s: {"similarity_score": 0.9, "video_path": "v.mp4"})
    d = {"id": "s01", "visual_type": "b-roll", "search_query": "fleet",
         "layout_spec": {"template": "quote", "params": {"quote": "arma"}},
         "x_custom": {"keep": True}}
    counts = e.resolve_dicts([d])
    assert counts == {"search": 1}
    assert d["matched_clip"]["video_path"] == "v.mp4"
    assert d["resolved_source"] == "search(0.90)"
    assert d["layout_spec"]["template"] == "quote"      # survived the round-trip
    assert d["x_custom"] == {"keep": True}              # unknown key survived


def test_art_types_membership():
    assert "archival-art" in ART_TYPES


# --- operator bridge (query-expansion layer) --------------------------------

def test_bridge_not_called_when_literal_hits():
    calls = []
    def bridge(s):
        calls.append(s.id)
        return ["should not be used"]
    e = AssetEngine(EngineConfig(),
                    search_fn=lambda s: {"similarity_score": 0.8, "video_path": "v.mp4"},
                    bridge_fn=bridge)
    s = scene()
    assert e.resolve(s) == "search(0.80)"
    assert calls == []          # cost guard: no LLM bridge on a literal hit


def test_bridged_search_hit():
    def search(s):
        # literal query misses; the metaphor probe hits
        if s.search_query == "a moth circling a flame":
            return {"similarity_score": 0.71, "video_path": "moth.mp4"}
        return None
    e = AssetEngine(EngineConfig(),
                    search_fn=search,
                    bridge_fn=lambda s: ["weathered hands", "a moth circling a flame"])
    s = scene(search_query="the pain of becoming yourself")
    assert e.resolve(s) == "search-bridged(0.71)"
    assert s.matched_clip["video_path"] == "moth.mp4"


def test_bridged_library_hit():
    def library(s):
        return "/lib/moth.jpg" if s.search_query == "a moth circling a flame" else None
    e = AssetEngine(EngineConfig(enable_generation=False),
                    search_fn=lambda s: None,
                    library_fn=library,
                    bridge_fn=lambda s: ["a moth circling a flame"])
    s = scene(search_query="the pain of becoming yourself")
    assert e.resolve(s) == "library-bridged(search-miss)"
    assert s.matched_asset == "/lib/moth.jpg"


def test_bridge_called_once_per_scene():
    calls = []
    def bridge(s):
        calls.append(1)
        return ["metaphor one", "metaphor two"]
    e = AssetEngine(EngineConfig(enable_generation=False),
                    search_fn=lambda s: None,      # search tier probes both, misses
                    library_fn=lambda s: None,     # library tier probes both, misses
                    bridge_fn=bridge)
    s = scene()
    assert e.resolve(s) == "none(search-miss)"
    assert len(calls) == 1     # one bridge call shared across tiers


def test_bridge_failure_contained():
    def bridge(s):
        raise RuntimeError("LLM down")
    e = AssetEngine(EngineConfig(enable_generation=False),
                    search_fn=lambda s: None,
                    bridge_fn=bridge)
    s = scene()
    assert e.resolve(s) == "none(search-miss)"


def test_bridge_disabled_by_config():
    calls = []
    e = AssetEngine(EngineConfig(enable_bridge=False, enable_generation=False),
                    search_fn=lambda s: None,
                    bridge_fn=lambda s: calls.append(1) or ["m"])
    s = scene()
    assert e.resolve(s) == "none(search-miss)"
    assert calls == []


# --- asset ladder completion (no-reuse + shot fulfillment) --------------------------

def test_no_reuse_same_library_asset(tmp_path):
    from nolan.asset_engine import AssetEngine, EngineConfig
    from nolan.scenes import Scene
    asset = str(tmp_path / "one.jpg")
    engine = AssetEngine(EngineConfig(enable_generation=False),
                         library_fn=lambda s: asset)
    s1 = Scene(id="s1", visual_type="b-roll", search_query="q")
    s2 = Scene(id="s2", visual_type="b-roll", search_query="q")
    assert engine.resolve(s1).startswith("library")
    assert s1.matched_asset == asset
    # same asset again -> treated as a miss, escalation continues to none()
    assert engine.resolve(s2).startswith("none")
    assert s2.matched_asset is None


def test_no_reuse_same_clip_segment():
    from nolan.asset_engine import AssetEngine, EngineConfig
    from nolan.scenes import Scene
    mc = {"video_path": "lib/v.mp4", "clip_start": 3.0, "similarity_score": 0.9}
    engine = AssetEngine(EngineConfig(enable_generation=False,
                                      enable_library=False,
                                      enable_bridge=False),
                         search_fn=lambda s: dict(mc))
    s1 = Scene(id="s1", visual_type="b-roll")
    s2 = Scene(id="s2", visual_type="b-roll")
    assert engine.resolve(s1).startswith("search")
    assert engine.resolve(s2).startswith("none")


def test_fulfill_shots_wanted(tmp_path):
    from nolan.asset_engine import AssetEngine
    from nolan.scenes import Scene

    class _R:
        def __init__(self, url): self.url = url

    class _Client:
        def search(self, q, max_results=3):
            return [_R(f"https://x/{abs(hash(q)) % 999}_{i}.jpg") for i in range(2)]

    fetched = []

    def fake_fetch(url, dest):
        dest.write_bytes(b"img")
        fetched.append(url)

    anchor = tmp_path / "anchor.jpg"
    anchor.write_bytes(b"img")
    s = Scene(id="s1", visual_type="b-roll", search_query="suburb aerial",
              matched_asset=str(anchor))
    s.extra["shots_wanted"] = 3
    done = AssetEngine.fulfill_shots_wanted(
        [s], nolan_config=None, project_path=tmp_path,
        client=_Client(), fetch=fake_fetch)
    assert done == 1
    shots = s.extra["shots"]
    assert shots[0]["src"] == str(anchor) and shots[0]["weight"] == 1.5
    assert len(shots) == 3 and len(fetched) == 2
    # the editing gate accepts what we authored
    from nolan.editing import validate_scene_editing
    assert validate_scene_editing({"id": "s1", "shots": shots}) == []


def test_fulfill_art_shots_require_title_match(tmp_path):
    """Extra views of a NAMED work must title-match the query — museum fuzzy
    search once filled Odyssey scenes with a Renaissance portrait. Unrelated
    titles → the scene stays single-still (unfulfilled, loud), never wrong art.
    """
    from nolan.asset_engine import AssetEngine
    from nolan.scenes import Scene

    class _R:
        def __init__(self, url, title):
            self.url, self.title = url, title
            self.source = "met"                 # open-access: passes archival tier
            self.source_url = None
            self.thumbnail_url = None
            self.license = None
            self.width = self.height = None

    class _Client:
        def __init__(self, results): self._results = results
        def search_assets(self, q, media_type=None, sources=None, max_results=6):
            return self._results

    def fake_fetch(url, dest):
        dest.write_bytes(b"img")

    def _scene(tmp_path):
        anchor = tmp_path / "anchor.jpg"
        anchor.write_bytes(b"img")
        s = Scene(id="s1", visual_type="archival-art",
                  search_query="Odysseus Sirens E440 stamnos",
                  matched_asset=str(anchor))
        s.extra["shots_wanted"] = 3
        return s

    # matching titles pass the filter
    s = _scene(tmp_path)
    ok = AssetEngine.fulfill_shots_wanted(
        [s], nolan_config=None, project_path=tmp_path,
        client=_Client([_R("https://x/a.jpg", "Odysseus and the Sirens E440 side view"),
                        _R("https://x/b.jpg", "Siren vase stamnos Odysseus detail")]),
        fetch=fake_fetch)
    assert ok == 1 and len(s.extra["shots"]) == 3

    # unrelated artworks are refused — no shots authored at all
    s2 = _scene(tmp_path)
    s2.id = "s2"
    ok = AssetEngine.fulfill_shots_wanted(
        [s2], nolan_config=None, project_path=tmp_path,
        client=_Client([_R("https://x/c.jpg", "Portrait of a Young Woman"),
                        _R("https://x/d.jpg", "Saint Philip Neri")]),
        fetch=fake_fetch)
    assert ok == 0 and "shots" not in s2.extra


def test_fulfill_skips_scene_with_existing_shots(tmp_path):
    from nolan.asset_engine import AssetEngine
    from nolan.scenes import Scene
    s = Scene(id="s1", visual_type="b-roll", matched_asset="a.jpg")
    s.extra["shots_wanted"] = 3
    s.extra["shots"] = [{"src": "human.jpg"}]     # human authoring wins
    done = AssetEngine.fulfill_shots_wanted(
        [s], nolan_config=None, project_path=tmp_path,
        client=object(), fetch=lambda u, d: None)
    assert done == 0 and s.extra["shots"] == [{"src": "human.jpg"}]
