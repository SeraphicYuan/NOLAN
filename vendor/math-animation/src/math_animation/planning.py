"""Provider-neutral constrained planning from script beats to typed visuals."""

from __future__ import annotations

import re
import math
from collections import Counter
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import Field, field_validator

from math_animation.bundle import sha256_json
from math_animation.contracts import (
    AssetRef,
    BeatSpec,
    EquationRevealBlock,
    EquationTransformBlock,
    FormulaSpec,
    FunctionPlotBlock,
    MathClaim,
    MathLedger,
    NarrationInput,
    NumberLineBlock,
    ProjectSpec,
    RenderSettings,
    RequestSpec,
    SecantToTangentBlock,
    StrictModel,
    StyleTemplateRef,
    TitleCardBlock,
    UtteranceTiming,
)
from math_animation.safety import normalize_math_expression


_INLINE_MATH = re.compile(r"\$(.+?)\$", flags=re.DOTALL)
_DISPLAY_MATH = re.compile(r"\\\[(.+?)\\\]", flags=re.DOTALL)
_BACKTICK = re.compile(r"`([^`]+)`")
_NUMBER = re.compile(r"(?<![A-Za-z])[-+]?(?:\d+(?:\.\d*)?|\.\d+)")

TemplateName = Literal[
    "title_card",
    "equation_reveal",
    "equation_transform",
    "function_plot",
    "secant_to_tangent",
    "number_line",
]


class PlanningRequest(StrictModel):
    project_id: str
    title: str
    script: str
    audience: str = "general"
    narration: NarrationInput = Field(default_factory=NarrationInput)
    style: StyleTemplateRef = Field(default_factory=StyleTemplateRef)
    assets: list[AssetRef] = Field(default_factory=list)
    render: RenderSettings = Field(default_factory=RenderSettings)

    @field_validator("script")
    @classmethod
    def script_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("script must not be blank")
        return value


class PlanningBeatContext(StrictModel):
    beat_index: int = Field(ge=0)
    text: str
    formulas: list[str] = Field(default_factory=list)
    diagnostic_codes: list[str] = Field(default_factory=list)
    previous_templates: list[str] = Field(default_factory=list)


class VisualDecision(StrictModel):
    template: TemplateName
    rationale: str
    confidence: float = Field(ge=0, le=1)
    expression: str | None = None
    values: list[float] = Field(default_factory=list)
    unsupported_intents: list[str] = Field(default_factory=list)


class PlannedBeatArtifact(StrictModel):
    beat_id: str
    source_text: str
    learning_objective: str
    selected_template: TemplateName
    rationale: str
    confidence: float = Field(ge=0, le=1)
    formula_ids: list[str] = Field(default_factory=list)
    unsupported_intents: list[str] = Field(default_factory=list)
    custom_python_requested: bool = False


class PlanningArtifact(StrictModel):
    schema_version: Literal["math-animation.planning.v1"] = (
        "math-animation.planning.v1"
    )
    planner_id: str
    request_sha256: str
    project_sha256: str
    beats: list[PlannedBeatArtifact]
    template_counts: dict[str, int]
    typed_template_ratio: float = Field(ge=0, le=1)
    custom_python_requests: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class PlanningResult:
    artifact: PlanningArtifact
    project: ProjectSpec


class VisualDecisionProvider(Protocol):
    provider_id: str

    def decide(self, context: PlanningBeatContext) -> VisualDecision:
        """Return a strict template decision; it cannot return Python source."""


def allowed_templates(context: PlanningBeatContext) -> list[TemplateName]:
    """Return only templates whose required authored inputs are available."""

    allowed: list[TemplateName] = ["title_card"]
    expression = _safe_expression(context.text)
    if context.formulas:
        allowed.append("equation_reveal")
    if len(context.formulas) >= 2:
        allowed.append("equation_transform")
    if expression is not None:
        allowed.extend(["function_plot", "secant_to_tangent"])
    if _NUMBER.search(context.text):
        allowed.append("number_line")
    return allowed


