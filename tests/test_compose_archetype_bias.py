"""compose.py archetype-bias (B4b) + the THEME_MODULE_REVIEW knob-drop fix.

Docs claim, tests enforce:
- every scene's CONTENT root is stamped with `data-archetype`, matching the composition registry — a
  first-class DOM fact whose real consumer is the layout linter (reads it for anchor-drift on composed
  frames), so it can't rot into a phantom field;
- the composer HONOURS the theme's `--r-card` knob (was dropped — hardcoded radii) so a flat theme
  (swiss/bauhaus, `--r-card:var(--r-flat)`) actually gets flat cards.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge"
for p in (str(REPO / "src"), str(BRIDGE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import compose  # noqa: E402
from nolan import composition as comp  # noqa: E402


def _frame():
    scenes = [
        {"id": "s1", "type": "statement", "start": 0.0, "dur": 5.0,
         "data": {"lines": ["A single claim"], "kicker": "Analysis"}},
        {"id": "s2", "type": "stat", "start": 5.0, "dur": 5.0,
         "data": {"items": [{"value": "7", "label": "voices"}]}},
    ]
    return compose.compose_frame("t1", 10.0, scenes, theme="swiss-ikb")


def test_scene_content_root_is_stamped_with_its_archetype():
    html = _frame()
    arches = re.findall(r'data-archetype="([^"]+)"', html)
    # statement -> editorial-column, stat -> centered-hero (from the registry)
    assert arches == [comp.block_archetype("statement"), comp.block_archetype("stat")]
    assert arches == ["editorial-column", "centered-hero"]
    # stamped on the track-2 content element (not a ground/scrim)
    assert 'data-archetype="editorial-column" data-track-index="2"' in html


def test_stamp_matches_explicit_meta_archetype_over_block_type():
    scenes = [{"id": "s1", "type": "statement", "start": 0.0, "dur": 3.0,
               "meta": {"archetype": "full-bleed-overlay"},
               "data": {"lines": ["x"], "kicker": "K"}}]
    html = compose.compose_frame("t2", 3.0, scenes, theme="highlighter-editorial")
    assert 'data-archetype="full-bleed-overlay"' in html


def test_raw_scene_is_not_stamped_being_archetype_agnostic():
    scenes = [{"id": "s1", "type": "raw", "start": 0.0, "dur": 3.0,
               "data": {"html": ['<section data-track-index="2" style="position:absolute;inset:0">'
                                  '<div style="position:absolute;left:40cqw;top:45cqh">hi</div></section>'],
                        "tl": []}}]
    html = compose.compose_frame("t3", 3.0, scenes, theme="highlighter-editorial")
    assert "data-archetype=" not in html   # raw has no fixed archetype (unless meta sets one)


def test_r_card_knob_is_honoured_not_hardcoded():
    # the CSS references the theme var (was hardcoded px) on the generic cards
    css = compose.CSS
    assert "var(--r-card" in css, "composer CSS must reference the theme --r-card knob"
    assert css.count("var(--r-card") >= 5, "all generic card radii should honour --r-card"
    # and the theme actually injects it, so it resolves to the theme's value (flat for swiss)
    tv = compose._theme_vars("swiss-ikb")
    assert re.search(r"--r-card:\s*var\(--r-flat\)", tv), "swiss theme should inject a flat --r-card"
    tv2 = compose._theme_vars("highlighter-editorial")
    assert re.search(r"--r-card:\s*14px", tv2), "highlighter theme should inject a rounded --r-card"


def test_linter_reads_the_stamped_archetype_from_the_composed_dom():
    # the REAL consumer: the layout linter picks the archetype straight from data-archetype (no sidecar)
    from nolan.hyperframes import layout_lint as L
    html = _frame()
    items = L._measure(L._parse(html), L._class_pos_rules(L._extract_css(html)))
    seen = {i.archetype for i in items if i.archetype}
    assert "editorial-column" in seen or "centered-hero" in seen, "linter did not read data-archetype"
