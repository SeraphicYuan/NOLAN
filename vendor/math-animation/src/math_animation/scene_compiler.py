"""Deterministic compiler for the persistent SceneProgram visual IR."""

from __future__ import annotations

from dataclasses import dataclass

from math_animation.contracts import (
    ActionCue,
    AnimatePointCloudTimeAction,
    AnimateTrackerAction,
    AnnotationVisualObject,
    ApplyMatrixAction,
    ArrowVisualObject,
    AxesVisualObject,
    BoundsPointAssertion,
    CameraAction,
    CircleVisualObject,
    ConnectorVisualObject,
    CreateAction,
    DotVisualObject,
    FadeInAction,
    FadeOutAction,
    FinitePointAssertion,
    FunctionGraphVisualObject,
    GroupVisualObject,
    IntervalVisualObject,
    LineVisualObject,
    MathTexVisualObject,
    MoveAction,
    OrbitCircleVisualObject,
    ParametricCurveVisualObject,
    ParametricSurfaceVisualObject,
    PointCloudVisualObject,
    PolygonVisualObject,
    PolylineVisualObject,
    RectangleVisualObject,
    RotateAction,
    ScaleAction,
    ScalarFieldFootprintVisualObject,
    SceneAction,
    SceneProgram,
    SetStyleAction,
    SpreadPointAssertion,
    TextVisualObject,
    TraceVisualObject,
    TrackedPointVisualObject,
    TransformMathAction,
    TransformPointCloudAction,
    VisualObject,
)
from math_animation.safety import (
    normalize_math_expression,
    normalize_vector_expression,
)
from math_animation.style import StyleTokens
from math_animation.timing import ResolvedBeat, resolve_anchor


@dataclass(frozen=True)
class CompiledSceneProgram:
    lines: list[str]
    scene_base: str
    duration_seconds: float


@dataclass(frozen=True)
class _ObjectNames:
    variable: str
    states: dict[str, str]
    state_functions: dict[str, str]
    samples: str | None
    time_tracker: str | None


@dataclass(frozen=True)
class _CompiledAnimation:
    setup_lines: list[str]
    expression: str
    cleanup_lines: list[str]


def _point(value: tuple[float, float, float]) -> str:
    return f"np.array({list(value)!r}, dtype=float)"


def _font_argument(font: str | None) -> str:
    return (
        f", font={font!r}"
        if font is not None
        else ""
    )


def _declare_text(
    item: TextVisualObject,
    names: _ObjectNames,
    style: StyleTokens,
) -> list[str]:
    font_size = item.font_size or style.typography.body_size
    font = item.font or style.typography.font
    weight = ", weight=BOLD" if item.weight == "bold" else ""
    lines = [
        f"{names.variable} = Text({item.text!r}, font_size={font_size}, "
        f"color={style.color_for(item.role)!r}{_font_argument(font)}{weight})",
    ]
    if item.max_width is not None:
        lines.extend(
            [
                f"if {names.variable}.width > {item.max_width!r}:",
                f"    {names.variable}.scale_to_fit_width({item.max_width!r})",
            ]
        )
    lines.append(f"{names.variable}.move_to({_point(item.position)})")
    return lines


def _declare_math_tex(
    item: MathTexVisualObject,
    names: _ObjectNames,
    style: StyleTokens,
) -> list[str]:
    font_size = item.font_size or style.typography.math_size
    parts = ", ".join(repr(part) for part in item.latex_parts)
    lines = [
        f"{names.variable} = MathTex({parts}, font_size={font_size}, "
        f"color={style.foreground!r})",
    ]
    if item.max_width is not None:
        lines.extend(
            [
                f"if {names.variable}.width > {item.max_width!r}:",
                f"    {names.variable}.scale_to_fit_width({item.max_width!r})",
            ]
        )
    lines.append(f"{names.variable}.move_to({_point(item.position)})")
    for index, role in enumerate(item.part_roles):
        lines.append(
            f"{names.variable}[{index}].set_color({style.color_for(role)!r})"
        )
    return lines


def _role_fill(
    *,
    fill_role: str | None,
    fill_opacity: float,
    style: StyleTokens,
) -> str:
    if fill_role is None or fill_opacity == 0:
        return ""
    return (
        f", fill_color={style.color_for(fill_role)!r}, "
        f"fill_opacity={fill_opacity!r}"
    )


def _shifted(
    point: tuple[float, float, float],
    position: tuple[float, float, float],
) -> str:
    return f"({_point(point)} + {_point(position)})"


def _declare_dot(
    item: DotVisualObject,
    names: _ObjectNames,
    style: StyleTokens,
) -> list[str]:
    return [
        f"{names.variable} = Dot({_point(item.position)}, "
        f"radius={item.radius!r}, color={style.color_for(item.role)!r})"
    ]


def _declare_line(
    item: LineVisualObject | ArrowVisualObject,
    names: _ObjectNames,
    style: StyleTokens,
) -> list[str]:
    constructor = "Arrow" if isinstance(item, ArrowVisualObject) else "Line"
    extra = f", tip_length={item.tip_length!r}" if isinstance(item, ArrowVisualObject) else ""
    return [
        f"{names.variable} = {constructor}("
        f"{_shifted(item.start, item.position)}, "
        f"{_shifted(item.end, item.position)}, "
        f"color={style.color_for(item.role)!r}, "
        f"stroke_width={item.stroke_width!r}{extra})"
    ]


