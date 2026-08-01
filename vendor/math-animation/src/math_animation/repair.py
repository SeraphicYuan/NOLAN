"""Typed diagnostics and bounded, deterministic project repairs.

The repair layer deliberately sits outside the stable ProjectSpec schema.  It
never accepts Python source or an arbitrary JSON patch: every allowed mutation
has a narrow contract and is revalidated through ProjectSpec before use.
"""

from __future__ import annotations

import math
import re
import textwrap
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from math_animation.blocks import compile_block
from math_animation.bundle import sha256_json
from math_animation.contracts import (
    AnimateTrackerAction,
    EquationRevealBlock,
    EquationTransformBlock,
    MathTexVisualObject,
    ParametricSurfaceVisualObject,
    PointCloudVisualObject,
    ProjectSpec,
    ResponsiveVisualOverride,
    ScalarFieldFootprintVisualObject,
    StrictModel,
    TextVisualObject,
    TitleCardBlock,
    TraceVisualObject,
    TrackedPointVisualObject,
)
from math_animation.math_validation import validate_math
from math_animation.style import normalize_style
from math_animation.timing import resolve_anchor, resolve_beats


DiagnosticCode = Literal[
    "text_overflow",
    "illegible_type",
    "blank_frame",
    "frozen_motion",
    "abrupt_discontinuity",
    "excessive_density",
    "timing_drift",
    "invariant_failure",
    "missing_input",
    "math_validation_failed",
    "invalid_latex",
    "media_mismatch",
    "template_mismatch",
    "render_failure",
]
DiagnosticSeverity = Literal["warning", "error", "refusal"]
RepairKind = Literal[
    "reposition_object",
    "set_responsive_scale",
    "set_font_size",
    "set_max_width",
    "shorten_generated_caption",
    "scale_timing",
    "reduce_density",
    "set_tracker_end_value",
    "swap_template",
    "regenerate_beat",
]


class Diagnostic(StrictModel):
    schema_version: Literal["math-animation.diagnostic.v1"] = (
        "math-animation.diagnostic.v1"
    )
    id: str
    code: DiagnosticCode
    severity: DiagnosticSeverity
    stage: Literal["audit", "compile", "preflight", "render", "review"]
    message: str
    beat_id: str | None = None
    object_id: str | None = None
    cue_id: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    suggested_repairs: list[RepairKind] = Field(default_factory=list)
    repairable: bool = False

    @model_validator(mode="after")
    def refusal_is_not_repairable(self) -> "Diagnostic":
        if self.severity == "refusal" and self.repairable:
            raise ValueError("refusal diagnostics cannot be marked repairable")
        return self


class RepositionObjectOperation(StrictModel):
    type: Literal["reposition_object"] = "reposition_object"
    beat_id: str
    object_id: str
    position: tuple[float, float, float]
    aspect_class: Literal["landscape", "square", "portrait"] | None = None
    reason_diagnostic_id: str


class SetResponsiveScaleOperation(StrictModel):
    type: Literal["set_responsive_scale"] = "set_responsive_scale"
    beat_id: str
    object_id: str
    aspect_class: Literal["landscape", "square", "portrait"]
    scale: float = Field(gt=0, le=4)
    reason_diagnostic_id: str


class SetFontSizeOperation(StrictModel):
    type: Literal["set_font_size"] = "set_font_size"
    beat_id: str
    object_id: str
    font_size: int = Field(ge=12, le=160)
    reason_diagnostic_id: str


class SetMaxWidthOperation(StrictModel):
    type: Literal["set_max_width"] = "set_max_width"
    beat_id: str
    object_id: str
    max_width: float = Field(gt=0)
    wrapped_text: str | None = None
    reason_diagnostic_id: str


class ShortenGeneratedCaptionOperation(StrictModel):
    type: Literal["shorten_generated_caption"] = "shorten_generated_caption"
    beat_id: str
    block_id: str
    field: Literal["caption", "title", "subtitle"]
    replacement: str
    reason_diagnostic_id: str


class ScaleTimingOperation(StrictModel):
    type: Literal["scale_timing"] = "scale_timing"
    beat_id: str
    factor: float = Field(gt=0, lt=1)
    target: Literal["scene_actions", "legacy_blocks"]
    reason_diagnostic_id: str


