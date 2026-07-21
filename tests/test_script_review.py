"""Phase-1 tests for the script review→revise loop (docs/SCRIPT_REVIEW_PROGRAM.md).

Honesty tests (docs claim, tests enforce):
- context-parity: the review inputs are a superset of the draft inputs, and every input
  actually appears in the rendered review brief;
- gate coverage: a gate run reports exactly the declared doors;
- rubric integrity: every archetype resolves and keeps the four core (base) questions.
Plus behavioral tests for the store's draft numbering and the gate's checks.
"""

import json

import pytest

from nolan.scriptwriter import ScriptProjectStore, review_task, revise_task
from nolan.scriptwriter.tasks import _DRAFT_INPUTS, _REVIEW_INPUTS
from nolan.scriptwriter import rubrics
from nolan.scriptwriter.gate import gate_text, SCRIPT_GATE_CHECKS


GOOD_SCRIPT = """# Video Script

**Total Duration:** 3:00

---

## The Hook [0:00 - 0:30]

Money moved fast and the world barely noticed the real cost of it all today.

## The Turn [0:30 - 1:00]

Then the tide changed and everyone felt the weight of what had quietly happened.
"""

FACTS_MD = """## Beat: The Hook
- money moved fast — src:[S1] · beat:hook

## Beat: The Turn
- the tide changed — src:[S1] · beat:turn
"""


# --------------------------------------------------------------------------
# Rubric registry
# --------------------------------------------------------------------------
def test_every_archetype_resolves_and_keeps_base_questions():
    base_ids = {d.id for d in rubrics.BASE_DIMENSIONS}
    for aid in rubrics.ARCHETYPES:
        rub = rubrics.get_rubric(aid)
        got = {d.id for d in rub.dimensions}
        # the four core producer questions (dims 1-4) must survive into every archetype
        for core in ("figurative-fitness", "voice-ownership", "example-strength",
                     "evidential-sufficiency"):
            assert core in got, f"{aid} dropped core dimension {core}"
        assert base_ids <= got, f"{aid} dropped a base dimension"


def test_dimension_reads_are_valid_tokens():
    rub = rubrics.get_rubric("long-form-argument")
    for d in rub.dimensions:
        for tok in d.reads:
            assert tok in rubrics.READ_TOKENS, f"{d.id} reads unknown token {tok}"


def test_review_and_revise_stage_split():
    rub = rubrics.get_rubric("general")
    assert [d.id for d in rub.revise_dimensions()] == ["final-coherence"]
    assert "final-coherence" not in {d.id for d in rub.review_dimensions()}
    # review dims come out strongest-first
    weights = [d.weight for d in rub.review_dimensions()]
    assert weights == sorted(weights, reverse=True)


def test_long_form_reweights_and_extends():
    rub = rubrics.get_rubric("long-form-argument")
    ev = next(d for d in rub.dimensions if d.id == "evidential-sufficiency")
    assert ev.weight == 5, "long-form must weight evidential density up"
    ids = {d.id for d in rub.dimensions}
    assert {"steelman-present", "number-integrity"} <= ids


def test_infer_archetype():
    assert rubrics.infer_archetype({"subject": "The AI debate and the economy",
                                    "target_minutes": 20}) == "long-form-argument"
    assert rubrics.infer_archetype({"subject": "How photosynthesis works",
                                    "target_minutes": 6}) == "explainer"
    assert rubrics.infer_archetype({"subject": "A quiet afternoon",
                                    "target_minutes": 5}) == "general"


# --------------------------------------------------------------------------
# Context parity (honesty)
# --------------------------------------------------------------------------
def test_review_inputs_superset_of_draft_inputs():
    assert set(_DRAFT_INPUTS) <= set(_REVIEW_INPUTS)
    assert "draft" in _REVIEW_INPUTS  # the one thing review adds beyond draft context


