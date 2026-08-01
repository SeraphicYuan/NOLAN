"""Grounded provider decisions for typed beat regeneration."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field

from math_animation.bundle import sha256_json
from math_animation.contracts import (
    EquationRevealBlock,
    EquationTransformBlock,
    MathTexVisualObject,
    ProjectSpec,
    StrictModel,
    TransformMathAction,
)
from math_animation.planning import (
    PlanningBeatContext,
    VisualDecision,
    VisualDecisionProvider,
    allowed_templates,
    validate_visual_decision,
)
from math_animation.repair import (
    Diagnostic,
    RegenerateBeatOperation,
    RepairPlan,
)


class RegenerationArtifact(StrictModel):
    schema_version: Literal["math-animation.regeneration.v1"] = (
        "math-animation.regeneration.v1"
    )
    source_project_sha256: str
    reason_diagnostic_id: str
    beat_id: str
    provider_id: str
    context: PlanningBeatContext
    allowed_templates: list[str]
    selected_formula_ids: list[str] = Field(default_factory=list)
    decision: VisualDecision
    decision_sha256: str


def _source_text(project: ProjectSpec, beat_id: str) -> str:
    beat = next(item for item in project.beats if item.id == beat_id)
    utterances = {
        utterance.id: utterance for utterance in project.narration.utterances
    }
    if beat.narration_utterance_id in utterances:
        return utterances[beat.narration_utterance_id].text
    return beat.title


def _referenced_formula_ids(project: ProjectSpec, beat_id: str) -> list[str]:
    beat = next(item for item in project.beats if item.id == beat_id)
    referenced: list[str] = []
    for block in beat.blocks:
        if isinstance(block, EquationRevealBlock) and block.formula_id:
            referenced.append(block.formula_id)
        elif isinstance(block, EquationTransformBlock):
            for parts in (block.from_latex, block.to_latex):
                match = next(
                    (
                        formula.id
                        for formula in project.math_ledger.formulas
                        if formula.latex_parts == parts
                    ),
                    None,
                )
                if match:
                    referenced.append(match)
    if beat.scene_program is not None:
        for item in beat.scene_program.objects:
            if isinstance(item, MathTexVisualObject) and item.formula_id:
                referenced.append(item.formula_id)
        for cue in beat.scene_program.cues:
            for action in cue.actions:
                if isinstance(action, TransformMathAction) and action.formula_id:
                    referenced.append(action.formula_id)
    return list(dict.fromkeys(referenced))


def _candidate_formula_ids(project: ProjectSpec, beat_id: str) -> list[str]:
    referenced = _referenced_formula_ids(project, beat_id)
    if referenced:
        return referenced[:2]
    beat = next(item for item in project.beats if item.id == beat_id)
    source = _source_text(project, beat_id)
    generic = {
        "a",
        "an",
        "and",
        "authored",
        "clearly",
        "equation",
        "formula",
        "show",
        "the",
        "this",
    }
    terms = (
        set(re.findall(r"[a-z0-9]+", f"{beat.title} {source}".lower()))
        - generic
    )
    ranked = sorted(
        project.math_ledger.formulas,
        key=lambda formula: (
            -len(
                terms
                & set(
                    re.findall(
                        r"[a-z0-9]+",
                        f"{formula.id} {formula.plain_language}".lower(),
                    )
                )
            ),
            formula.id,
        ),
    )
    # Do not expose an unrelated global formula merely because one exists.
    return [
        formula.id
        for formula in ranked
        if terms
        & set(
            re.findall(
                r"[a-z0-9]+",
                f"{formula.id} {formula.plain_language}".lower(),
            )
        )
    ][:2]


def regeneration_context(
    project: ProjectSpec,
    beat_id: str,
    diagnostics: list[Diagnostic],
) -> tuple[PlanningBeatContext, list[str]]:
    beat = next(item for item in project.beats if item.id == beat_id)
    formula_ids = _candidate_formula_ids(project, beat.id)
    formulas = {
        formula.id: formula for formula in project.math_ledger.formulas
    }
    previous = (
        [block.type for block in beat.blocks]
        if beat.blocks
        else ["scene_program"]
    )
    codes = list(
        dict.fromkeys(
            diagnostic.code
            for diagnostic in diagnostics
            if diagnostic.beat_id == beat.id
        )
    )
    return (
        PlanningBeatContext(
            beat_index=next(
                index
                for index, candidate in enumerate(project.beats)
                if candidate.id == beat.id
            ),
            text=_source_text(project, beat.id),
            formulas=[
                " ".join(formulas[formula_id].latex_parts)
                for formula_id in formula_ids
            ],
            diagnostic_codes=codes,
            previous_templates=previous,
        ),
        formula_ids,
    )


def generate_regeneration_artifacts(
    project: ProjectSpec,
    plan: RepairPlan,
    diagnostics: list[Diagnostic],
    provider: VisualDecisionProvider,
) -> list[RegenerationArtifact]:
    artifacts: list[RegenerationArtifact] = []
    for operation in plan.operations:
        if not isinstance(operation, RegenerateBeatOperation):
            continue
        context, formula_ids = regeneration_context(
            project,
            operation.beat_id,
            diagnostics,
        )
        allowed = allowed_templates(context)
        if sorted(allowed) != sorted(operation.allowed_templates):
            raise ValueError(
                "regeneration plan allowed templates do not match grounded "
                "beat inputs"
            )
        decision = validate_visual_decision(
            context,
            provider.decide(context),
        )
        selected_formula_ids: list[str] = []
        if decision.template == "equation_reveal":
            selected_formula_ids = formula_ids[:1]
        elif decision.template == "equation_transform":
            selected_formula_ids = formula_ids[:2]
        artifacts.append(
            RegenerationArtifact(
                source_project_sha256=sha256_json(project),
                reason_diagnostic_id=operation.reason_diagnostic_id,
                beat_id=operation.beat_id,
                provider_id=provider.provider_id,
                context=context,
                allowed_templates=allowed,
                selected_formula_ids=selected_formula_ids,
                decision=decision,
                decision_sha256=sha256_json(decision),
            )
        )
    return artifacts