def _declare_circle(
    item: CircleVisualObject,
    names: _ObjectNames,
    style: StyleTokens,
) -> list[str]:
    return [
        f"{names.variable} = Circle(radius={item.radius!r}, "
        f"color={style.color_for(item.role)!r}, "
        f"stroke_width={item.stroke_width!r}"
        f"{_role_fill(fill_role=item.fill_role, fill_opacity=item.fill_opacity, style=style)})",
        f"{names.variable}.move_to({_point(item.position)})",
    ]


def _declare_rectangle(
    item: RectangleVisualObject,
    names: _ObjectNames,
    style: StyleTokens,
) -> list[str]:
    return [
        f"{names.variable} = Rectangle(width={item.width!r}, "
        f"height={item.height!r}, color={style.color_for(item.role)!r}, "
        f"stroke_width={item.stroke_width!r}"
        f"{_role_fill(fill_role=item.fill_role, fill_opacity=item.fill_opacity, style=style)})",
        f"{names.variable}.move_to({_point(item.position)})",
    ]


def _declare_polygon(
    item: PolygonVisualObject,
    names: _ObjectNames,
    style: StyleTokens,
) -> list[str]:
    vertices = ", ".join(
        _shifted(vertex, item.position) for vertex in item.vertices
    )
    return [
        f"{names.variable} = Polygon({vertices}, "
        f"color={style.color_for(item.role)!r}, "
        f"stroke_width={item.stroke_width!r}"
        f"{_role_fill(fill_role=item.fill_role, fill_opacity=item.fill_opacity, style=style)})"
    ]


def _declare_polyline(
    item: PolylineVisualObject,
    names: _ObjectNames,
    style: StyleTokens,
) -> list[str]:
    points = list(item.points)
    if item.closed:
        points.append(points[0])
    rendered = ", ".join(_shifted(point, item.position) for point in points)
    return [
        f"{names.variable} = VMobject(color={style.color_for(item.role)!r}, "
        f"stroke_width={item.stroke_width!r})",
        f"{names.variable}.set_points_as_corners([{rendered}])",
    ]


def _declare_axes(
    item: AxesVisualObject,
    names: _ObjectNames,
    style: StyleTokens,
) -> list[str]:
    return [
        f"{names.variable} = Axes(x_range={item.x_range!r}, "
        f"y_range={item.y_range!r}, x_length={item.x_length!r}, "
        f"y_length={item.y_length!r}, tips={item.tips!r}, "
        f"axis_config={{'color': {style.color_for(item.role)!r}}})",
        f"{names.variable}.move_to({_point(item.position)})",
    ]


def _declare_function_graph(
    item: FunctionGraphVisualObject,
    names: _ObjectNames,
    all_names: dict[str, _ObjectNames],
    style: StyleTokens,
) -> list[str]:
    expression = normalize_math_expression(item.expression)
    range_argument = (
        f", x_range={item.x_range!r}" if item.x_range is not None else ""
    )
    lines = [
        f"{names.variable} = {all_names[item.axes].variable}.plot("
        f"lambda x: {expression}{range_argument}, "
        f"color={style.color_for(item.role)!r}, "
        f"stroke_width={item.stroke_width!r})"
    ]
    if item.position != (0.0, 0.0, 0.0):
        lines.append(f"{names.variable}.shift({_point(item.position)})")
    return lines


def _declare_parametric_curve(
    item: ParametricCurveVisualObject,
    names: _ObjectNames,
    style: StyleTokens,
) -> list[str]:
    components = [
        normalize_vector_expression(expression, variable_names={"t"})
        for expression in (item.x, item.y, item.z)
    ]
    return [
        f"{names.variable} = ParametricFunction("
        f"lambda t: np.array([{components[0]}, {components[1]}, "
        f"{components[2]}], dtype=float) + {_point(item.position)}, "
        f"t_range={item.parameter_range!r}, "
        f"color={style.color_for(item.role)!r}, "
        f"stroke_width={item.stroke_width!r})"
    ]


def _declare_parametric_surface(
    item: ParametricSurfaceVisualObject,
    names: _ObjectNames,
    style: StyleTokens,
) -> list[str]:
    function = f"{names.variable}_surface_point"
    u_samples = f"{names.variable}_u_samples"
    v_samples = f"{names.variable}_v_samples"
    sampled = f"{names.variable}_sampled_points"
    components = [
        normalize_vector_expression(expression, variable_names={"u", "v"})
        for expression in (item.x, item.y, item.z)
    ]
    lines = [
        f"def {function}(u, v):",
        f"    return np.array([{components[0]}, {components[1]}, "
        f"{components[2]}], dtype=float) + {_point(item.position)}",
        f"{u_samples} = np.linspace({item.u_range[0]!r}, "
        f"{item.u_range[1]!r}, {item.assertion_samples})",
        f"{v_samples} = np.linspace({item.v_range[0]!r}, "
        f"{item.v_range[1]!r}, {item.assertion_samples})",
        f"{sampled} = np.array([",
        f"    {function}(u, v) for u in {u_samples} for v in {v_samples}",
        "], dtype=float)",
        f"if not np.all(np.isfinite({sampled})):",
        f"    raise ValueError('surface {item.id} contains non-finite samples')",
    ]
    if item.maximum_absolute_coordinate is not None:
        lines.extend(
            [
                f"if np.max(np.abs({sampled})) > "
                f"{item.maximum_absolute_coordinate!r}:",
                f"    raise ValueError('surface {item.id} exceeds coordinate bound')",
            ]
        )
    lines.append(
        f"{names.variable} = Surface("
        f"lambda u, v: {function}(u, v), "
        f"u_range={item.u_range!r}, v_range={item.v_range!r}, "
        f"resolution={item.resolution!r}, "
        f"fill_color={style.color_for(item.role)!r}, "
        f"fill_opacity={item.fill_opacity!r}, "
        f"stroke_color={style.color_for(item.role)!r}, "
        f"stroke_width={item.stroke_width!r})"
    )
    return lines


