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
    provenance: dict = field(default_factory=dict)   # promoted effects: clip/agent/date
    # The craft guidance an agent needs to PICK this effect (module contract):
    # when it beats its neighbors, when it doesn't. Purpose = what; this = when.
    when_to_use: str = ""


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
        shared=["position", "theme", "accent"], when_to_use="Hook lines and thesis statements — a spoken headline the viewer should read as they hear it. Not for body prose (>8 words reads as a wall of text).",
        duration_default=4.0),
    MotionEffect(
        "bar-compare", "remotion", "rich-chart",
        "Animated bar comparison with count-up labels.", "BarCompare",
        content=[_p("title", "string", "chart title", required=True),
                 _p("bars", "array", "[{label, value, color?}] (2-4 bars)", required=True),
                 _p("prefix", "string", 'value prefix, e.g. "$" (or "+" for growth)', default=""),
                 _p("suffix", "string", 'value suffix, e.g. "B" or "%"', default="")],
        style=[_p("barStyle", "enum", "bar look", values=["flat", "gradient", "glass"], default="gradient")],
        shared=["theme"], when_to_use="2-4 quantities the narration explicitly compares ('X vs Y'). If the story is one series over time, use line-chart instead.",
        duration_default=5.0),
    MotionEffect(
        "k-shape", "remotion", "rich-chart",
        "Two diverging lines (rising vs falling) from a shared origin — the K split.", "KShape",
        content=[_p("title", "string", required=True), _p("topLabel", "string", required=True),
                 _p("bottomLabel", "string", required=True)],
        style=[_p("lineStyle", "enum", values=["straight", "zigzag"], default="straight"),
               _p("jitter", "int", "zigzag amplitude px", default=24),
               _p("segments", "int", "zigzag points", default=18)],
        shared=["theme"], when_to_use="Divergence narratives — winners/losers, rich/poor splitting from a shared origin. The shape IS the argument; don't use for mere difference.",
        duration_default=5.0),
    MotionEffect(
        "annotate-video", "remotion", "svg-annotation",
        "Draw-on circle + arrow + label pointing at a spot on b-roll.", "AnnotateOverVideo",
        content=[_p("label", "string", "the callout text", required=True),
                 _p("videoSrc", "string", "b-roll basename in public/"),
                 _p("focusX", "number", "circled spot x (0..1)", default=0.5),
                 _p("focusY", "number", "circled spot y (0..1)", default=0.42),
                 _p("rx", "number", "circle x-radius px", default=190),
                 _p("ry", "number", "circle y-radius px", default=120)],
        style=[_p("shapeStyle", "enum", values=["clean", "scribble"], default="clean")],
        shared=["position", "theme", "accent"], when_to_use="Direct the eye to ONE spot in busy b-roll the narration points at ('this building here'). Needs a stable shot behind it.",
        duration_default=4.0),
    MotionEffect(
        "annotate-stat", "remotion", "svg-annotation",
        "Emphasize one number/stat with a drawn circle + caption.", "AnnotateStat",
        content=[_p("value", "string", "the headline number string e.g. $28,000", required=True),
                 _p("label", "string", "short caption", default="")],
        style=[_p("shapeStyle", "enum", values=["clean", "scribble"], default="clean")],
        shared=["position", "theme", "accent"], when_to_use="One number the narration lands on hard and needs EMPHASIS. For scale-over-imagery (number + tangible referent) use stat-over.",
        duration_default=4.0),
    MotionEffect(
        "route-map", "remotion", "map",
        "Animated pins + routes over a basemap (money/flow/geo).", "RouteMap",
        content=[_p("title", "string", required=True),
                 _p("pins", "array", "[{x,y(0..1),label}]", required=True),
                 _p("mapSrc", "string", "basemap image basename in public/")],
        style=[_p("routeStyle", "enum", values=["arc", "straight"], default="arc")],
        shared=["theme"], when_to_use="Movement across geography — journeys, trade, money flows. Use when the narration names places in order; pins without narrative order confuse.",
        duration_default=5.0),
    MotionEffect(
        "premium-card", "remotion", "premium-card",
        "Glass/gradient hero or chapter title card.", "PremiumCard",
        content=[_p("title", "string", required=True), _p("subtitle", "string", default=""),
                 _p("kicker", "string", "small label above title", default="")],
        style=[_p("cardStyle", "enum", values=["glass", "gradient", "spotlight"], default="glass")],
        shared=["theme"], when_to_use="Chapter openers and the cold-open title. At most one per section — cards are punctuation, not content.",
        duration_default=4.0),

    MotionEffect(
        "timeline", "remotion", "map",
        "Era bands + event markers over a year axis — the recurring 'home base' "
        "infographic that ACCUMULATES across a video via the motif layer.",
        "Timeline",
        content=[_p("title", "string", default=""),
                 _p("start", "int", "axis start year (negative = BC)", required=True),
                 _p("end", "int", "axis end year", required=True),
                 _p("eras", "array", "[{label, from, to, color?}] era bands above the axis", default=[]),
                 _p("markers", "array", "[{year, label, emphasis?}] events on the axis "
                    "(the motif layer stamps isNew on this scene's delta)", default=[]),
                 _p("focus", "object", "{from, to} year window the camera eases onto", default=None)],
        shared=["theme"],
        when_to_use="Chronology the viewer should HOLD across the video — declare a "
                    "motif in plan meta and reference it per scene (motif id + delta) so "
                    "each return adds markers instead of redrawing from scratch. One-off "
                    "date mentions don't need it; three or more events across a span do.",
        duration_default=6.0),

    # ---- Curated Remotion blocks (Phase 3: one backend per intent) ----
    # Same effect ids + params as before; the executor's block path adapts
    # them to the flow-blocks library. Old specs stamped backend="python"
    # still render via the retained Python classes.
    MotionEffect(
        "counter", "block", "data",
        "Animated count-up number with a caption (a stat reveal).", "StatCount",
        content=[_p("value", "int", "the number (digits only)", required=True),
                 _p("label", "string", "caption", default=""),
                 _p("prefix", "string", 'leading sign/symbol before the number, e.g. "+", "$", "-". Use "+" for growth/increase.', default=""),
                 _p("suffix", "string", 'units after the number, e.g. "%", "B", "x"', default="")],
        shared=["position"], when_to_use="A single inline stat reveal — the cheapest data moment. Escalate to bar-compare (context) or stat-over (scale) when the number needs more.",
        duration_default=4.0),
    MotionEffect(
        "title", "block", "text",
        "Animated title card (title + subtitle + accent line).", "HeroStatement",
        content=[_p("title", "string", required=True), _p("subtitle", "string", default="")],
        shared=["position"], when_to_use="A section title inside the flow when a full premium-card is too heavy.",
        duration_default=4.0),
    MotionEffect(
        "lower-third", "block", "text",
        "Lower-third name/title caption.", "LowerThird",
        content=[_p("name", "string", "primary line", required=True),
                 _p("title", "string", "secondary line", default="")],
        shared=["position"], when_to_use="Introducing a person/source on screen (name + role) without leaving the shot.",
        duration_default=4.0),
    MotionEffect(
        "comparison", "block", "data",
        "Two-sided VS comparison.", "ComparisonVS",
        content=[_p("left_text", "string", required=True), _p("right_text", "string", required=True),
                 _p("left_subtitle", "string", default=""), _p("right_subtitle", "string", default=""),
                 _p("center_label", "string", default="VS")],
        when_to_use="A binary either/or the narration frames as a duel. For an IMAGERY collision use split-screen; for numbers use bar-compare.",
        duration_default=4.0),

    # ---- Python ----
    MotionEffect(
        "line-chart", "python", "rich-chart",
        "Animated single-series line chart (rise/crash/rally).", "LineChartRenderer",
        content=[_p("points", "array", "[[label, value], ...]", required=True),
                 _p("title", "string", default=""),
                 _p("value_prefix", "string", default=""), _p("value_suffix", "string", default="")],
        when_to_use="One series over time — rise, crash, rally. Best when the narration traces the shape as it draws.",
        duration_default=6.0),
    MotionEffect(
        "loop-diagram", "python", "diagram",
        "Animated feedback-loop: labelled nodes in a cycle with arrows.", "LoopDiagramRenderer",
        content=[_p("nodes", "string[]", "node labels in cycle order", required=True),
                 _p("title", "string", default=""), _p("center_label", "string", default="")],
        when_to_use="Feedback loops and cycles (A feeds B feeds C feeds A) that the narration walks around once.",
        duration_default=7.0),
    # ("photo-montage" (python) removed in Phase 3 — photo-montage-pro owns the
    #  intent; no stored specs referenced the python variant.)
    MotionEffect(
        "photo-montage-pro", "remotion", "photo-montage",
        "'Photos on a table' montage with a per-card motion system (Remotion): each card "
        "declares where it rests and how it arrives (from-edge + timing + easing) "
        "independently. Polaroid/plain/cutout frames, handwritten captions, Ken Burns "
        "camera. Use for flexible b-roll/asset presentation.", "PhotoMontage",
        content=[_p("cards", "array",
                    "[{src, x, y (0..1 rest center), scale?, rotation?, "
                    "from?:left|right|top|bottom|center|none, enterAt?, enterDur?, distance?, "
                    "ease?:out|inOut|spring, fade?, fromScale?, frame?:polaroid|plain|cutout, "
                    "caption?, captionAt?, captionDur?, shadow?, rotX?, rotY?, perspective?, "
                    "keys?:[{at,x?,y?,scale?,rotation?,rotX?,rotY?,opacity?,ease?}] (explicit "
                    "keyframe track; rotation=in-plane tilt, rotX/rotY=3D pan/tilt — for "
                    "appear-then-pan / fade-out / multi-step paths)}]", required=True),
                 _p("background", "string", "CSS color (e.g. #2a1216) or table-texture image path",
                    default="#241016")],
        style=[_p("vignette", "number", "edge darkening 0..1", default=0.5),
               _p("zoomStart", "number", "camera zoom at start", default=1.05),
               _p("zoomEnd", "number", "camera zoom at end", default=1.16),
               _p("panX", "number", "camera pan, fraction of width", default=-0.04),
               _p("panY", "number", "camera pan, fraction of height", default=0.0)],
        shared=["theme"], when_to_use="3-6 related stills that belong on one 'table' — an evidence cluster. Use when order/position of cards carries meaning; for a lone still use still-motion.",
        duration_default=10.0),
    MotionEffect(
        "photo-grid", "remotion", "photo-montage",
        "Procedural photo grid with a 3-step choreography (Remotion): images fly in to "
        "fill a cols×rows grid (sequenced one-by-one / by row / by col), then one image "
        "zooms to center while the grid peters out, then it returns to the grid. Computed "
        "from grid shape + timings — scales to dozens of images.", "PhotoGrid",
        content=[_p("cards", "array", "[{src, caption?}] images to place (cols*rows of them)",
                    required=True),
                 _p("cols", "int", "grid columns", default=8),
                 _p("rows", "int", "grid rows", default=5),
                 _p("focusIndex", "int", "which image zooms to center (default middle)", default=None),
                 _p("background", "string", "CSS color or texture image path", default="#241016")],
        style=[_p("order", "enum", "fly-in sequencing",
                  values=["one-by-one", "row", "col"], default="one-by-one"),
               _p("flyFrom", "enum", "where cells fly in from",
                  values=["edges", "bottom", "scale"], default="edges"),
               _p("frame", "enum", "card frame style",
                  values=["polaroid", "plain", "cutout"], default="polaroid"),
               _p("fillStart", "number", "sec before fly-in begins", default=0.2),
               _p("stagger", "number", "sec between successive units", default=0.08),
               _p("flyDur", "number", "sec each cell takes to fly in", default=0.6),
               _p("focusAt", "number", "sec the focus zoom starts (default after fill)", default=None),
               _p("focusHold", "number", "sec the focused image stays centered", default=1.6),
               _p("focusScale", "number", "centered height as fraction of frame", default=0.8),
               _p("margin", "number", "outer grid margin, fraction", default=0.05),
               _p("vignette", "number", "edge darkening 0..1", default=0.5)],
        shared=["theme"], when_to_use="MANY images (8+) as a wall — abundance of examples, then one zooms out as the specimen. Under 8 images the grid reads sparse.",
        duration_default=10.0),

    # ---- Still → motion / assembly (Remotion; executor routes these to nolan.still_motion) ----
    MotionEffect(
        "still-motion", "remotion", "camera",
        "Turn ONE still into a moving shot: motivated Ken Burns (push/pull/pan, origin on the "
        "salient subject), 2.5D parallax (rembg cutout over a blurred bg), rack-focus, blur-in, "
        "or an atmospheric overlay. The parallax/rack-focus cutout is derived automatically.", "StillMotion",
        content=[_p("image", "string", "the still image path", required=True),
                 _p("treatment", "enum", "how to animate the still",
                    values=["ken-burns-in", "ken-burns-out", "ken-burns-pan", "parallax",
                            "rack-focus", "blur-in", "atmospheric", "hold"], default="ken-burns-in"),
                 _p("direction", "enum", "pan/parallax direction", values=["left", "right"], default="right")],
        shared=[], when_to_use="The default life-giver for any single still held >3s. Treatment by mood: ken-burns for narrative pushes, parallax for depth drama, rack-focus for a revelation, atmospheric for tone holds.",
        duration_default=4.0),
    MotionEffect(
        "split-screen", "remotion", "composition",
        "The relational/dialectical collision: two stills side by side (left|right) with opposing "
        "slow pushes, a divider, and optional labels — shot A + shot B make a third meaning.", "SplitScreen",
        content=[_p("left", "string", "left image path", required=True),
                 _p("right", "string", "right image path", required=True),
                 _p("left_label", "string", "caption under the left half", default=""),
                 _p("right_label", "string", "caption under the right half", default="")],
        shared=[], when_to_use="The dialectical operator: two images whose collision makes a third meaning (then/now, cause/effect). Both halves must read at half width.",
        duration_default=4.0),
    MotionEffect(
        "stat-over", "remotion", "data",
        "SCALE payoff: a big count-up NUMBER over a tangible-referent shot (stadium crowd / city "
        "aerial / grains of sand) + a caption. Number and caption are styled from the video THEME.", "StatOver",
        content=[_p("image", "string", "the tangible-referent still path", required=True),
                 _p("value", "number", "the number to count up to", required=True),
                 _p("prefix", "string", 'e.g. "$"', default=""),
                 _p("suffix", "string", 'e.g. "B", "%"', default=""),
                 _p("caption", "string", "what the number means", default=""),
                 _p("decimals", "int", "decimal places", default=0)],
        shared=["theme", "accent"], when_to_use="The SCALE payoff: a number counted up over a tangible referent (crowd, aerial, grains). Use when the audience should FEEL the magnitude, not just read it.",
        duration_default=5.0),
    MotionEffect(
        "clip-montage", "remotion", "composition",
        "Assemble b-roll clips/stills into one video with shot-to-shot transitions "
        "(dissolve/slide/wipe/clockWipe/cut) via @remotion/transitions.", "ClipMontage",
        content=[_p("clips", "array", "[{path, kind:'video'|'image', duration(sec)}] in order", required=True),
                 _p("transition", "enum", "transition between every pair",
                    values=["fade", "slide", "wipe", "clockWipe", "cut"], default="fade"),
                 _p("trans_frames", "int", "transition length in frames", default=16)],
        shared=[], when_to_use="Sequencing 3+ short clips/stills into one continuous b-roll bed — time compression, 'meanwhile' energy. Uniform transitions only; for authored per-shot cuts use scene.shots.",
        duration_default=8.0),

    # ---- gap effects (2026-07): device mockups, before/after, race, whip, PiP, typewriter, shake ----
    MotionEffect(
        "screen-frame", "remotion", "composition",
        "Wrap a screenshot / screen-recording in a device mockup (browser, laptop, phone chrome).", "ScreenFrame",
        content=[_p("background", "string", "screenshot image path (staged)"),
                 _p("videoSrc", "string", "screen-recording video path (staged)"),
                 _p("url", "string", "browser address-bar text", default=""),
                 _p("label", "string", "caption under the frame", default="")],
        style=[_p("device", "enum", "which mockup", values=["browser", "laptop", "phone"], default="browser")],
        shared=["theme", "accent"],
        when_to_use="Show software, a website, an app, or a social post AS a device — screenshots gain credibility and context inside real chrome. Match device to the source (phone for apps/social, browser for the web, laptop for desktop apps).",
        duration_default=5.0),
    MotionEffect(
        "camera-shake", "remotion", "camera",
        "Handheld camera shake over a still/clip — an impact or tension punctuation.", "CameraShake",
        content=[_p("background", "string", "still image path (staged)"),
                 _p("videoSrc", "string", "clip path (staged)"),
                 _p("label", "string", "optional overlaid word", default="")],
        style=[_p("intensity", "number", "shake throw 0..1", default=0.6),
               _p("flash", "bool", "white impact flash at the start", default=True)],
        shared=["theme"],
        when_to_use="Punctuate an impact, shock, explosion, or tension beat over a shot. An exclamation mark — use sparingly; overuse reads as amateur.",
        duration_default=3.0),
    MotionEffect(
        "bar-race", "remotion", "rich-chart",
        "The racing bar chart: values grow AND overtake, bars reordering as the leader changes.", "BarRace",
        content=[_p("title", "string", default=""),
                 _p("bars", "array", "[{label, value, color?}] (2-8 bars)", required=True),
                 _p("prefix", "string", default=""), _p("suffix", "string", default="")],
        shared=["theme"],
        when_to_use="A race or accumulation where the ORDER changes over time — leaders overtake. If the quantities are fixed and you only compare magnitudes, use bar-compare instead.",
        duration_default=6.0),
    MotionEffect(
        "typewriter", "remotion", "text",
        "Text that builds character-by-character; 'decode' scrambles then locks each glyph.", "Typewriter",
        content=[_p("text", "string", "the line to type out", required=True)],
        style=[_p("mode", "enum", "reveal style", values=["type", "decode"], default="type"),
               _p("cursor", "bool", "show a blinking cursor", default=True)],
        shared=["theme", "accent"],
        when_to_use="Build text as if typed — a code line, a terminal command, a letter, a telegram, a search query. 'decode' gives data/hacker energy. Keep it short; long strings drag.",
        duration_default=5.0),
    MotionEffect(
        "before-after", "remotion", "composition",
        "A slider wipe revealing an 'after' image over a 'before' image on the same framing.", "BeforeAfter",
        content=[_p("background", "string", "the BEFORE image path (staged)", required=True),
                 _p("foreground", "string", "the AFTER image path (staged)", required=True),
                 _p("before_label", "string", default=""), _p("after_label", "string", default="")],
        shared=["theme", "accent"],
        when_to_use="Change on the SAME framing — restoration, before/after, prediction vs reality, redaction reveal. Needs two aligned images. For two DIFFERENT images colliding use split-screen.",
        duration_default=5.0),
    MotionEffect(
        "whip-transition", "remotion", "composition",
        "A fast whip-pan with motion blur handing off from one shot to the next.", "WhipTransition",
        content=[_p("background", "string", "the FROM image path (staged)", required=True),
                 _p("foreground", "string", "the TO image path (staged)", required=True)],
        style=[_p("direction", "enum", "pan direction", values=["left", "right"], default="left")],
        shared=["theme"],
        when_to_use="A punchy speed-cut between two shots for energy/pace. A transition BETWEEN two images; to sequence many clips use clip-montage.",
        duration_default=3.0),
    MotionEffect(
        "picture-in-picture", "remotion", "composition",
        "A floating inset window over a full-frame main shot (reaction / meanwhile / detail).", "PictureInPicture",
        content=[_p("background", "string", "main still path (staged)"),
                 _p("videoSrc", "string", "main clip path (staged)"),
                 _p("foreground", "string", "the inset image path (staged)", required=True),
                 _p("inset_label", "string", default="")],
        style=[_p("corner", "enum", "inset corner", values=["br", "bl", "tr", "tl"], default="br")],
        shared=["theme", "accent"],
        when_to_use="Overlay a second frame on a main shot — reaction, commentary, 'meanwhile', or a detail feed. The inset is the smaller, supporting image.",
        duration_default=5.0),
]

