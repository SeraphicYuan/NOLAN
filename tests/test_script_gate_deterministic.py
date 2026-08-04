"""The checks that must never reach a language model.

Both were found by a live loop and missed entirely by the LLM judge that reviewed the same draft:
a revise pass rewrote every beat and left all six timecodes at `[0:00]`, and declared `8:00` for a
script carrying 10:24 of narration. Neither is a matter of taste, both are arithmetic, and a
judge's attention spent on them is attention not spent on the prose.
"""

import pytest

from nolan.scriptwriter import gate

HEAD = "# Video Script\n\n**Total Duration:** {dur}\n\n"


def _script(beats, dur="8:00", words=40):
    body = "".join(f"## Beat {i} [{tc}]\n\n{'word ' * words}\n\n" for i, tc in enumerate(beats, 1))
    return HEAD.format(dur=dur) + body


def _check(rep, cid):
    return next((c for c in rep.checks if c.id == cid), None)


def test_collapsed_timecodes_fail():
    """THE REGRESSION. A revise pass rewrote every beat and left all six at [0:00]; the judge
    that reviewed that draft did not mention it once."""
    rep = gate.gate_text(_script(["0:00"] * 6))
    c = _check(rep, "timecodes")
    assert c and c.level == "fail" and "share one timecode" in c.message


def test_timecodes_must_increase():
    rep = gate.gate_text(_script(["0:00", "1:30", "1:10"]))
    c = _check(rep, "timecodes")
    assert c and c.level == "fail" and "not increasing" in c.message


def test_unparseable_timecodes_are_named():
    rep = gate.gate_text("# Video Script\n\n**Total Duration:** 8:00\n\n"
                         "## First beat\n\nwords here\n\n## Second beat [1:00]\n\nmore words\n")
    c = _check(rep, "timecodes")
    assert c and c.level == "fail" and "no parseable" in c.message


def test_good_timecodes_pass():
    rep = gate.gate_text(_script(["0:00", "1:30", "3:05", "4:45"]))
    c = _check(rep, "timecodes")
    assert c and c.level == "pass" and "strictly increasing" in c.message


def test_declared_duration_is_checked_against_the_words():
    """`**Total Duration:**` is whatever the writer typed, and on both real drafts it was wrong —
    8:20 declared for 9:04 of words, then 8:00 for 10:24. A script that overruns is a video that
    overruns, because narration owns duration."""
    # 1,500 words at 145 wpm is 10:20 (620s) against a declared 8:00 (480s) — 29% out.
    rep = gate.gate_text(_script(["0:00", "4:00"], dur="8:00", words=750))
    c = _check(rep, "declared-duration")
    assert c and c.level == "fail"
    assert "declared 8:00" in c.message and "10:20" in c.message and "29% out" in c.message

    # an honest declaration passes
    rep = gate.gate_text(_script(["0:00", "4:00"], dur="10:20", words=750))
    c = _check(rep, "declared-duration")
    assert c and c.level == "pass"


def test_a_missing_declaration_warns_rather_than_passing_silently():
    rep = gate.gate_text("## A beat [0:00]\n\n" + "word " * 300)
    c = _check(rep, "declared-duration")
    assert c and c.level == "warn"


def test_the_new_checks_do_not_pile_on_an_unparseable_draft():
    """When `format` has already failed there are no beats to judge; a second failure about
    timecodes would be noise about the same defect."""
    rep = gate.gate_text("this is not a script at all")
    assert _check(rep, "format").level == "fail"
    assert _check(rep, "timecodes") is None


def test_a_missing_draft_raises_instead_of_reporting_fail(tmp_path):
    """`or ""` gated the empty string and reported `format: fail — missing header, 0 beats`,
    which reads as a judgement about the draft. A mistyped name therefore produced a confident
    wrong answer instead of a complaint."""
    import json

    from nolan.scriptwriter import ScriptProjectStore

    slug = "p"
    sg = tmp_path / slug / "scriptgen"
    (sg / "drafts").mkdir(parents=True)
    (sg / "drafts" / "draft-01.md").write_text(_script(["0:00", "1:00"]), encoding="utf-8")
    (sg / "meta.json").write_text(json.dumps({"slug": slug, "name": "p", "subject": "s",
                                              "style_id": "x", "target_minutes": 8.0}),
                                  encoding="utf-8")
    store = ScriptProjectStore(tmp_path)

    with pytest.raises(FileNotFoundError, match="draft-01'"):
        gate.run_gate(slug, store=store, draft_name="draft-01")     # the .md is not optional
    rep = gate.run_gate(slug, store=store, draft_name="draft-01.md")
    assert _check(rep, "format").level == "pass"