def _declare_scalar_field_footprint(
    item: ScalarFieldFootprintVisualObject,
    names: _ObjectNames,
    style: StyleTokens,
) -> list[str]:
    expression = normalize_vector_expression(
        item.expression,
        variable_names={"x", "y"},
    )
    nx, ny = item.resolution
    dx = (item.x_range[1] - item.x_range[0]) / nx
    dy = (item.y_range[1] - item.y_range[0]) / ny
    x_samples = f"{names.variable}_x_samples"
    y_samples = f"{names.variable}_y_samples"
    values = f"{names.variable}_values"
    selected = f"{names.variable}_selected"
    cells = f"{names.variable}_cells"
    return [
        f"{x_samples} = np.linspace({item.x_range[0] + dx / 2!r}, "
        f"{item.x_range[1] - dx / 2!r}, {nx})",
        f"{y_samples} = np.linspace({item.y_range[0] + dy / 2!r}, "
        f"{item.y_range[1] - dy / 2!r}, {ny})",
        f"{values} = np.array([[{expression} for x in {x_samples}] "
        f"for y in {y_samples}], dtype=float)",
        f"if not np.all(np.isfinite({values})):",
        f"    raise ValueError('footprint {item.id} contains non-finite samples')",
        f"{selected} = {values} <= {item.threshold!r}",
        f"if not ({item.minimum_selected_fraction!r} <= "
        f"np.mean({selected}) <= {item.maximum_selected_fraction!r}):",
        f"    raise ValueError('footprint {item.id} selected fraction is invalid')",
        f"{cells} = []",
        f"for row, y in enumerate({y_samples}):",
        f"    for column, x in enumerate({x_samples}):",
        f"        if {selected}[row, column]:",
        f"            cell = Rectangle(width={dx!r}, height={dy!r}, "
        f"stroke_width={item.stroke_width!r}, "
        f"fill_color={style.color_for(item.role)!r}, "
        f"fill_opacity={item.fill_opacity!r})",
        f"            cell.move_to(np.array([x, y, 0.0], dtype=float) + "
        f"{_point(item.position)})",
        f"            {cells}.append(cell)",
        f"{names.variable} = VGroup(*{cells})",
    ]


def _declare_interval(
    item: IntervalVisualObject,
    names: _ObjectNames,
    style: StyleTokens,
) -> list[str]:
    color = style.color_for(item.role)
    start = f"np.array([{item.start!r}, 0.0, 0.0], dtype=float)"
    end = f"np.array([{item.end!r}, 0.0, 0.0], dtype=float)"
    parts = f"{names.variable}_parts"
    lines = [
        f"{parts} = [Line({start}, {end}, color={color!r}, "
        f"stroke_width={item.stroke_width!r})]",
    ]
    for closed, point in (
        (item.left_closed, start),
        (item.right_closed, end),
    ):
        if closed:
            lines.append(
                f"{parts}.append(Dot({point}, radius={item.marker_radius!r}, "
                f"color={color!r}))"
            )
        else:
            lines.append(
                f"{parts}.append(Circle(radius={item.marker_radius!r}, "
                f"color={color!r}).move_to({point}))"
            )
    if item.label is not None:
        lines.extend(
            [
                f"{names.variable}_label = Text({item.label!r}, "
                f"font_size={style.typography.body_size}, color={color!r}"
                f"{_font_argument(style.typography.font)})",
                f"{names.variable}_label.next_to({parts}[0], DOWN, buff=0.25)",
                f"{parts}.append({names.variable}_label)",
            ]
        )
    lines.extend(
        [
            f"{names.variable} = VGroup(*{parts})",
            f"{names.variable}.shift({_point(item.position)})",
        ]
    )
    return lines


def _declare_annotation(
    item: AnnotationVisualObject,
    names: _ObjectNames,
    style: StyleTokens,
) -> list[str]:
    label = f"{names.variable}_label"
    arrow = f"{names.variable}_arrow"
    font_size = item.font_size or style.typography.body_size
    lines = [
        f"{label} = Text({item.text!r}, font_size={font_size}, "
        f"color={style.color_for(item.role)!r}"
        f"{_font_argument(style.typography.font)})",
    ]
    if item.max_width is not None:
        lines.extend(
            [
                f"if {label}.width > {item.max_width!r}:",
                f"    {label}.scale_to_fit_width({item.max_width!r})",
            ]
        )
    lines.extend(
        [
            f"{label}.move_to({_shifted(item.label_position, item.position)})",
            f"{arrow} = Arrow({label}.get_center(), "
            f"{_shifted(item.point, item.position)}, "
            f"buff=0.12, color={style.color_for(item.role)!r})",
            f"{names.variable} = VGroup({arrow}, {label})",
        ]
    )
    return lines


