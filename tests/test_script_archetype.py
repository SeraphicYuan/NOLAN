"""Which rubric grades a draft, and why that must not be decided by the channel's name.

Measured on this repo: **7 of the 14 projects with no explicit archetype** had their rubric chosen
by their style slug rather than their subject, because `channel-great-books-explained` contains
the word "explained".

The cost was concrete. A Homer essay whose central move is rebutting the claim that the poems are
a forgery was graded as an `explainer` — and the explainer rubric has no `steelman-present`
dimension, so the one critique that essay most needed had nowhere to be filed. The judge raised it
anyway under `evidential-sufficiency`, which is the rubric leaking.
"""

import json

import pytest

from nolan.scriptwriter import ScriptProjectStore
from nolan.scriptwriter.rubrics import get_rubric, infer_archetype


def _meta(**kw):
    base = {"slug": "p", "name": "P", "subject": "", "description": "",
            "style_id": "", "target_minutes": 8.0}
    base.update(kw)
    return base


def test_the_style_slug_cannot_choose_the_rubric():
    """THE BUG. `style_id` names the VOICE, not the content — reading it is a category error,
    and the same essay in a different style would be graded against a different rubric."""
    hijacked = _meta(subject="The De Beers diamond cartel and manufactured scarcity",
                     style_id="channel-great-books-explained")
    assert infer_archetype(hijacked) != "explainer", (
        "an essay about a cartel is not an explainer because its CHANNEL is called 'explained'")

    # and the same subject is unaffected by which style renders it
    a = infer_archetype(_meta(subject="the history of the Roman empire", style_id="channel-x"))
    b = infer_archetype(_meta(subject="the history of the Roman empire",
                              style_id="channel-great-books-explained"))
    assert a == b == "narrative-history"


def test_subject_still_drives_the_inference():
    assert infer_archetype(_meta(subject="how a jet engine works")) == "explainer"
    assert infer_archetype(_meta(subject="the case for a wealth tax")) == "long-form-argument"
    assert infer_archetype(_meta(subject="the life of Ada Lovelace")) == "biography"
    assert infer_archetype(_meta(subject="the fall of Constantinople")) == "narrative-history"


def test_an_argument_essay_gets_the_steelman_dimension():
    """The dimension the Homer draft needed and could not be given."""
    arch = infer_archetype(_meta(subject="the truth about the diamond market"))
    dims = [d.id for d in get_rubric(arch).review_dimensions()]
    assert "steelman-present" in dims and "number-integrity" in dims


@pytest.fixture()
def store(tmp_path):
    slug = "p"
    sg = tmp_path / slug / "scriptgen"
    sg.mkdir(parents=True)
    (sg / "meta.json").write_text(json.dumps(_meta(
        slug=slug, subject="the case for nuclear power",
        style_id="channel-great-books-explained")), encoding="utf-8")
    return slug, ScriptProjectStore(tmp_path)


def test_an_inferred_archetype_is_pinned_so_it_cannot_re_derive(store):
    """A guess remade on every read is a moving target: editing the keyword list would silently
    re-grade every past project against a different rubric."""
    slug, st = store
    first = st.resolve_archetype(slug, pin=True)
    assert first == "long-form-argument"
    assert st.get(slug)["inferred_archetype"] == first

    # the heuristic now "changes" — the pinned decision must survive it
    import nolan.scriptwriter.rubrics as R
    orig = R.infer_archetype
    try:
        R.infer_archetype = lambda _m: "biography"
        assert st.resolve_archetype(slug) == first, "a pinned archetype must not re-derive"
    finally:
        R.infer_archetype = orig


def test_reading_without_pin_does_not_write(store):
    slug, st = store
    st.resolve_archetype(slug)
    assert not (st.get(slug).get("inferred_archetype")), "a plain read must not mutate meta"


def test_the_human_override_outranks_a_pin(store):
    slug, st = store
    st.resolve_archetype(slug, pin=True)
    meta = st.get(slug)
    meta["review_archetype"] = "narrative-history"
    st._save_meta(meta)
    assert st.resolve_archetype(slug) == "narrative-history"