class ReduceDensityOperation(StrictModel):
    type: Literal["reduce_density"] = "reduce_density"
    beat_id: str
    object_id: str
    sample_count: int | None = Field(default=None, ge=1)
    resolution: tuple[int, int] | None = None
    reason_diagnostic_id: str

    @model_validator(mode="after")
    def one_density_value(self) -> "ReduceDensityOperation":
        if (self.sample_count is None) == (self.resolution is None):
            raise ValueError(
                "reduce_density needs exactly one of sample_count or resolution"
            )
        return self


class SetTrackerEndValueOperation(StrictModel):
    type: Literal["set_tracker_end_value"] = "set_tracker_end_value"
    beat_id: str
    cue_id: str
    tracker_id: str
    end_value: float
    reason_diagnostic_id: str


class SwapTemplateOperation(StrictModel):
    type: Literal["swap_template"] = "swap_template"
    beat_id: str
    target_template: Literal["equation_reveal", "title_card"]
    formula_id: str | None = None
    reason_diagnostic_id: str


class RegenerateBeatOperation(StrictModel):
    """Provider boundary for a later model-backed beat regeneration node."""

    type: Literal["regenerate_beat"] = "regenerate_beat"
    beat_id: str
    allowed_templates: list[str] = Field(min_length=1)
    reason_diagnostic_id: str


RepairOperation = Annotated[
    RepositionObjectOperation
    | SetResponsiveScaleOperation
    | SetFontSizeOperation
    | SetMaxWidthOperation
    | ShortenGeneratedCaptionOperation
    | ScaleTimingOperation
    | ReduceDensityOperation
    | SetTrackerEndValueOperation
    | SwapTemplateOperation
    | RegenerateBeatOperation,
    Field(discriminator="type"),
]


class RepairPlan(StrictModel):
    schema_version: Literal["math-animation.repair-plan.v1"] = (
        "math-animation.repair-plan.v1"
    )
    source_project_sha256: str
    diagnostic_ids: list[str]
    operations: list[RepairOperation]
    affected_beat_ids: list[str]
    refused_diagnostic_ids: list[str] = Field(default_factory=list)


def _diagnostic(
    *,
    code: DiagnosticCode,
    severity: DiagnosticSeverity,
    stage: Literal["audit", "compile", "preflight", "render", "review"],
    message: str,
    beat_id: str | None = None,
    object_id: str | None = None,
    cue_id: str | None = None,
    evidence: dict[str, Any] | None = None,
    suggested_repairs: list[RepairKind] | None = None,
    repairable: bool = False,
) -> Diagnostic:
    identity = {
        "code": code,
        "stage": stage,
        "beat_id": beat_id,
        "object_id": object_id,
        "cue_id": cue_id,
        "message": message,
    }
    return Diagnostic(
        id=f"diag-{sha256_json(identity)[:12]}",
        code=code,
        severity=severity,
        stage=stage,
        message=message,
        beat_id=beat_id,
        object_id=object_id,
        cue_id=cue_id,
        evidence=evidence or {},
        suggested_repairs=suggested_repairs or [],
        repairable=repairable,
    )


def _aspect_class(project: ProjectSpec) -> Literal["landscape", "square", "portrait"]:
    ratio = project.render.pixel_width / project.render.pixel_height
    if ratio > 1.12:
        return "landscape"
    if ratio < 0.88:
        return "portrait"
    return "square"


def _shorten(text: str, limit: int = 72) -> str:
    if len(text) <= limit:
        return text
    candidate = text[: limit - 3].rsplit(" ", 1)[0].rstrip()
    if len(candidate) < limit // 2:
        candidate = text[: limit - 3].rstrip()
    return candidate + "..."


def _wrap_text(text: str, columns: int) -> str:
    return "\n".join(
        textwrap.wrap(
            " ".join(text.split()),
            width=columns,
            break_long_words=False,
            break_on_hyphens=False,
        )
    )