def validate_visual_decision(
    context: PlanningBeatContext,
    decision: VisualDecision,
) -> VisualDecision:
    """Enforce source grounding after every heuristic or model decision."""

    if decision.template == "equation_reveal" and not context.formulas:
        raise ValueError(
            "provider selected equation_reveal without authored formulas"
        )
    if decision.template == "equation_transform" and len(context.formulas) < 2:
        raise ValueError(
            "provider selected equation_transform without two authored formulas"
        )
    if decision.template in {"function_plot", "secant_to_tangent"}:
        if decision.expression is None:
            raise ValueError(
                f"provider selected {decision.template} without an expression"
            )
        normalized = normalize_math_expression(decision.expression)
        authored_expression = _safe_expression(context.text)
        if authored_expression is None or normalized != normalize_math_expression(
            authored_expression
        ):
            raise ValueError(
                "provider expression must exactly match an authored safe "
                "expression"
            )
    elif decision.expression is not None:
        raise ValueError(
            f"provider supplied an expression for {decision.template!r}"
        )
    if decision.template == "number_line":
        if not decision.values:
            raise ValueError(
                "provider selected number_line without numeric values"
            )
        authored_values = {float(value) for value in _NUMBER.findall(context.text)}
        if (
            not all(math.isfinite(value) for value in decision.values)
            or not set(decision.values).issubset(authored_values)
        ):
            raise ValueError(
                "provider number-line values must be finite authored values"
            )
    elif decision.values:
        raise ValueError(
            f"provider supplied number-line values for {decision.template!r}"
        )
    allowed = allowed_templates(context)
    if decision.template not in allowed:
        raise ValueError(
            f"provider selected {decision.template!r}, but authored inputs only "
            f"allow {allowed!r}"
        )
    return decision


