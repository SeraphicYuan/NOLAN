"""Type-role personality registry + executor (theme schema v2, Layer 1).

Docs claim, tests enforce: every theme names a personality that exists in the registry; the executor emits
that recipe's role vars resolving font slots against the theme's own fonts; every recipe (role, property)
is CONSUMED by a var(--{role}-{prop}) reference in the block CSS (the phantom-field guard); and the recipe
is emitted BEFORE tokens.css so a theme's explicit values still override (the ported exemplars keep theirs).
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge"
for p in (str(REPO / "src"), str(BRIDGE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import compose  # noqa: E402

REG = json.loads((REPO / "themes" / "composition" / "type_roles.json").read_text(encoding="utf-8"))
THEMES = sorted(d.name for d in (REPO / "themes").iterdir()
                if d.is_dir() and (d / "theme.json").exists())
COMPOSE_SRC = (BRIDGE / "compose.py").read_text(encoding="utf-8")


def test_registry_shape():
    assert REG["personalities"], "registry has no personalities"
    assert set(REG["slots"]) >= {"display", "body", "mono"}


def test_every_theme_has_a_valid_personality():
    ids = set(REG["personalities"])
    for th in THEMES:
        meta = json.loads((REPO / "themes" / th / "theme.json").read_text(encoding="utf-8"))
        tp = meta.get("typePersonality")
        assert tp in ids, f"{th}: typePersonality {tp!r} not in {sorted(ids)}"


def test_executor_emits_signature_role_vars():
    # elegant-italic → italic display + numerals (the vellum signature)
    css = compose._theme_type_roles("vellum")
    assert "--display-style: italic" in css and "--hero-num-style: italic" in css
    # editorial-serif → upright serif numerals
    assert "--hero-num-style: normal" in compose._theme_type_roles("newsroom")


def test_font_slots_resolve_to_theme_font_vars():
    # a mono-technical theme's eyebrow uses the mono slot → the theme's own --font-mono
    assert "--eyebrow-font: var(--font-mono)" in compose._theme_type_roles("blueprint")
    # a geometric-sans theme's eyebrow uses the display slot
    assert "--eyebrow-font: var(--font-display-en)" in compose._theme_type_roles("swiss-ikb")


def test_every_recipe_property_has_a_block_consumer():
    # phantom-field guard: every (role, prop) a recipe sets must be read by a var(--{role}-{prop})
    # reference in the composer source (else it's an authored value nothing consumes).
    for pid, recipe in REG["personalities"].items():
        for role, props in recipe.items():
            if role == "desc" or not isinstance(props, dict):
                continue
            for prop in props:
                token = f"var(--{role}-{prop}"
                assert token in COMPOSE_SRC, f"{pid}.{role}.{prop}: no block consumes {token})"


def test_recipe_emitted_before_tokens_css():
    # the executor must precede _theme_vars so a theme's own tokens.css overrides the recipe
    assert "_theme_type_roles(theme)}{_theme_vars(theme)}" in COMPOSE_SRC


def test_unknown_personality_emits_nothing():
    assert compose._theme_type_roles("__nonexistent__") == ""
