"""The revise pass's length budget.

Measured on a real run: applying 23 approved findings added **192 words** to a draft already 40%
over its declared duration — while pacing was one of the six high-severity findings the pass had
been told to fix. Every finding asks the writer to add, strengthen or show, so a set of them
applied at once is expansion, not surgery.

Narration owns duration in this pipeline. Words are seconds.
"""

import json

import pytest

from nolan.scriptwriter import ScriptProjectStore, tasks


def _draft(words, beats=3):
    per = max(1, words // beats)
    body = "".join(f"## Beat {i} [{i - 1}:00]\n\n{'word ' * per}\n\n" for i in range(1, beats + 1))
    return "# Video Script\n\n**Total Duration:** 8:00\n\n" + body


@pytest.fixture()
def store(tmp_path):
    slug = "p"
    sg = tmp_path / slug / "scriptgen"
    (sg / "drafts").mkdir(parents=True)
    (sg / "reviews").mkdir(parents=True)
    (sg / "drafts" / "draft-01.md").write_text(_draft(1316), encoding="utf-8")
    (sg / "reviews" / "review-01.findings.json").write_text("[]", encoding="utf-8")
    for n in ("brief.md", "facts.md", "beatmap.md", "citations.md", "factcheck.md"):
        (sg / n).write_text("x\n", encoding="utf-8")
    (sg / "meta.json").write_text(json.dumps({
        "slug": slug, "name": "P", "subject": "the case for nuclear power",
        "style_id": "s", "target_minutes": 8.0, "mode": "auto"}), encoding="utf-8")
    return slug, ScriptProjectStore(tmp_path)


def test_narration_words_counts_only_what_is_spoken():
    """Headings and timecodes are not read aloud, so counting the whole file overstates the
    runtime the budget exists to control."""
    text = _draft(300, beats=3)
    n = tasks._narration_words(text)
    assert 290 <= n <= 310, n
    assert n < len(text.split()), "headings must not be counted as narration"
    assert tasks._narration_words("") == 0
    assert tasks._narration_words("no beats at all") == 0


def test_the_budget_is_stated_as_a_hard_ceiling(store):
    slug, st = store
    brief = tasks.revise_task(slug, st, unattended=True)
    assert "LENGTH BUDGET" in brief
    assert "hard constraint, not a target" in brief
    # 8 min x 145 wpm = 1160, +/- 5%
    assert "1102" in brief and "1218" in brief
    # ...and it must say where the current draft actually stands. Computed, not hardcoded: the
    # fixture splits its word count across beats, so the real total is not the number asked for.
    actual = tasks._narration_words(st.read_draft(slug, "draft-01.md"))
    assert str(actual) in brief, f"brief should state the current {actual} words"


def test_the_budget_anchors_on_the_TARGET_not_the_current_draft(store):
    """Anchoring on the draft in hand would let an overrun ratchet: each round would bless the
    previous round's inflation as the new baseline, and a script could grow indefinitely while
    every individual round looked reasonable."""
    slug, st = store
    (st.root / slug / "scriptgen" / "drafts" / "draft-01.md").write_text(
        _draft(2400), encoding="utf-8")            # a wildly overrun draft
    brief = tasks.revise_task(slug, st, unattended=True)
    assert "1102" in brief and "1218" in brief, "the ceiling must not move with the draft"
    actual = tasks._narration_words(st.read_draft(slug, "draft-01.md"))
    assert actual > 2000, "fixture should be wildly overrun"
    assert str(actual) in brief, "but it must SAY where we are"


def test_the_budget_tracks_target_minutes(store):
    slug, st = store
    meta = st.get(slug)
    meta["target_minutes"] = 15.0
    st._save_meta(meta)
    brief = tasks.revise_task(slug, st, unattended=True)
    assert "2066" in brief and "2283" in brief          # 15 x 145 = 2175, +/- 5%


def test_the_brief_and_the_gate_agree_on_what_a_minute_costs():
    """If the brief budgeted at 150 wpm and the gate checked at 145, a draft could satisfy the
    instruction and fail the check — the pipeline would be arguing with itself."""
    from nolan.scriptwriter import gate
    assert tasks._REVISE_WPM == gate._WPM


def test_the_revise_brief_demands_recomputed_timecodes(store):
    """One revise pass rewrote every beat and left all six timecodes at [0:00], and declared 8:00
    for 10:24 of narration. Both are now checked deterministically, so the brief must ask."""
    slug, st = store
    brief = tasks.revise_task(slug, st, unattended=True)
    assert "Recompute" in brief and "strictly increasing" in brief
    assert "145 wpm" in brief