def _paragraphs(script: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\n\s*\n", script) if part.strip()]
    return parts or [script.strip()]


def _short_title(text: str) -> str:
    without_math = _DISPLAY_MATH.sub("equation", _INLINE_MATH.sub("equation", text))
    sentence = re.split(r"(?<=[.!?])\s+", without_math, maxsplit=1)[0].strip()
    return sentence if len(sentence) <= 32 else sentence[:29].rstrip() + "..."


def _extract_formulas(text: str) -> list[str]:
    return [
        value.strip()
        for value in [
            *_INLINE_MATH.findall(text),
            *_DISPLAY_MATH.findall(text),
        ]
        if value.strip()
    ]


def _safe_expression(text: str) -> str | None:
    candidates = _BACKTICK.findall(text)
    for formula in _extract_formulas(text):
        if "=" in formula:
            left, right = formula.split("=", 1)
            if left.strip() in {"y", "f(x)", "g(x)"}:
                candidates.append(right)
    for candidate in candidates:
        normalized_candidate = (
            candidate.strip()
            .replace("^", "**")
            .replace(r"\sin", "sin")
            .replace(r"\cos", "cos")
            .replace(r"\exp", "exp")
        )
        try:
            normalize_math_expression(normalized_candidate)
        except ValueError:
            continue
        return normalized_candidate
    return None


class HeuristicDecisionProvider:
    """Deterministic baseline and fallback for provider integration tests."""

    provider_id = "heuristic-constrained-v1"

    def decide(self, context: PlanningBeatContext) -> VisualDecision:
        lowered = context.text.lower()
        expression = _safe_expression(context.text)
        if expression is not None and any(
            word in lowered for word in ("secant", "tangent", "derivative")
        ):
            return VisualDecision(
                template="secant_to_tangent",
                expression=expression,
                rationale=(
                    "A safe function expression and a derivative/secant intent "
                    "match the reusable secant-to-tangent block."
                ),
                confidence=0.94,
            )
        if expression is not None and any(
            word in lowered for word in ("plot", "graph", "curve", "function")
        ):
            return VisualDecision(
                template="function_plot",
                expression=expression,
                rationale=(
                    "A safe explicit expression and graph intent match the "
                    "function-plot block."
                ),
                confidence=0.93,
            )
        if "number line" in lowered:
            values = []
            for match in _NUMBER.findall(context.text):
                value = float(match)
                if value not in values:
                    values.append(value)
            if values:
                return VisualDecision(
                    template="number_line",
                    values=values[:9],
                    rationale=(
                        "The script explicitly requests a number line and "
                        "contains finite numeric landmarks."
                    ),
                    confidence=0.96,
                )
        if len(context.formulas) >= 2 and any(
            word in lowered
            for word in ("becomes", "transform", "rewrite", "then", "simplify")
        ):
            return VisualDecision(
                template="equation_transform",
                rationale=(
                    "Two authored formulas plus transformation language match "
                    "the semantic equation-transform block."
                ),
                confidence=0.9,
            )
        if context.formulas:
            return VisualDecision(
                template="equation_reveal",
                rationale=(
                    "The script contains authored LaTeX, so the conservative "
                    "choice is a ledger-locked equation reveal."
                ),
                confidence=0.88,
            )

        unsupported = []
        if any(
            word in lowered
            for word in (
                "triangle",
                "polygon",
                "surface",
                "rotate",
                "vector",
                "probability tree",
            )
        ):
            unsupported.append(
                "No sufficiently specific parameters were present for a "
                "bespoke geometry plan; retained as a title-led beat."
            )
        return VisualDecision(
            template="title_card",
            rationale=(
                "No safe formula, plot expression, or numeric template trigger "
                "was found; preserve the script without inventing mathematics."
            ),
            confidence=0.62,
            unsupported_intents=unsupported,
        )


def objective_for_decision(decision: VisualDecision) -> str:
    return {
        "title_card": "Establish the narrated mathematical idea.",
        "equation_reveal": "Connect the narration to its authored formula.",
        "equation_transform": "Show the authored symbolic change.",
        "function_plot": "Relate an explicit expression to its graph.",
        "secant_to_tangent": "Connect secant motion to tangent behavior.",
        "number_line": "Locate the narrated values on a number line.",
    }[decision.template]


def _duration(
    utterance: UtteranceTiming,
    paragraph: str,
) -> float:
    if utterance.words:
        return utterance.words[-1].end_seconds - utterance.words[0].start_seconds
    return max(2.4, len(paragraph.split()) / 2.35 + 0.5)


def make_visual_block(
    decision: VisualDecision,
    *,
    beat_id: str,
    text: str,
    formulas: list[str],
    formula_ids: list[str],
    duration: float,
):
    run_time = min(1.0, max(0.45, duration * 0.32))
    teardown = 0.35
    caption_reveal = (
        0.25
        if decision.template in {"equation_transform", "secant_to_tangent"}
        else 0.0
    )
    hold = max(0.0, duration - run_time - teardown - caption_reveal)
    common = {
        "id": f"{beat_id}.{decision.template}",
        "run_time": run_time,
        "hold_seconds": hold,
    }
    if decision.template == "equation_reveal":
        return EquationRevealBlock(
            **common,
            formula_id=formula_ids[0],
            latex_parts=[formulas[0]],
            caption=_short_title(text),
        )
    if decision.template == "equation_transform":
        return EquationTransformBlock(
            **common,
            from_latex=[formulas[0]],
            to_latex=[formulas[1]],
            caption=_short_title(text),
        )
    if decision.template == "function_plot":
        assert decision.expression is not None
        return FunctionPlotBlock(
            **common,
            expression=decision.expression,
            label_latex=formulas[0] if formulas else None,
        )
    if decision.template == "secant_to_tangent":
        assert decision.expression is not None
        return SecantToTangentBlock(
            **common,
            expression=decision.expression,
            caption=_short_title(text),
        )
    if decision.template == "number_line":
        low = min(decision.values)
        high = max(decision.values)
        padding = max(1.0, (high - low) * 0.2)
        return NumberLineBlock(
            **common,
            x_range=(low - padding, high + padding, 1.0),
            values=decision.values,
            labels=[f"{value:g}" for value in decision.values],
        )
    return TitleCardBlock(
        **common,
        title=_short_title(text),
        subtitle="Conservative visual fallback — planner review recommended",
    )


class ConstrainedPlanner:
    """Emit a complete ProjectSpec while keeping provider output bounded."""

    def __init__(
        self,
        provider: VisualDecisionProvider | None = None,
    ):
        self.provider = provider or HeuristicDecisionProvider()

    def plan(self, request: PlanningRequest) -> PlanningResult:
        paragraphs = _paragraphs(request.script)
        supplied = request.narration.utterances
        if supplied and len(supplied) != len(paragraphs):
            raise ValueError(
                "narration utterance count must match script paragraph count "
                f"({len(supplied)} != {len(paragraphs)})"
            )
        utterances = (
            supplied
            if supplied
            else [
                UtteranceTiming(
                    id=f"utterance-{index:03d}",
                    text=paragraph,
                    words=[],
                )
                for index, paragraph in enumerate(paragraphs, start=1)
            ]
        )

        beats: list[BeatSpec] = []
        ledger_formulas: list[FormulaSpec] = []
        ledger_claims: list[MathClaim] = []
        planned: list[PlannedBeatArtifact] = []
        warnings: list[str] = []
        for index, (paragraph, utterance) in enumerate(
            zip(paragraphs, utterances, strict=True),
            start=1,
        ):
            beat_id = f"beat-{index:03d}"
            formulas = _extract_formulas(paragraph)
            formula_ids = []
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
                ledger_claims.append(
                    MathClaim(
                        id=f"claim.{index:03d}.{formula_index:02d}",
                        statement=f"The authored script asserts ${formula}$.",
                        verification="assumed",
                        assumptions=[
                            "The authored script is the source of truth pending "
                            "independent mathematical verification."
                        ],
                        evidence=[f"script beat {index}"],
                    )
                )
            context = PlanningBeatContext(
                beat_index=index - 1,
                text=paragraph,
                formulas=formulas,
            )
            decision = validate_visual_decision(
                context,
                self.provider.decide(context),
            )
            duration = _duration(utterance, paragraph)
            block = make_visual_block(
                decision,
                beat_id=beat_id,
                text=paragraph,
                formulas=formulas,
                formula_ids=formula_ids,
                duration=duration,
            )
            beats.append(
                BeatSpec(
                    id=beat_id,
                    title=_short_title(paragraph),
                    learning_objective=objective_for_decision(decision),
                    narration_utterance_id=utterance.id,
                    duration_seconds=duration,
                    blocks=[block],
                )
            )
            planned.append(
                PlannedBeatArtifact(
                    beat_id=beat_id,
                    source_text=paragraph,
                    learning_objective=objective_for_decision(decision),
                    selected_template=decision.template,
                    rationale=decision.rationale,
                    confidence=decision.confidence,
                    formula_ids=formula_ids,
                    unsupported_intents=decision.unsupported_intents,
                )
            )
            warnings.extend(
                f"{beat_id}: {warning}"
                for warning in decision.unsupported_intents
            )

        narration = request.narration.model_copy(
            update={"utterances": utterances}
        )
        if supplied and any(utterance.words for utterance in supplied):
            starts = [
                utterance.words[0].start_seconds
                for utterance in supplied
                if utterance.words
            ]
            ends = [
                utterance.words[-1].end_seconds
                for utterance in supplied
                if utterance.words
            ]
            target_duration = max(ends) - min(starts)
        else:
            target_duration = sum(
                beat.duration_seconds or 0.0 for beat in beats
            )
        project = ProjectSpec(
            project_id=request.project_id,
            title=request.title,
            request=RequestSpec(
                source_kind="script",
                content=request.script,
                audience=request.audience,
                script_policy="review",
                target_duration_seconds=target_duration,
            ),
            math_ledger=MathLedger(
                claims=ledger_claims,
                formulas=ledger_formulas,
            ),
            narration=narration,
            style=request.style,
            assets=request.assets,
            beats=beats,
            render=request.render,
        )
        counts = Counter(item.selected_template for item in planned)
        artifact = PlanningArtifact(
            planner_id=self.provider.provider_id,
            request_sha256=sha256_json(request),
            project_sha256=sha256_json(project),
            beats=planned,
            template_counts=dict(sorted(counts.items())),
            typed_template_ratio=1.0,
            warnings=warnings,
        )
        return PlanningResult(artifact=artifact, project=project)
