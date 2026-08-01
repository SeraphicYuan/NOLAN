"""Deterministic pedagogy heuristics for review and acceptance gating."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

from pydantic import Field

from math_animation.contracts import (
    AxesVisualObject,
    EquationRevealBlock,
    EquationTransformBlock,
    FunctionGraphVisualObject,
    MathTexVisualObject,
    NumberLineBlock,
    ProjectSpec,
    StrictModel,
    TextVisualObject,
    TransformMathAction,
    WordAnchor,
)
from math_animation.math_validation import validate_math
from math_animation.repair import analyze_project
from math_animation.timing import resolve_beats


PedagogyDimension = Literal[
    "mathematical_grounding",
    "objective_alignment",
    "progressive_disclosure",
    "pacing",
    "cognitive_load",
    "narration_sync",
    "legibility",
]


class PedagogyFinding(StrictModel):
    id: str
    dimension: PedagogyDimension
    severity: Literal["info", "warning", "error"]
    message: str
    beat_id: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    suggested_action: str | None = None


class PedagogyDimensionScore(StrictModel):
    dimension: PedagogyDimension
    score: float = Field(ge=0, le=1)
    weight: float = Field(gt=0, le=1)
    beat_scores: dict[str, float] = Field(default_factory=dict)


class PedagogyReport(StrictModel):
    schema_version: Literal["math-animation.pedagogy-report.v1"] = (
        "math-animation.pedagogy-report.v1"
    )
    status: Literal["passed", "needs_review", "failed"]
    total_score: float = Field(ge=0, le=1)
    dimensions: list[PedagogyDimensionScore]
    findings: list[PedagogyFinding] = Field(default_factory=list)
    evaluator_id: str = "deterministic-pedagogy-v1"
    limitations: list[str] = Field(
        default_factory=lambda: [
            "This rubric detects structural teaching risks; it does not prove "
            "that a learner will understand the explanation.",
            "Semantic alignment is keyword- and contract-based, not a human "
            "expert judgment.",
        ]
    )


_WEIGHTS: dict[PedagogyDimension, float] = {
    "mathematical_grounding": 0.12,
    "objective_alignment": 0.2,
    "progressive_disclosure": 0.16,
    "pacing": 0.14,
    "cognitive_load": 0.16,
    "narration_sync": 0.12,
    "legibility": 0.1,
}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _visual_facts(beat) -> dict[str, Any]:
    block_types = [block.type for block in beat.blocks]
    program = beat.scene_program
    objects = program.objects if program is not None else []
    cues = program.cues if program is not None else []
    return {
        "block_types": block_types,
        "math_count": sum(
            isinstance(item, MathTexVisualObject) for item in objects
        )
        + sum(
            isinstance(block, (EquationRevealBlock, EquationTransformBlock))
            for block in beat.blocks
        ),
        "graph_count": sum(
            isinstance(item, (AxesVisualObject, FunctionGraphVisualObject))
            for item in objects
        )
        + sum(block.type == "function_plot" for block in beat.blocks),
        "number_line": any(
            isinstance(block, NumberLineBlock) for block in beat.blocks
        ),
        "transform_count": sum(
            isinstance(block, EquationTransformBlock) for block in beat.blocks
        )
        + sum(
            isinstance(action, TransformMathAction)
            for cue in cues
            for action in cue.actions
        ),
        "object_count": len(objects),
        "cue_count": len(cues),
        "max_parallel_actions": max(
            (
                len(cue.actions) if cue.mode == "parallel" else 1
                for cue in cues
            ),
            default=1,
        ),
        "text_characters": sum(
            len(item.text)
            for item in objects
            if isinstance(item, TextVisualObject)
        )
        + sum(
            len(value)
            for block in beat.blocks
            for value in (
                getattr(block, "title", None),
                getattr(block, "subtitle", None),
                getattr(block, "caption", None),
            )
            if value
        ),
    }


def _alignment_score(text: str, facts: dict[str, Any]) -> tuple[float, str | None]:
    lowered = text.lower()
    if any(word in lowered for word in ("graph", "plot", "curve")):
        return (
            (1.0, None)
            if facts["graph_count"]
            else (0.25, "The objective mentions a graph but no graph is shown.")
        )
    if "number line" in lowered:
        return (
            (1.0, None)
            if facts["number_line"]
            else (0.25, "The objective mentions a number line but none is shown.")
        )
    if any(word in lowered for word in ("compare", "contrast", "versus")):
        return (
            (1.0, None)
            if facts["math_count"] >= 2
            else (0.45, "The comparison objective lacks two visible math objects.")
        )
    if any(
        word in lowered
        for word in ("derive", "step", "simplify", "transform", "rewrite")
    ):
        return (
            (1.0, None)
            if facts["transform_count"] >= 1
            else (0.5, "The procedural objective has no visible transformation.")
        )
    if any(word in lowered for word in ("equation", "formula", "identity")):
        return (
            (1.0, None)
            if facts["math_count"] >= 1
            else (0.4, "The objective names symbolic math but no formula is shown.")
        )
    return 0.82, None


def evaluate_pedagogy(project: ProjectSpec) -> PedagogyReport:
    """Score structural teaching quality without making learner-outcome claims."""

    findings: list[PedagogyFinding] = []
    scores: dict[PedagogyDimension, dict[str, float]] = defaultdict(dict)
    math_report = validate_math(project)
    grounding = {
        "passed": 1.0,
        "needs_review": 0.78,
        "failed": 0.0,
    }[math_report.status]
    if math_report.status != "passed":
        findings.append(
            PedagogyFinding(
                id="grounding.math-review",
                dimension="mathematical_grounding",
                severity=(
                    "error" if math_report.status == "failed" else "warning"
                ),
                message=(
                    "Mathematical claims or formulas require review before "
                    "pedagogical acceptance."
                ),
                evidence={
                    "warnings": math_report.warnings,
                    "errors": math_report.errors,
                },
                suggested_action="Verify the math ledger independently.",
            )
        )

    diagnostics = analyze_project(project)
    diagnostic_by_beat: dict[str, list] = defaultdict(list)
    for diagnostic in diagnostics:
        if diagnostic.beat_id:
            diagnostic_by_beat[diagnostic.beat_id].append(diagnostic)

    for resolved in resolve_beats(project):
        beat = resolved.beat
        beat_id = beat.id
        facts = _visual_facts(beat)
        scores["mathematical_grounding"][beat_id] = grounding

        utterance_text = (
            resolved.utterance.text if resolved.utterance is not None else ""
        )
        alignment, alignment_message = _alignment_score(
            " ".join(
                [beat.title, beat.learning_objective, utterance_text]
            ),
            facts,
        )
        scores["objective_alignment"][beat_id] = alignment
        if alignment_message:
            findings.append(
                PedagogyFinding(
                    id=f"{beat_id}.alignment",
                    dimension="objective_alignment",
                    severity="warning",
                    beat_id=beat_id,
                    message=alignment_message,
                    evidence=facts,
                    suggested_action=(
                        "Choose a template that directly represents the "
                        "learning objective."
                    ),
                )
            )

        if facts["transform_count"] >= 2:
            progressive = 1.0
        elif facts["transform_count"] == 1:
            progressive = 0.9
        elif facts["math_count"] >= 2:
            progressive = 0.84
        elif facts["math_count"] == 1:
            progressive = 0.75
        elif facts["cue_count"] >= 2:
            progressive = 0.72
        else:
            progressive = 0.58
        scores["progressive_disclosure"][beat_id] = progressive
        if progressive < 0.65:
            findings.append(
                PedagogyFinding(
                    id=f"{beat_id}.progressive",
                    dimension="progressive_disclosure",
                    severity="warning",
                    beat_id=beat_id,
                    message=(
                        "The beat presents one static idea without staged "
                        "disclosure."
                    ),
                    suggested_action=(
                        "Introduce or transform the central representation in "
                        "two or more meaningful stages."
                    ),
                )
            )

        if beat.scene_program is not None:
            active = sum(cue.duration_seconds for cue in beat.scene_program.cues)
        else:
            active = sum(block.run_time for block in beat.blocks)
        active_ratio = active / resolved.duration_seconds
        if 0.25 <= active_ratio <= 0.78:
            pacing = 1.0
        elif 0.15 <= active_ratio <= 0.9:
            pacing = 0.78
        else:
            pacing = 0.45
        scores["pacing"][beat_id] = pacing
        if pacing < 0.7:
            findings.append(
                PedagogyFinding(
                    id=f"{beat_id}.pacing",
                    dimension="pacing",
                    severity="warning",
                    beat_id=beat_id,
                    message="Visual action is poorly balanced against beat duration.",
                    evidence={
                        "active_seconds": active,
                        "duration_seconds": resolved.duration_seconds,
                        "active_fraction": active_ratio,
                    },
                    suggested_action=(
                        "Reserve time for both visual change and a stable "
                        "inspection hold."
                    ),
                )
            )

        load = 1.0
        load -= max(0, facts["object_count"] - 6) * 0.06
        load -= max(0, facts["max_parallel_actions"] - 4) * 0.08
        load -= max(0, facts["text_characters"] - 150) / 600
        load = _clamp(load)
        scores["cognitive_load"][beat_id] = load
        if load < 0.7:
            findings.append(
                PedagogyFinding(
                    id=f"{beat_id}.load",
                    dimension="cognitive_load",
                    severity="warning",
                    beat_id=beat_id,
                    message="The beat risks excessive simultaneous visual load.",
                    evidence=facts,
                    suggested_action=(
                        "Split the beat or reveal fewer objects concurrently."
                    ),
                )
            )

        if resolved.utterance is None:
            sync = 0.58
        elif resolved.utterance.words:
            aligned_duration = (
                resolved.utterance.words[-1].end_seconds
                - resolved.utterance.words[0].start_seconds
            )
            error = abs(resolved.duration_seconds - aligned_duration)
            word_anchored = any(
                isinstance(cue.start_at, WordAnchor)
                for cue in (
                    beat.scene_program.cues
                    if beat.scene_program is not None
                    else []
                )
            ) or any(
                isinstance(block.start_at, WordAnchor)
                for block in beat.blocks
            )
            if error <= 1 / project.render.frame_rate:
                # Exact beat alignment is strong evidence, but full credit
                # requires at least one semantically authored word anchor.
                sync = 1.0 if word_anchored else 0.88
            else:
                sync = 0.72 if word_anchored else 0.68
        else:
            sync = 0.76
        scores["narration_sync"][beat_id] = sync
        if sync < 0.7:
            findings.append(
                PedagogyFinding(
                    id=f"{beat_id}.sync",
                    dimension="narration_sync",
                    severity="warning",
                    beat_id=beat_id,
                    message="The beat has no word-aligned narration evidence.",
                    suggested_action="Attach Nolan word timestamps before final acceptance.",
                )
            )

        relevant = [
            item
            for item in diagnostic_by_beat.get(beat_id, [])
            if item.code
            in {"text_overflow", "illegible_type", "excessive_density"}
        ]
        legibility = _clamp(
            1.0
            - sum(
                0.5 if item.severity in {"error", "refusal"} else 0.2
                for item in relevant
            )
        )
        scores["legibility"][beat_id] = legibility
        for diagnostic in relevant:
            findings.append(
                PedagogyFinding(
                    id=f"{beat_id}.legibility.{diagnostic.id}",
                    dimension="legibility",
                    severity=(
                        "error"
                        if diagnostic.severity in {"error", "refusal"}
                        else "warning"
                    ),
                    beat_id=beat_id,
                    message=diagnostic.message,
                    evidence=diagnostic.evidence,
                    suggested_action=(
                        "Apply the corresponding typed layout repair."
                    ),
                )
            )

    dimensions: list[PedagogyDimensionScore] = []
    total = 0.0
    for dimension, weight in _WEIGHTS.items():
        beat_scores = scores[dimension]
        score = (
            sum(beat_scores.values()) / len(beat_scores)
            if beat_scores
            else 0.0
        )
        dimensions.append(
            PedagogyDimensionScore(
                dimension=dimension,
                score=score,
                weight=weight,
                beat_scores=beat_scores,
            )
        )
        total += score * weight
    total = _clamp(total)
    has_error = any(item.severity == "error" for item in findings)
    status: Literal["passed", "needs_review", "failed"]
    if has_error or total < 0.6:
        status = "failed"
    elif total < 0.78 or findings:
        status = "needs_review"
    else:
        status = "passed"
    return PedagogyReport(
        status=status,
        total_score=total,
        dimensions=dimensions,
        findings=findings,
    )
