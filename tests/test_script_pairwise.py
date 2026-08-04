"""The judge asked whether a draft got BETTER, and the refusal to turn that back into a score.

The failure being fixed: draft-02 of a real essay was better than draft-01 in six specific,
checkable ways — it replaced a bare assertion with real evidence, swapped an analogy the audience
had no relationship with, cut a line the channel had used in another script, showed Penelope's
shroud instead of asserting fidelity with two numbers, and repaired a hook/close contradiction.

It scored WORSE: 99 -> 117 weighted, 6 -> 8 high findings.

The mechanism is not noise. "List everything wrong" makes vagueness win — an assertion offers a
critic nothing to grip, an argument offers plenty — so counting findings is pointed backwards and
would have stopped a run that was working.
"""

import json

import pytest

from nolan.scriptwriter import ScriptProjectStore, pairwise, verdicts


def _draft(words=1000, beats=3, dur="8:00"):
    per = max(1, words // beats)
    body = "".join(f"## Beat {i} [{i - 1}:00]\n\n{'word ' * per}\n\n" for i in range(1, beats + 1))
    return f"# Video Script\n\n**Total Duration:** {dur}\n\n" + body


@pytest.fixture()
def store(tmp_path):
    slug = "p"
    sg = tmp_path / slug / "scriptgen"
    (sg / "drafts").mkdir(parents=True)
    (sg / "reviews").mkdir(parents=True)
    for n in ("brief.md", "facts.md", "beatmap.md", "citations.md", "factcheck.md"):
        (sg / n).write_text("x\n", encoding="utf-8")
    (sg / "meta.json").write_text(json.dumps({
        "slug": slug, "name": "P", "subject": "the case for nuclear power",
        "style_id": "s", "target_minutes": 8.0, "mode": "auto"}), encoding="utf-8")
    return slug, ScriptProjectStore(tmp_path)


def _write(store_t, n, words=1000):
    slug, st = store_t
    (st.root / slug / "scriptgen" / "drafts" / f"draft-{n:02d}.md").write_text(
        _draft(words), encoding="utf-8")


# --- the brief -------------------------------------------------------------------------------

def test_the_brief_forbids_counting(store):
    """Any metric built on counting findings is inverted. The instruction has to be explicit,
    because 'list what is wrong' is the natural thing for a critic to do."""
    _write(store, 1); _write(store, 2)
    brief = pairwise.pairwise_task(*store)
    assert "not writing a list of everything wrong" in brief
    assert "Do **not** count anything" in brief
    assert "No scores, no totals" in brief


def test_the_brief_puts_both_drafts_in_one_sitting(store):
    """A comparison inside ONE context needs no cross-session calibration — which is the other
    thing that made absolute scores unusable: the same draft judged twice scored 17 and 99."""
    _write(store, 1, words=900); _write(store, 2, words=1100)
    slug, st = store
    brief = pairwise.pairwise_task(*store)
    assert "draft-01.md" in brief and "draft-02.md" in brief
    assert "Read the previous draft first" in brief
    assert "judging the CHANGE" in brief
    # Computed, not hardcoded — the fixture splits its total across beats, so the real count is
    # not the number requested.
    from nolan.scriptwriter.tasks import _narration_words
    for n in (1, 2):
        w = _narration_words(st.read_draft(slug, f"draft-{n:02d}.md"))
        assert f"{w} narration words" in brief, f"draft-{n:02d} should report {w}"


def test_the_first_draft_is_not_compared_to_an_imaginary_predecessor(store):
    """Stated in the brief rather than silently producing a comparison against nothing."""
    _write(store, 1)
    brief = pairwise.pairwise_task(*store)
    assert "no previous draft" in brief
    assert '"vs_draft": null' in brief


def test_blockers_are_capped_in_the_brief(store):
    """23 findings applied at once is a rewrite, not surgery, and a rewrite is how the last
    revision got worse."""
    _write(store, 1); _write(store, 2)
    brief = pairwise.pairwise_task(*store)
    assert f"capped at {pairwise.MAX_BLOCKERS}" in brief
    assert "regressions` is the highest-value field" in brief


# --- the verdict -----------------------------------------------------------------------------

def test_a_regression_is_visible_even_when_the_draft_improved_overall():
    """A draft can be better on balance and still have broken a beat — and that beat is the
    cheapest thing in the loop to fix, being known, located and recent. An overall verdict alone
    would hide it."""
    v = verdicts.parse_verdict({
        "verdict": "better", "vs_draft": "draft-01",
        "gains": [{"beat": "hook", "what": "real evidence replaced an assertion"}],
        "regressions": [{"beat": "close", "what": "lost the callback", "severity": "med"}]})
    assert v.improved and v.regressed, "improved overall, still broke something"


def test_worse_is_a_sayable_verdict():
    v = verdicts.parse_verdict({"verdict": "worse", "vs_draft": "draft-01"})
    assert v.regressed and not v.improved


def test_blocking_filters_by_severity_and_returns_the_items():
    """The routing input is a filtered LIST, never a count — no function here hands out a number
    that looks like a quality score."""
    v = verdicts.parse_verdict({"verdict": "mixed", "vs_draft": "draft-01", "blockers": [
        {"beat": "a", "severity": "high"}, {"beat": "b", "severity": "med"},
        {"beat": "c", "severity": "low"}]})
    assert [b["beat"] for b in v.blocking(min_severity="high")] == ["a"]
    assert [b["beat"] for b in v.blocking(min_severity="med")] == ["a", "b"]
    assert not hasattr(v, "score"), "a Verdict must expose no aggregate score"


def test_a_malformed_verdict_keeps_the_evidence():
    """A bad word is a reason to be cautious, not a reason to throw away the gains, regressions
    and blockers that came with it."""
    v = verdicts.parse_verdict({"verdict": "excellent!!", "vs_draft": "draft-01",
                                "blockers": [{"beat": "a", "severity": "high"}]})
    assert v.verdict == verdicts.MIXED
    assert len(v.blockers) == 1


def test_a_bare_list_is_read_as_blockers_with_no_comparison():
    v = verdicts.parse_verdict([{"beat": "a", "severity": "high"}])
    assert v.verdict == verdicts.MIXED and v.vs_draft is None and len(v.blockers) == 1
    for junk in (None, "nope", 7):
        assert verdicts.parse_verdict(junk).verdict == verdicts.MIXED


def test_summarise_reports_events_not_a_total():
    v = verdicts.parse_verdict({
        "verdict": "better", "vs_draft": "draft-01",
        "gains": [{"beat": "a"}, {"beat": "b"}],
        "regressions": [{"beat": "c", "severity": "high"}],
        "blockers": [{"beat": "d", "severity": "high"}]})
    s = verdicts.summarise(v)
    assert "BETTER" in s and "REGRESSION" in s and "2 gain" in s


def test_verdict_round_trips_through_the_store(store):
    slug, st = store
    _write(store, 1); _write(store, 2)
    payload = {"verdict": "better", "vs_draft": "draft-01", "why": "stronger evidence",
               "gains": [{"beat": "hook", "what": "x"}], "regressions": [], "blockers": []}
    verdicts.verdict_path(st, slug, 2).write_text(json.dumps(payload), encoding="utf-8")
    v = verdicts.read_verdict(st, slug, 2)
    assert v and v.improved and v.why == "stronger evidence"
    assert verdicts.read_verdict(st, slug, 99) is None