def analyze_project(project: ProjectSpec) -> list[Diagnostic]:
    """Run deterministic, cheap checks before compilation or rendering."""

    diagnostics: list[Diagnostic] = []
    math_report = validate_math(project)
    if math_report.status == "failed":
        diagnostics.append(
            _diagnostic(
                code="math_validation_failed",
                severity="refusal",
                stage="audit",
                message="Mathematical artifact validation failed.",
                evidence={"errors": math_report.errors},
            )
        )

    missing: list[str] = []
    if project.narration.audio_path and not Path(
        project.narration.audio_path
    ).is_file():
        missing.append(f"narration audio: {project.narration.audio_path}")
    for asset in project.assets:
        if not Path(asset.path).is_file():
            missing.append(f"asset {asset.id}: {asset.path}")
    if missing:
        diagnostics.append(
            _diagnostic(
                code="missing_input",
                severity="refusal",
                stage="audit",
                message="Required local inputs are missing.",
                evidence={"missing": missing},
            )
        )

    aspect = _aspect_class(project)
    generated_text_limit = 38 if aspect == "portrait" else 72
    frame_width = 8.0 * project.render.pixel_width / project.render.pixel_height
    frame_height = 8.0
    style = normalize_style(project.style)

    try:
        resolved_beats = {item.beat.id: item for item in resolve_beats(project)}
    except ValueError as exc:
        diagnostics.append(
            _diagnostic(
                code="timing_drift",
                severity="error",
                stage="audit",
                message=str(exc),
                evidence={"exception": type(exc).__name__},
                suggested_repairs=["scale_timing"],
                repairable="needs" in str(exc) or "overlap" in str(exc),
            )
        )
        resolved_beats = {}

    for beat in project.beats:
        resolved = resolved_beats.get(beat.id)
        if beat.scene_program is None:
            required = 0.0
            for block in beat.blocks:
                compiled = compile_block(block, style)
                required += compiled.duration_seconds
                fields: list[tuple[str, str]] = []
                if isinstance(
                    block,
                    (EquationRevealBlock, EquationTransformBlock),
                ) and block.caption:
                    fields.append(("caption", block.caption))
                if isinstance(block, TitleCardBlock):
                    fields.append(("title", block.title))
                    if block.subtitle:
                        fields.append(("subtitle", block.subtitle))
                for field, text in fields:
                    if len(text) > generated_text_limit:
                        diagnostics.append(
                            _diagnostic(
                                code="text_overflow",
                                severity="error",
                                stage="audit",
                                message=(
                                    f"Generated {field} in block {block.id!r} "
                                    "is too long for a reusable layout."
                                ),
                                beat_id=beat.id,
                                object_id=block.id,
                                evidence={
                                    "field": field,
                                    "characters": len(text),
                                    "limit": generated_text_limit,
                                    "replacement": _shorten(
                                        text,
                                        generated_text_limit,
                                    ),
                                },
                                suggested_repairs=[
                                    "shorten_generated_caption"
                                ],
                                repairable=True,
                            )
                        )
            if (
                resolved is not None
                and required > resolved.duration_seconds + 1e-6
            ):
                factor = max(
                    0.05,
                    min(0.95, resolved.duration_seconds / required * 0.94),
                )
                diagnostics.append(
                    _diagnostic(
                        code="timing_drift",
                        severity="error",
                        stage="audit",
                        message=(
                            f"Beat {beat.id!r} needs {required:.3f}s of "
                            f"animation but only {resolved.duration_seconds:.3f}s "
                            "is available."
                        ),
                        beat_id=beat.id,
                        evidence={
                            "required_seconds": required,
                            "available_seconds": resolved.duration_seconds,
                            "factor": factor,
                            "target": "legacy_blocks",
                        },
                        suggested_repairs=["scale_timing"],
                        repairable=True,
                    )
                )
            if (
                len(beat.blocks) == 1
                and isinstance(beat.blocks[0], TitleCardBlock)
                and "authored formula" in beat.learning_objective.lower()
                and project.math_ledger.formulas
            ):
                title_terms = set(re.findall(r"[a-z0-9]+", beat.title.lower()))
                formula = max(
                    project.math_ledger.formulas,
                    key=lambda candidate: len(
                        title_terms
                        & set(
                            re.findall(
                                r"[a-z0-9]+",
                                (
                                    candidate.id
                                    + " "
                                    + candidate.plain_language
                                ).lower(),
                            )
                        )
                    ),
                )
                diagnostics.append(
                    _diagnostic(
                        code="template_mismatch",
                        severity="error",
                        stage="audit",
                        message=(
                            f"Beat {beat.id!r} promises an authored formula but "
                            "uses a title-card fallback."
                        ),
                        beat_id=beat.id,
                        object_id=beat.blocks[0].id,
                        evidence={"formula_id": formula.id},
                        suggested_repairs=["swap_template"],
                        repairable=True,
                    )
                )
            continue

        program = beat.scene_program
        trackers = {tracker.id: tracker for tracker in program.trackers}
        tracked_points = {
            item.id: item
            for item in program.objects
            if isinstance(item, TrackedPointVisualObject)
        }
        trace_targets: dict[str, TraceVisualObject] = {
            item.target: item
            for item in program.objects
            if isinstance(item, TraceVisualObject)
        }
        for item in program.objects:
            override = item.responsive.get(aspect)
            effective_position = (
                override.position
                if override is not None and override.position is not None
                else item.position
            )
            scale = override.scale if override is not None else 1.0
            if isinstance(item, (TextVisualObject, MathTexVisualObject)):
                base_size = (
                    item.font_size
                    or (
                        style.typography.math_size
                        if isinstance(item, MathTexVisualObject)
                        else style.typography.body_size
                    )
                )
                effective_size = base_size * scale
                readability_floor = max(
                    program.minimum_effective_font_size,
                    24.0 if aspect == "portrait" else 18.0,
                )
                if effective_size < readability_floor:
                    minimum_scale = min(
                        4.0,
                        readability_floor / base_size * 1.05,
                    )
                    diagnostics.append(
                        _diagnostic(
                            code="illegible_type",
                            severity="error",
                            stage="audit",
                            message=(
                                f"Object {item.id!r} effective font size "
                                f"{effective_size:.2f} is below "
                                f"{readability_floor:.2f}."
                            ),
                            beat_id=beat.id,
                            object_id=item.id,
                            evidence={
                                "aspect_class": aspect,
                                "effective_font_size": effective_size,
                                "minimum": readability_floor,
                                "scale": minimum_scale,
                            },
                            suggested_repairs=["set_responsive_scale"],
                            repairable=True,
                        )
                    )
                text_length = (
                    len(item.text)
                    if isinstance(item, TextVisualObject)
                    else sum(len(part) for part in item.latex_parts)
                )
                if (
                    isinstance(item, TextVisualObject)
                    and item.max_width is None
                    and text_length > max(40, int(frame_width * 8))
                ):
                    diagnostics.append(
                        _diagnostic(
                            code="text_overflow",
                            severity="error",
                            stage="audit",
                            message=(
                                f"Text object {item.id!r} has no width bound "
                                "for its output aspect."
                            ),
                            beat_id=beat.id,
                            object_id=item.id,
                            evidence={
                                "characters": text_length,
                                "max_width": max(
                                    0.5,
                                    frame_width
                                    - 2 * program.safe_area_margin
                                    - 0.3,
                                ),
                                "wrapped_text": _wrap_text(
                                    item.text,
                                    30 if aspect == "portrait" else 54,
                                ),
                            },
                            suggested_repairs=["set_max_width"],
                            repairable=True,
                        )
                    )
            margin = program.safe_area_margin
            x_outside = not (
                -frame_width / 2 + margin
                <= effective_position[0]
                <= frame_width / 2 - margin
            )
            y_outside = not (
                -frame_height / 2 + margin
                <= effective_position[1]
                <= frame_height / 2 - margin
            )
            clamped = (
                0.0 if x_outside else effective_position[0],
                0.0 if y_outside else effective_position[1],
                effective_position[2],
            )
            if program.enforce_safe_area and any(
                abs(left - right) > 1e-9
                for left, right in zip(effective_position, clamped, strict=True)
            ):
                diagnostics.append(
                    _diagnostic(
                        code="text_overflow",
                        severity="error",
                        stage="audit",
                        message=(
                            f"Object {item.id!r} anchor lies outside the "
                            f"{aspect} safe area."
                        ),
                        beat_id=beat.id,
                        object_id=item.id,
                        evidence={
                            "aspect_class": aspect,
                            "position": effective_position,
                            "clamped_position": clamped,
                        },
                        suggested_repairs=["reposition_object"],
                        repairable=True,
                    )
                )

            density: tuple[int, int] | int | None = None
            replacement: tuple[int, int] | int | None = None
            if isinstance(item, PointCloudVisualObject) and item.sample_count > 2000:
                density, replacement = item.sample_count, 2000
            elif isinstance(item, TraceVisualObject) and item.sample_count > 1200:
                density, replacement = item.sample_count, 1200
            elif isinstance(
                item,
                (ParametricSurfaceVisualObject, ScalarFieldFootprintVisualObject),
            ) and math.prod(item.resolution) > 1600:
                ratio = math.sqrt(1600 / math.prod(item.resolution))
                replacement = (
                    max(2, round(item.resolution[0] * ratio)),
                    max(2, round(item.resolution[1] * ratio)),
                )
                density = item.resolution
            if replacement is not None:
                diagnostics.append(
                    _diagnostic(
                        code="excessive_density",
                        severity="warning",
                        stage="audit",
                        message=f"Object {item.id!r} exceeds the v0.5 density budget.",
                        beat_id=beat.id,
                        object_id=item.id,
                        evidence={
                            "current": density,
                            "replacement": replacement,
                        },
                        suggested_repairs=["reduce_density"],
                        repairable=True,
                    )
                )

        if resolved is not None:
            cursor = 0.0
            for cue in program.cues:
                start = (
                    resolve_anchor(cue.start_at, resolved)
                    if cue.start_at is not None
                    else cursor
                )
                cursor = start + cue.duration_seconds
            if cursor > resolved.duration_seconds + 1e-6:
                factor = max(
                    0.05,
                    min(0.95, resolved.duration_seconds / cursor * 0.94),
                )
                diagnostics.append(
                    _diagnostic(
                        code="timing_drift",
                        severity="error",
                        stage="audit",
                        message=(
                            f"Scene actions in beat {beat.id!r} end at "
                            f"{cursor:.3f}s, after {resolved.duration_seconds:.3f}s."
                        ),
                        beat_id=beat.id,
                        evidence={
                            "required_seconds": cursor,
                            "available_seconds": resolved.duration_seconds,
                            "factor": factor,
                            "target": "scene_actions",
                        },
                        suggested_repairs=["scale_timing"],
                        repairable=True,
                    )
                )

        for cue in program.cues:
            for action in cue.actions:
                if not isinstance(action, AnimateTrackerAction):
                    continue
                tracker = trackers.get(action.tracker)
                if tracker is None or not math.isclose(
                    action.end_value,
                    tracker.initial_value,
                    abs_tol=1e-12,
                ):
                    continue
                candidates = [
                    trace_targets[point_id].end_value
                    for point_id, point in tracked_points.items()
                    if point.tracker == action.tracker and point_id in trace_targets
                    and not math.isclose(
                        trace_targets[point_id].end_value,
                        tracker.initial_value,
                        abs_tol=1e-12,
                    )
                ]
                if candidates:
                    diagnostics.append(
                        _diagnostic(
                            code="frozen_motion",
                            severity="error",
                            stage="audit",
                            message=(
                                f"Tracker {action.tracker!r} is animated to its "
                                "existing value despite an authored trace interval."
                            ),
                            beat_id=beat.id,
                            object_id=action.tracker,
                            cue_id=cue.id,
                            evidence={"end_value": candidates[0]},
                            suggested_repairs=["set_tracker_end_value"],
                            repairable=True,
                        )
                    )
                else:
                    diagnostics.append(
                        _diagnostic(
                            code="frozen_motion",
                            severity="refusal",
                            stage="audit",
                            message=(
                                f"Tracker {action.tracker!r} has no authored "
                                "non-static target from which to infer a repair."
                            ),
                            beat_id=beat.id,
                            object_id=action.tracker,
                            cue_id=cue.id,
                        )
                    )
    return diagnostics