def _declare_group(
    item: GroupVisualObject,
    names: _ObjectNames,
    all_names: dict[str, _ObjectNames],
) -> list[str]:
    members = ", ".join(all_names[member].variable for member in item.members)
    lines = [f"{names.variable} = VGroup({members})"]
    if item.position != (0.0, 0.0, 0.0):
        lines.append(f"{names.variable}.shift({_point(item.position)})")
    return lines


def _declare_tracked_point(
    item: TrackedPointVisualObject,
    names: _ObjectNames,
    tracker_names: dict[str, str],
    style: StyleTokens,
) -> list[str]:
    function = f"{names.variable}_position"
    updater = f"{names.variable}_position_updater"
    components = [
        normalize_vector_expression(expression, variable_names={"t"})
        for expression in (item.x, item.y, item.z)
    ]
    lines = [
        f"def {function}(t):",
        f"    return np.array([{components[0]}, {components[1]}, "
        f"{components[2]}], dtype=float) + {_point(item.position)}",
    ]
    for check_time in item.assertion_time_values:
        lines.extend(
            [
                f"if not np.all(np.isfinite({function}({check_time!r}))):",
                f"    raise ValueError("
                f"'tracked point {item.id} is non-finite at "
                f"t={check_time!r}')",
            ]
        )
        if item.maximum_absolute_coordinate is not None:
            lines.extend(
                [
                    f"if np.max(np.abs({function}({check_time!r}))) > "
                    f"{item.maximum_absolute_coordinate!r}:",
                    f"    raise ValueError("
                    f"'tracked point {item.id} exceeds coordinate bound at "
                    f"t={check_time!r}')",
                ]
            )
    tracker = tracker_names[item.tracker]
    lines.extend(
        [
            f"{names.variable} = Dot({function}({tracker}.get_value()), "
            f"radius={item.radius!r}, color={style.color_for(item.role)!r})",
            f"def {updater}(mob):",
            f"    mob.move_to({function}({tracker}.get_value()))",
            f"{names.variable}.add_updater({updater})",
        ]
    )
    return lines


def _declare_connector(
    item: ConnectorVisualObject,
    names: _ObjectNames,
    all_names: dict[str, _ObjectNames],
    style: StyleTokens,
) -> list[str]:
    constructor = "Arrow" if item.arrow else "Line"
    start = all_names[item.start_object].variable
    end = all_names[item.end_object].variable
    updater = f"{names.variable}_connector_updater"
    return [
        f"{names.variable} = {constructor}("
        f"{start}.get_center(), {end}.get_center(), buff={item.buff!r}, "
        f"color={style.color_for(item.role)!r}, "
        f"stroke_width={item.stroke_width!r})",
        f"def {updater}(mob):",
        f"    mob.put_start_and_end_on("
        f"{start}.get_center(), {end}.get_center())",
        f"{names.variable}.add_updater({updater})",
    ]


def _declare_orbit_circle(
    item: OrbitCircleVisualObject,
    names: _ObjectNames,
    all_names: dict[str, _ObjectNames],
    style: StyleTokens,
) -> list[str]:
    center = all_names[item.center_object].variable
    updater = f"{names.variable}_orbit_updater"
    return [
        f"{names.variable} = Circle("
        f"radius={item.radius!r}, color={style.color_for(item.role)!r}, "
        f"stroke_width={item.stroke_width!r}, "
        f"stroke_opacity={item.opacity!r})",
        f"{names.variable}.move_to({center}.get_center())",
        f"def {updater}(mob):",
        f"    mob.move_to({center}.get_center())",
        f"{names.variable}.add_updater({updater})",
    ]


def _declare_trace(
    item: TraceVisualObject,
    names: _ObjectNames,
    all_names: dict[str, _ObjectNames],
    style: StyleTokens,
) -> list[str]:
    target_function = f"{all_names[item.target].variable}_position"
    step = (item.end_value - item.start_value) / (item.sample_count - 1)
    return [
        f"{names.variable} = ParametricFunction("
        f"{target_function}, "
        f"t_range=({item.start_value!r}, {item.end_value!r}, {step!r}), "
        f"color={style.color_for(item.role)!r}, "
        f"stroke_width={item.stroke_width!r})"
    ]


