"""Per-theme font loader (compose.py, audit F3).

Docs claim, tests enforce: the composer must load each theme's ACTUAL declared families (it used to
@import a fixed 4, so ~22/26 themes rendered in a fallback). This checks that every declared primary
family we CAN load (Google Fonts, post-substitution) appears in the emitted @import for every theme, the
base fonts the composer CSS hardcodes always load, and the unloadable ones (Fontshare/commercial) are
reported — visible, not silent."""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge"
for p in (str(REPO / "src"), str(BRIDGE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import compose  # noqa: E402

THEMES = sorted(d.name for d in (REPO / "themes").iterdir()
                if d.is_dir() and (d / "tokens.css").exists())


def _loaded(theme):
    return {f.replace("+", " ") for f in re.findall(r"family=([^:]+):", compose._theme_fonts(theme))}


def test_emits_only_valid_at_import_rules():
    css = compose._theme_fonts("newsroom")
    assert css.startswith("@import"), "font block must be @import rules (must precede other CSS)"
    assert "fonts.googleapis.com/css2" in css and "display=swap" in css


def test_base_fonts_always_load():
    # the composer CSS hardcodes Lora / Inter / Libre Franklin — they must load for every theme
    for th in THEMES:
        got = _loaded(th)
        assert {"Lora", "Inter", "Libre Franklin"} <= got, f"{th}: base fonts missing ({got})"


def test_every_loadable_declared_primary_is_actually_loaded():
    # no theme silently renders a supported family in a fallback: every declared primary that IS a
    # Google-Fonts family (after Source Han→Noto substitution) appears in that theme's @import.
    for th in THEMES:
        got = _loaded(th)
        for fam in compose._theme_font_families(th):
            fam = compose._FONT_SUBSTITUTE.get(fam, fam)
            if fam in compose._GF_WEIGHTS:
                assert fam in got, f"{th}: declared {fam!r} is loadable but not emitted"


def test_known_theme_faces_render():
    # spot-check the distinctive display faces (were falling back before F3)
    assert "Playfair Display" in _loaded("newsroom")
    assert "Archivo Black" in _loaded("bauhaus-bold")
    assert "Fraunces" in _loaded("kraft-paper")
    # Source Han → Noto substitution
    assert "Noto Sans SC" in _loaded("swiss-ikb") or "Noto Serif SC" in _loaded("dark-botanical")


def test_unloadable_fonts_are_reported_not_silent():
    # Fontshare/commercial families we can't @import must be surfaced (audit F3 tier B/D), not hidden.
    audit = (REPO / "docs" / "ENGINE_AUDIT.md").read_text(encoding="utf-8")
    unloadable = set()
    for th in THEMES:
        for fam in compose._theme_font_families(th):
            fam = compose._FONT_SUBSTITUTE.get(fam, fam)
            if fam not in compose._GF_WEIGHTS:
                unloadable.add(fam)
    # whatever the loader can't handle is named in the audit doc (so the gap is tracked)
    for fam in unloadable:
        assert fam in audit, f"unloadable font {fam!r} not recorded in docs/ENGINE_AUDIT.md"
