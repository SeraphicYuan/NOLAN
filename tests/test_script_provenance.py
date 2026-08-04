"""Provenance, and the comparability guard it exists to power.

The incident: the same draft judged twice scored 17 and 99 — 5.8x, zero high findings versus six.
Explaining that took an hour of git archaeology, and the cause was partly that the two runs used
different output contracts and thirteen days of prompt changes sat between them. `findings.json`
records what was found and nothing about the instrument, so two numbers that cannot be compared
look exactly like two that can.
"""

import json

import pytest

from nolan.scriptwriter import ScriptProjectStore, provenance, tasks


@pytest.fixture()
def store(tmp_path):
    slug = "probe-project"
    sg = tmp_path / slug / "scriptgen"
    (sg / "drafts").mkdir(parents=True)
    (sg / "reviews").mkdir(parents=True)
    (sg / "drafts" / "draft-01.md").write_text(
        "# Video Script\n\n**Total Duration:** 8:00\n\n## A beat [0:00]\n\nWords here.\n",
        encoding="utf-8")
    for n in ("brief.md", "facts.md", "beatmap.md", "citations.md", "factcheck.md", "angles.md"):
        (sg / n).write_text("x\n", encoding="utf-8")
    (sg / "meta.json").write_text(json.dumps({
        "slug": slug, "name": "Probe", "subject": "s",
        "style_id": "channel-great-books-explained", "target_minutes": 8.0,
        "mode": "auto", "sources": [], "review_archetype": "long-form-argument",
        "composite_spine": {"structure": "chronological"}}), encoding="utf-8")
    return slug, ScriptProjectStore(tmp_path)


def _prov(store_t, **kw):
    slug, st = store_t
    brief = kw.pop("brief", None) or tasks.review_task(slug, st, unattended=True)
    return provenance.judge_provenance(slug, st, brief=brief, draft_n=1,
                                       unattended=kw.pop("unattended", True), **kw)


def test_the_code_records_the_instrument_not_the_agents_word(store):
    """Asking an agent to report its own prompt version is asking the instrument to describe
    itself. Everything checkable is captured from the objects that produced it."""
    p = _prov(store)
    for field in ("brief_sha256", "rubric_sha256", "rubric_dims", "archetype", "contract",
                  "nolan_commit", "style_id", "spine", "target_minutes", "created_at"):
        assert field in p, f"provenance must record {field}"
    assert len(p["brief_sha256"]) == 64
    assert p["archetype"] == "long-form-argument"
    assert p["spine"] == "chronological"
    # Only these two come from the agent, and their ABSENCE is recorded rather than guessed.
    assert p["model"] is None and p["session"] is None


def test_a_changed_brief_changes_the_hash(store):
    """THE FIELD THAT MATTERS. Any reworded dimension, different output contract or new
    constraint moves this — which is exactly the change that silently invalidated the Phase 2
    comparison."""
    slug, st = store
    attended = provenance.judge_provenance(
        slug, st, brief=tasks.review_task(slug, st, unattended=False), draft_n=1,
        unattended=False)
    unattended = _prov(store)
    assert attended["brief_sha256"] != unattended["brief_sha256"]
    assert attended["contract"] == "attended" and unattended["contract"] == "unattended"


def test_comparable_refuses_across_instruments(store):
    """Scores from different instruments are not two measurements of a draft — they are one
    measurement each of two different questions."""
    a = _prov(store)
    b = dict(a, brief_sha256="deadbeef" * 8)
    ok, why = provenance.comparable(a, b)
    assert not ok and "brief" in why

    c = dict(a, contract="attended")
    ok, why = provenance.comparable(a, c)
    assert not ok and "contract" in why

    ok, why = provenance.comparable(a, dict(a))
    assert ok and "same instrument" in why


def test_missing_provenance_is_never_comparable(store):
    """A pre-provenance findings file is exactly the case that caused the incident. Treating
    absence as 'probably fine' would reintroduce it."""
    a = _prov(store)
    for other in (None, {}):
        ok, why = provenance.comparable(a, other)
        assert not ok and "no provenance" in why


def test_a_moved_repo_warns_but_does_not_refuse(store):
    """Weaker signal than the brief hash — most of the repo cannot affect a judgement — so it
    reports rather than blocks, and says what moved."""
    a = _prov(store)
    b = dict(a, nolan_commit="0000000")
    ok, why = provenance.comparable(a, b)
    assert ok and "repo moved" in why


def test_the_review_brief_asks_for_only_the_two_agent_fields(store):
    """The agent is asked for `model` and `session` and nothing else — restating what the code
    already knows would invite a confident wrong answer."""
    slug, st = store
    for unattended in (True, False):
        brief = tasks.review_task(slug, st, unattended=unattended)
        assert "provenance.json" in brief
        assert '"model"' in brief and '"session"' in brief
        assert "Leave every other field exactly as you found it" in brief


def test_provenance_round_trips_to_disk(store):
    slug, st = store
    p = _prov(store)
    provenance.write_provenance(st, slug, 1, p)
    back = provenance.read_provenance(st, slug, 1)
    assert back == p
    assert provenance.provenance_path(st, slug, 1).name == "review-01.provenance.json"
