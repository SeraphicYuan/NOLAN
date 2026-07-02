"""Tests for L3 agentic auto-pairing planner (nolan.evoke_broll._auto_plan).

Constructs an EvokeBrollSearch without __init__ (which needs config/network) and drives the
planner with a mock LLM to verify operator validation, fallback de-duplication, and defaults."""
import asyncio
from types import SimpleNamespace

from nolan.evoke_broll import EvokeBrollSearch, _OP


def _searcher(reply: str):
    s = EvokeBrollSearch.__new__(EvokeBrollSearch)     # bypass __init__ (no config/network)
    async def _gen(prompt, sys=None):
        return reply
    s.llm = SimpleNamespace(generate=_gen)
    return s


def _ctx():
    return SimpleNamespace(beats=[1], brief=lambda max_chars=1400: "SUBJECT: X",
                           beat_context=lambda i, **k: "ARC POSITION: beat 1 of 1")


def _plan(reply):
    return asyncio.run(_searcher(reply)._auto_plan(_ctx(), 0, "a line"))


def test_valid_plan_passthrough():
    p = _plan('{"primary": "knowledge", "fallback": "tonal", "why": "names a real vase"}')
    assert p["primary"] == "knowledge" and p["fallback"] == "tonal"
    assert "vase" in p["why"]


def test_invalid_operators_default():
    # garbage operators → sensible defaults (knowledge primary, tonal fallback)
    p = _plan('{"primary": "banana", "fallback": "nonsense", "why": ""}')
    assert p["primary"] in _OP and p["fallback"] in _OP
    assert p["primary"] == "knowledge" and p["fallback"] == "tonal"


def test_fallback_deduped():
    # primary == fallback → fallback is changed to something else
    p = _plan('{"primary": "tonal", "fallback": "tonal", "why": "mood beat"}')
    assert p["primary"] == "tonal" and p["fallback"] != "tonal" and p["fallback"] in _OP


def test_non_json_reply_defaults():
    p = _plan("I think knowledge would be best here, honestly.")
    assert p["primary"] in _OP and p["fallback"] in _OP     # no crash, valid ops


def test_all_operators_are_pickable():
    for op in ("tonal", "conceptual", "ironic", "trait", "relational", "scale", "knowledge"):
        p = _plan('{"primary": "%s", "fallback": "tonal", "why": "x"}' % op)
        assert p["primary"] == op


# ---- meta-judge ----
def _judge(reply, picks=None):
    s = _searcher(reply)
    picks = picks if picks is not None else [{"kind": "image", "source": "artic", "why": "the real vase"}]
    return asyncio.run(s._auto_judge(_ctx(), 0, "a line", "knowledge", picks))


def test_judge_accept():
    j = _judge('{"score": 8, "verdict": "accept", "why": "the actual work, clean"}')
    assert j["verdict"] == "accept" and j["score"] == 8.0


def test_judge_reject_explicit():
    j = _judge('{"score": 7, "verdict": "reject", "why": "wrong era"}')
    assert j["verdict"] == "reject"                       # explicit reject wins even with a decent score


def test_judge_low_score_forces_reject():
    j = _judge('{"score": 3, "verdict": "accept", "why": "meh"}')
    assert j["verdict"] == "reject"                       # score < 5 → reject regardless


def test_judge_empty_picks_reject():
    assert _judge("{}", picks=[])["verdict"] == "reject"


def test_judge_clamps_and_defaults():
    assert _judge('{"score": 99}')["score"] == 10.0       # clamp
    assert _judge("not json")["score"] == 6.0             # default when unparseable