def _declare_point_cloud(
    item: PointCloudVisualObject,
    names: _ObjectNames,
    style: StyleTokens,
) -> list[str]:
    assert names.samples is not None
    assert names.time_tracker is not None
    lines = [
        f"{names.samples} = np.linspace({item.sample_start!r}, "
        f"{item.sample_end!r}, "
        f"{item.sample_count}, dtype=float)",
        f"{names.time_tracker} = ValueTracker({item.time_value!r})",
    ]

    position = _point(item.position)
    for state in item.states:
        available_names = {"i", "t"}
        function = names.state_functions[state.id]
        lines.extend(
            [
                f"def {function}(t):",
                f"    i = {names.samples}",
            ]
        )
        for binding in item.bindings:
            expression = normalize_vector_expression(
                binding.expression,
                variable_names=available_names,
            )
            lines.append(f"    {binding.name} = {expression}")
            available_names.add(binding.name)
        components = [
            normalize_vector_expression(
                expression,
                variable_names=available_names,
            )
            for expression in (state.x, state.y, state.z)
        ]
        state_variable = names.states[state.id]
        lines.extend(
            [
                f"    return np.column_stack((",
                f"        _point_component({components[0]}, i),",
                f"        _point_component({components[1]}, i),",
                f"        _point_component({components[2]}, i),",
                f"    )) + {position}",
                f"{state_variable} = {function}({item.time_value!r})",
            ]
        )
    axis_index = {"x": 0, "y": 1, "z": 2}
    for assertion in item.projection_assertions:
        source = names.state_functions[assertion.source_state]
        target = names.state_functions[assertion.target_state]
        source_axes = [axis_index[axis] for axis in assertion.source_axes]
        target_axes = [axis_index[axis] for axis in assertion.target_axes]
        check_times = assertion.time_values or [item.time_value]
        for check_time in check_times:
            lines.extend(
                [
                    f"if not np.allclose("
                    f"{source}({check_time!r})[:, {source_axes!r}], "
                    f"{target}({check_time!r})[:, {target_axes!r}], "
                    f"atol={assertion.absolute_tolerance!r}, rtol=0.0):",
                    f"    raise ValueError("
                    f"'projection assertion {assertion.id} failed "
                    f"at t={check_time!r}')",
                ]
            )
    for assertion in item.numeric_assertions:
        state_function = names.state_functions[assertion.state]
        check_times = assertion.time_values or [item.time_value]
        for check_time in check_times:
            checked = f"{state_function}({check_time!r})"
            if isinstance(assertion, FinitePointAssertion):
                condition = f"np.all(np.isfinite({checked}))"
            elif isinstance(assertion, BoundsPointAssertion):
                axis = axis_index[assertion.axis]
                condition = (
                    f"(np.min({checked}[:, {axis}]) >= {assertion.minimum!r} "
                    f"and np.max({checked}[:, {axis}]) <= "
                    f"{assertion.maximum!r})"
                )
            elif isinstance(assertion, SpreadPointAssertion):
                axis = axis_index[assertion.axis]
                condition = (
                    f"(np.ptp({checked}[:, {axis}]) >= "
                    f"{assertion.minimum_span!r})"
                )
            else:
                raise TypeError(
                    f"unsupported numeric assertion: {type(assertion).__name__}"
                )
            lines.extend(
                [
                    f"if not {condition}:",
                    f"    raise ValueError("
                    f"'point assertion {assertion.id} failed "
                    f"at t={check_time!r}')",
                ]
            )
    lines.extend(
        [
            f"{names.variable} = PMobject(stroke_width={item.stroke_width!r})",
            f"{names.variable}.add_points("
            f"{names.states[item.initial_state]}, "
            f"color={style.color_for(item.role)!r}, alpha={item.opacity!r})",
        ]
    )
    return lines


def _declare_object(
    item: VisualObject,
    names: _ObjectNames,
    all_names: dict[str, _ObjectNames],
    tracker_names: dict[str, str],
    style: StyleTokens,
    aspect_class: str,
) -> list[str]:
    override = item.responsive.get(aspect_class)
    if override is not None:
        updates: dict[str, object] = {}
        if override.position is not None:
            updates["position"] = override.position
        if override.layout is not None:
            updates["layout"] = override.layout
        if updates:
            item = item.model_copy(update=updates)

    if isinstance(item, TextVisualObject):
        lines = _declare_text(item, names, style)
    elif isinstance(item, MathTexVisualObject):
        lines = _declare_math_tex(item, names, style)
    elif isinstance(item, DotVisualObject):
        lines = _declare_dot(item, names, style)
    elif isinstance(item, (LineVisualObject, ArrowVisualObject)):
        lines = _declare_line(item, names, style)
    elif isinstance(item, CircleVisualObject):
        lines = _declare_circle(item, names, style)
    elif isinstance(item, RectangleVisualObject):
        lines = _declare_rectangle(item, names, style)
    elif isinstance(item, PolygonVisualObject):
        lines = _declare_polygon(item, names, style)
    elif isinstance(item, PolylineVisualObject):
        lines = _declare_polyline(item, names, style)
    elif isinstance(item, AxesVisualObject):
        lines = _declare_axes(item, names, style)
    elif isinstance(item, FunctionGraphVisualObject):
        lines = _declare_function_graph(item, names, all_names, style)
    elif isinstance(item, ParametricCurveVisualObject):
        lines = _declare_parametric_curve(item, names, style)
    elif isinstance(item, ParametricSurfaceVisualObject):
        lines = _declare_parametric_surface(item, names, style)
    elif isinstance(item, ScalarFieldFootprintVisualObject):
        lines = _declare_scalar_field_footprint(item, names, style)
    elif isinstance(item, IntervalVisualObject):
        lines = _declare_interval(item, names, style)
    elif isinstance(item, AnnotationVisualObject):
        lines = _declare_annotation(item, names, style)
    elif isinstance(item, GroupVisualObject):
        lines = _declare_group(item, names, all_names)
    elif isinstance(item, TrackedPointVisualObject):
        lines = _declare_tracked_point(
            item,
            names,
            tracker_names,
            style,
        )
    elif isinstance(item, ConnectorVisualObject):
        lines = _declare_connector(item, names, all_names, style)
    elif isinstance(item, OrbitCircleVisualObject):
        lines = _declare_orbit_circle(item, names, all_names, style)
    elif isinstance(item, TraceVisualObject):
        lines = _declare_trace(item, names, all_names, style)
    elif isinstance(item, PointCloudVisualObject):
        lines = _declare_point_cloud(item, names, style)
    else:
        raise TypeError(f"unsupported scene object: {type(item).__name__}")

    if item.layout is not None:
        direction = {
            "up": "UP",
            "down": "DOWN",
            "left": "LEFT",
            "right": "RIGHT",
        }[item.layout.direction]
        aligned = (
            ", aligned_edge="
            + {
                "up": "UP",
                "down": "DOWN",
                "left": "LEFT",
                "right": "RIGHT",
            }[item.layout.aligned_edge]
            if item.layout.aligned_edge is not None
            else ""
        )
        lines.append(
            f"{names.variable}.next_to("
            f"{all_names[item.layout.relative_to].variable}, {direction}, "
            f"buff={item.layout.buffer!r}{aligned})"
        )
    if override is not None and override.scale != 1.0:
        lines.append(f"{names.variable}.scale({override.scale!r})")
    return lines


