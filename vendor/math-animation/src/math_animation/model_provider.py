"""Structured model-provider adapters for constrained visual decisions."""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any, Literal

from pydantic import Field

from math_animation.bundle import sha256_json, write_json_atomic
from math_animation.contracts import StrictModel
from math_animation.planning import (
    PlanningBeatContext,
    VisualDecision,
    allowed_templates,
    validate_visual_decision,
)


class ModelProviderError(RuntimeError):
    pass


class ModelProviderConfig(StrictModel):
    provider: Literal["openai"] = "openai"
    model: str = Field(min_length=1)
    timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    max_output_tokens: int = Field(default=600, ge=100, le=4000)
    store: bool = False


class ModelCallRecord(StrictModel):
    schema_version: Literal["math-animation.model-call.v1"] = (
        "math-animation.model-call.v1"
    )
    call_index: int = Field(ge=1)
    provider: str
    model: str
    context_sha256: str
    context: PlanningBeatContext
    allowed_templates: list[str]
    status: Literal["passed", "failed"]
    response_id: str | None = None
    response_model: str | None = None
    elapsed_seconds: float = Field(ge=0)
    usage: dict[str, Any] = Field(default_factory=dict)
    decision: VisualDecision | None = None
    error: str | None = None


_INSTRUCTIONS = """\
You are the constrained visual-decision node in a mathematical animation
pipeline. Select exactly one reusable template from the allowed list.

Hard rules:
- Return only the supplied VisualDecision schema.
- Never return Python, Manim code, JSON patches, or new mathematical claims.
- Equations may only use formulas already present in the context.
- Plot/secant expressions must exactly copy the authored safe expression.
- Number-line values must be a subset of numbers written in the context.
- Prefer a different suitable template when diagnostics say the previous
  representation was blank, frozen, or discontinuous.
- Use title_card when the authored inputs do not support a more specific block.
"""


class OpenAIResponsesDecisionProvider:
    """OpenAI Responses API adapter with Pydantic structured output.

    The client is injectable so request construction and validation can be
    tested without network access. With no injected client, the official SDK
    resolves ``OPENAI_API_KEY`` in its normal way.
    """

    def __init__(
        self,
        config: ModelProviderConfig,
        *,
        client: Any | None = None,
    ):
        self.config = config
        self.provider_id = f"openai-responses:{config.model}"
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ModelProviderError(
                    "OpenAI provider requires the optional 'model' dependency"
                ) from exc
            try:
                client = OpenAI(timeout=config.timeout_seconds)
            except Exception as exc:
                raise ModelProviderError(
                    "could not initialize the OpenAI provider; configure "
                    "OPENAI_API_KEY or inject a client"
                ) from exc
        self._client = client
        self.audit_records: list[ModelCallRecord] = []

    def decide(self, context: PlanningBeatContext) -> VisualDecision:
        allowed = allowed_templates(context)
        call_index = len(self.audit_records) + 1
        response_id: str | None = None
        response_model: str | None = None
        usage: dict[str, Any] = {}
        started = time.perf_counter()
        try:
            response = self._client.responses.parse(
                model=self.config.model,
                instructions=_INSTRUCTIONS,
                input=json.dumps(
                    {
                        "context": context.model_dump(mode="json"),
                        "allowed_templates": allowed,
                    },
                    ensure_ascii=False,
                ),
                text_format=VisualDecision,
                max_output_tokens=self.config.max_output_tokens,
                store=self.config.store,
            )
            response_id = getattr(response, "id", None)
            response_model = getattr(response, "model", None)
            raw_usage = getattr(response, "usage", None)
            if raw_usage is not None:
                usage = (
                    raw_usage.model_dump(mode="json")
                    if hasattr(raw_usage, "model_dump")
                    else dict(raw_usage)
                    if isinstance(raw_usage, dict)
                    else {"value": str(raw_usage)}
                )
            parsed = getattr(response, "output_parsed", None)
            if parsed is None:
                raise ModelProviderError(
                    "model response did not contain a parsed VisualDecision"
                )
            decision = validate_visual_decision(
                context,
                VisualDecision.model_validate(parsed),
            )
        except Exception as exc:
            self.audit_records.append(
                ModelCallRecord(
                    call_index=call_index,
                    provider="openai",
                    model=self.config.model,
                    context_sha256=sha256_json(context),
                    context=context,
                    allowed_templates=allowed,
                    status="failed",
                    response_id=response_id,
                    response_model=response_model,
                    elapsed_seconds=time.perf_counter() - started,
                    usage=usage,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            if isinstance(exc, (ValueError, ModelProviderError)):
                raise
            raise ModelProviderError(
                f"OpenAI decision request failed: {type(exc).__name__}: {exc}"
            ) from exc
        self.audit_records.append(
            ModelCallRecord(
                call_index=call_index,
                provider="openai",
                model=self.config.model,
                context_sha256=sha256_json(context),
                context=context,
                allowed_templates=allowed,
                status="passed",
                response_id=response_id,
                response_model=response_model,
                elapsed_seconds=time.perf_counter() - started,
                usage=usage,
                decision=decision,
            )
        )
        return decision

    def write_audit(self, destination: Path) -> None:
        write_json_atomic(
            destination,
            {
                "schema_version": "math-animation.model-calls.v1",
                "provider_id": self.provider_id,
                "calls": [
                    record.model_dump(mode="json")
                    for record in self.audit_records
                ],
            },
        )
