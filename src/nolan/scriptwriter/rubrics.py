"""Review-rubric registry — the typed questions a fresh-eyes critic asks of a draft.

This is the ``review_rubrics`` registry from ``docs/SCRIPT_REVIEW_PROGRAM.md`` (§2, §4).
A rubric is a list of **dimensions**; each dimension is one located critique instruction
with a ``when_to_use``, the artifacts it ``reads``, a ``weight`` (emphasis), and a
``stage`` — ``review`` dimensions run in the diagnose-only critic pass, the single
``revise`` dimension (the final coherence read) runs in the revision pass.

The **base rubric** (7 dimensions) applies to every script. **Archetypes** layer on
top: they re-weight base dimensions and add specialised ones (e.g. a long-form business
argument weights evidential density up and adds steelman + number-integrity checks).
The archetype is *inferred* by default from the project meta and *overridable* by the
human — mirroring how the spine-type is already inferred from the style guide.

Honesty: ``tests/test_script_review.py`` pins that every dimension's ``reads`` are real
artifact tokens, that ``get_rubric`` resolves each seeded archetype, and that the base
dimensions survive into every archetype (a rubric can't silently drop the human's
four core questions).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

# The artifact tokens a dimension may declare it reads. Kept in lockstep with the
# context the drafting step is given (see tasks.py _REVIEW_INPUTS) so the critic can
# never be asked to judge something on less context than the writer had.
READ_TOKENS = ("brief", "style", "facts", "beatmap", "draft", "citations", "factcheck")


@dataclass
class RubricDimension:
    id: str
    title: str
    question: str          # the actual instruction handed to the critic
    when_to_use: str
    reads: tuple           # subset of READ_TOKENS
    weight: int = 3        # 1..5 — emphasis / ordering in the rendered rubric
    stage: str = "review"  # "review" (diagnose) | "revise" (the closing coherence read)
    severity_hint: str = ""


# --------------------------------------------------------------------------
# Base rubric — dims 1..4 are the producer's four hand-questions, sharpened;
# 5..6 are the long-form failure modes those questions imply; 7 is the closing read.
# --------------------------------------------------------------------------
BASE_DIMENSIONS: List[RubricDimension] = [
    RubricDimension(
        id="figurative-fitness",
        title="Figurative fitness",
        question=(
            "Audit every metaphor, analogy, and allegory in the draft. For each, decide: "
            "is it EARNED (it clarifies or intensifies a real point), ACCURATE (it does not "
            "distort the fact it dramatizes), and LOAD-BEARING (the beat is weaker without it)? "
            "Flag any that is merely decorative, mixed/incoherent, clichéd, or that bends a fact "
            "for effect. For each weak one, either cut it or replace it with a stronger image "
            "drawn from the actual source material — never invent flourish that isn't grounded."
        ),
        when_to_use="Always. The first thing that separates a strong essay from a competent one.",
        reads=("draft", "facts"),
        weight=4,
    ),
    RubricDimension(
        id="voice-ownership",
        title="Voice ownership vs. attribution",
        question=(
            "By default we paraphrase and assert in our OWN analytical voice. The target for "
            "non-load-bearing attributions is ZERO — do NOT merely trim or reduce them; strip them "
            "out entirely. Name a source ONLY when (a) the person or institution is prominent enough "
            "that the name itself adds authority the argument needs, or (b) it is a first-person "
            "human quote whose exact wording must stay verbatim and in context. Everything else — "
            "'According to X…', 'As Y argues…', 'X points out…' — becomes our own claim, fact "
            "preserved, name removed. **A commentator's name appearing more than once or twice is "
            "itself a flag:** keep it on the ONE or two lines where the phrasing is genuinely theirs "
            "or the named authority IS the point, and strip it everywhere else. (Concretely: a pundit "
            "cited 4–5 times across the script should end at 0–2.) Conversely, flag any genuinely "
            "prominent authority or human quote we absorbed into our voice when it should be credited."
        ),
        when_to_use="Always. Over-attribution makes an essay read like a book report.",
        reads=("draft", "citations"),
        weight=4,
        severity_hint="A repeated non-load-bearing name is at least 'med', not 'low'.",
    ),
    RubricDimension(
        id="example-strength",
        title="Example strength",
        question=(
            "For each example the draft uses, ask: is this the CLEAREST, most CONCRETE instance of "
            "the point it serves? Flag examples that are weak, generic, confusing, off-target, or "
            "that make the listener work to see the connection. Replace each with a sharper, more "
            "vivid instance drawn from facts.md — or, if none exists there, research a stronger one "
            "and ground it."
        ),
        when_to_use="Always. Weak examples quietly drain a beat of its force.",
        reads=("draft", "facts"),
        weight=4,
    ),
    RubricDimension(
        id="evidential-sufficiency",
        title="Evidential sufficiency",
        question=(
            "For THIS video's type and length, does each beat carry ENOUGH well-chosen examples and "
            "specific detail to feel substantive — neither thin/asserted nor padded/repetitive? "
            "Identify beats that are under-supported (claims without a concrete anchor, numbers "
            "without context, turns without evidence). For each, research and insert well-sourced "
            "specifics IN THE RIGHT PLACE, and update facts.md + citations.md so every addition is "
            "grounded, not invented."
        ),
        when_to_use="Always; weight up for long, detail-dependent formats.",
        reads=("draft", "facts", "citations"),
        weight=4,
    ),
    RubricDimension(
        id="throughline-payoff",
        title="Through-line & payoff",
        question=(
            "Check the spine. Does every beat earn its place by serving the through-line? If the "
            "script carries more than one thread, do the threads actually BRAID into the declared "
            "macro-structure (chronological / hierarchical / …), or do they merely sit side by "
            "side? Verify the hook makes a promise and the body pays it off, and that any refrain "
            "or label recurs with purpose and lands at the close. Flag beats that wander, threads "
            "that don't connect, and promises left unpaid."
        ),
        when_to_use="Always. The composite-spine coherence check lives here.",
        reads=("draft", "beatmap"),
        weight=3,
    ),
    RubricDimension(
        id="retention-redundancy",
        title="Retention & redundancy",
        question=(
            "Read for drag. Flag any mid-script sag, any point made more than once, any sentence or "
            "beat that could be cut with no loss, and any refrain used so often it deadens. A long "
            "script earns its length only if every beat pulls. Propose specific cuts and tightenings."
        ),
        when_to_use="Always; weight up for anything over ~12 minutes.",
        reads=("draft",),
        weight=3,
    ),
    RubricDimension(
        id="final-coherence",
        title="Final coherence pass",
        question=(
            "This is the CLOSING pass, run AFTER the other fixes are applied. Read the whole script "
            "start to finish as one continuous piece: restore a consistent voice across patched "
            "sections, smooth every transition where an edit was made, remove any seam where new "
            "material was grafted in, and confirm the beat structure and total duration still hold. "
            "The goal is that a listener cannot tell where the revisions happened."
        ),
        when_to_use="Always, as the last thing the revision pass does.",
        reads=("draft",),
        weight=5,
        stage="revise",
    ),
]


@dataclass
class Archetype:
    id: str
    title: str
    when_to_use: str
    extra_dimensions: List[RubricDimension] = field(default_factory=list)
    reweight: Dict[str, int] = field(default_factory=dict)


ARCHETYPES: Dict[str, Archetype] = {
    "general": Archetype(
        id="general",
        title="General essay",
        when_to_use="Default when no stronger archetype is inferred.",
    ),
    "long-form-argument": Archetype(
        id="long-form-argument",
        title="Long-form argument (business / economics / debate)",
        when_to_use=(
            "A ~15min+ essay that advances a thesis with data and counter-argument — the AI-debate "
            "archetype. Detail-dependent; both-sides integrity matters."
        ),
        reweight={"evidential-sufficiency": 5, "retention-redundancy": 4},
        extra_dimensions=[
            RubricDimension(
                id="steelman-present",
                title="Genuine steelman",
                question=(
                    "The strongest counter-case must appear at FULL strength, in our own voice — "
                    "not strawmanned, rushed, or skipped. Verify the draft genuinely steelmans the "
                    "opposing view before it renders judgment, so the verdict reads as earned "
                    "judgment rather than cheerleading. Flag every place the counter-argument is "
                    "weakened or absent, and strengthen it."
                ),
                when_to_use="Any argumentative / both-sides essay.",
                reads=("draft", "facts"),
                weight=4,
            ),
            RubricDimension(
                id="number-integrity",
                title="Number integrity",
                question=(
                    "Every number, date, and quantitative claim must be traceable to citations.md "
                    "and appropriately HEDGED where it is an estimate or single-sourced. Flag any "
                    "figure stated with false precision or unearned certainty, any that can't be "
                    "traced, and any '[needs-check]' claim presented as settled fact. Soften or cut."
                ),
                when_to_use="Any data-heavy essay.",
                reads=("draft", "citations", "factcheck"),
                weight=4,
            ),
        ],
    ),
    "narrative-history": Archetype(
        id="narrative-history",
        title="Narrative history",
        when_to_use="A story-driven historical piece — chronology, character, scene.",
        reweight={"figurative-fitness": 5, "throughline-payoff": 4},
    ),
    "biography": Archetype(
        id="biography",
        title="Biography",
        when_to_use="A life told as an arc; character and turning points carry it.",
        reweight={"throughline-payoff": 5},
    ),
    "explainer": Archetype(
        id="explainer",
        title="Explainer",
        when_to_use="A how/what-is piece; clarity and example strength carry it.",
        reweight={"example-strength": 5, "evidential-sufficiency": 4},
    ),
}

DEFAULT_ARCHETYPE = "general"


@dataclass
class Rubric:
    archetype: str
    title: str
    dimensions: List[RubricDimension]

    def review_dimensions(self) -> List[RubricDimension]:
        """Diagnose-stage dimensions, strongest-weighted first (stable within a weight)."""
        dims = [d for d in self.dimensions if d.stage == "review"]
        return sorted(dims, key=lambda d: -d.weight)

    def revise_dimensions(self) -> List[RubricDimension]:
        return [d for d in self.dimensions if d.stage == "revise"]


def infer_archetype(meta: dict) -> str:
    """Best-effort default archetype from the project meta. Overridable by the human.

    Deterministic keyword + length heuristic — honest and cheap; the point is that the
    UI/CLI can override it, not that it's clever.
    """
    hay = " ".join(str(meta.get(k, "")) for k in ("subject", "style_id", "name", "description")).lower()
    try:
        mins = float(meta.get("target_minutes") or 8.0)
    except (TypeError, ValueError):
        mins = 8.0
    keywords = {
        "long-form-argument": ("debate", "argument", "econom", "business", "finance", "market",
                                "bubble", "policy", "the case for", "the truth about", "why "),
        "narrative-history": ("history", " war", "ancient", "empire", "story of", "the rise",
                              "dynasty", "revolution", "the fall"),
        "biography": ("life of", "biography", "who was", "the man who"),
        "explainer": ("how ", "explained", "what is", "guide to", " works", "science of"),
    }
    for arch, kws in keywords.items():
        if any(k in hay for k in kws):
            return arch
    return "long-form-argument" if mins >= 15 else DEFAULT_ARCHETYPE


def get_rubric(archetype_id: Optional[str]) -> Rubric:
    """Resolve a rubric: base dimensions (re-weighted) + the archetype's extra dimensions."""
    arch = ARCHETYPES.get((archetype_id or "").strip()) or ARCHETYPES[DEFAULT_ARCHETYPE]
    dims: Dict[str, RubricDimension] = {d.id: replace(d) for d in BASE_DIMENSIONS}
    for did, w in arch.reweight.items():
        if did in dims:
            dims[did] = replace(dims[did], weight=w)
    ordered = list(dims.values()) + [replace(d) for d in arch.extra_dimensions]
    return Rubric(archetype=arch.id, title=arch.title, dimensions=ordered)