def _create_animation(
    action: CreateAction,
    item: VisualObject,
    names: _ObjectNames,
) -> _CompiledAnimation:
    animation = action.animation
    if animation == "auto":
        if isinstance(item, MathTexVisualObject):
            animation = "write"
        elif isinstance(
            item,
            (
                LineVisualObject,
                ArrowVisualObject,
                CircleVisualObject,
                RectangleVisualObject,
                PolygonVisualObject,
                PolylineVisualObject,
                AxesVisualObject,
                FunctionGraphVisualObject,
                ParametricCurveVisualObject,
                ParametricSurfaceVisualObject,
                ScalarFieldFootprintVisualObject,
                IntervalVisualObject,
                ConnectorVisualObject,
                OrbitCircleVisualObject,
                TraceVisualObject,
            ),
        ):
            animation = "create"
        else:
            animation = "fade_in"
    constructor = {
        "create": "Create",
        "fade_in": "FadeIn",
        "write": "Write",
    }[animation]
    setup = (
        [f"self.add_fixed_in_frame_mobjects({names.variable})"]
        if item.fixed_in_frame
        else []
    )
    return _CompiledAnimation(
        setup_lines=setup,
        expression=f"{constructor}({names.variable})",
        cleanup_lines=[],
    )


def _compile_animation(
    action: SceneAction,
    *,
    item: VisualObject,
    names: _ObjectNames,
    action_index: int,
    style: StyleTokens,
) -> _CompiledAnimation:
    if isinstance(action, CreateAction):
        return _create_animation(action, item, names)
    if isinstance(action, FadeInAction):
        return _CompiledAnimation([], f"FadeIn({names.variable})", [])
    if isinstance(action, FadeOutAction):
        return _CompiledAnimation([], f"FadeOut({names.variable})", [])
    if isinstance(action, MoveAction):
        return _CompiledAnimation(
            [],
            f"{names.variable}.animate(rate_func={action.rate_func}).move_to("
            f"{_point(action.position)})",
            [],
        )
    if isinstance(action, ScaleAction):
        return _CompiledAnimation(
            [],
            f"{names.variable}.animate(rate_func={action.rate_func}).scale("
            f"{action.factor!r})",
            [],
        )
    if isinstance(action, RotateAction):
        about = (
            f", about_point={_point(action.about_point)}"
            if action.about_point is not None
            else ""
        )
        return _CompiledAnimation(
            [],
            f"{names.variable}.animate(rate_func={action.rate_func}).rotate("
            f"{action.angle_degrees!r} * DEGREES, "
            f"axis={_point(action.axis)}{about})",
            [],
        )
    if isinstance(action, ApplyMatrixAction):
        return _CompiledAnimation(
            [],
            f"ApplyMatrix(np.array({action.matrix!r}, dtype=float), "
            f"{names.variable})",
            [],
        )
    if isinstance(action, SetStyleAction):
        expression = f"{names.variable}.animate"
        if action.role is not None:
            expression += f".set_color({style.color_for(action.role)!r})"
        if action.opacity is not None:
            expression += f".set_opacity({action.opacity!r})"
        if action.stroke_width is not None:
            expression += f".set_stroke(width={action.stroke_width!r})"
        return _CompiledAnimation([], expression, [])
    if isinstance(action, TransformMathAction):
        target = f"{names.variable}_math_target_{action_index}"
        parts = ", ".join(repr(part) for part in action.latex_parts)
        font_size = item.font_size if isinstance(item, MathTexVisualObject) else None
        setup = [
            f"{target} = MathTex({parts}, "
            f"font_size={font_size or style.typography.math_size}, "
            f"color={style.foreground!r})",
        ]
        for index, role in enumerate(action.part_roles):
            setup.append(
                f"{target}[{index}].set_color({style.color_for(role)!r})"
            )
        if isinstance(item, MathTexVisualObject) and item.max_width is not None:
            setup.extend(
                [
                    f"if {target}.width > {item.max_width!r}:",
                    f"    {target}.scale_to_fit_width({item.max_width!r})",
                ]
            )
        setup.append(f"{target}.move_to({names.variable})")
        cleanup = [f"{names.variable} = {target}"]
        if item.fixed_in_frame:
            cleanup.append(
                f"self.add_fixed_in_frame_mobjects({names.variable})"
            )
        return _CompiledAnimation(
            setup,
            f"TransformMatchingTex({names.variable}, {target}, "
            f"rate_func={action.rate_func})",
            cleanup,
        )
    if isinstance(action, TransformPointCloudAction):
        target = f"{names.variable}_target_{action_index}"
        assert names.time_tracker is not None
        return _CompiledAnimation(
            setup_lines=[
                f"{target} = {names.variable}.copy()",
                f"{target}.points = {names.state_functions[action.state]}("
                f"{names.time_tracker}.get_value()).copy()",
            ],
            expression=(
                f"Transform({names.variable}, {target}, "
                f"rate_func={action.rate_func})"
            ),
            cleanup_lines=[],
        )
    if isinstance(action, AnimatePointCloudTimeAction):
        updater = f"{names.variable}_updater_{action_index}"
        assert names.time_tracker is not None
        state_function = names.state_functions[action.state]
        return _CompiledAnimation(
            setup_lines=[
                f"def {updater}(mob):",
                f"    mob.points = {state_function}("
                f"{names.time_tracker}.get_value())",
                f"{names.variable}.add_updater({updater})",
            ],
            expression=(
                f"{names.time_tracker}.animate(rate_func={action.rate_func})"
                f".set_value({action.end_time!r})"
            ),
            cleanup_lines=[
                f"{names.variable}.clear_updaters()",
                f"{names.variable}.points = {state_function}("
                f"{names.time_tracker}.get_value()).copy()",
            ],
        )
    raise TypeError(f"action does not compile to an animation: {action.type!r}")