def build_repair_plan(
    project: ProjectSpec,
    diagnostics: list[Diagnostic],
    *,
    enable_regeneration: bool = False,
) -> RepairPlan:
    operations: list[RepairOperation] = []
    refused: list[str] = []
    regeneration_beats: set[str] = set()
    for diagnostic in diagnostics:
        if (
            enable_regeneration
            and diagnostic.beat_id
            and diagnostic.beat_id not in regeneration_beats
            and "regenerate_beat" in diagnostic.suggested_repairs
        ):
            from math_animation.planning import allowed_templates
            from math_animation.regeneration import regeneration_context

            context, _ = regeneration_context(
                project,
                diagnostic.beat_id,
                diagnostics,
            )
            operations.append(
                RegenerateBeatOperation(
                    beat_id=diagnostic.beat_id,
                    allowed_templates=allowed_templates(context),
                    reason_diagnostic_id=diagnostic.id,
                )
            )
            regeneration_beats.add(diagnostic.beat_id)
            continue
        if not diagnostic.repairable:
            if diagnostic.severity in {"error", "refusal"}:
                refused.append(diagnostic.id)
            continue
        evidence = diagnostic.evidence
        if diagnostic.code == "text_overflow" and "replacement" in evidence:
            operations.append(
                ShortenGeneratedCaptionOperation(
                    beat_id=diagnostic.beat_id or "",
                    block_id=diagnostic.object_id or "",
                    field=evidence["field"],
                    replacement=evidence["replacement"],
                    reason_diagnostic_id=diagnostic.id,
                )
            )
        elif diagnostic.code == "text_overflow" and "max_width" in evidence:
            operations.append(
                SetMaxWidthOperation(
                    beat_id=diagnostic.beat_id or "",
                    object_id=diagnostic.object_id or "",
                    max_width=evidence["max_width"],
                    wrapped_text=evidence.get("wrapped_text"),
                    reason_diagnostic_id=diagnostic.id,
                )
            )
        elif diagnostic.code == "text_overflow" and "clamped_position" in evidence:
            operations.append(
                RepositionObjectOperation(
                    beat_id=diagnostic.beat_id or "",
                    object_id=diagnostic.object_id or "",
                    position=tuple(evidence["clamped_position"]),
                    aspect_class=evidence.get("aspect_class"),
                    reason_diagnostic_id=diagnostic.id,
                )
            )
        elif diagnostic.code == "illegible_type":
            operations.append(
                SetResponsiveScaleOperation(
                    beat_id=diagnostic.beat_id or "",
                    object_id=diagnostic.object_id or "",
                    aspect_class=evidence["aspect_class"],
                    scale=evidence["scale"],
                    reason_diagnostic_id=diagnostic.id,
                )
            )
        elif diagnostic.code == "timing_drift" and diagnostic.beat_id:
            operations.append(
                ScaleTimingOperation(
                    beat_id=diagnostic.beat_id,
                    factor=evidence["factor"],
                    target=evidence["target"],
                    reason_diagnostic_id=diagnostic.id,
                )
            )
        elif diagnostic.code == "excessive_density":
            replacement = evidence["replacement"]
            operations.append(
                ReduceDensityOperation(
                    beat_id=diagnostic.beat_id or "",
                    object_id=diagnostic.object_id or "",
                    sample_count=(
                        replacement if isinstance(replacement, int) else None
                    ),
                    resolution=(
                        tuple(replacement)
                        if isinstance(replacement, (tuple, list))
                        else None
                    ),
                    reason_diagnostic_id=diagnostic.id,
                )
            )
        elif diagnostic.code == "frozen_motion":
            operations.append(
                SetTrackerEndValueOperation(
                    beat_id=diagnostic.beat_id or "",
                    cue_id=diagnostic.cue_id or "",
                    tracker_id=diagnostic.object_id or "",
                    end_value=evidence["end_value"],
                    reason_diagnostic_id=diagnostic.id,
                )
            )
        elif diagnostic.code == "template_mismatch":
            operations.append(
                SwapTemplateOperation(
                    beat_id=diagnostic.beat_id or "",
                    target_template="equation_reveal",
                    formula_id=evidence["formula_id"],
                    reason_diagnostic_id=diagnostic.id,
                )
            )
    affected = sorted({operation.beat_id for operation in operations})
    return RepairPlan(
        source_project_sha256=sha256_json(project),
        diagnostic_ids=[diagnostic.id for diagnostic in diagnostics],
        operations=operations,
        affected_beat_ids=affected,
        refused_diagnostic_ids=refused,
    )