def test_review_brief_references_every_context_input(tmp_path):
    store = ScriptProjectStore(tmp_path)
    slug = store.create("Parity Test", subject="A long-form argument about the economy",
                        style_id="channel-x", target_minutes=20)
    store.script_path(slug).write_text(GOOD_SCRIPT, encoding="utf-8")  # gives a numbered draft
    brief = review_task(slug, store)
    # each declared input must be locatable in the brief so the critic reads the writer's context
    for needle in ("brief.md", "style_guide.md", "facts.md", "beatmap.md",
                   "citations.md", "factcheck.md", "drafts/draft-01.md"):
        assert needle in brief, f"review brief omits {needle}"
    # the typed rubric must be inlined
    assert "evidential-sufficiency" in brief and "archetype" in brief


# --------------------------------------------------------------------------
# Store: draft numbering + review artifacts
# --------------------------------------------------------------------------
def test_current_draft_seeds_from_script(tmp_path):
    store = ScriptProjectStore(tmp_path)
    slug = store.create("Seed", subject="x", style_id="s", target_minutes=8)
    # placeholder script → nothing to review yet
    assert store.current_draft(slug) == (0, None)
    store.script_path(slug).write_text(GOOD_SCRIPT, encoding="utf-8")
    num, path = store.current_draft(slug)
    assert num == 1 and path.name == "draft-01.md"
    assert store.next_draft_number(slug) == 2


def test_review_archetype_override_and_reviews_listing(tmp_path):
    store = ScriptProjectStore(tmp_path)
    slug = store.create("Arch", subject="A quiet story", style_id="s", target_minutes=6)
    assert store.resolve_archetype(slug) == "general"          # inferred
    store.set_review_archetype(slug, "narrative-history")
    assert store.resolve_archetype(slug) == "narrative-history"  # overridden
    assert store.list_reviews(slug) == []
    store.reviews_dir(slug).mkdir(parents=True, exist_ok=True)
    store.review_path(slug, 1).write_text("# review", encoding="utf-8")
    revs = store.list_reviews(slug)
    assert len(revs) == 1 and revs[0]["n"] == 1 and revs[0]["has_findings"] is False


def test_pipeline_state_machine_ticks_on_new_draft(tmp_path):
    store = ScriptProjectStore(tmp_path)
    slug = store.create("PS", subject="x", style_id="s", target_minutes=8)
    assert store.get(slug)["state"] == "new"                       # placeholder script only
    store.facts_path(slug).write_text("- a fact", encoding="utf-8")
    assert store.get(slug)["state"] == "grounded"
    store.angles_path(slug).write_text("## angle", encoding="utf-8")
    assert store.get(slug)["state"] == "angled"
    store.drafts_dir(slug).mkdir(parents=True, exist_ok=True)
    (store.drafts_dir(slug) / "draft-01.md").write_text("# Video Script\n## A [0:00]\nx\n", encoding="utf-8")
    assert store.get(slug)["state"] == "drafted"
    store.reviews_dir(slug).mkdir(parents=True, exist_ok=True)
    store.review_path(slug, 1).write_text("# review", encoding="utf-8")
    assert store.get(slug)["state"] == "reviewed"
    # THE FIX: draft-02 exists but the revision-01.md changelog has NOT been written yet
    (store.drafts_dir(slug) / "draft-02.md").write_text("# Video Script\n## A [0:00]\nx\n", encoding="utf-8")
    assert not store.revision_path(slug, 1).exists()
    assert store.get(slug)["state"] == "revised"                   # ticks on the new draft


def test_revise_targets_next_draft(tmp_path):
    store = ScriptProjectStore(tmp_path)
    slug = store.create("Rev", subject="x", style_id="s", target_minutes=8)
    store.script_path(slug).write_text(GOOD_SCRIPT, encoding="utf-8")
    brief = revise_task(slug, store)
    assert "draft-02.md" in brief and "review-01" in brief


