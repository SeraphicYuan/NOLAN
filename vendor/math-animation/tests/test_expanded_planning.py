from pathlib import Path

import pytest

from math_animation.compiler import ManimCompiler
from math_animation.expanded_planning import (
    ConceptComparisonPlan,
    ExpandedPlanner,
    ExpandedVisualDecision,
    EquationSequencePlan,
    PedagogicalIntent,
    PlanningBeatContext,
)
from math_animation.planning import PlanningRequest
from math_animation.style import normalize_style


def test_expanded_planner_selects_sequence_and_comparison_and_compiles(
    tmp_path: Path,
) -> None:
    result = ExpandedPlanner().plan(
        PlanningRequest(
            project_id="expanded",
            title="Expanded templates",
            script=(
                "Derive the solution step by step: $3x+5=20$, then "
                "$3x=15$, so $x=5$.\n\n"
                "Compare $y=x^2$ versus $y=2x^2$ and explain the difference."
            ),
        )
    )
    assert [
        beat.selected_template for beat in result.artifact.beats
    ] == ["equation_sequence", "concept_comparison"]
    assert result.artifact.custom_python_requests == []
    assert len(result.project.math_ledger.formulas) == 5
    sequence = result.project.beats[0].scene_program
    comparison = result.project.beats[1].scene_program
    assert sequence is not None
    assert comparison is not None
    assert [
        action.formula_id
        for cue in sequence.cues
        for action in cue.actions
        if action.type == "transform_math"
    ] == ["formula.001.02", "formula.001.03"]
    assert {
        item.formula_id
        for item in comparison.objects
        if item.type == "math_tex"
    } == {"formula.002.01", "formula.002.02"}
    comparison_math = [
        item for item in comparison.objects if item.type == "math_tex"
    ]
    assert (
        abs(
            comparison_math[0].position[0]
            - comparison_math[1].position[0]
        )
        >= 6.8
    )
    compilation = ManimCompiler().compile(
        result.project,
        normalize_style(result.project.style),
        tmp_path,
    )
    assert len(compilation.source_files) == 2


class _OutOfRangeProvider:
    provider_id = "out-of-range"

    def decide(
        self,
        context: PlanningBeatContext,
    ) -> ExpandedVisualDecision:
        return ExpandedVisualDecision(
            rationale="Invalid on purpose.",
            confidence=1,
            pedagogy=PedagogicalIntent(learning_goal="Solve the equation."),
            plan=EquationSequencePlan(formula_indices=[0, 1, 99]),
        )


def test_expanded_provider_cannot_reference_unauthored_formula() -> None:
    with pytest.raises(ValueError, match="outside the source"):
        ExpandedPlanner(_OutOfRangeProvider()).plan(
            PlanningRequest(
                project_id="grounding",
                title="Grounding",
                script="Derive $x+2=4$, then $x=2$, then $2=2$.",
            )
        )


def test_comparison_plan_requires_distinct_formula_indices() -> None:
    with pytest.raises(ValueError, match="distinct"):
        ConceptComparisonPlan(
            left_formula_index=0,
            right_formula_index=0,
        )