BY_ID = {e.id: e for e in REGISTRY}



# --- promoted effects (agent-proposed, deterministically gated) ---------------
# nolan.effect_promotion appends accepted proposals to registry_custom.json —
# promoted effects are DATA, never hand-edits to this file. A broken custom
# file is reported loudly and skipped, never silently half-loaded.
def _load_custom() -> List[MotionEffect]:
    import json as _json
    import logging as _logging
    from pathlib import Path as _Path
    p = _Path(__file__).parent / "registry_custom.json"
    if not p.exists():
        return []
    out: List[MotionEffect] = []
    try:
        for e in _json.loads(p.read_text(encoding="utf-8")):
            out.append(MotionEffect(
                e["id"], e.get("backend", "remotion"), e.get("category", "promoted"),
                e.get("purpose", ""), e["target"],
                content=[Param(**c) for c in e.get("content", [])],
                style=[Param(**s) for s in e.get("style", [])],
                shared=list(e.get("shared", [])),
                duration_default=float(e.get("duration_default", 4.0)),
                provenance=dict(e.get("provenance", {})),
                when_to_use=str(e.get("when_to_use", ""))))
    except Exception as exc:
        _logging.getLogger(__name__).error("registry_custom.json unusable: %s", exc)
        return []
    return out


REGISTRY.extend(_load_custom())
BY_ID.update({e.id: e for e in REGISTRY})   # BY_ID is defined above this loader


def get_effect(effect_id: str) -> Optional[MotionEffect]:
    return BY_ID.get(effect_id)


def normalize_position(position) -> dict:
    """Anchor name or {x,y} -> concrete {x,y} in 0..1 (used by both backends)."""
    if isinstance(position, dict) and "x" in position and "y" in position:
        return {"x": float(position["x"]), "y": float(position["y"])}
    fx, fy = ANCHORS.get(str(position), ANCHORS["center"])
    return {"x": fx, "y": fy}
