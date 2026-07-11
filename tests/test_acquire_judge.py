"""Tests for the VLM usability FLOOR (src/nolan/acquire/judge.py) — pure prompt/parse/decision, no VLM.
Enforces: the floor drops flagged + low-usable images, but a NEUTRAL verdict (VLM down) keeps the asset."""
from nolan.acquire import judge_prompt, extract_json, parse_verdict, is_junk, UNUSABLE_FLAGS


def test_prompt_carries_beat_and_framing():
    ev = judge_prompt({"query": "shell company puzzle", "evocative": True})
    co = judge_prompt({"query": "data center servers", "evocative": False})
    assert "shell company puzzle" in ev and "EVOCATIVE" in ev
    assert "data center servers" in co and "CONCRETE" in co


def test_extract_json_handles_fences_and_prose():
    assert extract_json('{"usable": 7}')["usable"] == 7
    assert extract_json('```json\n{"usable": 5}\n```')["usable"] == 5
    assert extract_json('Sure! Here: {"usable": 3, "flags": ""} done')["usable"] == 3
    assert extract_json("not json at all") == {}
    assert extract_json("") == {}


def test_parse_verdict_normalises_and_clamps():
    v = parse_verdict({"usable": 12, "flags": "  watermark ", "caption": "a\nb", "why": "x"})
    assert v["usable"] == 10.0                      # clamped to 0..10
    assert v["flags"] == "watermark"                # stripped
    assert v["caption"] == "a b"                    # newline flattened
    assert parse_verdict(None)["usable"] is None    # garbled → neutral
    assert parse_verdict({"usable": "n/a"})["usable"] is None


def test_is_junk_floor_and_flags():
    assert is_junk({"usable": 8, "flags": "watermark"})            # flagged → out regardless of score
    assert is_junk({"usable": 2, "flags": ""}, floor=4.0)          # below floor → out
    assert not is_junk({"usable": 8, "flags": ""}, floor=4.0)      # clean + high → kept
    assert not is_junk({"usable": None, "flags": ""})              # NEUTRAL (VLM down) → kept, never emptied
    # off-topic notes come back in flags but are caught by the LOW usable score, not the flag list
    assert is_junk({"usable": 2, "flags": "a sports car, not a permit"}, floor=4.0)


def test_every_unusable_flag_trips():
    for f in UNUSABLE_FLAGS:
        assert is_junk({"usable": 9, "flags": f})