# --------------------------------------------------------------------------
# Gate
# --------------------------------------------------------------------------
def test_verify_revision_flags_untouched_findings(tmp_path):
    store = ScriptProjectStore(tmp_path)
    slug = store.create("V", subject="x", style_id="s", target_minutes=8)
    store.drafts_dir(slug).mkdir(parents=True, exist_ok=True)
    (store.drafts_dir(slug) / "draft-01.md").write_text(
        "# Video Script\n## A [0:00]\nthe cryptic plough detail here stays or goes now.\n", encoding="utf-8")
    (store.drafts_dir(slug) / "draft-02.md").write_text(
        "# Video Script\n## A [0:00]\nclean prose without it now here today friends.\n", encoding="utf-8")
    store.reviews_dir(slug).mkdir(parents=True, exist_ok=True)
    approved = [
        {"id": "f1", "dim": "example-strength", "quote": "the cryptic plough detail here stays"},  # cut
        {"id": "f2", "dim": "figurative-fitness", "quote": "clean prose without it now here today"},  # present in new
    ]
    store.review_approved_path(slug, 1).write_text(json.dumps(approved), encoding="utf-8")
    from nolan.scriptwriter.gate import verify_revision
    v = verify_revision(store, slug, 1)
    assert v["new_draft_exists"] and v["approved"] == 2 and v["checkable"] == 2
    assert v["changed"] == 1 and v["untouched"] == 1 and "f2" in v["untouched_ids"]


def test_create_with_presets(tmp_path):
    store = ScriptProjectStore(tmp_path)
    slug = store.create("P", subject="the economy debate", style_id="s", target_minutes=20,
                        angle="the confidence trick",
                        composite_spine={"structure": "braided", "threads": ["a", "b"], "binding": "x"},
                        review_archetype="long-form-argument",
                        ad_hoc_questions=["are metaphors strong?", "  "])
    m = store.get(slug)
    assert m["chosen_angle"] == "the confidence trick"          # a create-time angle IS the chosen one
    assert m["composite_spine"]["structure"] == "braided"
    assert m["review_archetype"] == "long-form-argument"
    assert m["ad_hoc_questions"] == ["are metaphors strong?"]   # blanks filtered
    assert store.resolve_archetype(slug) == "long-form-argument"
    # single/auto/empty presets, and invalid spine rejected
    s2 = store.create("Q", subject="x", style_id="s", composite_spine={"structure": "auto"})
    assert store.get(s2)["composite_spine"]["structure"] == "auto"
    with pytest.raises(ValueError):
        store.create("R", subject="x", style_id="s",
                     composite_spine={"structure": "braided", "threads": ["only one"]})


def test_set_target_minutes(tmp_path):
    store = ScriptProjectStore(tmp_path)
    slug = store.create("L", subject="x", style_id="s", target_minutes=8)
    store.set_target_minutes(slug, 20)
    assert store.get(slug)["target_minutes"] == 20.0
    assert store.target_words(slug) == 3000            # 20 * 150, flows into the gate
    with pytest.raises(ValueError):
        store.set_target_minutes(slug, 0)
    with pytest.raises(ValueError):
        store.set_target_minutes(slug, "abc")


def test_angle_candidates_parse(tmp_path):
    store = ScriptProjectStore(tmp_path)
    slug = store.create("A", subject="x", style_id="s", target_minutes=8)
    store.angles_path(slug).write_text(
        "# Candidate angles\n### Angle 1 — The first thesis **[CHOSEN]**\nbody one\n"
        "### Angle 2 — The second thesis\nbody two\n", encoding="utf-8")
    c = store.angle_candidates(slug)
    assert len(c) == 2
    assert c[0]["n"] == 1 and c[0]["chosen"] and "first thesis" in c[0]["title"].lower()
    assert c[1]["n"] == 2 and not c[1]["chosen"]
    assert "chosen" not in c[0]["title"].lower()          # the [CHOSEN] marker is stripped


def test_gate_reports_every_declared_door():
    rep = gate_text(GOOD_SCRIPT, facts_md=FACTS_MD, target_words=30)
    assert {c.id for c in rep.checks} == set(SCRIPT_GATE_CHECKS)


def test_gate_passes_a_well_formed_grounded_draft():
    rep = gate_text(GOOD_SCRIPT, facts_md=FACTS_MD, target_words=30)
    levels = {c.id: c.level for c in rep.checks}
    assert rep.ok
    assert levels["format"] == "pass"
    assert levels["beat-grounding"] == "pass"
    assert levels["needs-check"] == "pass"
    assert levels["word-count"] == "pass"


