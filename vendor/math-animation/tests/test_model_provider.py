from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from math_animation.contracts import (
    ActionCue,
    BeatSpec,
    CreateAction,
    DotVisualObject,
    FormulaSpec,
    MathLedger,
    NarrationInput,
    ProjectSpec,
    RequestSpec,
    SceneProgram,
    UtteranceTiming,
)
from math_animation.model_provider import (
    ModelProviderConfig,
    OpenAIResponsesDecisionProvider,
)
from math_animation.planning import PlanningBeatContext, VisualDecision
from math_animation.regeneration import generate_regeneration_artifacts
from math_animation.repair import (
    Diagnostic,
    apply_repair_plan,
    build_repair_plan,
)


class _FakeResponses:
    def __init__(self, decision: VisualDecision):
        self.decision = decision
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            id="response-test",
            output_parsed=self.decision,
        )


class _FakeClient:
    def __init__(self, decision: VisualDecision):
        self.responses = _FakeResponses(decision)


def test_openai_provider_uses_structured_output_and_records_audit(
    tmp_path: Path,
) -> None:
    decision = VisualDecision(
        template="function_plot",
        expression="sin(x)",
        rationale="The script explicitly asks for this graph.",
        confidence=0.91,
    )
    client = _FakeClient(decision)
    provider = OpenAIResponsesDecisionProvider(
        ModelProviderConfig(model="test-model"),
        client=client,
    )
    context = PlanningBeatContext(
        beat_index=0,
        text="Graph the function `sin(x)`.",
    )
    assert provider.decide(context) == decision
    call = client.responses.calls[0]
    assert call["text_format"] is VisualDecision
    assert call["store"] is False
    payload = json.loads(call["input"])
    assert "function_plot" in payload["allowed_templates"]
    assert "custom_scene" not in payload["allowed_templates"]
    assert provider.audit_records[0].response_id == "response-test"
    destination = tmp_path / "model-calls.json"
    provider.write_audit(destination)
    assert json.loads(destination.read_text())["calls"][0]["status"] == "passed"


def test_model_provider_cannot_invent_a_safe_but_unauthored_expression() -> None:
    provider = OpenAIResponsesDecisionProvider(
        ModelProviderConfig(model="test-model"),
        client=_FakeClient(
            VisualDecision(
                template="function_plot",
                expression="cos(x)",
                rationale="Invented on purpose.",
                confidence=1.0,
            )
        ),
    )
    with pytest.raises(ValueError, match="exactly match"):
        provider.decide(
            PlanningBeatContext(
                beat_index=0,
                text="Graph `sin(x)`.",
            )
        )
    assert provider.audit_records[0].status == "failed"


class _RegenerationProvider:
    provider_id = "regeneration-test"

    def decide(self, context: PlanningBeatContext) -> VisualDecision:
        assert context.diagnostic_codes == ["blank_frame"]
        assert context.previous_templates == ["scene_program"]
        return VisualDecision(
            template="equation_reveal",
            rationale="Use the authored formula instead of the blank geometry.",
            confidence=0.98,
        )


def test_regeneration_artifact_replaces_only_the_diagnosed_beat() -> None:
    project = ProjectSpec(
        project_id="regenerate",
        title="Regenerate",
        request=RequestSpec(content="Show the balance equation."),
        math_ledger=MathLedger(
            formulas=[
                FormulaSpec(
                    id="balance",
                    latex_parts=["3x+5=20"],
                    plain_language="Balance equation",
                )
            ]
        ),
        narration=NarrationInput(
            utterances=[
                UtteranceTiming(
                    id="balance.words",
                    text="Show the balance equation.",
                )
            ]
        ),
        beats=[
            BeatSpec(
                id="blank",
                title="Balance equation",
                learning_objective="Show the authored balance equation.",
                narration_utterance_id="balance.words",
                duration_seconds=2.0,
                scene_program=SceneProgram(
                    objects=[
                        DotVisualObject(id="almost-invisible", radius=0.001)
                    ],
                    cues=[
                        ActionCue(
                            id="show",
                            actions=[
                                CreateAction(
                                    target="almost-invisible",
                                    run_time=0.5,
                                )
                            ],
                        )
                    ],
                ),
            )
        ],
    )
    diagnostic = Diagnostic(
        id="diag-blank",
        code="blank_frame",
        severity="warning",
        stage="review",
        message="Stable frame is blank.",
        beat_id="blank",
        suggested_repairs=["regenerate_beat"],
    )
    plan = build_repair_plan(
        project,
        [diagnostic],
        enable_regeneration=True,
    )
    assert [operation.type for operation in plan.operations] == [
        "regenerate_beat"
    ]
    artifacts = generate_regeneration_artifacts(
        project,
        plan,
        [diagnostic],
        _RegenerationProvider(),
    )
    repaired = apply_repair_plan(
        project,
        plan,
        regenerations=artifacts,
    )
    block = repaired.beats[0].blocks[0]
    assert block.type == "equation_reveal"
    assert block.formula_id == "balance"
    assert repaired.beats[0].scene_program is None
