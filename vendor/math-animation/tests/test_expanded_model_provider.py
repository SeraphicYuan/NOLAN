import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from math_animation.expanded_model_provider import (
    OpenAIExpandedDecisionProvider,
)
from math_animation.expanded_planning import (
    ExpandedVisualDecision,
    EquationSequencePlan,
    PedagogicalIntent,
)
from math_animation.model_provider import ModelProviderConfig
from math_animation.planning import PlanningBeatContext


class _FakeResponses:
    def __init__(self, decision: ExpandedVisualDecision):
        self.decision = decision
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            id="response-expanded-test",
            model="test-model-resolved",
            output_parsed=self.decision,
            usage={"input_tokens": 10, "output_tokens": 20},
        )


class _FakeClient:
    def __init__(self, decision: ExpandedVisualDecision):
        self.responses = _FakeResponses(decision)


def _decision(indices: list[int]) -> ExpandedVisualDecision:
    return ExpandedVisualDecision(
        rationale="Use progressive disclosure for the authored derivation.",
        confidence=0.97,
        pedagogy=PedagogicalIntent(
            learning_goal="Derive the equation in three authored steps.",
            teaching_strategy="procedural",
        ),
        plan=EquationSequencePlan(formula_indices=indices),
    )


def test_expanded_openai_provider_uses_schema_and_audits(
    tmp_path: Path,
) -> None:
    client = _FakeClient(_decision([0, 1, 2]))
    provider = OpenAIExpandedDecisionProvider(
        ModelProviderConfig(model="test-model"),
        client=client,
    )
    context = PlanningBeatContext(
        beat_index=0,
        text="Derive $x+2=4$, then $x=2$, then $2=2$.",
        formulas=["x+2=4", "x=2", "2=2"],
    )
    assert provider.decide(context).plan.template == "equation_sequence"
    call = client.responses.calls[0]
    assert call["text_format"] is ExpandedVisualDecision
    assert "equation_sequence" in json.loads(call["input"])[
        "allowed_templates"
    ]
    assert provider.audit_records[0].response_id == "response-expanded-test"
    destination = tmp_path / "expanded-model-calls.json"
    provider.write_audit(destination)
    assert json.loads(destination.read_text())["calls"][0]["status"] == "passed"


def test_expanded_model_provider_rejects_unauthored_formula_index() -> None:
    provider = OpenAIExpandedDecisionProvider(
        ModelProviderConfig(model="test-model"),
        client=_FakeClient(_decision([0, 1, 9])),
    )
    with pytest.raises(ValueError, match="outside the source"):
        provider.decide(
            PlanningBeatContext(
                beat_index=0,
                text="Derive $x+2=4$, then $x=2$, then $2=2$.",
                formulas=["x+2=4", "x=2", "2=2"],
            )
        )
    assert provider.audit_records[0].status == "failed"
