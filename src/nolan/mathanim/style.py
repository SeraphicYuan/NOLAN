"""NOLAN theme -> Manim style tokens.

A math clip is mounted full-frame inside an essay. If it arrives in the engine's
stock dark palette while the essay is cream-on-ink editorial, the beat reads as a
different film spliced in. So the theme the composition was authored in drives
the Manim scene's background, type colour and — the part that actually matters —
its SEMANTIC colours.

The engine reserves distinct roles for what is CHANGING versus what is FIXED in a
derivation. `docs/NOLAN_INTEGRATION.md` warns about exactly one failure here:

    "Semantic roles must remain distinct after mapping. Brand colors should not
     make 'changing' and 'fixed' quantities visually indistinguishable."

A theme is one accent plus a text ramp, so deriving six roles from it can quietly
collapse two of them and make a derivation unreadable — the viewer can no longer
tell which term moved. `check_roles` measures that in OKLab and refuses rather
than shipping a scene whose colour coding says nothing. Distinctness is built
from CHROMA as well as hue, so it survives a colour-blind viewer: `fixed` is a
near-grey and `changing` is saturated, which stays legible when the hue does not.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[3]
THEMES_DIR = REPO / "themes"

# The engine's own defaults, kept as the fallback when a theme is missing or
# unparseable. They are a designed palette, not a guess.
_FALLBACK = {
    "shell": "#0c0c0b",
    "text": "#faf9f5",
    "text-mute": "#b0aea5",
    "accent": "#6a9bcc",
}

# Minimum OKLab distance between two roles that must not be confused. Calibrated
# against pairs, not picked: 0.016 (#4d7a4d/#477957) and 0.091 (#007c8b/#007d52)
# are pairs a designer would call the same colour; 0.149 (#d6e5ff/#4dd2ff), 0.184
# (green/red) and 1.000 (black/white) are pairs nobody would confuse. 0.12 sits in
# the gap. Measured across all 34 shipped themes: 0 fail, tightest real margin
# 0.125 (8-bit-orbit) — so the floor is live, not decorative.
MIN_ROLE_DISTANCE = 0.12

# WHICH pairs are checked, and why not all of them.
#
# The first version of this check compared all 15 pairs and failed 30 of 34
# themes — the all-false-positives shape docs/WIRING_CHECKLIST.md #11 says makes
# a gate worthless. Two of those pairs were real (a bad `fixed` derivation, fixed
# below); the rest were noise, because `positive` and `changing` colliding costs
# nothing when no template ever puts them on screen together.
#
# What survives is the set whose confusion DESTROYS MEANING:
#   changing/fixed      the pairing `docs/NOLAN_INTEGRATION.md` names by hand —
#                       lose it and the viewer cannot tell which term moved
#   positive/negative   opposite meanings; looking alike inverts the reading
#   primary/changing    the emphasised thing vs the moving thing
#   primary/fixed       emphasis vs ordinary type
#   changing/secondary  two simultaneously-animated voices
#
# Anything else an author actually puts together in one scene is caught per-scene
# by passing `used_roles` — measure what is used, not what is possible.
CONTRASTIVE_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("changing", "fixed"),
    ("positive", "negative"),
    ("primary", "changing"),
    ("primary", "fixed"),
    ("changing", "secondary"),
)
# Minimum WCAG contrast against the background. Math strokes and thin glyphs need
# more than the 3.0 large-text floor; 4.0 keeps a 2px axis readable at 1080p.
MIN_ROLE_CONTRAST = 4.0

_HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_CSS_VAR = re.compile(r"^\s*--([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;", re.M)


# --- colour space ----------------------------------------------------------------------------
# sRGB <-> OKLab/OKLCh (Björn Ottosson's formulation). OKLab because we need a
# perceptual distance: a euclidean gap in sRGB says a dark blue and a dark green
# are far apart when the eye reads both as "dark".


def _parse_hex(value: str) -> Optional[Tuple[float, float, float]]:
    match = _HEX.match((value or "").strip())
    if not match:
        return None
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return tuple(int(digits[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def _to_hex(rgb: Tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02x}" for c in rgb)


def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _delinear(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def _oklab(rgb: Tuple[float, float, float]) -> Tuple[float, float, float]:
    r, g, b = (_linear(c) for c in rgb)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (v ** (1 / 3) if v > 0 else -((-v) ** (1 / 3)) for v in (l, m, s))
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _from_oklab(lab: Tuple[float, float, float]) -> Tuple[float, float, float]:
    L, a, b = lab
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = (v ** 3 for v in (l_, m_, s_))
    r = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bl = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return tuple(min(1.0, max(0.0, _delinear(c))) for c in (r, g, bl))  # type: ignore[return-value]


def _to_lch(lab: Tuple[float, float, float]) -> Tuple[float, float, float]:
    L, a, b = lab
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360.0


def _from_lch(lch: Tuple[float, float, float]) -> Tuple[float, float, float]:
    L, C, h = lch
    rad = math.radians(h)
    return L, C * math.cos(rad), C * math.sin(rad)


def distance(left: str, right: str) -> float:
    """Perceptual distance between two hex colours (OKLab euclidean)."""

    a, b = _parse_hex(left), _parse_hex(right)
    if a is None or b is None:
        return 0.0
    la, lb = _oklab(a), _oklab(b)
    return math.dist(la, lb)


def _relative_luminance(rgb: Tuple[float, float, float]) -> float:
    r, g, b = (_linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(left: str, right: str) -> float:
    """WCAG contrast ratio between two hex colours (1.0 .. 21.0)."""

    a, b = _parse_hex(left), _parse_hex(right)
    if a is None or b is None:
        return 1.0
    la, lb = _relative_luminance(a), _relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _fit_contrast(colour: str, background: str, target: float) -> str:
    """Walk a colour's OKLab lightness until it clears `target` against the bg.

    Hue and chroma are held: the theme chose the hue, and the only honest lever
    for legibility is how light the mark is against its own canvas. Walks AWAY
    from the background's lightness, so it darkens on cream and lightens on ink.
    """

    rgb = _parse_hex(colour)
    bg = _parse_hex(background)
    if rgb is None or bg is None:
        return colour
    if contrast(colour, background) >= target:
        return colour
    L, C, h = _to_lch(_oklab(rgb))
    direction = 1.0 if _oklab(bg)[0] < 0.5 else -1.0
    best, best_ratio = colour, contrast(colour, background)
    for step in range(1, 41):
        candidate_L = min(1.0, max(0.0, L + direction * step * 0.02))
        candidate = _to_hex(_from_oklab(_from_lch((candidate_L, C, h))))
        ratio = contrast(candidate, background)
        if ratio > best_ratio:
            best, best_ratio = candidate, ratio
        if ratio >= target:
            return candidate
    return best  # unreachable target (a mid-grey canvas); return the best we found


def _rotate(colour: str, degrees: float, *, chroma: Optional[float] = None) -> str:
    rgb = _parse_hex(colour)
    if rgb is None:
        return colour
    L, C, h = _to_lch(_oklab(rgb))
    return _to_hex(_from_oklab(_from_lch((L, C if chroma is None else chroma, h + degrees))))


def _desaturate(colour: str, factor: float) -> str:
    rgb = _parse_hex(colour)
    if rgb is None:
        return colour
    L, C, h = _to_lch(_oklab(rgb))
    return _to_hex(_from_oklab(_from_lch((L, C * factor, h))))


# --- theme reading ---------------------------------------------------------------------------


def theme_palette(theme: Optional[str]) -> Dict[str, str]:
    """The hex tokens a theme declares, from `tokens.css` (the real palette).

    `theme.json`'s `preview` block is a four-colour SUMMARY for the theme picker;
    `tokens.css` is what the composition actually renders in, including the text
    ramp. Read the ramp so `muted` is the theme's own muted and not a guess, and
    fall back through preview to the engine defaults.
    """

    palette = dict(_FALLBACK)
    if not theme:
        return palette
    tokens = THEMES_DIR / str(theme) / "tokens.css"
    if tokens.is_file():
        text = tokens.read_text(encoding="utf-8", errors="replace")
        found = {name: value for name, value in _CSS_VAR.findall(text)}
        for key in ("shell", "surface", "text", "text-2", "text-mute", "accent", "rule"):
            if key in found and _parse_hex(found[key]):
                palette[key] = found[key].lower()
        if palette.get("shell"):
            return palette
    meta = THEMES_DIR / str(theme) / "theme.json"
    if meta.is_file():
        import json

        try:
            preview = (json.loads(meta.read_text(encoding="utf-8")) or {}).get("preview") or {}
        except (json.JSONDecodeError, OSError):
            preview = {}
        for src, dst in (("shell", "shell"), ("text", "text"), ("accent", "accent")):
            if _parse_hex(preview.get(src, "")):
                palette[dst] = preview[src].lower()
    return palette


# Where a theme's face is unavailable to Manim, substitute by TYPE PERSONALITY rather than
# letting Pango choose. The HTML side pulls its faces from Google Fonts at render time; Manim
# asks Pango, which only sees fonts INSTALLED on the machine — so `font='Libre Franklin'` fell
# back to generic "Sans" with mangled kerning, and said so only in a stderr log nothing read
# (the render exits 0). A personality-matched system face keeps a math beat in the same visual
# register as the essay; the mismatch is REPORTED either way, because a silent substitution is
# how the two halves drift apart without anyone noticing.
_PERSONALITY_FALLBACK = {
    "geometric-sans": ("Century Gothic", "Segoe UI", "Arial"),
    "editorial-serif": ("Georgia", "Cambria", "Times New Roman"),
    "mono-technical": ("Consolas", "Courier New"),
    "brutalist-heavy": ("Franklin Gothic", "Arial", "Segoe UI"),
    "friendly-rounded": ("Arial Rounded MT", "Segoe UI", "Verdana"),
    "elegant-italic": ("Constantia", "Georgia", "Cambria"),
}
_LAST_RESORT = ("Segoe UI", "Arial", "Verdana")


def _theme_meta(theme: Optional[str]) -> Dict:
    if not theme:
        return {}
    meta = THEMES_DIR / str(theme) / "theme.json"
    if not meta.is_file():
        return {}
    import json

    try:
        return json.loads(meta.read_text(encoding="utf-8")) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def theme_fonts(theme: Optional[str]) -> Optional[str]:
    """The theme's display face, as a single family name Manim can ask Pango for."""

    fonts = _theme_meta(theme).get("fonts") or {}
    family = fonts.get("displayEn") or fonts.get("body")
    return str(family) if family else None


