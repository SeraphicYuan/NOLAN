"""The graph's move after a round — including the one a replay could never have found.

    D:\\env\\nolan\\python.exe -X utf8 -m pytest explore/2026-08-02-script-loop-graph/ -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import loop_control as lc                                    # noqa: E402
from nolan.scriptwriter.verdicts import parse_verdict        # noqa: E402


def _v(verdict="better", *, regressions=(), blockers=()):
    return parse_verdict({"verdict": verdict, "vs_draft": "draft-01",
                          "regressions": list(regressions), "blockers": list(blockers)})


def _b(dim, beat, severity="high"):
    return {"dim": dim, "beat": beat, "severity": severity}


# --- persistence -----------------------------------------------------------------------------

def test_persistence_counts_only_a_consecutive_run():
    """A blocker raised, fixed, then raised again is two events — not one that resisted two
    passes. Conflating them would escalate something the loop actually handled."""
    rounds = [[_b("voice", "hook")], [], [_b("voice", "hook")]]
    assert lc.persistence(rounds)[("voice", "hook")] == 1
    assert not lc.stuck(rounds)

    survived = [[_b("voice", "hook")], [_b("voice", "hook")], [_b("voice", "hook")]]
    assert lc.persistence(survived)[("voice", "hook")] == 3
    assert lc.stuck(survived) == [("voice", "hook")]


def test_persistence_matches_on_dim_and_beat_not_wording():
    """A judge rephrases. Matching on text would report every persisted finding as newly
    discovered — precisely the blindness being fixed."""
    a = {"dim": "voice-ownership", "beat": "The Hook", "problem": "too many attributions"}
    b = {"dim": "voice-ownership", "beat": "the hook  ", "problem": "still cites X four times"}
    assert lc._key(a) == lc._key(b)
    assert lc.stuck([[a], [b]]) == [("voice-ownership", "the hook")]


def test_a_finding_only_in_an_older_round_is_not_stuck():
    assert not lc.stuck([[_b("x", "a")], [_b("y", "b")]])


# --- routing ---------------------------------------------------------------------------------

def test_a_failing_gate_is_not_a_judgement_call():
    """Collapsed timecodes and a declared duration 30% out are arithmetic — nothing for a human
    to weigh and no reason to spend a judgement."""
    a = lc.decide(_v("better"), round_n=1, rounds=[], gate_ok=False,
                  gate_failures=["timecodes", "declared-duration"])
    assert a.action == lc.CONTINUE
    assert "timecodes" in a.why and "arithmetic" in a.why


def test_a_regression_reverts_and_narrows_the_change_set():
    """THE ACTION A REPLAY COULD NOT FIND. Recorded runs only ever contain rounds that improved,
    so nothing in the historical data implies this move exists."""
    v = _v("worse",
           regressions=[{"beat": "close", "what": "lost the callback", "severity": "high"}],
           blockers=[_b("a", "b1", "high"), _b("c", "b2", "med"), _b("d", "b3", "low")])
    a = lc.decide(v, round_n=1, rounds=[])
    assert a.action == lc.REVERT
    assert len(a.retry_with) == 1 and a.retry_with[0]["severity"] == "high"
    assert "retry with 1 high-severity item(s) instead of 3" in a.why


def test_a_better_draft_that_broke_a_beat_fixes_FORWARD_and_never_reverts():
    """THIS TEST ASSERTED THE OPPOSITE UNTIL P8 RAN, and P8 is why it changed.

    Three drafts, three styles, two archetypes: every one was judged BETTER with something
    broken. Reverting on any regression therefore discarded a net improvement in 100% of real
    cases — one of them over a single `low`-severity break. Same shape as the finding-count bug
    it replaced: defensible in the abstract, backwards on contact with data.

    The gains survive; the break becomes the next pass's change set.
    """
    v = _v("better", regressions=[{"beat": "hook", "what": "dropped the promise"}])
    a = lc.decide(v, round_n=1, rounds=[])
    assert a.action == lc.CONTINUE
    assert "keep the gains and fix forward" in a.why
    assert [r["beat"] for r in a.retry_with] == ["hook"]      # carried, not discarded


def test_the_carried_set_narrows_to_highs_when_there_are_any():
    """Fix-forward still applies P6's smaller-change-set hypothesis: target what is
    unambiguously severe rather than re-litigating every break at once."""
    v = _v("better", regressions=[{"beat": "a", "severity": "high"},
                                  {"beat": "b", "severity": "low"},
                                  {"beat": "c", "severity": "med"}])
    a = lc.decide(v, round_n=1, rounds=[])
    assert a.action == lc.CONTINUE
    assert [r["beat"] for r in a.retry_with] == ["a"]


def test_a_worse_draft_still_reverts():
    """The case P6 was built for is untouched: no gains to protect, so go back."""
    v = _v("worse", regressions=[{"beat": "close", "what": "lost the callback"}],
           blockers=[_b("a", "b1", "high")])
    assert lc.decide(v, round_n=1, rounds=[]).action == lc.REVERT


def test_an_ambiguous_verdict_that_broke_something_reverts():
    """`mixed` is not an improvement to protect. Only a clear `better` earns fix-forward."""
    v = _v("mixed", regressions=[{"beat": "hook", "what": "dropped the promise"}])
    assert lc.decide(v, round_n=1, rounds=[]).action == lc.REVERT


def test_a_stuck_blocker_escalates_to_a_human():
    """Two passes aimed at it and still there means the loop is not what fixes it."""
    stuck_b = _b("figurative-fitness", "the mirror")
    a = lc.decide(_v("better", blockers=[stuck_b]), round_n=2,
                  rounds=[[stuck_b], [stuck_b]])
    assert a.action == lc.ASK and "survived 2 passes" in a.why


def test_max_rounds_is_its_own_terminal_state():
    """A run that hit the ceiling must never read like one that converged."""
    a = lc.decide(_v("better", blockers=[_b("x", "y", "high")]),
                  round_n=lc.MAX_ROUNDS, rounds=[])
    assert a.action == lc.STOP and "max_rounds_reached" in a.why
    assert "ceiling, not convergence" in a.why
    assert lc.summarise_run([a])["max_rounds_reached"] == 1


def test_a_clean_stop_is_not_counted_as_max_rounds():
    clean = lc.decide(_v("better"), round_n=1, rounds=[])
    assert clean.action == lc.STOP
    assert lc.summarise_run([clean])["max_rounds_reached"] == 0


def test_improving_with_high_blockers_keeps_going():
    a = lc.decide(_v("better", blockers=[_b("x", "y", "high")]), round_n=1, rounds=[])
    assert a.action == lc.CONTINUE and "another pass is paying" in a.why


def test_a_missing_verdict_asks_rather_than_guessing():
    assert lc.decide(None, round_n=1, rounds=[]).action == lc.ASK


def test_an_ambiguous_verdict_with_no_high_blockers_is_a_judgement_call():
    assert lc.decide(_v("mixed"), round_n=1, rounds=[]).action == lc.ASK


def test_nothing_here_routes_on_a_count_of_blockers():
    """The metric that inverted last time. Twelve low-severity blockers must not outrank one
    high — a long list is not evidence of a bad draft."""
    many_low = _v("better", blockers=[_b("d", f"b{i}", "low") for i in range(12)])
    one_high = _v("better", blockers=[_b("d", "b", "high")])
    assert lc.decide(many_low, round_n=1, rounds=[]).action == lc.STOP
    assert lc.decide(one_high, round_n=1, rounds=[]).action == lc.CONTINUE