# --------------------------------------------------------------------------
# Rendering — the rubric as markdown injected into the task briefs.
# --------------------------------------------------------------------------
def _render_dim(n: int, d: RubricDimension) -> str:
    reads = ", ".join(d.reads)
    return (f"### {n}. {d.title}  ·  `{d.id}`  ·  weight {d.weight}/5\n"
            f"_Reads: {reads}._\n\n{d.question}\n")


def render_review_md(rubric: Rubric, ad_hoc: Optional[List[str]] = None) -> str:
    """The rubric block for the diagnose-only critic pass (review_task)."""
    lines = [f"## Review rubric — archetype: **{rubric.archetype}** ({rubric.title})",
             "",
             "Work each dimension in order. For EACH finding, record: the beat it lives in, the "
             "exact phrase/line at issue, a severity (`high` / `med` / `low`), the problem, and a "
             "CONCRETE proposed fix. Diagnose only — do NOT edit the draft in this pass.", ""]
    for i, d in enumerate(rubric.review_dimensions(), 1):
        lines.append(_render_dim(i, d))
    ad_hoc = [q.strip() for q in (ad_hoc or []) if q.strip()]
    if ad_hoc:
        lines.append("### + Ad-hoc questions for THIS run")
        lines.append("_Producer-supplied; treat with the same rigor as the rubric above._\n")
        for q in ad_hoc:
            lines.append(f"- {q}")
        lines.append("")
    return "\n".join(lines)


def render_coherence_md(rubric: Rubric) -> str:
    """The closing-read instruction for the revision pass (revise_task)."""
    dims = rubric.revise_dimensions()
    if not dims:
        return ""
    return _render_dim(1, dims[0])
