from pathlib import Path

import pytest

from math_animation.compiler import ManimCompiler
from math_animation.contracts import NarrationInput, UtteranceTiming
from math_animation.planning import (
    ConstrainedPlanner,
    PlanningBeatContext,
    PlanningRequest,
    VisualDecision,
)
from math_animation.style import normalize_style


def test_constrained_planner_selects_common_templates_and_compiles(
    tmp_path: Path,
) -> None:
    request = PlanningRequest(
        project_id="planned",
        title="Planned",
        script=(
            "Reveal the balance equation $3x+5=20$.\n\n"
            "Graph the function `sin(x)` and connect it to periodic motion.\n\n"
            "Place -2, 0, and 3 on a number line."
        ),
    )
    result = ConstrainedPlanner().plan(request)
    assert [
        beat.selected_template for beat in result.artifact.beats
    ] == ["equation_reveal", "function_plot", "number_line"]
    assert result.artifact.custom_python_requests == []
    assert all(
        not beat.custom_python_requested for beat in result.artifact.beats
    )
    compilation = ManimCompiler().compile(
        result.project,
        normalize_style(result.project.style),
        tmp_path,
    )
    assert len(compilation.source_files) == 3


def test_planner_uses_aligned_utterances_and_preserves_audio() -> None:
    narration = NarrationInput(
        audio_path="/tmp/narration.wav",
        utterances=[
            UtteranceTiming(id="u1", text="First formula", words=[]),
            UtteranceTiming(id="u2", text="Second formula", words=[]),
        ],
    )
    result = ConstrainedPlanner().plan(
        PlanningRequest(
            project_id="aligned",
            title="Aligned",
            script="First $x=1$.\n\nSecond $y=2$.",
            narration=narration,
        )
    )
    assert result.project.narration.audio_path == "/tmp/narration.wav"
    assert [beat.narration_utterance_id for beat in result.project.beats] == [
        "u1",
        "u2",
    ]


def test_narration_count_must_match_script_beats() -> None:
    narration = NarrationInput(
        utterances=[UtteranceTiming(id="only", text="Only", words=[])]
    )
    with pytest.raises(ValueError, match="utterance count"):
        ConstrainedPlanner().plan(
            PlanningRequest(
                project_id="mismatch",
                title="Mismatch",
                script="First.\n\nSecond.",
                narration=narration,
            )
        )


class _InvalidProvider:
    provider_id = "invalid-test-provider"

    def decide(self, context: PlanningBeatContext) -> VisualDecision:
        return VisualDecision(
            template="equation_reveal",
            rationale="invalid on purpose",
            confidence=1,
        )


def test_provider_cannot_invent_formula_for_equation_template() -> None:
    with pytest.raises(ValueError, match="without authored formulas"):
        ConstrainedPlanner(_InvalidProvider()).plan(
            PlanningRequest(
                project_id="provider-boundary",
                title="Provider boundary",
                script="No formula appears here.",
            )
        )


class _UnsafeExpressionProvider:
    provider_id = "unsafe-expression-provider"

    def decide(self, context: PlanningBeatContext) -> VisualDecision:
        return VisualDecision(
            template="function_plot",
            expression="__import__('os').system('id')",
            rationale="unsafe on purpose",
            confidence=1,
        )


def test_provider_expression_passes_the_same_safety_gate() -> None:
    with pytest.raises(ValueError, match="approved math functions"):
        ConstrainedPlanner(_UnsafeExpressionProvider()).plan(
            PlanningRequest(
                project_id="unsafe-provider",
                title="Unsafe provider",
                script="Graph something.",
            )
        )
