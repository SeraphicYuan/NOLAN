"""Expanded typed templates and pedagogy-aware visual decisions."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol

from pydantic import Field, model_validator

from math_animation.bundle import sha256_json
from math_animation.contracts import (
    ActionCue,
    BeatSpec,
    CreateAction,
    FormulaSpec,
    MathClaim,
    MathLedger,
    MathTexVisualObject,
    NarrationInput,
    ProjectSpec,
    RequestSpec,
    ResponsiveVisualOverride,
    SceneProgram,
    StrictModel,
    TextVisualObject,
    TransformMathAction,
    UtteranceTiming,
)
from math_animation.planning import (
    HeuristicDecisionProvider,
    PlanningBeatContext,
    PlanningRequest,
    TemplateName,
    VisualDecision,
    _duration,
    _extract_formulas,
    _paragraphs,
    _short_title,
    allowed_templates,
    make_visual_block,
    objective_for_decision,
    validate_visual_decision,
)


TeachingStrategy = Literal[
    "conceptual",
    "procedural",
    "comparison",
    "misconception_first",
]
ExpandedTemplateName = Literal[
    "title_card",
    "equation_reveal",
    "equation_transform",
    "function_plot",
    "secant_to_tangent",
    "number_line",
    "equation_sequence",
    "concept_comparison",
]


class PedagogicalIntent(StrictModel):
    learning_goal: str
    teaching_strategy: TeachingStrategy = "conceptual"
    misconception_to_address: str | None = None
    cognitive_load: Literal["low", "moderate"] = "moderate"


class PacingProfile(StrictModel):
    action_fraction: float = Field(default=0.65, ge=0.3, le=0.85)
    final_hold_fraction: float = Field(default=0.2, ge=0.05, le=0.5)

    @model_validator(mode="after")
    def reserves_transition_time(self) -> "PacingProfile":
        if self.action_fraction + self.final_hold_fraction > 0.95:
            raise ValueError(
                "pacing must reserve at least five percent for transitions"
            )
        return self


class BasicTemplatePlan(StrictModel):
    template: Literal[
        "title_card",
        "equation_reveal",
        "equation_transform",
        "function_plot",
        "secant_to_tangent",
        "number_line",
    ]
    formula_indices: list[int] = Field(default_factory=list)
    expression: str | None = None
    values: list[float] = Field(default_factory=list)
    caption_policy: Literal["none", "beat_title"] = "beat_title"
    pacing: PacingProfile = Field(default_factory=PacingProfile)


class EquationSequencePlan(StrictModel):
    template: Literal["equation_sequence"] = "equation_sequence"
    formula_indices: list[int] = Field(min_length=3, max_length=6)
    pacing: PacingProfile = Field(default_factory=PacingProfile)

    @model_validator(mode="after")
    def formulas_are_unique(self) -> "EquationSequencePlan":
        if len(self.formula_indices) != len(set(self.formula_indices)):
            raise ValueError("equation sequence formula indices must be unique")
        return self


class ConceptComparisonPlan(StrictModel):
    template: Literal["concept_comparison"] = "concept_comparison"
    left_formula_index: int = Field(ge=0)
    right_formula_index: int = Field(ge=0)
    left_label: str | None = Field(default=None, max_length=32)
    right_label: str | None = Field(default=None, max_length=32)
    pacing: PacingProfile = Field(default_factory=PacingProfile)

    @model_validator(mode="after")
    def formulas_are_distinct(self) -> "ConceptComparisonPlan":
        if self.left_formula_index == self.right_formula_index:
            raise ValueError("comparison requires two distinct formulas")
        return self


ExpandedTemplatePlan = Annotated[
    BasicTemplatePlan | EquationSequencePlan | ConceptComparisonPlan,
    Field(discriminator="template"),
]


class ExpandedVisualDecision(StrictModel):
    schema_version: Literal["math-animation.visual-decision.v2"] = (
        "math-animation.visual-decision.v2"
    )
    rationale: str
    confidence: float = Field(ge=0, le=1)
    pedagogy: PedagogicalIntent
    plan: ExpandedTemplatePlan
    unsupported_intents: list[str] = Field(default_factory=list)


class ExpandedPlannedBeatArtifact(StrictModel):
    beat_id: str
    source_text: str
    selected_template: ExpandedTemplateName
    teaching_strategy: TeachingStrategy
    learning_goal: str
    rationale: str
    confidence: float = Field(ge=0, le=1)
    formula_ids: list[str] = Field(default_factory=list)


class ExpandedPlanningArtifact(StrictModel):
    schema_version: Literal["math-animation.expanded-planning.v1"] = (
        "math-animation.expanded-planning.v1"
    )
    planner_id: str
    request_sha256: str
    project_sha256: str
    beats: list[ExpandedPlannedBeatArtifact]
    template_counts: dict[str, int]
    custom_python_requests: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ExpandedPlanningResult:
    artifact: ExpandedPlanningArtifact
    project: ProjectSpec


class ExpandedDecisionProvider(Protocol):
    provider_id: str

    def decide(self, context: PlanningBeatContext) -> ExpandedVisualDecision:
        ...


def allowed_expanded_templates(
    context: PlanningBeatContext,
) -> list[ExpandedTemplateName]:
    """Return expanded templates whose authored inputs are available."""

    allowed: list[ExpandedTemplateName] = list(
        # The v1 helper remains the authority for existing template inputs.
        allowed_templates(context)
    )
    if len(context.formulas) >= 3:
        allowed.append("equation_sequence")
    if len(context.formulas) >= 2:
        allowed.append("concept_comparison")
    return allowed


def _intent(
    text: str,
    *,
    strategy: TeachingStrategy,
) -> PedagogicalIntent:
    return PedagogicalIntent(
        learning_goal=_short_title(text),
        teaching_strategy=strategy,
        cognitive_load="moderate",
    )


class HeuristicExpandedDecisionProvider:
    """Deterministic expanded-template baseline."""

    provider_id = "heuristic-expanded-v1"

    def __init__(self):
        self._basic = HeuristicDecisionProvider()

    def decide(self, context: PlanningBeatContext) -> ExpandedVisualDecision:
        lowered = context.text.lower()
        if len(context.formulas) >= 3 and any(
            word in lowered
            for word in ("step", "sequence", "derive", "then", "simplify")
        ):
            return ExpandedVisualDecision(
                rationale=(
                    "Three or more authored formulas and sequential language "
                    "match progressive equation disclosure."
                ),
                confidence=0.95,
                pedagogy=_intent(context.text, strategy="procedural"),
                plan=EquationSequencePlan(
                    formula_indices=list(range(min(6, len(context.formulas))))
                ),
            )
        if len(context.formulas) >= 2 and any(
            word in lowered
            for word in ("compare", "contrast", "versus", "difference")
        ):
            if "standard form" in lowered and "vertex form" in lowered:
                left_label, right_label = "Standard form", "Vertex form"
            elif "before" in lowered and "after" in lowered:
                left_label, right_label = "Before", "After"
            else:
                left_label, right_label = "First form", "Second form"
            return ExpandedVisualDecision(
                rationale=(
                    "Two authored formulas and comparison language match the "
                    "responsive comparison template."
                ),
                confidence=0.94,
                pedagogy=_intent(context.text, strategy="comparison"),
                plan=ConceptComparisonPlan(
                    left_formula_index=0,
                    right_formula_index=1,
                    left_label=left_label,
                    right_label=right_label,
                ),
            )
        basic = self._basic.decide(context)
        formula_indices: list[int] = []
        if basic.template == "equation_reveal":
            formula_indices = [0]
        elif basic.template == "equation_transform":
            formula_indices = [0, 1]
        return ExpandedVisualDecision(
            rationale=basic.rationale,
            confidence=basic.confidence,
            pedagogy=_intent(context.text, strategy="conceptual"),
            plan=BasicTemplatePlan(
                template=basic.template,
                formula_indices=formula_indices,
                expression=basic.expression,
                values=basic.values,
            ),
            unsupported_intents=basic.unsupported_intents,
        )


def validate_expanded_decision(
    context: PlanningBeatContext,
    decision: ExpandedVisualDecision,
) -> ExpandedVisualDecision:
    plan = decision.plan
    if isinstance(plan, BasicTemplatePlan):
        expected_count = {
            "equation_reveal": 1,
            "equation_transform": 2,
        }.get(plan.template, 0)
        if len(plan.formula_indices) != expected_count:
            raise ValueError(
                f"{plan.template} requires {expected_count} formula indices"
            )
        if any(
            index < 0 or index >= len(context.formulas)
            for index in plan.formula_indices
        ):
            raise ValueError("basic template formula index is outside the source")
        validate_visual_decision(
            context,
            VisualDecision(
                template=plan.template,
                rationale=decision.rationale,
                confidence=decision.confidence,
                expression=plan.expression,
                values=plan.values,
                unsupported_intents=decision.unsupported_intents,
            ),
        )
    elif isinstance(plan, EquationSequencePlan):
        if any(
            index < 0 or index >= len(context.formulas)
            for index in plan.formula_indices
        ):
            raise ValueError(
                "equation sequence formula index is outside the source"
            )
    elif isinstance(plan, ConceptComparisonPlan):
        if (
            plan.left_formula_index >= len(context.formulas)
            or plan.right_formula_index >= len(context.formulas)
        ):
            raise ValueError("comparison formula index is outside the source")
    if plan.template not in allowed_expanded_templates(context):
        raise ValueError(
            f"provider selected {plan.template!r}, but authored inputs only "
            f"allow {allowed_expanded_templates(context)!r}"
        )
    return decision


def _scene_for_sequence(
    *,
    beat_id: str,
    duration: float,
    plan: EquationSequencePlan,
    formulas: list[str],
    formula_ids: list[str],
) -> SceneProgram:
    indices = plan.formula_indices
    action_count = len(indices)
    run_time = max(
        0.25,
        min(0.8, duration * plan.pacing.action_fraction / action_count),
    )
    formula = MathTexVisualObject(
        id=f"{beat_id}.sequence.formula",
        formula_id=formula_ids[indices[0]],
        latex_parts=[formulas[indices[0]]],
        font_size=76,
        max_width=8.5,
    )
    cues = [
        ActionCue(
            id=f"{beat_id}.sequence.show",
            actions=[
                CreateAction(
                    target=formula.id,
                    animation="write",
                    run_time=run_time,
                )
            ],
        )
    ]
    for step, formula_index in enumerate(indices[1:], start=1):
        cues.append(
            ActionCue(
                id=f"{beat_id}.sequence.step-{step:02d}",
                actions=[
                    TransformMathAction(
                        target=formula.id,
                        formula_id=formula_ids[formula_index],
                        latex_parts=[formulas[formula_index]],
                        run_time=run_time,
                    )
                ],
            )
        )
    return SceneProgram(objects=[formula], cues=cues)


def _scene_for_comparison(
    *,
    beat_id: str,
    duration: float,
    plan: ConceptComparisonPlan,
    formulas: list[str],
    formula_ids: list[str],
) -> SceneProgram:
    indices = [plan.left_formula_index, plan.right_formula_index]
    objects = [
        MathTexVisualObject(
            id=f"{beat_id}.comparison.left",
            formula_id=formula_ids[indices[0]],
            latex_parts=[formulas[indices[0]]],
            position=(-3.4, 0.0, 0.0),
            font_size=68,
            max_width=5.0,
            responsive={
                "portrait": ResponsiveVisualOverride(
                    position=(0.0, 1.2, 0.0)
                )
            },
        ),
        MathTexVisualObject(
            id=f"{beat_id}.comparison.right",
            formula_id=formula_ids[indices[1]],
            latex_parts=[formulas[indices[1]]],
            position=(3.4, 0.0, 0.0),
            font_size=68,
            max_width=5.0,
            responsive={
                "portrait": ResponsiveVisualOverride(
                    position=(0.0, -1.2, 0.0)
                )
            },
        ),
    ]
    for side, label, x_position, y_position in (
        ("left", plan.left_label, -3.4, -0.9),
        ("right", plan.right_label, 3.4, -0.9),
    ):
        if label:
            objects.append(
                TextVisualObject(
                    id=f"{beat_id}.comparison.{side}.label",
                    text=label,
                    position=(x_position, y_position, 0.0),
                    font_size=28,
                    responsive={
                        "portrait": ResponsiveVisualOverride(
                            position=(
                                0.0,
                                0.55 if side == "left" else -1.85,
                                0.0,
                            )
                        )
                    },
                )
            )
    run_time = max(
        0.3,
        min(1.0, duration * plan.pacing.action_fraction),
    )
    return SceneProgram(
        objects=objects,
        cues=[
            ActionCue(
                id=f"{beat_id}.comparison.show",
                mode="parallel",
                actions=[
                    CreateAction(
                        target=item.id,
                        animation="write",
                        run_time=run_time,
                    )
                    for item in objects
                ],
            )
        ],
    )


# Public aliases. The two builders above own the proven geometry, responsive
# overrides and pacing for these templates. NOLAN's adapter authors the same
# scenes from LaTeX the agent wrote rather than from script formula indices, and
# reaching for a private name across a package boundary is how two copies of one
# layout start drifting. Same functions, supported spelling.
scene_for_sequence = _scene_for_sequence
scene_for_comparison = _scene_for_comparison


class ExpandedPlanner:
    """Plan scripts with common multi-step pedagogical templates."""

    def __init__(self, provider: ExpandedDecisionProvider | None = None):
        self.provider = provider or HeuristicExpandedDecisionProvider()

    def plan(self, request: PlanningRequest) -> ExpandedPlanningResult:
        paragraphs = _paragraphs(request.script)
        supplied = request.narration.utterances
        if supplied and len(supplied) != len(paragraphs):
            raise ValueError(
                "narration utterance count must match script paragraph count"
            )
        utterances = (
            supplied
            if supplied
            else [
                UtteranceTiming(
                    id=f"utterance-{index:03d}",
                    text=paragraph,
                )
                for index, paragraph in enumerate(paragraphs, start=1)
            ]
        )
        beats: list[BeatSpec] = []
        ledger_formulas: list[FormulaSpec] = []
        claims: list[MathClaim] = []
        artifacts: list[ExpandedPlannedBeatArtifact] = []
        for index, (paragraph, utterance) in enumerate(
            zip(paragraphs, utterances, strict=True),
            start=1,
        ):
            beat_id = f"beat-{index:03d}"
            formulas = _extract_formulas(paragraph)
            formula_ids: list[str] = []
            for formula_index, formula in enumerate(formulas, start=1):
                formula_id = f"formula.{index:03d}.{formula_index:02d}"
                formula_ids.append(formula_id)
                ledger_formulas.append(
                    FormulaSpec(
                        id=formula_id,
                        latex_parts=[formula],
                        plain_language=_short_title(paragraph),
                    )
                )
                claims.append(
                    MathClaim(
                        id=f"claim.{index:03d}.{formula_index:02d}",
                        statement=f"The authored script asserts ${formula}$.",
                        verification="assumed",
                        evidence=[f"script beat {index}"],
                    )
                )
            context = PlanningBeatContext(
                beat_index=index - 1,
                text=paragraph,
                formulas=formulas,
            )
            decision = validate_expanded_decision(
                context,
                self.provider.decide(context),
            )
            duration = _duration(utterance, paragraph)
            if isinstance(decision.plan, EquationSequencePlan):
                beat = BeatSpec(
                    id=beat_id,
                    title=_short_title(paragraph),
                    learning_objective=decision.pedagogy.learning_goal,
                    narration_utterance_id=utterance.id,
                    duration_seconds=duration,
                    scene_program=_scene_for_sequence(
                        beat_id=beat_id,
                        duration=duration,
                        plan=decision.plan,
                        formulas=formulas,
                        formula_ids=formula_ids,
                    ),
                )
            elif isinstance(decision.plan, ConceptComparisonPlan):
                beat = BeatSpec(
                    id=beat_id,
                    title=_short_title(paragraph),
                    learning_objective=decision.pedagogy.learning_goal,
                    narration_utterance_id=utterance.id,
                    duration_seconds=duration,
                    scene_program=_scene_for_comparison(
                        beat_id=beat_id,
                        duration=duration,
                        plan=decision.plan,
                        formulas=formulas,
                        formula_ids=formula_ids,
                    ),
                )
            else:
                basic = decision.plan
                selected_formulas = [
                    formulas[item] for item in basic.formula_indices
                ]
                selected_ids = [
                    formula_ids[item] for item in basic.formula_indices
                ]
                visual_decision = VisualDecision(
                    template=basic.template,
                    rationale=decision.rationale,
                    confidence=decision.confidence,
                    expression=basic.expression,
                    values=basic.values,
                    unsupported_intents=decision.unsupported_intents,
                )
                block = make_visual_block(
                    visual_decision,
                    beat_id=beat_id,
                    text=paragraph,
                    formulas=(
                        selected_formulas
                        if selected_formulas
                        else formulas
                    ),
                    formula_ids=(
                        selected_ids if selected_ids else formula_ids
                    ),
                    duration=duration,
                )
                beat = BeatSpec(
                    id=beat_id,
                    title=_short_title(paragraph),
                    learning_objective=(
                        decision.pedagogy.learning_goal
                        or objective_for_decision(visual_decision)
                    ),
                    narration_utterance_id=utterance.id,
                    duration_seconds=duration,
                    blocks=[block],
                )
            beats.append(beat)
            artifacts.append(
                ExpandedPlannedBeatArtifact(
                    beat_id=beat_id,
                    source_text=paragraph,
                    selected_template=decision.plan.template,
                    teaching_strategy=decision.pedagogy.teaching_strategy,
                    learning_goal=decision.pedagogy.learning_goal,
                    rationale=decision.rationale,
                    confidence=decision.confidence,
                    formula_ids=formula_ids,
                )
            )
        narration = request.narration.model_copy(
            update={"utterances": utterances}
        )
        project = ProjectSpec(
            project_id=request.project_id,
            title=request.title,
            request=RequestSpec(
                source_kind="script",
                content=request.script,
                audience=request.audience,
                script_policy="review",
                target_duration_seconds=sum(
                    beat.duration_seconds or 0.0 for beat in beats
                ),
            ),
            math_ledger=MathLedger(
                claims=claims,
                formulas=ledger_formulas,
            ),
            narration=narration,
            style=request.style,
            assets=request.assets,
            beats=beats,
            render=request.render,
        )
        counts = Counter(item.selected_template for item in artifacts)
        artifact = ExpandedPlanningArtifact(
            planner_id=self.provider.provider_id,
            request_sha256=sha256_json(request),
            project_sha256=sha256_json(project),
            beats=artifacts,
            template_counts=dict(sorted(counts.items())),
        )
        return ExpandedPlanningResult(artifact=artifact, project=project)
