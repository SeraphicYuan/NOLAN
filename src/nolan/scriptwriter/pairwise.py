"""The judge, asked a question it can actually answer: **did this get better?**

WHY THE OLD QUESTION WAS WRONG, and it is not a subtle failure. Draft-02 of a real essay was
better than draft-01 in six specific, checkable ways — it replaced a bare assertion ("Complexity
is not fraud") with the real evidence (the poem is in a language nobody ever spoke, dialects and
centuries layered together, and *a forger at a desk leaves no layers*), swapped an analogy the
audience had no relationship with for one it did, cut a line the channel had already used in
another script, showed Penelope's shroud instead of asserting her fidelity with two numbers, and
repaired a contradiction where the hook called Homer's blindness doubtful and the close asserted
it flatly.

It scored **worse**: 99 → 117 weighted, 6 → 8 high-severity findings.

The mechanism is not noise and not a bad judge. **Asking "list everything wrong" makes vagueness
win.** "Complexity is not fraud" is unfalsifiable and offers a critic nothing to grip; the layered-
language argument invites "which dialects, dated how?" A draft earns criticism by being
substantive, so any metric built on counting findings is pointed backwards — it would have stopped
a run that was working.

So this pass never counts. It reads BOTH drafts in ONE sitting and answers three questions:

  1. **which is better**, and by how much — a judgement, made once, on both texts together
  2. **what the revision broke** — regressions are the expensive failure and the one a
     finding-list buries among twenty other items
  3. **what still blocks shipping** — a short list, severity-ranked, capped

A comparison inside one context also needs no cross-session calibration, which is the other thing
that made absolute scores unusable: the same draft judged by two sessions scored 17 and 99.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:                                  # pragma: no cover
    from .store import ScriptProjectStore

# How many blockers the judge may return. A cap is not tidiness — it is what stops this becoming
# the thing it replaced. Twenty-three findings applied at once is a rewrite, not surgery, and
# produced the regression that motivated all of this.
MAX_BLOCKERS = 6

# The verdict vocabulary. Deliberately coarse: a judge asked for a 0-100 score will invent
# precision it does not have, and the loop only ever needs to know which way to go.
VERDICTS = ("better", "worse", "mixed", "same")


def pairwise_task(slug: str, store: "ScriptProjectStore", unattended: bool = True) -> str:
    """Brief for a COMPARATIVE judgement of draft N against draft N-1.

    Falls back to an absolute read on the first draft, where there is nothing to compare against —
    stated in the brief rather than silently producing a comparison with an imaginary predecessor.
    """
    from .rubrics import get_rubric, render_review_md
    from .tasks import _narration_words, project_paths

    meta = store.get(slug)
    _, sg = project_paths(slug, store)
    style_id = meta["style_id"]
    archetype = store.resolve_archetype(slug, pin=True)
    rubric = get_rubric(archetype)
    rubric_md = render_review_md(rubric, meta.get("ad_hoc_questions") or [])

    num, path = store.current_draft(slug)
    if not num:
        return (f"# NOLAN pairwise REVIEW — \"{meta['name']}\"\n\n"
                "No draft exists yet. Draft first.\n")

    cur_words = _narration_words(path.read_text(encoding="utf-8"))
    target_words = int(float(meta.get("target_minutes") or 8.0) * 145)
    out_rel = f"{sg}/reviews/review-{num:02d}.pairwise.json"
    prov_rel = f"{sg}/reviews/review-{num:02d}.provenance.json"

    prev = store.draft_path(slug, f"draft-{num - 1:02d}.md") if num > 1 else None
    if prev is None:
        compare_block = (
            f"## There is no previous draft\n"
            f"`draft-{num:02d}` is the first, so there is nothing to compare it against. Set "
            f'`"verdict": "same"` and `"vs_draft": null`, and spend your effort on **blockers** —'
            f" what would stop this shipping as it stands.")
    else:
        prev_words = _narration_words(prev.read_text(encoding="utf-8"))
        compare_block = (
            f"## Read BOTH, in this order\n"
            f"- **previous:** `{sg}/drafts/{prev.name}` ({prev_words} narration words)\n"
            f"- **current:**  `{sg}/drafts/{path.name}` ({cur_words} narration words)\n\n"
            f"Read the previous draft first, then the current one. You are judging the CHANGE, "
            f"not auditing the current draft in isolation.")

    return f"""# NOLAN pairwise REVIEW: "{meta['name']}"

Judge whether `draft-{num:02d}` is **better than** the draft before it — and what still blocks it.

**You are not writing a list of everything wrong.** A draft that argues earns more criticism than
one that asserts, so a long list is not evidence of a bad draft and a short one is not evidence of
a good one. Reward the version that is stronger to read, even when it exposes more surface to
criticise.

{compare_block}

## Context (the same material the writer had)
- **Brief:** `{sg}/brief.md`   · **Beatmap:** `{sg}/beatmap.md`
- **Facts:** `{sg}/facts.md`   · **Citations:** `{sg}/citations.md`
- **Style guide (voice):** `script_styles/{style_id}/style_guide.md`
- **Length target:** ~{target_words} narration words; the current draft is {cur_words}.

## What to weigh — rubric `{archetype}`
{rubric_md}

## Output → `{out_rel}` (a single JSON object)
```json
{{
  "verdict": "better|worse|mixed|same",
  "vs_draft": "draft-{num - 1:02d}",
  "confidence": "high|med|low",
  "why": "<2-4 sentences: the decisive reason, naming what changed>",
  "gains":      [{{"beat": "<name>", "what": "<what improved, quote the change>"}}],
  "regressions":[{{"beat": "<name>", "what": "<what got worse>", "severity": "high|med|low"}}],
  "blockers":   [{{"beat": "<name>", "dim": "<rubric dim-id>", "severity": "high|med|low",
                   "quote": "<exact phrase>", "problem": "<one line>", "fix": "<concrete change>"}}]
}}
```

Rules that decide whether this is useful:
- **`blockers` is capped at {MAX_BLOCKERS}** — the things that would genuinely stop you shipping,
  strongest first. Not everything you noticed. A pass that returns twenty items produces a
  revision that rewrites the script, and a rewrite is how the last one got worse.
- **`regressions` is the highest-value field.** Something the revision broke is worth more than
  anything it merely failed to improve, and it is the one thing an isolated read cannot see.
- **`verdict` is about the CHANGE.** "worse" means the previous draft was better to read — say so
  plainly; that verdict is allowed and acting on it is cheap.
- Quote the draft. A critique that cannot be located cannot be applied.
- Do **not** count anything. No scores, no totals, no "N issues found".

## Provenance — add your two fields to `{prov_rel}`
That file already exists and records the brief, rubric, archetype and commit. Fill in ONLY
`"model"` (the model you are running as) and `"session"` (your agent name). Leave everything else
exactly as you found it.

## FINAL STEP — signal completion
After `{out_rel}` is written, create `{sg}/.runs/pairwise-{num:02d}.done` containing one line
naming your verdict. The pipeline waits on this file.

STOP after that. Do not touch any draft.
"""