def apply_repair_plan(
    project: ProjectSpec,
    plan: RepairPlan,
    *,
    regenerations: list[Any] | None = None,
) -> ProjectSpec:
    if sha256_json(project) != plan.source_project_sha256:
        raise ValueError("repair plan source hash does not match the project")
    payload = project.model_dump(mode="json")
    beats = {beat["id"]: beat for beat in payload["beats"]}
    formulas = {
        formula["id"]: formula
        for formula in payload["math_ledger"]["formulas"]
    }
    regeneration_by_reason = {
        artifact.reason_diagnostic_id: artifact
        for artifact in (regenerations or [])
    }

    for operation in plan.operations:
        beat = beats.get(operation.beat_id)
        if beat is None:
            raise ValueError(
                f"repair operation references unknown beat {operation.beat_id!r}"
            )
        if isinstance(operation, ShortenGeneratedCaptionOperation):
            block = next(
                (
                    item
                    for item in beat["blocks"]
                    if item["id"] == operation.block_id
                ),
                None,
            )
            if block is None or operation.field not in block:
                raise ValueError("caption repair target does not exist")
            block[operation.field] = operation.replacement
        elif isinstance(
            operation,
            (
                RepositionObjectOperation,
                SetResponsiveScaleOperation,
                SetFontSizeOperation,
                SetMaxWidthOperation,
                ReduceDensityOperation,
            ),
        ):
            objects = beat["scene_program"]["objects"]
            item = next(
                (
                    candidate
                    for candidate in objects
                    if candidate["id"] == operation.object_id
                ),
                None,
            )
            if item is None:
                raise ValueError("scene-object repair target does not exist")
            if isinstance(operation, RepositionObjectOperation):
                if operation.aspect_class is None:
                    item["position"] = list(operation.position)
                else:
                    override = item["responsive"].setdefault(
                        operation.aspect_class,
                        ResponsiveVisualOverride().model_dump(mode="json"),
                    )
                    override["position"] = list(operation.position)
            elif isinstance(operation, SetResponsiveScaleOperation):
                override = item["responsive"].setdefault(
                    operation.aspect_class,
                    ResponsiveVisualOverride().model_dump(mode="json"),
                )
                override["scale"] = operation.scale
            elif isinstance(operation, SetFontSizeOperation):
                item["font_size"] = operation.font_size
            elif isinstance(operation, SetMaxWidthOperation):
                item["max_width"] = operation.max_width
                if operation.wrapped_text is not None:
                    if "text" not in item:
                        raise ValueError(
                            "wrapped width repair requires a text object"
                        )
                    if operation.wrapped_text.split() != item["text"].split():
                        raise ValueError(
                            "wrapped width repair may only add line breaks"
                        )
                    item["text"] = operation.wrapped_text
            elif isinstance(operation, ReduceDensityOperation):
                if operation.sample_count is not None:
                    item["sample_count"] = operation.sample_count
                else:
                    item["resolution"] = list(operation.resolution or ())
        elif isinstance(operation, ScaleTimingOperation):
            if operation.target == "legacy_blocks":
                for block in beat["blocks"]:
                    block["run_time"] *= operation.factor
                    block["hold_seconds"] *= operation.factor
            else:
                for cue in beat["scene_program"]["cues"]:
                    for action in cue["actions"]:
                        action["run_time"] *= operation.factor
        elif isinstance(operation, SetTrackerEndValueOperation):
            cue = next(
                (
                    item
                    for item in beat["scene_program"]["cues"]
                    if item["id"] == operation.cue_id
                ),
                None,
            )
            if cue is None:
                raise ValueError("tracker repair cue does not exist")
            action = next(
                (
                    item
                    for item in cue["actions"]
                    if item["type"] == "animate_tracker"
                    and item["tracker"] == operation.tracker_id
                ),
                None,
            )
            if action is None:
                raise ValueError("tracker repair action does not exist")
            action["end_value"] = operation.end_value
        elif isinstance(operation, SwapTemplateOperation):
            if operation.target_template == "equation_reveal":
                formula = formulas.get(operation.formula_id or "")
                if formula is None:
                    raise ValueError("template swap formula does not exist")
                old = beat["blocks"][0]
                duration = beat["duration_seconds"] or 2.4
                run_time = min(1.0, max(0.45, duration * 0.32))
                beat["blocks"] = [
                    EquationRevealBlock(
                        id=old["id"],
                        run_time=run_time,
                        hold_seconds=max(0.0, duration - run_time - 0.35),
                        formula_id=formula["id"],
                        latex_parts=formula["latex_parts"],
                        caption=_shorten(beat["title"]),
                    ).model_dump(mode="json")
                ]
            else:
                old = beat["blocks"][0]
                beat["blocks"] = [
                    TitleCardBlock(
                        id=old["id"],
                        title=beat["title"],
                        run_time=old["run_time"],
                        hold_seconds=old["hold_seconds"],
                    ).model_dump(mode="json")
                ]
        elif isinstance(operation, RegenerateBeatOperation):
            from math_animation.planning import (
                make_visual_block,
                objective_for_decision,
            )
            artifact = regeneration_by_reason.get(
                operation.reason_diagnostic_id
            )
            if artifact is None:
                raise ValueError(
                    "regenerate_beat requires a matching typed regeneration "
                    "artifact"
                )
            if (
                artifact.source_project_sha256
                != plan.source_project_sha256
                or artifact.beat_id != operation.beat_id
                or artifact.decision.template not in operation.allowed_templates
            ):
                raise ValueError(
                    "regeneration artifact does not match its repair operation"
                )
            formula_parts = [
                " ".join(formulas[formula_id]["latex_parts"])
                for formula_id in artifact.selected_formula_ids
            ]
            duration = beat["duration_seconds"] or 2.4
            replacement = make_visual_block(
                artifact.decision,
                beat_id=operation.beat_id,
                text=artifact.context.text,
                formulas=formula_parts,
                formula_ids=artifact.selected_formula_ids,
                duration=duration,
            )
            beat["blocks"] = [replacement.model_dump(mode="json")]
            beat["scene_program"] = None
            beat["learning_objective"] = objective_for_decision(
                artifact.decision
            )
    return ProjectSpec.model_validate(payload)