def _camera_arguments(action: CameraAction) -> str:
    arguments: list[str] = []
    if action.phi_degrees is not None:
        arguments.append(f"phi={action.phi_degrees!r} * DEGREES")
    if action.theta_degrees is not None:
        arguments.append(f"theta={action.theta_degrees!r} * DEGREES")
    if action.zoom is not None:
        arguments.append(f"zoom={action.zoom!r}")
    if action.frame_center is not None:
        arguments.append(f"frame_center={_point(action.frame_center)}")
    return ", ".join(arguments)


def _compile_tracker_animation(
    action: AnimateTrackerAction,
    tracker_names: dict[str, str],
) -> _CompiledAnimation:
    return _CompiledAnimation(
        [],
        f"{tracker_names[action.tracker]}.animate("
        f"rate_func={action.rate_func}).set_value({action.end_value!r})",
        [],
    )


def _compile_sequential_cue(
    cue: ActionCue,
    *,
    objects: dict[str, VisualObject],
    names: dict[str, _ObjectNames],
    action_index: int,
    style: StyleTokens,
    tracker_names: dict[str, str],
) -> tuple[list[str], int]:
    lines: list[str] = []
    for action in cue.actions:
        if isinstance(action, CameraAction):
            arguments = _camera_arguments(action)
            lines.append(
                f"self.move_camera({arguments}, run_time={action.run_time!r})"
            )
        elif isinstance(action, AnimateTrackerAction):
            compiled = _compile_tracker_animation(action, tracker_names)
            lines.append(
                f"self.play({compiled.expression}, run_time={action.run_time!r})"
            )
        else:
            compiled = _compile_animation(
                action,
                item=objects[action.target],
                names=names[action.target],
                action_index=action_index,
                style=style,
            )
            lines.extend(compiled.setup_lines)
            lines.append(
                f"self.play({compiled.expression}, run_time={action.run_time!r})"
            )
            lines.extend(compiled.cleanup_lines)
        action_index += 1
    return lines, action_index


def _compile_parallel_cue(
    cue: ActionCue,
    *,
    objects: dict[str, VisualObject],
    names: dict[str, _ObjectNames],
    action_index: int,
    style: StyleTokens,
    tracker_names: dict[str, str],
) -> tuple[list[str], int]:
    lines: list[str] = []
    animations: list[str] = []
    cleanup_lines: list[str] = []
    camera: CameraAction | None = None
    for action in cue.actions:
        if isinstance(action, CameraAction):
            camera = action
        elif isinstance(action, AnimateTrackerAction):
            compiled = _compile_tracker_animation(action, tracker_names)
            animations.append(compiled.expression)
        else:
            compiled = _compile_animation(
                action,
                item=objects[action.target],
                names=names[action.target],
                action_index=action_index,
                style=style,
            )
            lines.extend(compiled.setup_lines)
            animations.append(compiled.expression)
            cleanup_lines.extend(compiled.cleanup_lines)
        action_index += 1

    run_time = cue.actions[0].run_time
    if camera is not None:
        arguments = _camera_arguments(camera)
        if animations:
            arguments = (
                f"{arguments}, added_anims=[{', '.join(animations)}]"
                if arguments
                else f"added_anims=[{', '.join(animations)}]"
            )
        lines.append(f"self.move_camera({arguments}, run_time={run_time!r})")
    else:
        lines.append(
            f"self.play({', '.join(animations)}, run_time={run_time!r})"
        )
    lines.extend(cleanup_lines)
    return lines, action_index


