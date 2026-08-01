"""Versioned public contracts shared by authoring, Manim, and Nolan adapters."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from math_animation.safety import normalize_vector_expression

SCHEMA_VERSION = "math-animation.project.v1"
SCENE_PROGRAM_SCHEMA_VERSION = "math-animation.scene-program.v1"
TIMELINE_SCHEMA_VERSION = "math-animation.timeline.v1"
MANIFEST_SCHEMA_VERSION = "math-animation.manifest.v1"
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_BINDING_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


class StrictModel(BaseModel):
    """Base model that rejects misspelled or silently ignored fields."""

    model_config = ConfigDict(extra="forbid")


def _validate_id(value: str) -> str:
    if not _ID_PATTERN.fullmatch(value):
        raise ValueError(
            "must begin with an alphanumeric character and contain only "
            "letters, digits, period, underscore, or hyphen"
        )
    return value


class AssetRef(StrictModel):
    id: str
    path: str
    media_type: Literal["image", "video", "audio", "svg", "data", "other"]
    sha256: str | None = None
    attribution: str | None = None

    _asset_id = field_validator("id")(_validate_id)


class MathClaim(StrictModel):
    id: str
    statement: str
    verification: Literal["verified", "assumed", "needs_review"] = "needs_review"
    assumptions: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)

    _claim_id = field_validator("id")(_validate_id)


class FormulaSpec(StrictModel):
    id: str
    latex_parts: list[str] = Field(min_length=1)
    plain_language: str
    symbol_roles: dict[str, str] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)

    _formula_id = field_validator("id")(_validate_id)


class MathLedger(StrictModel):
    claims: list[MathClaim] = Field(default_factory=list)
    formulas: list[FormulaSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def ids_are_unique(self) -> "MathLedger":
        claim_ids = [claim.id for claim in self.claims]
        formula_ids = [formula.id for formula in self.formulas]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("math claim ids must be unique")
        if len(formula_ids) != len(set(formula_ids)):
            raise ValueError("formula ids must be unique")
        return self


class StyleTemplateRef(StrictModel):
    """Temporary bridge for Nolan's future style-template schema.

    ``raw`` is intentionally preserved verbatim. The style adapter consumes only
    recognized keys and includes the original payload in the run bundle.
    """

    template_id: str = "default"
    version: str = "placeholder-v1"
    provider: Literal["placeholder", "nolan"] = "placeholder"
    raw: dict[str, Any] = Field(default_factory=dict)

    _template_id = field_validator("template_id")(_validate_id)


class WordTiming(StrictModel):
    word: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def end_after_start(self) -> "WordTiming":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be greater than start_seconds")
        return self


class UtteranceTiming(StrictModel):
    id: str
    text: str
    words: list[WordTiming] = Field(default_factory=list)

    _utterance_id = field_validator("id")(_validate_id)

    @model_validator(mode="after")
    def words_are_ordered(self) -> "UtteranceTiming":
        previous_end = -1.0
        for word in self.words:
            if word.start_seconds < previous_end:
                raise ValueError("word timings must be ordered and non-overlapping")
            previous_end = word.end_seconds
        return self


class NarrationInput(StrictModel):
    """Narration and alignment produced outside this module, normally by Nolan."""

    provider: Literal["none", "nolan", "external"] = "none"
    audio_path: str | None = None
    utterances: list[UtteranceTiming] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_utterance_ids(self) -> "NarrationInput":
        ids = [utterance.id for utterance in self.utterances]
        if len(ids) != len(set(ids)):
            raise ValueError("utterance ids must be unique")
        return self


class SecondsAnchor(StrictModel):
    type: Literal["seconds"] = "seconds"
    seconds: float = Field(ge=0)
    scope: Literal["beat", "project"] = "beat"


class WordAnchor(StrictModel):
    type: Literal["word"] = "word"
    utterance_id: str
    word_index: int = Field(ge=0)
    edge: Literal["start", "end"] = "start"
    offset_seconds: float = 0.0

    _utterance_id = field_validator("utterance_id")(_validate_id)


class BeatFractionAnchor(StrictModel):
    type: Literal["beat_fraction"] = "beat_fraction"
    fraction: float = Field(ge=0, le=1)


TimelineAnchor = Annotated[
    SecondsAnchor | WordAnchor | BeatFractionAnchor,
    Field(discriminator="type"),
]


class CameraPose(StrictModel):
    phi_degrees: float = 0.0
    theta_degrees: float = -90.0
    zoom: float = Field(default=1.0, gt=0)
    frame_center: tuple[float, float, float] = (0.0, 0.0, 0.0)


class ScalarTrackerSpec(StrictModel):
    id: str
    initial_value: float = 0.0

    _tracker_id = field_validator("id")(_validate_id)


class RelativeLayout(StrictModel):
    relative_to: str
    direction: Literal["up", "down", "left", "right"]
    buffer: float = Field(default=0.35, ge=0)
    aligned_edge: Literal["up", "down", "left", "right"] | None = None

    _relative_to_id = field_validator("relative_to")(_validate_id)


class ResponsiveVisualOverride(StrictModel):
    """Optional authored adjustment selected from the output aspect class."""

    position: tuple[float, float, float] | None = None
    scale: float = Field(default=1.0, gt=0, le=4)
    layout: RelativeLayout | None = None


class VisualObjectBase(StrictModel):
    id: str
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    fixed_in_frame: bool = False
    layout: RelativeLayout | None = None
    responsive: dict[
        Literal["landscape", "square", "portrait"],
        ResponsiveVisualOverride,
    ] = Field(default_factory=dict)

    _visual_object_id = field_validator("id")(_validate_id)


class TextVisualObject(VisualObjectBase):
    type: Literal["text"] = "text"
    text: str
    role: str = "foreground"
    font_size: int | None = Field(default=None, ge=12, le=160)
    font: str | None = None
    max_width: float | None = Field(default=None, gt=0)
    weight: Literal["normal", "bold"] = "normal"

    @field_validator("text")
    @classmethod
    def reject_accidental_literal_newlines(cls, value: str) -> str:
        if "\\n" in value:
            raise ValueError(
                "text contains a literal backslash-n; use an actual newline "
                "for multiline text"
            )
        return value


class MathTexVisualObject(VisualObjectBase):
    type: Literal["math_tex"] = "math_tex"
    formula_id: str | None = None
    latex_parts: list[str] = Field(min_length=1)
    part_roles: list[str] = Field(default_factory=list)
    font_size: int | None = Field(default=None, ge=12, le=160)
    max_width: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def roles_match_parts(self) -> "MathTexVisualObject":
        if self.part_roles and len(self.part_roles) != len(self.latex_parts):
            raise ValueError("part_roles must be empty or match latex_parts")
        return self


class DotVisualObject(VisualObjectBase):
    type: Literal["dot"] = "dot"
    role: str = "primary"
    radius: float = Field(default=0.08, gt=0, le=1)


class LineVisualObject(VisualObjectBase):
    type: Literal["line"] = "line"
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    role: str = "foreground"
    stroke_width: float = Field(default=4.0, gt=0, le=30)


class ArrowVisualObject(VisualObjectBase):
    type: Literal["arrow"] = "arrow"
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    role: str = "primary"
    stroke_width: float = Field(default=4.0, gt=0, le=30)
    tip_length: float = Field(default=0.25, gt=0, le=1)


class CircleVisualObject(VisualObjectBase):
    type: Literal["circle"] = "circle"
    radius: float = Field(default=1.0, gt=0)
    role: str = "primary"
    stroke_width: float = Field(default=4.0, gt=0, le=30)
    fill_role: str | None = None
    fill_opacity: float = Field(default=0.0, ge=0, le=1)


class RectangleVisualObject(VisualObjectBase):
    type: Literal["rectangle"] = "rectangle"
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    role: str = "primary"
    stroke_width: float = Field(default=4.0, gt=0, le=30)
    fill_role: str | None = None
    fill_opacity: float = Field(default=0.0, ge=0, le=1)


class PolygonVisualObject(VisualObjectBase):
    type: Literal["polygon"] = "polygon"
    vertices: list[tuple[float, float, float]] = Field(min_length=3)
    role: str = "primary"
    stroke_width: float = Field(default=4.0, gt=0, le=30)
    fill_role: str | None = None
    fill_opacity: float = Field(default=0.0, ge=0, le=1)


class PolylineVisualObject(VisualObjectBase):
    type: Literal["polyline"] = "polyline"
    points: list[tuple[float, float, float]] = Field(min_length=2)
    role: str = "primary"
    stroke_width: float = Field(default=4.0, gt=0, le=30)
    closed: bool = False


class AxesVisualObject(VisualObjectBase):
    type: Literal["axes"] = "axes"
    x_range: tuple[float, float, float] = (-5.0, 5.0, 1.0)
    y_range: tuple[float, float, float] = (-3.0, 3.0, 1.0)
    x_length: float = Field(default=8.0, gt=0)
    y_length: float = Field(default=5.0, gt=0)
    role: str = "muted"
    tips: bool = False


class FunctionGraphVisualObject(VisualObjectBase):
    type: Literal["function_graph"] = "function_graph"
    axes: str
    expression: str
    x_range: tuple[float, float] | None = None
    role: str = "primary"
    stroke_width: float = Field(default=4.0, gt=0, le=30)

    _axes_id = field_validator("axes")(_validate_id)

    @field_validator("expression")
    @classmethod
    def expression_is_safe(cls, value: str) -> str:
        from math_animation.safety import normalize_math_expression

        normalize_math_expression(value)
        return value


class ParametricCurveVisualObject(VisualObjectBase):
    type: Literal["parametric_curve"] = "parametric_curve"
    parameter_range: tuple[float, float, float]
    x: str
    y: str
    z: str = "0"
    role: str = "primary"
    stroke_width: float = Field(default=4.0, gt=0, le=30)

    @model_validator(mode="after")
    def expressions_are_safe(self) -> "ParametricCurveVisualObject":
        if self.parameter_range[1] <= self.parameter_range[0]:
            raise ValueError("parameter range end must exceed start")
        for expression in (self.x, self.y, self.z):
            normalize_vector_expression(expression, variable_names={"t"})
        return self


class ParametricSurfaceVisualObject(VisualObjectBase):
    type: Literal["parametric_surface"] = "parametric_surface"
    u_range: tuple[float, float]
    v_range: tuple[float, float]
    x: str
    y: str
    z: str
    resolution: tuple[int, int] = (24, 24)
    role: str = "primary"
    fill_opacity: float = Field(default=0.65, ge=0, le=1)
    stroke_width: float = Field(default=0.5, ge=0, le=10)
    assertion_samples: int = Field(default=11, ge=3, le=101)
    maximum_absolute_coordinate: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def surface_is_well_formed(self) -> "ParametricSurfaceVisualObject":
        if self.u_range[1] <= self.u_range[0]:
            raise ValueError("u_range end must exceed start")
        if self.v_range[1] <= self.v_range[0]:
            raise ValueError("v_range end must exceed start")
        if min(self.resolution) < 2 or max(self.resolution) > 200:
            raise ValueError("surface resolution entries must be in [2, 200]")
        for expression in (self.x, self.y, self.z):
            normalize_vector_expression(expression, variable_names={"u", "v"})
        return self


class ScalarFieldFootprintVisualObject(VisualObjectBase):
    """Sampled cells satisfying ``expression <= threshold`` in the xy-plane."""

    type: Literal["scalar_field_footprint"] = "scalar_field_footprint"
    expression: str
    x_range: tuple[float, float]
    y_range: tuple[float, float]
    threshold: float = 0.0
    resolution: tuple[int, int] = (25, 17)
    role: str = "positive"
    fill_opacity: float = Field(default=0.28, gt=0, le=1)
    stroke_width: float = Field(default=0.0, ge=0, le=5)
    minimum_selected_fraction: float = Field(default=0.001, ge=0, le=1)
    maximum_selected_fraction: float = Field(default=0.999, ge=0, le=1)

    @model_validator(mode="after")
    def footprint_is_well_formed(self) -> "ScalarFieldFootprintVisualObject":
        if self.x_range[1] <= self.x_range[0]:
            raise ValueError("x_range end must exceed start")
        if self.y_range[1] <= self.y_range[0]:
            raise ValueError("y_range end must exceed start")
        if min(self.resolution) < 3 or max(self.resolution) > 200:
            raise ValueError("footprint resolution entries must be in [3, 200]")
        if self.maximum_selected_fraction < self.minimum_selected_fraction:
            raise ValueError(
                "maximum_selected_fraction must not be below the minimum"
            )
        normalize_vector_expression(
            self.expression,
            variable_names={"x", "y"},
        )
        return self


class IntervalVisualObject(VisualObjectBase):
    type: Literal["interval"] = "interval"
    start: float
    end: float
    left_closed: bool = True
    right_closed: bool = True
    role: str = "primary"
    stroke_width: float = Field(default=6.0, gt=0, le=30)
    marker_radius: float = Field(default=0.11, gt=0, le=0.5)
    label: str | None = None
    expected_width: float | None = Field(default=None, gt=0)
    absolute_tolerance: float = Field(default=1e-9, gt=0)

    @model_validator(mode="after")
    def interval_is_well_formed(self) -> "IntervalVisualObject":
        if self.end <= self.start:
            raise ValueError("interval end must exceed start")
        if (
            self.expected_width is not None
            and abs((self.end - self.start) - self.expected_width)
            > self.absolute_tolerance
        ):
            raise ValueError(
                "interval width does not agree with expected_width"
            )
        return self


class AnnotationVisualObject(VisualObjectBase):
    type: Literal["annotation"] = "annotation"
    text: str
    point: tuple[float, float, float]
    label_position: tuple[float, float, float]
    role: str = "changing"
    font_size: int | None = Field(default=None, ge=12, le=96)
    max_width: float | None = Field(default=None, gt=0)


class GroupVisualObject(VisualObjectBase):
    type: Literal["group"] = "group"
    members: list[str] = Field(min_length=1)

    @field_validator("members")
    @classmethod
    def members_are_valid_ids(cls, values: list[str]) -> list[str]:
        return [_validate_id(value) for value in values]

    @model_validator(mode="after")
    def members_are_unique(self) -> "GroupVisualObject":
        if len(self.members) != len(set(self.members)):
            raise ValueError("group members must be unique")
        return self


class TrackedPointVisualObject(VisualObjectBase):
    type: Literal["tracked_point"] = "tracked_point"
    tracker: str
    x: str
    y: str
    z: str = "0"
    role: str = "primary"
    radius: float = Field(default=0.07, gt=0, le=1)
    assertion_time_values: list[float] = Field(default_factory=list)
    maximum_absolute_coordinate: float | None = Field(default=None, gt=0)

    _tracker_id = field_validator("tracker")(_validate_id)

    @model_validator(mode="after")
    def expressions_are_safe(self) -> "TrackedPointVisualObject":
        for expression in (self.x, self.y, self.z):
            normalize_vector_expression(expression, variable_names={"t"})
        return self


class ConnectorVisualObject(VisualObjectBase):
    type: Literal["connector"] = "connector"
    start_object: str
    end_object: str
    arrow: bool = True
    role: str = "primary"
    stroke_width: float = Field(default=4.0, gt=0, le=30)
    buff: float = Field(default=0.0, ge=0)

    _start_id = field_validator("start_object")(_validate_id)
    _end_id = field_validator("end_object")(_validate_id)


class OrbitCircleVisualObject(VisualObjectBase):
    type: Literal["orbit_circle"] = "orbit_circle"
    center_object: str
    radius: float = Field(gt=0)
    role: str = "muted"
    stroke_width: float = Field(default=2.0, gt=0, le=30)
    opacity: float = Field(default=0.6, ge=0, le=1)

    _center_id = field_validator("center_object")(_validate_id)


class TraceVisualObject(VisualObjectBase):
    type: Literal["trace"] = "trace"
    target: str
    role: str = "changing"
    stroke_width: float = Field(default=3.0, gt=0, le=30)
    start_value: float = 0.0
    end_value: float = 1.0
    sample_count: int = Field(default=240, ge=8, le=4000)

    _target_id = field_validator("target")(_validate_id)

    @model_validator(mode="after")
    def interval_is_increasing(self) -> "TraceVisualObject":
        if self.end_value <= self.start_value:
            raise ValueError("end_value must be greater than start_value")
        return self


class ExpressionBinding(StrictModel):
    name: str
    expression: str

    @field_validator("name")
    @classmethod
    def name_is_a_safe_identifier(cls, value: str) -> str:
        if not _BINDING_PATTERN.fullmatch(value):
            raise ValueError(
                "must be a Python-style identifier beginning with a letter"
            )
        if value in {"i", "t", "pi", "np"}:
            raise ValueError(f"{value!r} is reserved")
        return value


class PointCloudState(StrictModel):
    id: str
    x: str
    y: str
    z: str

    _point_cloud_state_id = field_validator("id")(_validate_id)


class ProjectionAssertion(StrictModel):
    id: str
    source_state: str
    source_axes: tuple[
        Literal["x", "y", "z"],
        Literal["x", "y", "z"],
    ]
    target_state: str
    target_axes: tuple[
        Literal["x", "y", "z"],
        Literal["x", "y", "z"],
    ]
    time_values: list[float] = Field(default_factory=list)
    absolute_tolerance: float = Field(default=1e-9, gt=0)

    _assertion_id = field_validator("id")(_validate_id)
    _source_state_id = field_validator("source_state")(_validate_id)
    _target_state_id = field_validator("target_state")(_validate_id)

    @model_validator(mode="after")
    def axes_are_distinct(self) -> "ProjectionAssertion":
        if len(set(self.source_axes)) != 2 or len(set(self.target_axes)) != 2:
            raise ValueError("projection axes must contain two distinct axes")
        return self


class FinitePointAssertion(StrictModel):
    type: Literal["finite"] = "finite"
    id: str
    state: str
    time_values: list[float] = Field(default_factory=list)

    _assertion_id = field_validator("id")(_validate_id)
    _state_id = field_validator("state")(_validate_id)


class BoundsPointAssertion(StrictModel):
    type: Literal["bounds"] = "bounds"
    id: str
    state: str
    axis: Literal["x", "y", "z"]
    minimum: float
    maximum: float
    time_values: list[float] = Field(default_factory=list)

    _assertion_id = field_validator("id")(_validate_id)
    _state_id = field_validator("state")(_validate_id)

    @model_validator(mode="after")
    def maximum_exceeds_minimum(self) -> "BoundsPointAssertion":
        if self.maximum <= self.minimum:
            raise ValueError("bounds maximum must exceed minimum")
        return self


class SpreadPointAssertion(StrictModel):
    type: Literal["spread"] = "spread"
    id: str
    state: str
    axis: Literal["x", "y", "z"]
    minimum_span: float = Field(gt=0)
    time_values: list[float] = Field(default_factory=list)

    _assertion_id = field_validator("id")(_validate_id)
    _state_id = field_validator("state")(_validate_id)


PointCloudNumericAssertion = Annotated[
    FinitePointAssertion | BoundsPointAssertion | SpreadPointAssertion,
    Field(discriminator="type"),
]


class PointCloudVisualObject(VisualObjectBase):
    type: Literal["point_cloud"] = "point_cloud"
    sample_count: int = Field(ge=1, le=10_000)
    sample_start: float = 0.0
    sample_end: float
    time_value: float = 0.0
    bindings: list[ExpressionBinding] = Field(default_factory=list)
    states: list[PointCloudState] = Field(min_length=1)
    initial_state: str
    projection_assertions: list[ProjectionAssertion] = Field(default_factory=list)
    numeric_assertions: list[PointCloudNumericAssertion] = Field(
        default_factory=list
    )
    role: str = "primary"
    stroke_width: float = Field(default=2.0, gt=0, le=20)
    opacity: float = Field(default=1.0, ge=0, le=1)

    @model_validator(mode="after")
    def point_cloud_references_are_valid(self) -> "PointCloudVisualObject":
        if self.sample_end <= self.sample_start:
            raise ValueError("sample_end must be greater than sample_start")
        binding_names = [binding.name for binding in self.bindings]
        if len(binding_names) != len(set(binding_names)):
            raise ValueError("point-cloud binding names must be unique")
        state_ids = [state.id for state in self.states]
        if len(state_ids) != len(set(state_ids)):
            raise ValueError("point-cloud state ids must be unique")
        if self.initial_state not in state_ids:
            raise ValueError(
                f"initial_state {self.initial_state!r} is not a declared state"
            )
        assertion_ids = [item.id for item in self.projection_assertions]
        assertion_ids.extend(item.id for item in self.numeric_assertions)
        if len(assertion_ids) != len(set(assertion_ids)):
            raise ValueError("point-cloud assertion ids must be unique")
        for assertion in self.projection_assertions:
            if assertion.source_state not in state_ids:
                raise ValueError(
                    f"projection assertion {assertion.id!r} references unknown "
                    f"source state {assertion.source_state!r}"
                )
            if assertion.target_state not in state_ids:
                raise ValueError(
                    f"projection assertion {assertion.id!r} references unknown "
                    f"target state {assertion.target_state!r}"
                )
        for assertion in self.numeric_assertions:
            if assertion.state not in state_ids:
                raise ValueError(
                    f"numeric assertion {assertion.id!r} references unknown "
                    f"state {assertion.state!r}"
                )
        available_names = {"i", "t"}
        for binding in self.bindings:
            normalize_vector_expression(
                binding.expression,
                variable_names=available_names,
            )
            available_names.add(binding.name)
        for state in self.states:
            for expression in (state.x, state.y, state.z):
                normalize_vector_expression(
                    expression,
                    variable_names=available_names,
                )
        return self


VisualObject = Annotated[
    TextVisualObject
    | MathTexVisualObject
    | DotVisualObject
    | LineVisualObject
    | ArrowVisualObject
    | CircleVisualObject
    | RectangleVisualObject
    | PolygonVisualObject
    | PolylineVisualObject
    | AxesVisualObject
    | FunctionGraphVisualObject
    | ParametricCurveVisualObject
    | ParametricSurfaceVisualObject
    | ScalarFieldFootprintVisualObject
    | IntervalVisualObject
    | AnnotationVisualObject
    | GroupVisualObject
    | TrackedPointVisualObject
    | ConnectorVisualObject
    | OrbitCircleVisualObject
    | TraceVisualObject
    | PointCloudVisualObject,
    Field(discriminator="type"),
]


class SceneActionBase(StrictModel):
    run_time: float = Field(default=1.0, gt=0)


class CreateAction(SceneActionBase):
    type: Literal["create"] = "create"
    target: str
    animation: Literal["auto", "create", "fade_in", "write"] = "auto"

    _target_id = field_validator("target")(_validate_id)


class TransformPointCloudAction(SceneActionBase):
    type: Literal["transform_point_cloud"] = "transform_point_cloud"
    target: str
    state: str
    rate_func: Literal["smooth", "linear"] = "smooth"

    _target_id = field_validator("target")(_validate_id)
    _state_id = field_validator("state")(_validate_id)


class FadeOutAction(SceneActionBase):
    type: Literal["fade_out"] = "fade_out"
    target: str

    _target_id = field_validator("target")(_validate_id)


class FadeInAction(SceneActionBase):
    type: Literal["fade_in"] = "fade_in"
    target: str

    _target_id = field_validator("target")(_validate_id)


class AnimatePointCloudTimeAction(SceneActionBase):
    type: Literal["animate_point_cloud_time"] = "animate_point_cloud_time"
    target: str
    state: str
    end_time: float
    rate_func: Literal["smooth", "linear"] = "linear"

    _target_id = field_validator("target")(_validate_id)
    _state_id = field_validator("state")(_validate_id)


class MoveAction(SceneActionBase):
    type: Literal["move"] = "move"
    target: str
    position: tuple[float, float, float]
    rate_func: Literal["smooth", "linear"] = "smooth"

    _target_id = field_validator("target")(_validate_id)


class ScaleAction(SceneActionBase):
    type: Literal["scale"] = "scale"
    target: str
    factor: float = Field(gt=0)
    rate_func: Literal["smooth", "linear"] = "smooth"

    _target_id = field_validator("target")(_validate_id)


class RotateAction(SceneActionBase):
    type: Literal["rotate"] = "rotate"
    target: str
    angle_degrees: float
    axis: tuple[float, float, float] = (0.0, 0.0, 1.0)
    about_point: tuple[float, float, float] | None = None
    rate_func: Literal["smooth", "linear"] = "smooth"

    _target_id = field_validator("target")(_validate_id)

    @field_validator("axis")
    @classmethod
    def axis_is_nonzero(
        cls,
        value: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        if sum(component * component for component in value) == 0:
            raise ValueError("rotation axis must be nonzero")
        return value


class ApplyMatrixAction(SceneActionBase):
    type: Literal["apply_matrix"] = "apply_matrix"
    target: str
    matrix: tuple[
        tuple[float, float],
        tuple[float, float],
    ]
    expected_determinant: float | None = None
    determinant_tolerance: float = Field(default=1e-9, gt=0)

    _target_id = field_validator("target")(_validate_id)

    @model_validator(mode="after")
    def determinant_matches(self) -> "ApplyMatrixAction":
        if self.expected_determinant is not None:
            determinant = (
                self.matrix[0][0] * self.matrix[1][1]
                - self.matrix[0][1] * self.matrix[1][0]
            )
            if abs(determinant - self.expected_determinant) > (
                self.determinant_tolerance
            ):
                raise ValueError(
                    "matrix determinant does not match expected_determinant"
                )
        return self


class SetStyleAction(SceneActionBase):
    type: Literal["set_style"] = "set_style"
    target: str
    role: str | None = None
    opacity: float | None = Field(default=None, ge=0, le=1)
    stroke_width: float | None = Field(default=None, gt=0, le=30)

    _target_id = field_validator("target")(_validate_id)

    @model_validator(mode="after")
    def changes_something(self) -> "SetStyleAction":
        if self.role is None and self.opacity is None and self.stroke_width is None:
            raise ValueError("set_style action must change at least one property")
        return self


class TransformMathAction(SceneActionBase):
    type: Literal["transform_math"] = "transform_math"
    target: str
    formula_id: str | None = None
    latex_parts: list[str] = Field(min_length=1)
    part_roles: list[str] = Field(default_factory=list)
    rate_func: Literal["smooth", "linear"] = "smooth"

    _target_id = field_validator("target")(_validate_id)

    @model_validator(mode="after")
    def roles_match_parts(self) -> "TransformMathAction":
        if self.part_roles and len(self.part_roles) != len(self.latex_parts):
            raise ValueError("part_roles must be empty or match latex_parts")
        return self


class AnimateTrackerAction(SceneActionBase):
    type: Literal["animate_tracker"] = "animate_tracker"
    tracker: str
    end_value: float
    rate_func: Literal["smooth", "linear"] = "linear"

    _tracker_id = field_validator("tracker")(_validate_id)


class CameraAction(SceneActionBase):
    type: Literal["camera"] = "camera"
    phi_degrees: float | None = None
    theta_degrees: float | None = None
    zoom: float | None = Field(default=None, gt=0)
    frame_center: tuple[float, float, float] | None = None

    @model_validator(mode="after")
    def changes_something(self) -> "CameraAction":
        if (
            self.phi_degrees is None
            and self.theta_degrees is None
            and self.zoom is None
            and self.frame_center is None
        ):
            raise ValueError("camera action must change at least one camera property")
        return self


SceneAction = Annotated[
    CreateAction
    | TransformPointCloudAction
    | AnimatePointCloudTimeAction
    | MoveAction
    | ScaleAction
    | RotateAction
    | ApplyMatrixAction
    | SetStyleAction
    | TransformMathAction
    | AnimateTrackerAction
    | FadeInAction
    | FadeOutAction
    | CameraAction,
    Field(discriminator="type"),
]


class ActionCue(StrictModel):
    id: str
    start_at: TimelineAnchor | None = None
    mode: Literal["sequential", "parallel"] = "sequential"
    actions: list[SceneAction] = Field(min_length=1)

    _cue_id = field_validator("id")(_validate_id)

    @model_validator(mode="after")
    def parallel_actions_share_a_clock(self) -> "ActionCue":
        if self.mode == "parallel":
            run_times = {round(action.run_time, 9) for action in self.actions}
            if len(run_times) != 1:
                raise ValueError("parallel actions must use the same run_time")
            camera_count = sum(
                isinstance(action, CameraAction) for action in self.actions
            )
            if camera_count > 1:
                raise ValueError("a parallel cue may contain at most one camera action")
        return self

    @property
    def duration_seconds(self) -> float:
        durations = [action.run_time for action in self.actions]
        return max(durations) if self.mode == "parallel" else sum(durations)


class SceneProgram(StrictModel):
    schema_version: Literal["math-animation.scene-program.v1"] = (
        SCENE_PROGRAM_SCHEMA_VERSION
    )
    scene_kind: Literal["2d", "3d"] = "2d"
    initial_camera: CameraPose | None = None
    enforce_safe_area: bool = True
    safe_area_margin: float = Field(default=0.15, ge=0, le=2)
    minimum_effective_font_size: float = Field(default=16.0, ge=8, le=48)
    trackers: list[ScalarTrackerSpec] = Field(default_factory=list)
    objects: list[VisualObject] = Field(min_length=1)
    cues: list[ActionCue] = Field(min_length=1)

    @model_validator(mode="after")
    def references_and_lifetimes_are_valid(self) -> "SceneProgram":
        object_ids = [item.id for item in self.objects]
        if len(object_ids) != len(set(object_ids)):
            raise ValueError("scene object ids must be unique")
        cue_ids = [cue.id for cue in self.cues]
        if len(cue_ids) != len(set(cue_ids)):
            raise ValueError("scene cue ids must be unique")
        if self.scene_kind == "2d" and self.initial_camera is not None:
            raise ValueError("initial_camera is only valid for a 3d scene")

        tracker_ids = [tracker.id for tracker in self.trackers]
        if len(tracker_ids) != len(set(tracker_ids)):
            raise ValueError("scene tracker ids must be unique")
        trackers = set(tracker_ids)
        objects = {item.id: item for item in self.objects}
        declared: set[str] = set()
        for item in self.objects:
            layouts = [item.layout] + [
                override.layout for override in item.responsive.values()
            ]
            for layout in (candidate for candidate in layouts if candidate is not None):
                if layout.relative_to not in declared:
                    raise ValueError(
                        f"object {item.id!r} layout must reference an earlier "
                        f"object, got {layout.relative_to!r}"
                    )
            if isinstance(item, FunctionGraphVisualObject):
                axes = objects.get(item.axes)
                if item.axes not in declared or not isinstance(axes, AxesVisualObject):
                    raise ValueError(
                        f"function graph {item.id!r} must reference earlier axes"
                    )
            if isinstance(item, GroupVisualObject):
                missing = [member for member in item.members if member not in declared]
                if missing:
                    raise ValueError(
                        f"group {item.id!r} members must be declared earlier: "
                        f"{missing!r}"
                    )
            if isinstance(item, TrackedPointVisualObject):
                if item.tracker not in trackers:
                    raise ValueError(
                        f"tracked point {item.id!r} references unknown tracker "
                        f"{item.tracker!r}"
                    )
            if isinstance(item, ConnectorVisualObject):
                if (
                    item.start_object not in declared
                    or item.end_object not in declared
                ):
                    raise ValueError(
                        f"connector {item.id!r} endpoints must be declared earlier"
                    )
            if isinstance(item, OrbitCircleVisualObject):
                if item.center_object not in declared:
                    raise ValueError(
                        f"orbit circle {item.id!r} center must be declared earlier"
                    )
            if isinstance(item, TraceVisualObject):
                target = objects.get(item.target)
                if (
                    item.target not in declared
                    or not isinstance(target, TrackedPointVisualObject)
                ):
                    raise ValueError(
                        f"trace {item.id!r} target must be an earlier tracked point"
                    )
            declared.add(item.id)

        created: set[str] = set()
        for cue in self.cues:
            before_cue = set(created)
            if cue.mode == "parallel":
                parallel_creates = [
                    action.target
                    for action in cue.actions
                    if isinstance(action, CreateAction)
                ]
                if len(parallel_creates) != len(set(parallel_creates)):
                    raise ValueError(
                        "a parallel cue cannot create the same object twice"
                    )
            for action in cue.actions:
                if isinstance(action, CameraAction):
                    if self.scene_kind != "3d":
                        raise ValueError("camera actions require scene_kind='3d'")
                    continue
                if isinstance(action, AnimateTrackerAction):
                    if action.tracker not in trackers:
                        raise ValueError(
                            f"action references unknown tracker {action.tracker!r}"
                        )
                    continue
                target = objects.get(action.target)
                if target is None:
                    raise ValueError(
                        f"action references unknown object {action.target!r}"
                    )
                if isinstance(action, CreateAction):
                    if action.target in created:
                        raise ValueError(
                            f"object {action.target!r} may only be created once"
                        )
                    if cue.mode == "parallel" and action.target in before_cue:
                        raise ValueError(
                            f"object {action.target!r} was already created"
                        )
                    if cue.mode == "sequential":
                        created.add(action.target)
                    continue
                available = before_cue if cue.mode == "parallel" else created
                if action.target not in available:
                    raise ValueError(
                        f"object {action.target!r} is used before it is created"
                    )
                if isinstance(
                    action,
                    (TransformPointCloudAction, AnimatePointCloudTimeAction),
                ):
                    if not isinstance(target, PointCloudVisualObject):
                        raise ValueError(
                            f"{action.type} target must be a point_cloud"
                        )
                    if action.state not in {state.id for state in target.states}:
                        raise ValueError(
                            f"point cloud {target.id!r} has no state "
                            f"{action.state!r}"
                        )
                if isinstance(action, TransformMathAction):
                    if not isinstance(target, MathTexVisualObject):
                        raise ValueError(
                            "transform_math target must be a math_tex object"
                        )
            if cue.mode == "parallel":
                created.update(
                    action.target
                    for action in cue.actions
                    if isinstance(action, CreateAction)
                )
        return self


class BlockBase(StrictModel):
    id: str
    start_at: TimelineAnchor | None = None
    run_time: float = Field(default=1.0, gt=0)
    hold_seconds: float = Field(default=0.0, ge=0)
    clear_at_end: bool = True
    """Fade the block's objects out when it finishes.

    True is right for a STANDALONE video, where consecutive beats share one canvas and a beat that
    did not clean up would bleed into the next. It is wrong wherever the CUT is the transition: the
    clip ends on an empty frame, and if the following scene waits on a word-anchored reveal the
    viewer sees a hole. Measured in a NOLAN essay: ink fell to 0.000% for ~0.9s at one cut, and no
    gate noticed — a freeze guard looks for a STUCK frame, not an empty one.

    Set False to hold the final state through the block's last frame instead.
    """

    _block_id = field_validator("id")(_validate_id)


class TitleCardBlock(BlockBase):
    type: Literal["title_card"] = "title_card"
    title: str
    subtitle: str | None = None


class EquationRevealBlock(BlockBase):
    type: Literal["equation_reveal"] = "equation_reveal"
    formula_id: str | None = None
    latex_parts: list[str] = Field(min_length=1)
    part_roles: list[str] = Field(default_factory=list)
    caption: str | None = None

    @model_validator(mode="after")
    def roles_match_parts(self) -> "EquationRevealBlock":
        if self.part_roles and len(self.part_roles) != len(self.latex_parts):
            raise ValueError("part_roles must be empty or match latex_parts")
        return self


class EquationTransformBlock(BlockBase):
    type: Literal["equation_transform"] = "equation_transform"
    from_latex: list[str] = Field(min_length=1)
    to_latex: list[str] = Field(min_length=1)
    caption: str | None = None


class FunctionPlotBlock(BlockBase):
    type: Literal["function_plot"] = "function_plot"
    expression: str
    x_range: tuple[float, float, float] = (-4.0, 4.0, 1.0)
    y_range: tuple[float, float, float] = (-3.0, 5.0, 1.0)
    label_latex: str | None = None
    role: str = "primary"


class SecantToTangentBlock(BlockBase):
    type: Literal["secant_to_tangent"] = "secant_to_tangent"
    expression: str = "0.25*x**2"
    x_range: tuple[float, float, float] = (-4.0, 4.0, 1.0)
    y_range: tuple[float, float, float] = (-2.0, 5.0, 1.0)
    x0: float = 0.5
    h_start: float = Field(default=2.5, gt=0)
    h_end: float = Field(default=0.08, gt=0)
    caption: str | None = None


class NumberLineBlock(BlockBase):
    type: Literal["number_line"] = "number_line"
    x_range: tuple[float, float, float] = (-5.0, 5.0, 1.0)
    values: list[float] = Field(min_length=1)
    labels: list[str] = Field(default_factory=list)
    role: str = "primary"

    @model_validator(mode="after")
    def labels_match_values(self) -> "NumberLineBlock":
        if self.labels and len(self.labels) != len(self.values):
            raise ValueError("labels must be empty or match values")
        return self


class CustomSceneBlock(BlockBase):
    """Audited escape hatch; disabled unless compilation explicitly enables it."""

    type: Literal["custom_scene"] = "custom_scene"
    scene_class: str
    source: str


VisualBlock = Annotated[
    TitleCardBlock
    | EquationRevealBlock
    | EquationTransformBlock
    | FunctionPlotBlock
    | SecantToTangentBlock
    | NumberLineBlock
    | CustomSceneBlock,
    Field(discriminator="type"),
]


class BeatSpec(StrictModel):
    id: str
    title: str
    learning_objective: str
    narration_utterance_id: str | None = None
    duration_seconds: float | None = Field(default=None, gt=0)
    blocks: list[VisualBlock] = Field(default_factory=list)
    scene_program: SceneProgram | None = None

    _beat_id = field_validator("id")(_validate_id)

    @model_validator(mode="after")
    def uses_one_visual_representation(self) -> "BeatSpec":
        if bool(self.blocks) == (self.scene_program is not None):
            raise ValueError(
                "beat must define exactly one of blocks or scene_program"
            )
        return self


class RequestSpec(StrictModel):
    source_kind: Literal["topic", "script", "screenplay"] = "screenplay"
    content: str
    audience: str = "general"
    script_policy: Literal["locked", "review", "coauthor"] = "review"
    target_duration_seconds: float | None = Field(default=None, gt=0)


class RenderSettings(StrictModel):
    renderer: Literal["cairo", "opengl"] = "cairo"
    quality: Literal["l", "m", "h", "p", "k"] = "l"
    pixel_width: int = Field(default=1920, ge=320, le=7680)
    pixel_height: int = Field(default=1080, ge=240, le=4320)
    frame_rate: int = Field(default=30, ge=1, le=120)
    transparent: bool = False
    seed: int = 17


class ProjectSpec(StrictModel):
    schema_version: Literal["math-animation.project.v1"] = SCHEMA_VERSION
    project_id: str
    title: str
    request: RequestSpec
    math_ledger: MathLedger = Field(default_factory=MathLedger)
    narration: NarrationInput = Field(default_factory=NarrationInput)
    style: StyleTemplateRef = Field(default_factory=StyleTemplateRef)
    assets: list[AssetRef] = Field(default_factory=list)
    beats: list[BeatSpec] = Field(min_length=1)
    render: RenderSettings = Field(default_factory=RenderSettings)

    _project_id = field_validator("project_id")(_validate_id)

    @model_validator(mode="after")
    def references_are_valid(self) -> "ProjectSpec":
        beat_ids = [beat.id for beat in self.beats]
        if len(beat_ids) != len(set(beat_ids)):
            raise ValueError("beat ids must be unique")
        utterance_ids = {item.id for item in self.narration.utterances}
        formulas = {item.id: item for item in self.math_ledger.formulas}
        for beat in self.beats:
            if (
                beat.narration_utterance_id is not None
                and beat.narration_utterance_id not in utterance_ids
            ):
                raise ValueError(
                    f"beat {beat.id!r} references unknown narration utterance "
                    f"{beat.narration_utterance_id!r}"
                )
            for block in beat.blocks:
                if isinstance(block, EquationRevealBlock) and block.formula_id:
                    if block.formula_id not in formulas:
                        raise ValueError(
                            f"block {block.id!r} references unknown formula "
                            f"{block.formula_id!r}"
                        )
                    if block.latex_parts != formulas[block.formula_id].latex_parts:
                        raise ValueError(
                            f"block {block.id!r} does not preserve the ledger's "
                            f"latex_parts for formula {block.formula_id!r}"
                        )
            if beat.scene_program is not None:
                for item in beat.scene_program.objects:
                    if (
                        isinstance(item, MathTexVisualObject)
                        and item.formula_id is not None
                    ):
                        if item.formula_id not in formulas:
                            raise ValueError(
                                f"scene object {item.id!r} references unknown "
                                f"formula {item.formula_id!r}"
                            )
                        if (
                            item.latex_parts
                            != formulas[item.formula_id].latex_parts
                        ):
                            raise ValueError(
                                f"scene object {item.id!r} does not preserve the "
                                f"ledger's latex_parts for formula "
                                f"{item.formula_id!r}"
                            )
                for cue in beat.scene_program.cues:
                    for action in cue.actions:
                        if (
                            isinstance(action, TransformMathAction)
                            and action.formula_id is not None
                        ):
                            if action.formula_id not in formulas:
                                raise ValueError(
                                    "scene action references unknown formula "
                                    f"{action.formula_id!r}"
                                )
                            if (
                                action.latex_parts
                                != formulas[action.formula_id].latex_parts
                            ):
                                raise ValueError(
                                    "transform_math action does not preserve "
                                    f"ledger formula {action.formula_id!r}"
                                )
        return self


class TimelineClip(StrictModel):
    beat_id: str
    scene_class: str
    source_path: str
    expected_media_path: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    duration_seconds: float = Field(gt=0)
    alpha: bool = False


class TimelineArtifact(StrictModel):
    schema_version: Literal["math-animation.timeline.v1"] = TIMELINE_SCHEMA_VERSION
    project_id: str
    frame_rate: int
    pixel_width: int
    pixel_height: int
    audio_path: str | None = None
    clips: list[TimelineClip]
    duration_seconds: float = Field(ge=0)


class RunManifest(StrictModel):
    schema_version: Literal["math-animation.manifest.v1"] = MANIFEST_SCHEMA_VERSION
    run_id: str
    project_id: str
    status: Literal["compiling", "compiled", "rendering", "completed", "failed"]
    created_utc: str
    completed_utc: str | None = None
    project_sha256: str
    style_sha256: str
    compiler_version: str
    allow_custom_python: bool = False
    artifacts: list[str] = Field(default_factory=list)
    renders: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