def classify_exception(exc: Exception) -> Diagnostic:
    """Turn a pipeline exception into a stable diagnostic/refusal."""

    detail = str(exc)
    lowered = detail.lower()
    if "missing local input" in lowered or "narration audio" in lowered:
        code: DiagnosticCode = "missing_input"
        severity: DiagnosticSeverity = "refusal"
        stage = "preflight"
    elif "mathematical artifact validation failed" in lowered:
        code, severity, stage = "math_validation_failed", "refusal", "preflight"
    elif "latex preflight failed" in lowered:
        code, severity, stage = "invalid_latex", "refusal", "preflight"
    elif "non-finite" in lowered or "assertion" in lowered:
        code, severity, stage = "invariant_failure", "refusal", "render"
    elif "duration" in lowered or "needs" in lowered and "animation" in lowered:
        code, severity, stage = "timing_drift", "error", "compile"
    elif "screen-safe" in lowered or "effective font size" in lowered:
        code, severity, stage = "text_overflow", "error", "render"
    else:
        code, severity, stage = "render_failure", "refusal", "render"
    object_match = re.search(
        r"(?:for|object|surface)\s+['\"]?([A-Za-z0-9._-]+)",
        detail,
    )
    return _diagnostic(
        code=code,
        severity=severity,
        stage=stage,
        message=detail,
        object_id=object_match.group(1) if object_match else None,
        evidence={"exception_type": type(exc).__name__},
        repairable=False,
    )
