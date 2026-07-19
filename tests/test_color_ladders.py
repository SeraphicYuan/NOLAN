"""Color ladders (theme schema v2, Layer 2 — auto-derived opacity/alpha depth via native CSS color-mix).

A single-accent / single-hue theme expresses its depth as ONE base colour + a function: its card tint /
soft fill / glow / hairline (or its secondary/muted/faint text) are `color-mix(in srgb, var(--base) N%,
transparent)` in tokens.css — so changing the base updates the whole ladder, and because it's native CSS it
is read by BOTH render paths (the HyperFrames composer and the Remotion pipeline) with no runtime executor.

Docs claim, tests enforce: the exemplars keep the ladder as a FUNCTION of one base var (not re-hardcoded
rgba), the base var each references exists, and the mix percentages ascend (a real ladder, not flat).
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# theme -> (base var, [ladder step vars])
LADDERS = {
    "blue-professional": ("--accent", ["--surface-3", "--accent-soft", "--accent-glow", "--rule"]),
    "vellum":            ("--text",   ["--text-2", "--text-mute", "--text-faint"]),
}

_MIX = re.compile(r"color-mix\(\s*in\s+srgb\s*,\s*var\((--[\w-]+)\)\s+([\d.]+)%\s*,\s*transparent\s*\)")


def _decl(css, var):
    m = re.search(rf"^\s*{re.escape(var)}\s*:\s*([^;]+);", css, re.M)
    return m.group(1).strip() if m else None


def test_exemplars_derive_depth_from_one_base_via_color_mix():
    for theme, (base, steps) in LADDERS.items():
        css = (REPO / "themes" / theme / "tokens.css").read_text(encoding="utf-8")
        assert _decl(css, base), f"{theme}: base {base} not defined"
        pcts = []
        for var in steps:
            val = _decl(css, var)
            assert val, f"{theme}: {var} missing"
            m = _MIX.match(val)
            assert m, f"{theme}: {var} must be color-mix(var(--base) N%, transparent), got {val!r}"
            assert m.group(1) == base, f"{theme}: {var} mixes {m.group(1)}, expected the ladder base {base}"
            pcts.append(float(m.group(2)))
        # a real ladder is monotonic + distinct (accent rises 4→20; fg-alpha falls 62→35)
        assert len(set(pcts)) == len(pcts), f"{theme}: ladder percentages {pcts} must be distinct"
        assert pcts == sorted(pcts) or pcts == sorted(pcts, reverse=True), \
            f"{theme}: ladder percentages {pcts} should be monotonic"


def test_ladder_base_is_a_plain_color_not_itself_derived():
    # the base of a ladder must be a concrete colour (hex), so "change one colour" is a real single knob
    for theme, (base, _) in LADDERS.items():
        css = (REPO / "themes" / theme / "tokens.css").read_text(encoding="utf-8")
        assert re.match(r"#[0-9a-fA-F]{3,6}$", _decl(css, base)), f"{theme}: {base} should be a hex literal"
