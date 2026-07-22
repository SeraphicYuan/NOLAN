"""P6: emotion-arc assignment (validated) + deterministic marker application."""

import asyncio

from nolan import emotion_arc as ea


def _secs(n):
    return [{"title": f"Beat {i}", "body": f"Some narration for beat {i} here."} for i in range(n)]


def test_pivot_budget():
    assert ea.pivot_budget(3) == 1 and ea.pivot_budget(9) == 3 and ea.pivot_budget(30) == 4


def test_parse_validates_registry_and_cap():
    n = 8
    # 'bogus' is not in the registry → dropped; capped at max_marked=2
    text = 'noise {"0": "grave", "2": "bogus", "5": "wry", "7": "urgent"} tail'
    out = ea.parse_arc_response(text, n, max_marked=2)
    assert out[0] == "grave"
    assert out[2] is None                     # invalid tone dropped
    assert sum(1 for x in out if x) == 2      # capped to 2
    assert len(out) == n


def test_parse_handles_garbage():
    assert ea.parse_arc_response("no json here", 4, max_marked=2) == [None] * 4


def test_assign_arc_with_fake_llm():
    async def fake_generate(prompt):
        assert "emotional pivot" in prompt and "grave" in prompt   # registry + restraint in prompt
        return '{"0": "tense", "4": "grave"}'
    out = asyncio.run(ea.assign_arc(_secs(6), generate=fake_generate))
    assert out[0] == "tense" and out[4] == "grave" and sum(1 for x in out if x) == 2


def test_apply_inserts_updates_and_strips():
    md = ("# Video Script\n---\n"
          "## Cold open\nThe hook line here.\n\n"
          "## The turn\n[delivery: stale]\nThe pivot line here.\n\n"
          "## The close\nThe final line here.\n")
    out = ea.apply_arc_to_script(md, ["tense", None, "warm"])
    # beat 0 got a marker inserted right under its heading
    assert "## Cold open\n[delivery: tense]\n" in out
    # beat 1's stale marker was stripped (now None)
    assert "[delivery: stale]" not in out
    # beat 2 got warm
    assert "## The close\n[delivery: warm]\n" in out
    # spoken text preserved
    assert "The hook line here." in out and "The pivot line here." in out


def test_apply_roundtrips_with_parse_script_sections():
    """A written delivery is read back by the A6 parser as that beat's delivery, not spoken."""
    from nolan.script import parse_script_sections
    md = "# S\n---\n## One\nFirst beat body.\n\n## Two\nSecond beat body.\n"
    out = ea.apply_arc_to_script(md, ["grave", None])
    secs = parse_script_sections(out)
    assert secs[0]["delivery"] == "grave" and "grave" not in secs[0]["body"]
    assert secs[1].get("delivery") is None