def resolve_font(
    theme: Optional[str], available: Optional[Sequence[str]] = None
) -> Tuple[Optional[str], Optional[str]]:
    """(font Manim should use, note if it is not the theme's own face).

    `available` is what the RENDER environment's Pango can see. Pass None (or an empty list)
    when that cannot be determined and the theme's face is used as authored — an unknown font
    list is not evidence that a font is missing.
    """

    wanted = theme_fonts(theme)
    if not wanted or not available:
        return wanted, None
    installed = {str(f).strip().lower(): str(f) for f in available}
    if wanted.strip().lower() in installed:
        return wanted, None

    personality = str(_theme_meta(theme).get("typePersonality") or "")
    for candidate in _PERSONALITY_FALLBACK.get(personality, ()) + _LAST_RESORT:
        if candidate.strip().lower() in installed:
            return installed[candidate.strip().lower()], (
                f"the theme's face {wanted!r} is not installed for Manim, so this clip is set in "
                f"{candidate!r} (closest {personality or 'available'} match). Install {wanted!r} "
                f"on the render machine to match the HTML exactly — Manim asks Pango for system "
                f"fonts, it cannot use the essay's webfonts."
            )
    return None, (
        f"the theme's face {wanted!r} is not installed for Manim and no fallback matched; "
        f"Pango will choose, and the clip will not match the essay's typography."
    )