def compile_scene_program(
    program: SceneProgram,
    style: StyleTokens,
    resolved: ResolvedBeat,
    *,
    pixel_width: int,
    pixel_height: int,
) -> CompiledSceneProgram:
    """Compile one validated SceneProgram into a persistent Manim scene body."""

    objects = {item.id: item for item in program.objects}
    aspect_ratio = pixel_width / pixel_height
    aspect_class = (
        "landscape"
        if aspect_ratio > 1.15
        else "portrait"
        if aspect_ratio < 0.87
        else "square"
    )
    tracker_names = {
        tracker.id: f"tracker_{index}"
        for index, tracker in enumerate(program.trackers)
    }
    names: dict[str, _ObjectNames] = {}
    for index, item in enumerate(program.objects):
        state_names = (
            {
                state.id: f"obj_{index}_state_{state_index}"
                for state_index, state in enumerate(item.states)
            }
            if isinstance(item, PointCloudVisualObject)
            else {}
        )
        names[item.id] = _ObjectNames(
            variable=f"obj_{index}",
            states=state_names,
            state_functions=(
                {
                    state.id: f"obj_{index}_points_{state_index}"
                    for state_index, state in enumerate(item.states)
                }
                if isinstance(item, PointCloudVisualObject)
                else {}
            ),
            samples=(
                f"obj_{index}_samples"
                if isinstance(item, PointCloudVisualObject)
                else None
            ),
            time_tracker=(
                f"obj_{index}_time"
                if isinstance(item, PointCloudVisualObject)
                else None
            ),
        )

    lines = [
        f"self.camera.background_color = {style.background!r}",
        f"self.next_section({resolved.beat.id!r})",
    ]
    if program.enforce_safe_area:
        lines.extend(
            [
                "def _assert_screen_safe(mob, object_id, margin):",
                "    left = -config.frame_width / 2 + margin",
                "    right = config.frame_width / 2 - margin",
                "    bottom = -config.frame_height / 2 + margin",
                "    top = config.frame_height / 2 - margin",
                "    if (mob.get_left()[0] < left or mob.get_right()[0] > right",
                "            or mob.get_bottom()[1] < bottom",
                "            or mob.get_top()[1] > top):",
                "        raise ValueError(",
                "            f'screen-safe assertion failed for {object_id}'",
                "        )",
            ]
        )
    if any(isinstance(item, PointCloudVisualObject) for item in program.objects):
        lines.extend(
            [
                "def _point_component(value, samples):",
                "    component = np.asarray(value, dtype=float)",
                "    if component.ndim == 0:",
                "        return np.full(samples.shape, float(component))",
                "    return np.broadcast_to(component, samples.shape).astype(float)",
            ]
        )
    if program.initial_camera is not None:
        camera = program.initial_camera
        lines.append(
            "self.set_camera_orientation("
            f"phi={camera.phi_degrees!r} * DEGREES, "
            f"theta={camera.theta_degrees!r} * DEGREES, "
            f"zoom={camera.zoom!r}, "
            f"frame_center={_point(camera.frame_center)})"
        )

    for tracker in program.trackers:
        lines.append(
            f"{tracker_names[tracker.id]} = "
            f"ValueTracker({tracker.initial_value!r})"
        )
    for item in program.objects:
        override = item.responsive.get(aspect_class)
        if isinstance(
            item,
            (TextVisualObject, MathTexVisualObject, AnnotationVisualObject),
        ):
            if isinstance(item, MathTexVisualObject):
                base_font_size = item.font_size or style.typography.math_size
            else:
                base_font_size = item.font_size or style.typography.body_size
            effective_font_size = base_font_size * (
                override.scale if override is not None else 1.0
            )
            if effective_font_size < program.minimum_effective_font_size:
                raise ValueError(
                    f"object {item.id!r} effective font size "
                    f"{effective_font_size:.2f} is below the scene minimum "
                    f"{program.minimum_effective_font_size:.2f}"
                )
        lines.extend(
            _declare_object(
                item,
                names[item.id],
                names,
                tracker_names,
                style,
                aspect_class,
            )
        )
        if program.enforce_safe_area and (
            item.fixed_in_frame
            or isinstance(item, (TextVisualObject, MathTexVisualObject))
        ):
            lines.append(
                f"_assert_screen_safe({names[item.id].variable}, "
                f"{item.id!r}, {program.safe_area_margin!r})"
            )

    cursor = 0.0
    action_index = 0
    for cue in program.cues:
        start = resolve_anchor(cue.start_at, resolved) if cue.start_at else cursor
        if start < cursor - 1e-6:
            raise ValueError(
                f"scene cue {cue.id!r} starts at {start:.3f}s, before the "
                f"previous cue ends at {cursor:.3f}s; combine simultaneous "
                "work in a parallel cue"
            )
        if start > cursor:
            lines.append(f"self.wait({start - cursor!r})")
        if cue.mode == "parallel":
            cue_lines, action_index = _compile_parallel_cue(
                cue,
                objects=objects,
                names=names,
                action_index=action_index,
                style=style,
                tracker_names=tracker_names,
            )
        else:
            cue_lines, action_index = _compile_sequential_cue(
                cue,
                objects=objects,
                names=names,
                action_index=action_index,
                style=style,
                tracker_names=tracker_names,
            )
        lines.extend(cue_lines)
        cursor = start + cue.duration_seconds

    if cursor > resolved.duration_seconds + 1e-6:
        raise ValueError(
            f"beat {resolved.beat.id!r} needs {cursor:.3f}s of scene actions "
            f"but its narration/timeline allows {resolved.duration_seconds:.3f}s"
        )
    if resolved.duration_seconds > cursor:
        lines.append(f"self.wait({resolved.duration_seconds - cursor!r})")
    return CompiledSceneProgram(
        lines=lines,
        scene_base="ThreeDScene" if program.scene_kind == "3d" else "Scene",
        duration_seconds=cursor,
    )
