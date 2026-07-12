"""Honesty test — the catalog claims theme-drivenness; this enforces it (docs claim, tests enforce).

Two bug classes bit the aeneid run: (1) _theme_vars truncated any token containing ';' (vintage-
editorial's data-URI --surface-pattern), leaving an unclosed url(" that corrupted the whole injected
block → BLANK frames; (2) unreadable palettes. Both are catchable at the TOKEN level (no 26×17 render):
a truncated value leaves unbalanced quotes/parens, and contrast is luminance math on the resolved hex.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "render-service" / "_lab_hyperframes" / "bridge"))
import compose  # noqa: E402

THEMES = REPO / "themes"


def _theme_ids():
    return sorted(d.name for d in THEMES.iterdir() if (d / "tokens.css").exists())


def _hex(v):
    """Resolve a token value to (r,g,b) if it's a #hex or rgb() color, else None."""
    v = v.strip()
    m = re.match(r"#([0-9a-fA-F]{6})$", v) or re.match(r"#([0-9a-fA-F]{3})$", v)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", v)
    return tuple(int(x) for x in m.groups()) if m else None


def _lum(rgb):
    def ch(c):
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _tokens(theme):
    css = compose._theme_vars(theme)                      # the "#root{ … }" block the composer injects
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+)", css))


def test_every_theme_injects_valid_css():
    """A truncated token value (the ';'-in-url bug) leaves an unclosed quote/paren that corrupts the
    whole #root{…} rule → blank frames. Balanced quotes + parens is the cheap invariant that catches it."""
    for t in _theme_ids():
        css = compose._theme_vars(t)
        assert css, f"theme {t}: _theme_vars returned nothing"
        assert css.count('"') % 2 == 0, f"theme {t}: unbalanced quotes in injected CSS — a token value was truncated"
        assert css.count("(") == css.count(")"), f"theme {t}: unbalanced parens — a url() value was truncated"


def test_every_theme_palette_is_readable():
    """Core text and the highlight must clear a readable contrast on their background (WCAG ~AA-large 3.0)."""
    for t in _theme_ids():
        tok = _tokens(t)
        pairs = [("--text", "--surface"), ("--accent-ink", "--accent")]
        for fg, bg in pairs:
            a, b = _hex(tok.get(fg, "")), _hex(tok.get(bg, ""))
            if a and b:
                c = _contrast(a, b)
                assert c >= 2.8, f"theme {t}: {fg} on {bg} contrast {c:.1f} — unreadable"