# --- the mapping -----------------------------------------------------------------------------


def semantic_colors(palette: Dict[str, str]) -> Dict[str, str]:
    """Six distinguishable semantic roles from one accent and a text ramp.

    The derivation is deliberate, not decorative:

      primary   the theme's accent — whatever the essay already emphasises with
      changing  the accent rotated far around the hue circle AND kept saturated;
                this is the term the viewer must watch move
      fixed     the foreground, barely desaturated — because a term that did NOT
                change should look like ordinary type. Two earlier derivations
                (text-2 desaturated; a constructed mid-grey) both collided with
                `changing` on light themes, where fitting every role for contrast
                pushes them all dark and the lightness axis stops separating
                anything: 5/34 and 12/34 themes failed. Ordinary type is both the
                honest design answer and the one that measures clean at 0/34
      secondary a far rotation the other way — a second voice, not the subject
      positive/ conventional green/red, refitted for THIS background's lightness
      negative  rather than assumed against a dark one

    `fixed` staying near-neutral while `changing` stays saturated means the pair
    is separated by CHROMA as well as hue, so it survives a colour-blind viewer.
    """

    background = palette.get("shell", _FALLBACK["shell"])
    accent = palette.get("accent", _FALLBACK["accent"])
    text = palette.get("text", _FALLBACK["text"])

    accent_c = _to_lch(_oklab(_parse_hex(accent) or (0.5, 0.5, 0.5)))[1]
    roles = {
        "primary": accent,
        # 150 deg, not 180: the exact complement of a blue accent lands in a
        # muddy yellow-green that fights thin strokes. 150 keeps it separable
        # while staying a colour a designer would pick. The chroma floor matters
        # on light themes, where fitting for contrast darkens everything and an
        # unsaturated rotation would just read as another dark neutral.
        "changing": _rotate(accent, 150.0, chroma=max(accent_c, 0.12)),
        "fixed": _desaturate(text, 0.15),
        "secondary": _rotate(accent, 255.0, chroma=max(accent_c, 0.10)),
        "positive": "#70a37f",
        "negative": "#c96a6a",
    }
    return {
        role: _fit_contrast(colour, background, MIN_ROLE_CONTRAST)
        for role, colour in roles.items()
    }


