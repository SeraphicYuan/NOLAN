"""Phase-2 tests: the spine-structure registry + composite-spine wiring.

Honesty / back-compat: every structure resolves, thread bounds validate, `single` stays
the default (today's behaviour), and a composite spine round-trips through the store and
surfaces in ScriptContext.
"""

import pytest

from nolan.scriptwriter import spine_structures as ss
from nolan.scriptwriter import ScriptProjectStore


def test_every_structure_resolves_and_has_bounds():
    for sid, s in ss.STRUCTURES.items():
        assert ss.get_structure(sid).id == sid
        assert 1 <= s.min_threads <= s.max_threads
        assert s.when_to_use and s.beat_guidance


def test_unknown_structure_falls_back_to_single():
    assert ss.get_structure("nope").id == "single"
    assert ss.get_structure("").id == "single"


def test_validate_thread_bounds():
    ok, _ = ss.validate_composite_spine({})                      # empty = single = valid
    assert ok
    ok, _ = ss.validate_composite_spine(
        {"structure": "braided", "threads": ["a", "b"]})
    assert ok
    ok, err = ss.validate_composite_spine(
        {"structure": "braided", "threads": ["only one"]})       # braided needs >=2
    assert not ok and "2" in err
    ok, err = ss.validate_composite_spine({"structure": "made-up", "threads": []})
    assert not ok and "unknown" in err


def test_single_renders_no_beat_guidance():
    assert ss.render_structure_guidance({"structure": "single"}) == ""
    assert ss.render_structure_guidance({}) == ""


def test_composite_renders_threads_and_binding():
    md = ss.render_structure_guidance(
        {"structure": "braided", "threads": ["the human story", "the systemic story"],
         "binding": "the person is the system in miniature"})
    assert "Braided" in md and "human story" in md and "miniature" in md


def test_menu_lists_all_structures():
    menu = ss.render_structures_menu()
    for sid in ss.STRUCTURES:
        assert sid in menu


def test_auto_spine_valid_and_renders_pick_instruction():
    ok, _ = ss.validate_composite_spine({"structure": "auto"})
    assert ok
    g = ss.render_structure_guidance({"structure": "auto"})
    assert "YOU choose it" in g and "structure = auto" in g
    assert "Single spine" not in g          # must NOT mis-fall-back to single


def test_store_and_brief_carry_auto_spine(tmp_path):
    from nolan.scriptwriter import v3_task
    store = ScriptProjectStore(tmp_path)
    slug = store.create("Au", subject="the economy debate", style_id="s", target_minutes=8)
    store.set_composite_spine(slug, "auto", [], "")
    assert store.get(slug)["composite_spine"]["structure"] == "auto"
    brief = v3_task(slug, store)                         # full-auto uses v3
    assert "YOU choose it" in brief                      # the agent is told to pick the structure


def test_store_composite_spine_roundtrip_and_validation(tmp_path):
    store = ScriptProjectStore(tmp_path)
    slug = store.create("Braid", subject="x", style_id="s", target_minutes=10)
    assert store.get(slug)["composite_spine"] == {}                  # default single
    store.set_composite_spine(slug, "braided",
                              ["human thread", "systemic thread"], "one in miniature")
    sp = store.get(slug)["composite_spine"]
    assert sp["structure"] == "braided" and len(sp["threads"]) == 2
    # invalid thread count is rejected
    with pytest.raises(ValueError):
        store.set_composite_spine(slug, "thesis-antithesis-synthesis", ["only one"], "")
    # setting back to single clears it
    store.set_composite_spine(slug, "single", [], "")
    assert store.get(slug)["composite_spine"] == {}


def test_scriptcontext_surfaces_composite_spine(tmp_path):
    from nolan.script_context import ScriptContext
    store = ScriptProjectStore(tmp_path)
    slug = store.create("Ctx", subject="x", style_id="s", target_minutes=10)
    store.set_composite_spine(slug, "chronological", ["rise", "fall"], "the arc of a boom")
    store.script_path(slug).write_text(
        "# Video Script\n\n**Total Duration:** 1:00\n\n---\n\n## Rise [0:00]\n\nUp.\n\n## Fall [0:30]\n\nDown.\n",
        encoding="utf-8")
    ctx = ScriptContext.load(tmp_path / slug)
    assert ctx.spine.get("structure") == "chronological"
    assert ctx.angle == "the arc of a boom"          # synthesized flat angle for back-compat
    assert "SPINE STRUCTURE: chronological" in ctx.brief()