def test_gate_fails_malformed_script():
    rep = gate_text("just some prose with no headings at all", target_words=100)
    assert not rep.ok
    assert any(c.id == "format" and c.level == "fail" for c in rep.checks)


def test_gate_fails_on_needs_check_leak():
    leaked = GOOD_SCRIPT + "\n## Extra [1:00 - 1:30]\n\nThis is huge [needs-check] and certain.\n"
    rep = gate_text(leaked, facts_md=FACTS_MD, target_words=30)
    assert any(c.id == "needs-check" and c.level == "fail" for c in rep.checks)
    assert not rep.ok


def test_gate_flags_dropped_beat_between_drafts():
    prev = GOOD_SCRIPT
    new = """# Video Script

**Total Duration:** 1:30

---

## The Hook [0:00 - 0:30]

Money moved fast and the world barely noticed the real cost of it all today.
"""
    rep = gate_text(new, facts_md=FACTS_MD, target_words=15, prev_draft_text=prev)
    cont = next(c for c in rep.checks if c.id == "beat-continuity")
    assert cont.level == "warn" and "turn" in cont.message.lower()


def test_gate_wordcount_warns_when_far_off_target():
    rep = gate_text(GOOD_SCRIPT, facts_md=FACTS_MD, target_words=3000)
    wc = next(c for c in rep.checks if c.id == "word-count")
    assert wc.level == "warn"


def test_gate_grounds_beats_from_beatmap_covers():
    """Authoritative per-beat source map is beatmap covers — grounding works even when
    facts.md is grouped by function (not by the script's beat titles)."""
    beatmap = ("## Braided beat list\n"
               "## The Hook · pace:d · covers:[S1] · serves-spine:opens cold\n"
               "## The Turn · pace:a · covers:[S1,S2] · serves-spine:escalates\n")
    function_facts = "## hook\n- money moved fast — src:[S1]\n## turn\n- the tide changed — src:[S1]\n"
    rep = gate_text(GOOD_SCRIPT, facts_md=function_facts, beatmap_md=beatmap, target_words=30)
    bg = next(c for c in rep.checks if c.id == "beat-grounding")
    assert bg.level == "pass" and "trace to a source" in bg.message


def test_gate_grounding_partial_match_defers_to_corpus():
    """A beatmap that matches only SOME script beats (fuzzy, <80%) must not false-warn about
    the unmatched ones — it defers to the corpus signal instead."""
    script = """# Video Script

**Total Duration:** 2:00

---

## Alpha [0:00]

One two three four five six seven eight nine ten words here now today.

## Beta [0:20]

Another line of prose that is reasonably long and carries real narration here.

## Gamma [0:40]

A third beat with its own distinct wording and no beatmap title overlap at all.

## Delta [1:00]

Yet a fourth beat whose beatmap counterpart was re-worded past recognition here.

## Epsilon [1:20]

Fifth beat prose continuing on with more words to fill the narration space now.
"""
    # beatmap only clearly matches "Alpha" (1/5 = 20% < 80%) → must NOT per-beat-warn
    beatmap = "## Alpha · pace:d · covers:[S1] · serves:x\n## Zeta · covers:[S2]\n"
    facts = "\n".join(f"- fact {i} — src:[S1]" for i in range(8))
    rep = gate_text(script, facts_md=facts, beatmap_md=beatmap, target_words=50)
    bg = next(c for c in rep.checks if c.id == "beat-grounding")
    assert bg.level == "pass" and "source-backed facts" in bg.message


def test_gate_grounding_corpus_fallback_not_false_warn():
    """Function-grouped facts + no usable beatmap → corpus signal, not a false 'ungrounded'."""
    function_facts = ("## hook\n- a — src:[S1]\n- b — src:[S2]\n"
                      "## turn\n- c — src:[S3]\n- d — src:[S4]\n")
    rep = gate_text(GOOD_SCRIPT, facts_md=function_facts, target_words=30)
    bg = next(c for c in rep.checks if c.id == "beat-grounding")
    assert bg.level == "pass" and "source-backed facts" in bg.message