def check_roles(payload: Dict, used_roles: Optional[List[str]] = None) -> List[str]:
    """Every way this palette would make a derivation unreadable. Empty = fine.

    Two layers. Always: the `CONTRASTIVE_PAIRS` whose confusion destroys meaning.
    Additionally, when `used_roles` names the roles a SCENE actually puts on
    screen together, every pair among those — because an author who colours three
    parts of one equation has made them contrastive by using them that way, and
    only the scene knows that.

    Both directions are measured: roles far enough APART from each other, and
    each far enough from the BACKGROUND to be seen at all.
    """

    problems: List[str] = []
    colors = payload.get("colors", {}) or {}
    semantic = payload.get("semantic_colors", {}) or {}
    background = colors.get("background", "")

    checked = set(CONTRASTIVE_PAIRS)
    if used_roles:
        present = sorted({r for r in used_roles if r in semantic})
        for i, left in enumerate(present):
            for right in present[i + 1:]:
                checked.add((left, right))
    for left, right in sorted(checked):
        if left not in semantic or right not in semantic:
            continue
        gap = distance(semantic[left], semantic[right])
        if gap < MIN_ROLE_DISTANCE:
            problems.append(
                f"semantic roles {left!r} ({semantic[left]}) and {right!r} "
                f"({semantic[right]}) are {gap:.3f} apart in OKLab, under the "
                f"{MIN_ROLE_DISTANCE} floor — a viewer cannot tell which term moved"
            )
    for role, colour in sorted(semantic.items()):
        ratio = contrast(colour, background)
        if ratio < MIN_ROLE_CONTRAST:
            problems.append(
                f"semantic role {role!r} ({colour}) has {ratio:.2f}:1 contrast on "
                f"{background} — under the {MIN_ROLE_CONTRAST}:1 floor for thin marks"
            )
    fg_ratio = contrast(colors.get("foreground", ""), background)
    if fg_ratio < MIN_ROLE_CONTRAST:
        problems.append(
            f"foreground {colors.get('foreground')} has {fg_ratio:.2f}:1 contrast "
            f"on {background} — equations would be hard to read"
        )
    return problems


def style_payload(
    theme: Optional[str],
    *,
    canvas_height: int = 1080,
    available_fonts: Optional[Sequence[str]] = None,
) -> Dict:
    """The `StyleTemplateRef.raw` payload for a comp's theme.

    Type sizes scale with the canvas because Manim sizes glyphs in scene units
    against a fixed 8.0-unit frame height: the same `font_size` that reads at
    1080p is unreadable in a 540p proxy render.
    """

    palette = theme_palette(theme)
    background = palette.get("shell", _FALLBACK["shell"])
    font, font_note = resolve_font(theme, available_fonts)
    scale = max(0.5, min(2.0, canvas_height / 1080.0))
    return {
        "colors": {
            "background": background,
            "foreground": _fit_contrast(
                palette.get("text", _FALLBACK["text"]), background, MIN_ROLE_CONTRAST
            ),
            "muted": _fit_contrast(
                palette.get("text-mute", _FALLBACK["text-mute"]), background, 3.0
            ),
        },
        "semantic_colors": semantic_colors(palette),
        "typography": {
            "font": font,
            "title_size": max(16, round(64 * scale)),
            "body_size": max(12, round(30 * scale)),
            "math_size": max(16, round(58 * scale)),
        },
        "motion": {
            "create_seconds": 1.0,
            "transform_seconds": 1.2,
            "beat_hold_seconds": 0.4,
        },
        # advisory only; `_font_note` is underscore-prefixed so it never reads as narration and
        # the engine's StrictModel keeps it in `raw` without interpreting it
        **({"_font_note": font_note} if font_note else {}),
    }
