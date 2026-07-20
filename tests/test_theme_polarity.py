"""Honesty test for B6 — theme POLARITY (docs claim, tests enforce).

A block must not hardcode a dark stage that clashes with a light theme (the aeneid ran on the light
vintage-editorial theme and hit exactly this). The rules, enforced here at COMPOSE level (no render):
  · a text block's register follows its GROUND, not a hardcoded default — footage (light ink + scrim)
    only over real footage, else PAPER (var(--text) on var(--surface): correct on light AND dark);
  · comparison/carousel backdrops are theme-aware — dramatic dark only on dark themes;
  · the diagram flips to its (already-complete) dark variant only on dark themes.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "render-service" / "_lab_hyperframes" / "bridge"))
import compose  # noqa: E402

LIGHT, DARK = "vintage-editorial", "blueprint"


def _frame(block, data, theme):
    sc = {"id": "s1", "type": block, "start": 0, "dur": 8, "data": data}
    return compose.compose_frame("f", 8, [sc], theme=theme)


def _body(html):
    return re.sub(r"<style>.*?</style>", "", html, flags=re.S)   # drop CSS defs; inspect APPLIED markup only


def test_polarity_detection():
    assert compose._theme_polarity(LIGHT) == "light"
    assert compose._theme_polarity(DARK) == "dark"
    assert compose._theme_polarity("does-not-exist") == "light"        # safe fallback


def test_statement_register_follows_ground_not_a_hardcoded_default():
    # ungrounded -> PAPER on BOTH themes (dark ink on light, light ink on dark — both legible)
    for th in (LIGHT, DARK):
        h = _frame("statement", {"lines": ["hi"]}, th)
        assert "stmt paper-t" in h and "stmt footage-t" not in h, th
    # image-grounded -> FOOTAGE (light ink + scrim reads over the footage) regardless of theme
    for th in (LIGHT, DARK):
        h = _frame("statement", {"lines": ["hi"], "ground": {"kind": "image", "src": "x.jpg"}}, th)
        assert "stmt footage-t" in h, th
    # an EXPLICIT register is still honored (no silent override of author intent)
    assert "stmt footage-t" in _frame("statement", {"lines": ["hi"], "register": "footage"}, LIGHT)


def test_comparison_backdrop_and_title_are_polarity_aware():
    data = {"title": "T", "left": {"type": "text", "title": "A"}, "right": {"type": "text", "title": "B"}}
    hl, hd = _frame("comparison", data, LIGHT), _frame("comparison", data, DARK)
    assert "inset:0;background:var(--shell)" in hl          # light theme -> theme-surface backdrop (no dark gaps)
    # dark theme: a THEME-FAITHFUL token backdrop (_page_bg = var(--shell)/--surface). The old hardcoded
    # #0a0b0c dark backdrop was replaced by the comparison theme-faithful fix — the drama now comes from
    # the theme's OWN dark tokens, so a hardcoded hex must never leak.
    assert ("inset:0;background:var(--shell)" in hd or "inset:0;background:var(--surface)" in hd)
    assert "inset:0;background:#0a0b0c" not in hd           # the backdrop is NOT a hardcoded dark hex anymore
    assert "cmp-htitle light" in _body(hl)                  # text panels on a light theme -> light title scrim
    assert "cmp-htitle light" not in _body(hd)
    assert "var(--surface-2)" in hl                         # paper side fill follows the theme (was cold #F1F3F2)


def test_diagram_uses_its_dark_variant_only_on_dark_themes():
    data = {"root": {"label": "R", "children": [{"label": "A"}, {"label": "B"}]}}
    dl, dd = _body(_frame("diagram", data, LIGHT)), _body(_frame("diagram", data, DARK))
    assert "dg-dark" not in dl and "dgbg dark" not in dl
    assert "dg-dark" in dd or "dgbg dark" in dd


def test_paper_ink_is_themed_not_a_cold_hardcode():
    # a paper reveal must emit var(--text), never the old cold #2B2D2C, in the actual markup
    h = _body(_frame("statement", {"lines": ["hi there"], "reveal": "gradient", "operative": "hi"}, LIGHT))
    assert "#2B2D2C" not in h
    assert "var(--text)" in h
