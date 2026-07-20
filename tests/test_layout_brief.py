"""Honesty tests for the theme->authoring composition-dialect brief (nolan.hyperframes.layout_brief).

The load-bearing invariant: the variant MENU the brief shows an authoring agent must EQUAL the pool the
deterministic composer (compose.py::_resolve_variant) will actually accept for that theme — otherwise the
agent is briefed on arrangements the composer discards, or the composer picks arrangements the agent was
never told about. Both read the same two registries; these tests pin them together so they can't drift.
"""
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge"
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(BRIDGE))

import compose  # noqa: E402
from nolan.hyperframes.layout_brief import theme_layout_brief  # noqa: E402

VARIANTS = json.loads((REPO / "themes" / "composition" / "layout_variants.json").read_text(encoding="utf-8"))["blocks"]
SAMPLE_THEMES = ["vellum", "bauhaus-bold", "blueprint", "blue-professional", "aurora-mesh"]


def _brief_block_menu(brief: str, block: str):
    """The variant ids the brief lists under a block heading (in `code` backticks)."""
    if f"**{block}**" not in brief:
        return None
    seg = brief.split(f"**{block}**", 1)[1].split("\n- **", 1)[0]
    # each variant line is '    - `vid` — ...'; ignore the 'default `x`;' inline note by taking line-leading ticks
    ids = []
    for line in seg.splitlines():
        m = re.match(r"\s*-\s*`([a-z0-9\-]+)`", line)
        if m:
            ids.append(m.group(1))
    return ids


def _composer_pool(block: str, theme: str):
    """The variant ids compose.py's pool would allow for this theme (theme-sanctioned zones + the default),
    ignoring content-fit — the exact set the brief should advertise."""
    reg = VARIANTS[block]
    variants = reg["variants"]
    allowed = compose._theme_allowed_zones(theme)
    dflt = reg.get("default")
    return {v for v, m in variants.items() if not allowed or m.get("zone") in allowed or v == dflt}


def test_empty_for_unknown_theme():
    assert theme_layout_brief("no-such-theme-xyz") == ""
    assert theme_layout_brief(None) == ""


@pytest.mark.parametrize("theme", SAMPLE_THEMES)
def test_brief_is_nonempty_and_names_the_theme(theme):
    b = theme_layout_brief(theme)
    assert b, f"{theme}: expected a non-empty dialect brief"
    assert "composition dialect" in b
    assert "Layout variants per block" in b


@pytest.mark.parametrize("theme", SAMPLE_THEMES)
def test_brief_menu_matches_composer_pool(theme):
    """The load-bearing invariant: brief menu per block == composer pool per block (no drift)."""
    b = theme_layout_brief(theme)
    for block in VARIANTS:
        menu = _brief_block_menu(b, block)
        pool = _composer_pool(block, theme)
        # a block is listed iff it has a sanctioned pool; every listed id is in the pool and vice-versa
        assert menu is not None, f"{theme}/{block}: block missing from brief (pool={pool})"
        assert set(menu) == pool, f"{theme}/{block}: brief menu {set(menu)} != composer pool {pool}"


@pytest.mark.parametrize("theme", SAMPLE_THEMES)
def test_block_default_always_offered(theme):
    """A theme never strips a block of its canonical (default) form."""
    b = theme_layout_brief(theme)
    for block, reg in VARIANTS.items():
        menu = _brief_block_menu(b, block)
        assert reg["default"] in menu, f"{theme}/{block}: default {reg['default']!r} not offered"
