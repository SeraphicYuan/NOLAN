"""Deterministic Manim block registry and source emitters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from math_animation.contracts import (
    EquationRevealBlock,
    EquationTransformBlock,
    FunctionPlotBlock,
    NumberLineBlock,
    SecantToTangentBlock,
    TitleCardBlock,
    VisualBlock,
)
from math_animation.safety import normalize_math_expression
from math_animation.style import StyleTokens


@dataclass(frozen=True)
class CompiledBlock:
    lines: list[str]
    duration_seconds: float


BlockEmitter = Callable[[VisualBlock, StyleTokens], CompiledBlock]
_REGISTRY: dict[str, BlockEmitter] = {}


def register(name: str) -> Callable[[BlockEmitter], BlockEmitter]:
    def decorator(function: BlockEmitter) -> BlockEmitter:
        if name in _REGISTRY:
            raise RuntimeError(f"duplicate Manim block registration: {name}")
        _REGISTRY[name] = function
        return function

    return decorator


def available_blocks() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def compile_block(block: VisualBlock, style: StyleTokens) -> CompiledBlock:
    try:
        emitter = _REGISTRY[block.type]
    except KeyError as exc:
        raise ValueError(f"no deterministic compiler for block {block.type!r}") from exc
    return emitter(block, style)


def _name(block_id: str) -> str:
    return re.sub(r"\W+", "_", block_id).strip("_").lower()


def _font_kwargs(style: StyleTokens) -> str:
    return (
        f", font={style.typography.font!r}"
        if style.typography.font is not None
        else ""
    )


def _fit_to_safe_width(name: str, *, margin: float = 0.8) -> list[str]:
    return [
        f"if {name}.width > config.frame_width - {margin!r}:",
        f"    {name}.scale_to_fit_width(config.frame_width - {margin!r})",
    ]


@register("title_card")
def _title_card(block: VisualBlock, style: StyleTokens) -> CompiledBlock:
    assert isinstance(block, TitleCardBlock)
    stem = _name(block.id)
    lines = [
        f"{stem}_title = Text({block.title!r}, font_size={style.typography.title_size}, "
        f"color={style.foreground!r}{_font_kwargs(style)})",
        *_fit_to_safe_width(f"{stem}_title"),
    ]
    names = [f"{stem}_title"]
    if block.subtitle:
        lines.extend(
            [
                f"{stem}_subtitle = Text({block.subtitle!r}, "
                f"font_size={style.typography.body_size}, color={style.muted!r}"
                f"{_font_kwargs(style)})",
                *_fit_to_safe_width(f"{stem}_subtitle"),
                f"{stem}_subtitle.next_to({stem}_title, DOWN, buff=0.45)",
            ]
        )
        names.append(f"{stem}_subtitle")
    animations = ", ".join(f"FadeIn({name})" for name in names)
    lines.append(f"self.play({animations}, run_time={block.run_time!r})")
    if block.hold_seconds:
        lines.append(f"self.wait({block.hold_seconds!r})")
    lines.append(f"self.play(FadeOut(VGroup({', '.join(names)})), run_time=0.35)")
    return CompiledBlock(lines, block.run_time + block.hold_seconds + 0.35)


@register("equation_reveal")
def _equation_reveal(block: VisualBlock, style: StyleTokens) -> CompiledBlock:
    assert isinstance(block, EquationRevealBlock)
    stem = _name(block.id)
    parts = ", ".join(repr(part) for part in block.latex_parts)
    lines = [
        f"{stem}_formula = MathTex({parts}, font_size={style.typography.math_size})",
        *_fit_to_safe_width(f"{stem}_formula"),
    ]
    for index, role in enumerate(block.part_roles):
        lines.append(
            f"{stem}_formula[{index}].set_color({style.color_for(role)!r})"
        )
    animations = [f"Write({stem}_formula)"]
    names = [f"{stem}_formula"]
    if block.caption:
        lines.extend(
            [
                f"{stem}_caption = Text({block.caption!r}, "
                f"font_size={style.typography.body_size}, color={style.muted!r}"
                f"{_font_kwargs(style)})",
                *_fit_to_safe_width(f"{stem}_caption"),
                f"{stem}_caption.to_edge(DOWN)",
            ]
        )
        animations.append(f"FadeIn({stem}_caption)")
        names.append(f"{stem}_caption")
    lines.append(
        f"self.play({', '.join(animations)}, run_time={block.run_time!r})"
    )
    if block.hold_seconds:
        lines.append(f"self.wait({block.hold_seconds!r})")
    lines.append(f"self.play(FadeOut(VGroup({', '.join(names)})), run_time=0.35)")
    return CompiledBlock(lines, block.run_time + block.hold_seconds + 0.35)


@register("equation_transform")
def _equation_transform(block: VisualBlock, style: StyleTokens) -> CompiledBlock:
    assert isinstance(block, EquationTransformBlock)
    stem = _name(block.id)
    before = ", ".join(repr(part) for part in block.from_latex)
    after = ", ".join(repr(part) for part in block.to_latex)
    first = max(0.2, block.run_time * 0.35)
    second = max(0.2, block.run_time - first)
    lines = [
        f"{stem}_from = MathTex({before}, font_size={style.typography.math_size}, "
        f"color={style.foreground!r})",
        f"{stem}_to = MathTex({after}, font_size={style.typography.math_size}, "
        f"color={style.color_for('primary')!r})",
        *_fit_to_safe_width(f"{stem}_from"),
        *_fit_to_safe_width(f"{stem}_to"),
        f"self.play(Write({stem}_from), run_time={first!r})",
        f"self.play(TransformMatchingTex({stem}_from, {stem}_to), run_time={second!r})",
    ]
    names = [f"{stem}_from"]
    if block.caption:
        lines.extend(
            [
                f"{stem}_caption = Text({block.caption!r}, "
                f"font_size={style.typography.body_size}, color={style.muted!r}"
                f"{_font_kwargs(style)})",
                *_fit_to_safe_width(f"{stem}_caption"),
                f"{stem}_caption.to_edge(DOWN)",
                f"self.play(FadeIn({stem}_caption), run_time=0.25)",
            ]
        )
        names.append(f"{stem}_caption")
    if block.hold_seconds:
        lines.append(f"self.wait({block.hold_seconds!r})")
    lines.append(f"self.play(FadeOut(VGroup({', '.join(names)})), run_time=0.35)")
    extra = 0.25 if block.caption else 0.0
    return CompiledBlock(
        lines, block.run_time + block.hold_seconds + 0.35 + extra
    )


@register("function_plot")
def _function_plot(block: VisualBlock, style: StyleTokens) -> CompiledBlock:
    assert isinstance(block, FunctionPlotBlock)
    stem = _name(block.id)
    expression = normalize_math_expression(block.expression)
    lines = [
        f"{stem}_axes = Axes(x_range={block.x_range!r}, y_range={block.y_range!r}, "
        f"tips=False, axis_config={{'color': {style.muted!r}}})",
        f"{stem}_graph = {stem}_axes.plot(lambda x: {expression}, "
        f"color={style.color_for(block.role)!r})",
    ]
    names = [f"{stem}_axes", f"{stem}_graph"]
    animations = [f"Create({stem}_axes)", f"Create({stem}_graph)"]
    if block.label_latex:
        lines.extend(
            [
                f"{stem}_label = MathTex({block.label_latex!r}, "
                f"font_size={style.typography.body_size}, color={style.foreground!r})",
                *_fit_to_safe_width(f"{stem}_label"),
                f"{stem}_label.to_corner(UR)",
            ]
        )
        names.append(f"{stem}_label")
        animations.append(f"FadeIn({stem}_label)")
    lines.append(
        f"self.play({', '.join(animations)}, run_time={block.run_time!r})"
    )
    if block.hold_seconds:
        lines.append(f"self.wait({block.hold_seconds!r})")
    lines.append(f"self.play(FadeOut(VGroup({', '.join(names)})), run_time=0.35)")
    return CompiledBlock(lines, block.run_time + block.hold_seconds + 0.35)


@register("secant_to_tangent")
def _secant_to_tangent(block: VisualBlock, style: StyleTokens) -> CompiledBlock:
    assert isinstance(block, SecantToTangentBlock)
    stem = _name(block.id)
    expression = normalize_math_expression(block.expression)
    intro = max(0.25, block.run_time * 0.35)
    motion = max(0.25, block.run_time - intro)
    lines = [
        f"def {stem}_f(x):",
        f"    return {expression}",
        f"{stem}_axes = Axes(x_range={block.x_range!r}, y_range={block.y_range!r}, "
        f"tips=False, axis_config={{'color': {style.muted!r}}})",
        f"{stem}_graph = {stem}_axes.plot({stem}_f, "
        f"color={style.color_for('primary')!r})",
        f"{stem}_h = ValueTracker({block.h_start!r})",
        f"{stem}_fixed = Dot({stem}_axes.c2p({block.x0!r}, "
        f"{stem}_f({block.x0!r})), color={style.color_for('fixed')!r})",
        f"{stem}_moving = always_redraw(lambda: Dot({stem}_axes.c2p("
        f"{block.x0!r} + {stem}_h.get_value(), "
        f"{stem}_f({block.x0!r} + {stem}_h.get_value())), "
        f"color={style.color_for('changing')!r}))",
        f"{stem}_secant = always_redraw(lambda: Line("
        f"{stem}_axes.c2p({block.x0!r} - 1.3, "
        f"{stem}_f({block.x0!r}) - 1.3 * "
        f"(({stem}_f({block.x0!r}+{stem}_h.get_value())-{stem}_f({block.x0!r}))/"
        f"{stem}_h.get_value())), "
        f"{stem}_axes.c2p({block.x0!r} + 1.3, "
        f"{stem}_f({block.x0!r}) + 1.3 * "
        f"(({stem}_f({block.x0!r}+{stem}_h.get_value())-{stem}_f({block.x0!r}))/"
        f"{stem}_h.get_value())), color={style.color_for('secondary')!r}))",
        f"self.play(Create({stem}_axes), Create({stem}_graph), "
        f"FadeIn({stem}_fixed), FadeIn({stem}_moving), Create({stem}_secant), "
        f"run_time={intro!r})",
        f"self.play({stem}_h.animate.set_value({block.h_end!r}), "
        f"run_time={motion!r}, rate_func=smooth)",
    ]
    names = [
        f"{stem}_axes",
        f"{stem}_graph",
        f"{stem}_fixed",
        f"{stem}_moving",
        f"{stem}_secant",
    ]
    if block.caption:
        lines.extend(
            [
                f"{stem}_caption = Text({block.caption!r}, "
                f"font_size={style.typography.body_size}, color={style.muted!r}"
                f"{_font_kwargs(style)})",
                *_fit_to_safe_width(f"{stem}_caption"),
                f"{stem}_caption.to_edge(DOWN)",
                f"self.play(FadeIn({stem}_caption), run_time=0.25)",
            ]
        )
        names.append(f"{stem}_caption")
    if block.hold_seconds:
        lines.append(f"self.wait({block.hold_seconds!r})")
    lines.append(f"self.play(FadeOut(VGroup({', '.join(names)})), run_time=0.35)")
    extra = 0.25 if block.caption else 0.0
    return CompiledBlock(
        lines, block.run_time + block.hold_seconds + 0.35 + extra
    )


@register("number_line")
def _number_line(block: VisualBlock, style: StyleTokens) -> CompiledBlock:
    assert isinstance(block, NumberLineBlock)
    stem = _name(block.id)
    labels = block.labels or [str(value) for value in block.values]
    lines = [
        f"{stem}_line = NumberLine(x_range={block.x_range!r}, include_numbers=False, "
        f"color={style.muted!r})",
        f"{stem}_dots = VGroup(*[Dot({stem}_line.n2p(value), "
        f"color={style.color_for(block.role)!r}) for value in {block.values!r}])",
        f"{stem}_labels = VGroup(*[Text(label, "
        f"font_size={style.typography.body_size}, color={style.foreground!r}"
        f"{_font_kwargs(style)}) "
        f"for label in {labels!r}])",
        f"[_label.next_to(_dot, UP) for _label, _dot in "
        f"zip({stem}_labels, {stem}_dots)]",
        f"self.play(Create({stem}_line), LaggedStart(*[FadeIn(dot) for dot in "
        f"{stem}_dots], lag_ratio=0.15), FadeIn({stem}_labels), "
        f"run_time={block.run_time!r})",
    ]
    if block.hold_seconds:
        lines.append(f"self.wait({block.hold_seconds!r})")
    lines.append(
        f"self.play(FadeOut(VGroup({stem}_line, {stem}_dots, {stem}_labels)), "
        "run_time=0.35)"
    )
    return CompiledBlock(lines, block.run_time + block.hold_seconds + 0.35)
