from math_animation.contracts import (
    ActionCue,
    BeatSpec,
    CreateAction,
    NarrationInput,
    ProjectSpec,
    RequestSpec,
    SceneProgram,
    TextVisualObject,
    UtteranceTiming,
)
from math_animation.expanded_planning import ExpandedPlanner
from math_animation.pedagogy import evaluate_pedagogy
from math_animation.planning import PlanningRequest


def test_expanded_templates_pass_structural_pedagogy_rubric() -> None:
    result = ExpandedPlanner().plan(
        PlanningRequest(
            project_id="pedagogy-pass",
            title="Pedagogy pass",
            script=(
                "Derive step by step: $3x+5=20$, then $3x=15$, then $x=5$.\n\n"
                "Compare $y=x^2$ versus $y=2x^2$."
            ),
        )
    )
    report = evaluate_pedagogy(result.project)
    assert report.status == "passed"
    assert report.total_score >= 0.9
    assert {item.dimension for item in report.dimensions} == {
        "mathematical_grounding",
        "objective_alignment",
        "progressive_disclosure",
        "pacing",
        "cognitive_load",
        "narration_sync",
        "legibility",
    }
    assert report.limitations


def test_rubric_flags_misaligned_overloaded_static_visual() -> None:
    objects = [
        TextVisualObject(
            id=f"label-{index}",
            text="A long competing annotation " * 3,
            position=(0, 0, 0),
        )
        for index in range(10)
    ]
    project = ProjectSpec(
        project_id="pedagogy-risk",
        title="Pedagogy risk",
        request=RequestSpec(content="Graph the function clearly."),
        narration=NarrationInput(
            utterances=[
                UtteranceTiming(
                    id="risk.words",
                    text="Graph the function clearly.",
                )
            ]
        ),
        beats=[
            BeatSpec(
                id="risk",
                title="Graph the function",
                learning_objective="Graph the curve and explain its shape.",
                narration_utterance_id="risk.words",
                duration_seconds=5,
                scene_program=SceneProgram(
                    objects=objects,
                    cues=[
                        ActionCue(
                            id="show-all",
                            mode="parallel",
                            actions=[
                                CreateAction(target=item.id, run_time=0.2)
                                for item in objects
                            ],
                        )
                    ],
                ),
            )
        ],
    )
    report = evaluate_pedagogy(project)
    finding_ids = {item.id for item in report.findings}
    assert "risk.alignment" in finding_ids
    assert "risk.load" in finding_ids
    assert report.status in {"needs_review", "failed"}
    assert report.total_score < 0.78
