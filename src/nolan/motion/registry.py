"""Motion library registry — the single source of truth for the spec system.

A scene design (natural language) is compiled by an LLM into a *spec*; the spec is
validated against this registry and executed on the right backend. Everything else
(LLM manifest, prompt guide, validator, executor) derives from here.

Design: SHARED params (position/theme/accent — supported by many motions) are declared
once; each MotionEffect declares its own content/style params plus which shared params
it supports. Add params here over time as we learn what matters per-motion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional


# --- parameter descriptor ---------------------------------------------------
@dataclass
class Param:
    name: str
    type: str                       # enum|string|int|number|color|position|theme|string[]|array
    doc: str = ""
    values: Optional[List[Any]] = None   # for enum
    default: Any = None
    required: bool = False


# --- shared vocabulary ------------------------------------------------------
# Named anchors -> normalized (x, y). Mirrored in render-service/remotion-lib/src/layout.ts
# and compatible with src/nolan/renderer/layout.py Position.
ANCHORS = {
    "top-left": (0.2, 0.18), "top": (0.5, 0.16), "top-right": (0.8, 0.18),
    "left": (0.2, 0.5), "center": (0.5, 0.5), "right": (0.8, 0.5),
    "bottom-left": (0.2, 0.82), "bottom": (0.5, 0.84), "bottom-right": (0.8, 0.82),
    "upper-third": (0.5, 0.3), "lower-third": (0.5, 0.72),
}
THEMES = ["dark-editorial", "light", "high-contrast"]

SHARED: dict[str, Param] = {
    "position": Param("position", "position", "Where the element sits: a named anchor or {x,y} in 0..1.",
                      values=list(ANCHORS.keys()), default="center"),
    "theme": Param("theme", "theme", "Visual theme.", values=THEMES, default="dark-editorial"),
    "accent": Param("accent", "color", "Accent/highlight color override (hex).", default=None),
}


# --- effect descriptor ------------------------------------------------------
@dataclass
class MotionEffect:
    id: str                         # spec effect id, e.g. "annotate-stat"
    backend: str                    # "python" | "remotion"
    category: str
    purpose: str
    target: str                     # remotion composition id, or python renderer class name
    content: List[Param] = field(default_factory=list)
    style: List[Param] = field(default_factory=list)
    shared: List[str] = field(default_factory=list)   # names from SHARED this effect supports
    duration_default: float = 4.0


def _p(name, type, doc="", values=None, default=None, required=False):
    return Param(name, type, doc, values, default, required)


# --- the registry -----------------------------------------------------------
REGISTRY: List[MotionEffect] = [
    # ---- Remotion ----
    MotionEffect(
        "kinetic-text", "remotion", "kinetic-text",
        "Reveal a short headline word-by-word, accenting key words.", "Kinetic",
        content=[_p("text", "string", "the headline line", required=True),
                 _p("highlights", "string[]", "key words to accent (lowercased)", default=[])],
        shared=["position", "theme", "accent"], duration_default=4.0),
    MotionEffect(
        "bar-compare", "remotion", "rich-chart",
        "Animated bar comparison with count-up labels.", "BarCompare",
        content=[_p("title", "string", "chart title", required=True),
                 _p("bars", "array", "[{label, value, color?}] (2-4 bars)", required=True),
                 _p("prefix", "string", 'value prefix, e.g. "$" (or "+" for growth)', default=""),
                 _p("suffix", "string", 'value suffix, e.g. "B" or "%"', default="")],
        style=[_p("barStyle", "enum", "bar look", values=["flat", "gradient", "glass"], default="gradient")],
        shared=["theme"], duration_default=5.0),
    MotionEffect(
        "k-shape", "remotion", "rich-chart",
        "Two diverging lines (rising vs falling) from a shared origin — the K split.", "KShape",
        content=[_p("title", "string", required=True), _p("topLabel", "string", required=True),
                 _p("bottomLabel", "string", required=True)],
        style=[_p("lineStyle", "enum", values=["straight", "zigzag"], default="straight"),
               _p("jitter", "int", "zigzag amplitude px", default=24),
               _p("segments", "int", "zigzag points", default=18)],
        shared=["theme"], duration_default=5.0),
    MotionEffect(
        "annotate-video", "remotion", "svg-annotation",
        "Draw-on circle + arrow + label pointing at a spot on b-roll.", "AnnotateOverVideo",
        content=[_p("label", "string", "the callout text", required=True),
                 _p("videoSrc", "string", "b-roll basename in public/")],
        style=[_p("shapeStyle", "enum", values=["clean", "scribble"], default="clean")],
        shared=["position", "theme", "accent"], duration_default=4.0),
    MotionEffect(
        "annotate-stat", "remotion", "svg-annotation",
        "Emphasize one number/stat with a drawn circle + caption.", "AnnotateStat",
        content=[_p("value", "string", "the headline number string e.g. $28,000", required=True),
                 _p("label", "string", "short caption", default="")],
        style=[_p("shapeStyle", "enum", values=["clean", "scribble"], default="clean")],
        shared=["position", "theme", "accent"], duration_default=4.0),
    MotionEffect(
        "route-map", "remotion", "map",
        "Animated pins + routes over a basemap (money/flow/geo).", "RouteMap",
        content=[_p("title", "string", required=True),
                 _p("pins", "array", "[{x,y(0..1),label}]", required=True),
                 _p("mapSrc", "string", "basemap image basename in public/")],
        style=[_p("routeStyle", "enum", values=["arc", "straight"], default="arc")],
        shared=["theme"], duration_default=5.0),
    MotionEffect(
        "premium-card", "remotion", "premium-card",
        "Glass/gradient hero or chapter title card.", "PremiumCard",
        content=[_p("title", "string", required=True), _p("subtitle", "string", default=""),
                 _p("kicker", "string", "small label above title", default="")],
        style=[_p("cardStyle", "enum", values=["glass", "gradient", "spotlight"], default="glass")],
        shared=["theme"], duration_default=4.0),

    # ---- Python ----
    MotionEffect(
        "counter", "python", "data",
        "Animated count-up number with a caption (a stat reveal).", "CounterRenderer",
        content=[_p("value", "int", "the number (digits only)", required=True),
                 _p("label", "string", "caption", default=""),
                 _p("prefix", "string", 'leading sign/symbol before the number, e.g. "+", "$", "-". Use "+" for growth/increase.', default=""),
                 _p("suffix", "string", 'units after the number, e.g. "%", "B", "x"', default="")],
        style=[_p("tone", "enum", values=["neutral", "success", "danger"], default="neutral")],
        shared=["position"], duration_default=4.0),
    MotionEffect(
        "title", "python", "text",
        "Animated title card (title + subtitle + accent line).", "TitleRenderer",
        content=[_p("title", "string", required=True), _p("subtitle", "string", default="")],
        shared=["position"], duration_default=4.0),
    MotionEffect(
        "lower-third", "python", "text",
        "Lower-third name/title caption.", "LowerThirdRenderer",
        content=[_p("name", "string", "primary line", required=True),
                 _p("title", "string", "secondary line", default="")],
        shared=["position"], duration_default=4.0),
    MotionEffect(
        "comparison", "python", "data",
        "Two-sided VS comparison.", "ComparisonRenderer",
        content=[_p("left_text", "string", required=True), _p("right_text", "string", required=True),
                 _p("left_subtitle", "string", default=""), _p("right_subtitle", "string", default=""),
                 _p("center_label", "string", default="VS")],
        duration_default=4.0),
    MotionEffect(
        "line-chart", "python", "rich-chart",
        "Animated single-series line chart (rise/crash/rally).", "LineChartRenderer",
        content=[_p("points", "array", "[[label, value], ...]", required=True),
                 _p("title", "string", default=""),
                 _p("value_prefix", "string", default=""), _p("value_suffix", "string", default="")],
        duration_default=6.0),
    MotionEffect(
        "loop-diagram", "python", "diagram",
        "Animated feedback-loop: labelled nodes in a cycle with arrows.", "LoopDiagramRenderer",
        content=[_p("nodes", "string[]", "node labels in cycle order", required=True),
                 _p("title", "string", default=""), _p("center_label", "string", default="")],
        duration_default=7.0),
]

BY_ID = {e.id: e for e in REGISTRY}


def get_effect(effect_id: str) -> Optional[MotionEffect]:
    return BY_ID.get(effect_id)


def normalize_position(position) -> dict:
    """Anchor name or {x,y} -> concrete {x,y} in 0..1 (used by both backends)."""
    if isinstance(position, dict) and "x" in position and "y" in position:
        return {"x": float(position["x"]), "y": float(position["y"])}
    fx, fy = ANCHORS.get(str(position), ANCHORS["center"])
    return {"x": fx, "y": fy}
