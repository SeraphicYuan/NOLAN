"""Tests for the perceptual render gate's pure logic (no VLM) — prompt / parse / floor / beat-label."""
from nolan.hyperframes import render_gate as rg


def test_prompt_carries_the_beat():
    p = rg.judge_prompt("water pouring into a reservoir")
    assert "water pouring into a reservoir" in p and "legible" in p and "relevant" in p


def test_prompt_role_awareness():
    lit = rg.judge_prompt("gavel hitting a sound block", atmospheric=False)
    atm = rg.judge_prompt("Lake Tahoe", atmospheric=True)
    assert "IS the subject" in lit                      # literal-subject block → depict the thing
    assert "ESTABLISHING GROUND" in atm and "NOT off-topic" in atm   # atmospheric ground → establishing OK


def test_extract_json_handles_fences_and_prose():
    assert rg.extract_json('{"legible": 7}')["legible"] == 7
    assert rg.extract_json('here: {"legible": 5, "relevant": 6} ok')["relevant"] == 6
    assert rg.extract_json("nope") == {}


def test_parse_clamps_and_neutralises():
    v = rg.parse_verdict({"legible": 12, "relevant": -3, "flags": " off-topic "})
    assert v["legible"] == 10.0 and v["relevant"] == 0.0 and v["flags"] == "off-topic"
    assert rg.parse_verdict(None)["legible"] is None
    assert rg.parse_verdict({"legible": "n/a"})["legible"] is None


def test_is_bad_floor_and_flags():
    assert rg.is_bad({"legible": 2, "relevant": 9, "flags": ""})          # illegible text
    assert rg.is_bad({"legible": 9, "relevant": 2, "flags": ""})          # off-topic imagery
    assert rg.is_bad({"legible": 9, "relevant": 9, "flags": "blank"})     # blank/clipped -> out
    assert not rg.is_bad({"legible": 8, "relevant": 8, "flags": ""})      # clean + high
    assert not rg.is_bad({"legible": None, "relevant": None, "flags": ""})  # VLM down -> advisory, not bad


def test_beat_label_prefers_anchor_then_content():
    assert rg._beat_label({"type": "stat", "data": {"anchor": "sixty-one thousand", "operative": "x"}}) == "sixty-one thousand"
    assert rg._beat_label({"type": "statement", "data": {"lines": [{"text": "the grid is strained"}]}}) == "the grid is strained"
    assert rg._beat_label({"type": "diagram", "data": {}}) == "diagram"
