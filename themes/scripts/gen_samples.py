"""Generate the theme × archetype SAMPLE MATRIX: compose one canonical, theme-neutral seed scene per
archetype under every theme, mount each as a seek-able page, and (a sibling node script screenshots it).
The renders power the /themes "Samples" tab (visual specimen gallery) + double as an engine audit — any
cell that doesn't read as its archetype is a registry/layout finding (see docs/ENGINE_AUDIT.md).

Seeds are STATIC (final-state HTML, theme-neutral `var(--…)`, no motion) so a screenshot needs no timeline;
they exercise the archetype's LAYOUT, with neutral placeholder content (the sample shows the theme's
treatment, not a topic). Run:  python -X utf8 themes/scripts/gen_samples.py   then the node shooter.
"""
import json, re, sys
from pathlib import Path

# Windows-python path (this runs under D:\env\nolan\python.exe)
REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge"
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(BRIDGE))
import compose  # noqa: E402

OUT = REPO / "themes" / "_samples"
OUT.mkdir(parents=True, exist_ok=True)
DUR = 4.0
_PROBE = "_probe"                                        # shared image assets (see gen_block_probe) for visual samples


def _ensure_probe_assets():
    """Copy a couple of b-roll stills into _samples/_probe/ so visual samples (comparison variants) have real
    images. Idempotent; shares the dir gen_block_probe uses."""
    import shutil
    ap = OUT / _PROBE
    ap.mkdir(parents=True, exist_ok=True)
    if not (ap / "img4.png").exists():
        for i, f in enumerate(sorted((REPO / "projects" / "_library" / "_broll_generated").glob("*.png"))[:5]):
            shutil.copyfile(f, ap / f"img{i}.png")

# ── canonical seeds — one per archetype (static, theme-neutral). type "raw" = hand-authored final-state;
# a block name = the real production block (shows exactly what the pipeline emits).
_CENTERED_HERO = (
    '<section class="scene clip" data-track-index="2" style="position:absolute;inset:0;display:flex;'
    'flex-direction:column;align-items:center;justify-content:center;gap:calc(2.4cqh*var(--density,1));color:var(--text)">'
    '<div style="font-weight:var(--eyebrow-weight,700);'
    'font-size:calc(var(--eyebrow-size,1.15cqw)*var(--type-scale,1));'
    'font-family:var(--eyebrow-font,var(--font-mono)),ui-monospace;line-height:1;'
    'letter-spacing:var(--eyebrow-tracking,.34em);text-transform:var(--eyebrow-transform,uppercase);'
    'color:var(--eyebrow-color,var(--text-2))">By the numbers</div>'
    '<div style="font-weight:var(--hero-num-weight,800);font-style:var(--hero-num-style,normal);font-size:calc(20cqw*var(--type-scale,1));line-height:0.84;font-family:var(--hero-num-font,var(--font-display-en));letter-spacing:var(--hero-num-track,-0.02em)">'
    '73<span style="color:var(--accent)">%</span></div>'
    '<div style="width:8cqw;height:0.5cqh;background:var(--accent);border-radius:2px"></div></section>')

_FRAMED = (
    '<section class="scene clip" data-track-index="2" style="position:absolute;inset:0;display:flex;'
    'align-items:center;justify-content:center;color:var(--text)">'
    '<div style="width:50cqw;height:60cqh;border:var(--bw,2px) solid var(--text);border-radius:var(--r-card,4px);'
    'box-shadow:var(--card-shadow,none);'
    'display:flex;flex-direction:column;align-items:center;justify-content:center;gap:calc(2.2cqh*var(--density,1));'
    'background:var(--surface)">'
    '<div style="font:700 0.95cqw/1 var(--font-mono),ui-monospace;letter-spacing:.32em;'
    'text-transform:uppercase;color:var(--text-2)">Figure 01</div>'
    '<div style="font:600 calc(3.2cqw*var(--type-scale,1))/1.15 var(--font-display-en);font-style:var(--display-style,normal);text-align:center;max-width:36cqw">'
    'The specimen, framed<br>and presented</div></div></section>')

_SWISS_GRID = (
    '<section class="scene clip" data-track-index="2" style="position:absolute;inset:calc(9cqw*var(--density,1));display:grid;'
    'grid-template-columns:1fr 1fr 1fr;grid-auto-rows:1fr;gap:calc(2.4cqw*var(--density,1));color:var(--text)">'
    + "".join(
        '<div style="border-top:2px solid var(--accent);padding-top:1.4cqh">'
        f'<div style="font:800 calc(4.6cqw*var(--type-scale,1))/1 var(--font-display-en)">{i:02d}</div>'
        '<div style="font:600 1cqw/1.35 var(--font-mono),ui-monospace;letter-spacing:.14em;'
        'text-transform:uppercase;color:var(--text-2);margin-top:0.8cqh">Item label</div></div>'
        for i in range(1, 7))
    + '</section>')

_SIDEBAR = (
    '<section class="scene clip" data-track-index="2" style="position:absolute;inset:0;display:flex;'
    'color:var(--text)">'
    '<div style="width:22cqw;background:var(--accent);color:var(--surface);display:flex;'
    'align-items:center;justify-content:center;font:800 calc(13cqw*var(--type-scale,1))/1 var(--font-display-en)">01</div>'
    '<div style="flex:1;display:flex;flex-direction:column;justify-content:center;padding:0 calc(6cqw*var(--density,1));'
    'gap:calc(1.6cqh*var(--density,1))">'
    '<div style="font:700 0.95cqw/1 var(--font-mono),ui-monospace;letter-spacing:.32em;'
    'text-transform:uppercase;color:var(--text-2)">The first step</div>'
    '<div style="font:700 calc(4cqw*var(--type-scale,1))/1.12 var(--font-display-en);font-style:var(--display-style,normal);max-width:52cqw">'
    'A running marker beside the body</div></div></section>')

# a clean, static, theme-robust timeline (all events visible on a spine; no images; respects polarity) —
# the archetype's ideal layout (the Vox `timeline` block is the animated cinematic production variant)
_TIMELINE = (
    '<section class="scene clip" data-track-index="2" style="position:absolute;inset:0;display:flex;'
    'flex-direction:column;justify-content:center;padding:0 calc(9cqw*var(--density,1));color:var(--text)">'
    '<div style="font:700 0.95cqw/1 var(--font-mono),ui-monospace,monospace;letter-spacing:.32em;'
    'text-transform:uppercase;color:var(--text-2)">A short history</div>'
    '<div style="position:relative;margin-top:13cqh;height:0.32cqh;background:var(--accent)">'
    + "".join(
        f'<div style="position:absolute;left:{x}%;top:50%;transform:translate(-50%,-50%);text-align:center">'
        f'<div style="position:absolute;left:50%;bottom:2.4cqh;transform:translateX(-50%);'
        f'font:800 calc(3.4cqw*var(--type-scale,1))/1 var(--font-display-en);font-style:var(--display-style,normal);white-space:nowrap">{yr}</div>'
        '<div style="width:1.5cqw;height:1.5cqw;border-radius:50%;background:var(--accent);'
        'border:0.28cqw solid var(--surface);box-sizing:border-box"></div>'
        f'<div style="position:absolute;left:50%;top:2.4cqh;transform:translateX(-50%);'
        f'font:600 0.9cqw/1.35 var(--font-mono),ui-monospace,monospace;letter-spacing:.08em;'
        f'text-transform:uppercase;color:var(--text-2);white-space:nowrap">{lb}</div></div>'
        for x, yr, lb in [(12, "1969", "First<br>message"), (37, "1983", "TCP / IP"),
                          (62, "1991", "The web"), (87, "2007", "Mobile")])
    + '</div></section>')

# ── the 3 archetypes that previously had no specimen (split-screen / full-bleed-overlay / focal-card).
# Static, theme-neutral var() layouts in the same house style as the other raw archetype seeds. ──
_SPLIT_SCREEN = (
    '<section class="scene clip" data-track-index="2" style="position:absolute;inset:0;display:flex;color:var(--text)">'
    '<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2.4cqh;padding:0 6cqw">'
    '<div style="font:700 0.9cqw/1 var(--font-mono),ui-monospace,monospace;letter-spacing:.3em;text-transform:uppercase;color:var(--text-2)">Before</div>'
    '<div style="font-weight:var(--display-weight,700);font-style:var(--display-style,normal);font-size:calc(9cqw*var(--type-scale,1));line-height:1;font-family:var(--font-display-en)">Slow</div></div>'
    '<div style="width:var(--rule-w,2px);background:var(--rule)"></div>'
    '<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2.4cqh;padding:0 6cqw;background:var(--accent);color:var(--accent-ink)">'
    '<div style="font:700 0.9cqw/1 var(--font-mono),ui-monospace,monospace;letter-spacing:.3em;text-transform:uppercase;opacity:.82">After</div>'
    '<div style="font-weight:var(--display-weight,700);font-style:var(--display-style,normal);font-size:calc(9cqw*var(--type-scale,1));line-height:1;font-family:var(--font-display-en)">Fast</div></div></section>')

_FULL_BLEED_OVERLAY = (
    '<section class="scene clip" data-track-index="2" style="position:absolute;inset:0;color:#fff">'
    '<div style="position:absolute;inset:0;background:radial-gradient(ellipse 72% 62% at 64% 30%,var(--accent),transparent 66%),linear-gradient(150deg,var(--text),var(--shell))"></div>'
    '<div style="position:absolute;inset:0;background:linear-gradient(transparent 42%,rgba(0,0,0,0.6))"></div>'
    '<div style="position:absolute;left:6cqw;right:6cqw;bottom:12cqh">'
    '<div style="font:700 0.9cqw/1 var(--font-mono),ui-monospace,monospace;letter-spacing:.3em;text-transform:uppercase;opacity:.85;margin-bottom:2.2cqh">The feature</div>'
    '<div data-fit data-fit-w="88cqw" data-fit-origin="left bottom" style="font-weight:var(--display-weight,700);font-style:var(--display-style,normal);font-size:calc(8cqw*var(--type-scale,1));line-height:1.04;font-family:var(--font-display-en);white-space:nowrap">The whole story,<br>in one frame</div></div></section>')

_FOCAL_CARD = (
    '<section class="scene clip" data-track-index="2" style="position:absolute;inset:0;display:flex;flex-direction:column;'
    'align-items:center;justify-content:center;gap:3.2cqh;color:var(--text)">'
    '<div style="font:700 0.9cqw/1 var(--font-mono),ui-monospace,monospace;letter-spacing:.3em;text-transform:uppercase;color:var(--text-2)">The subject</div>'
    '<div style="width:30cqw;height:46cqh;background:var(--surface);border:var(--bw,2px) solid var(--rule);'
    'border-radius:var(--r-card,10px);box-shadow:var(--card-shadow,0 1cqw 3cqw rgba(0,0,0,0.2));display:flex;align-items:center;justify-content:center">'
    '<div style="font-weight:var(--display-weight,700);font-style:var(--display-style,normal);font-size:calc(5cqw*var(--type-scale,1));font-family:var(--font-display-en)">Fig 1</div></div></section>')

# THEME IDENTITY CARD — a single specimen that shows the theme's DNA in its own tokens: the palette
# (shell/surface/accent/text + the derived ladder), the four type roles (eyebrow / display / stat-value /
# body / mono), and the shape (card radius + border weight + card-shadow). Generic (no theme name — the
# book generator adds that); every value is a var() so it renders in the theme's real identity, and the
# theme's declared decoration furniture auto-composites over it. This is the hero panel of the theme book.
_ID_SW = [("shell", "var(--shell)"), ("surface", "var(--surface)"), ("surface-2", "var(--surface-2)"),
          ("accent", "var(--accent)"), ("accent 8%", "var(--accent-soft)"), ("rule", "var(--rule)"),
          ("text", "var(--text)"), ("text-2", "var(--text-2)")]
_IDENTITY = (
    '<section class="scene clip" data-track-index="2" style="position:absolute;inset:0;'
    'padding:5.5cqw 6cqw;color:var(--text);display:flex;flex-direction:column;justify-content:center;'
    'gap:4cqh;font-family:var(--font-body)">'
    '<div style="display:flex;gap:1.3cqw">'
    + "".join(f'<div style="flex:1;display:flex;flex-direction:column;gap:0.9cqh">'
              f'<div style="height:7.5cqh;border-radius:var(--r-card,4px);background:{c};'
              f'border:1px solid var(--rule,rgba(128,128,128,0.28))"></div>'
              f'<div style="font-family:var(--font-mono),ui-monospace;font-size:0.72cqw;letter-spacing:.05em;'
              f'color:var(--text-2);text-transform:uppercase">{n}</div></div>'
              for n, c in _ID_SW)
    + '</div>'
    '<div style="display:flex;gap:4cqw;align-items:center">'
    '<div style="font-family:var(--hero-num-font,var(--font-display-en));font-style:var(--hero-num-style,normal);'
    'font-weight:var(--hero-num-weight,800);font-size:9cqw;line-height:0.78;'
    'letter-spacing:var(--hero-num-track,-0.02em)">73<span style="color:var(--accent)">%</span></div>'
    '<div style="flex:1;display:flex;flex-direction:column;gap:1.3cqh">'
    '<div style="font-family:var(--eyebrow-font,var(--font-mono)),ui-monospace;font-weight:var(--eyebrow-weight,600);'
    'letter-spacing:var(--eyebrow-tracking,.2em);text-transform:var(--eyebrow-transform,uppercase);'
    'font-size:1cqw;color:var(--eyebrow-color,var(--text-2))">Eyebrow · the kicker</div>'
    '<div style="font-family:var(--font-display-en);font-style:var(--display-style,normal);'
    'font-weight:var(--display-weight,700);font-size:3.1cqw;line-height:1.02">The quick brown fox jumps</div>'
    '<div style="font-family:var(--font-body);font-size:1.35cqw;line-height:1.4;color:var(--text-2);max-width:50cqw">'
    'Body — over the lazy dog. The five boxing wizards jump quickly. 0123456789.</div>'
    '<div style="font-family:var(--font-mono),ui-monospace;font-size:0.95cqw;letter-spacing:.12em;color:var(--text-mute)">'
    'MONO · LABEL · CAPTION · 01 / 02 / 03</div>'
    '</div>'
    '<div style="width:15cqw;height:20cqh;border:var(--bw,2px) solid var(--text);border-radius:var(--r-card,4px);'
    'box-shadow:var(--card-shadow,none);background:var(--surface);display:flex;flex-direction:column;'
    'align-items:center;justify-content:center;gap:0.6cqh">'
    '<div style="font-family:var(--font-display-en);font-style:var(--display-style,normal);'
    'font-weight:var(--display-weight,700);font-size:2cqw">Card</div>'
    '<div style="font-family:var(--font-mono),ui-monospace;font-size:0.7cqw;color:var(--text-2)">radius·border·shadow</div>'
    '</div></div></section>')

# The first six are ARCHETYPE specimens (canonical layout per archetype). The last three are BLOCK
# specimens — real production blocks that exercise the type-role / component character the archetype seeds
# don't: `stat` shows the LIVE stat block (hero-num + stat-label roles), `bullet-list` shows the
# bullet-marker component (Layer 4), `chart` shows the bar shape (Layer 3). A `_arch` maps a block specimen
# to its home archetype for the scene meta (the specimen KEY stays the label in the matrix).
SEEDS = {
    "identity":         {"type": "raw", "_arch": "framed", "data": {"html": [_IDENTITY], "tl": []}},
    "centered-hero":    {"type": "raw", "data": {"html": [_CENTERED_HERO], "tl": []}},
    "editorial-column": {"type": "statement",
                         "data": {"kicker": "The claim", "lines": ["The models are", "getting cheaper", "and better"],
                                  "captionBar": "Source: model benchmarks 2021–2024"}},
    "framed":           {"type": "raw", "data": {"html": [_FRAMED], "tl": []}},
    "swiss-grid":       {"type": "raw", "data": {"html": [_SWISS_GRID], "tl": []}},
    "sidebar":          {"type": "raw", "data": {"html": [_SIDEBAR], "tl": []}},
    "timeline":         {"type": "raw", "data": {"html": [_TIMELINE], "tl": []}},
    "split-screen":     {"type": "raw", "data": {"html": [_SPLIT_SCREEN], "tl": []}},
    "full-bleed-overlay": {"type": "raw", "data": {"html": [_FULL_BLEED_OVERLAY], "tl": []}},
    "focal-card":       {"type": "raw", "data": {"html": [_FOCAL_CARD], "tl": []}},
    "quadrant":         {"type": "quadrant", "_arch": "quadrant",
                         "data": {"kicker": "Where to focus", "title": "Effort vs impact", "titleHi": "impact",
                                  "x": {"label": "Effort", "lo": "Low", "hi": "High"}, "y": {"label": "Impact", "lo": "Low", "hi": "High"},
                                  "quadrants": {"tl": "Quick wins", "tr": "Big bets", "bl": "Time sinks", "br": "Fill-ins"},
                                  "items": [{"x": 0.22, "y": 0.82, "label": "Captions", "hl": True}, {"x": 0.78, "y": 0.84, "label": "New renderer"},
                                            {"x": 0.24, "y": 0.24, "label": "Logo tweak"}, {"x": 0.72, "y": 0.2, "label": "Rewrite CLI"}]}},
    "asymmetric-hero":  {"type": "hero", "_arch": "asymmetric-hero",
                         "data": {"src": f"{_PROBE}/img0.png", "side": "left", "kicker": "Chapter one",
                                  "title": ["The idea that", "changed everything"], "titleHi": "changed", "sub": "A story in three acts."}},
    "stat":             {"type": "stat", "_arch": "centered-hero",
                         "data": {"kicker": "By the numbers",
                                  "items": [{"value": "73%", "label": "of teams shipped faster", "underline": True, "cue": 0.6,
                                             "delta": {"dir": "up", "value": "+12 pts YoY"}},
                                            {"value": "2.4x", "label": "median throughput gain", "cue": 1.0,
                                             "delta": {"dir": "down", "value": "-0.3x QoQ"}}]}},
    "bullet-list":      {"type": "bullet_list", "_arch": "editorial-column",
                         "data": {"kicker": "What changed", "title": "Three shifts that matter", "titleHi": "matter",
                                  "items": ["Models got cheaper and better", "Context windows grew to millions",
                                            "Agents can now use real tools"]}},
    "chart":            {"type": "chart", "_arch": "framed",
                         "data": {"kicker": "Adoption", "title": "Growth by year", "type": "bar", "suffix": "%",
                                  "highlight": 3,
                                  "series": [{"label": "'21", "value": 18}, {"label": "'22", "value": 34},
                                             {"label": "'23", "value": 52}, {"label": "'24", "value": 73}]}},
    "pull-quote":       {"type": "pull_quote", "_arch": "editorial-column",
                         "data": {"kicker": "In their words", "hi": "invent it", "cite": "Alan Kay, 1971",
                                  "quote": "The best way to predict the future is to invent it."}},
    "comparison-table": {"type": "comparison_table", "_arch": "comparison-table",
                         "data": {"kicker": "How we compare",
                                  "columns": [{"label": "Manual"}, {"label": "NOLAN", "highlight": True}, {"label": "Others"}],
                                  "rows": [{"label": "Theme-aware", "cells": ["no", "yes", "partial"]},
                                           {"label": "Auto-render", "cells": ["partial", "yes", "no"]},
                                           {"label": "Editable", "cells": ["yes", "yes", "partial"]},
                                           {"label": "Cost", "cells": ["$$$$", "$", "$$$"]}]}},
    "ledger":           {"type": "ledger", "_arch": "ledger",
                         "data": {"kicker": "Contents",
                                  "rows": [{"title": "Ingest", "desc": "Source → beats, split by narration", "meta": "01 · 2 min"},
                                           {"title": "Author", "desc": "Scene plan against a chosen theme", "meta": "02 · 4 min"},
                                           {"title": "Acquire", "desc": "Assets per beat: library + stock + gen", "meta": "03 · 6 min"},
                                           {"title": "Render", "desc": "Compose frames, assemble to final", "meta": "04 · 8 min"}]}},
    "comparison":       {"type": "comparison", "_arch": "split-screen",   # VISUAL contrast (comparison is image/video only now)
                         "data": {"kicker": "Before / after", "title": "The shift", "titleHi": "shift", "vs": True,
                                  "left": {"type": "image", "src": f"{_PROBE}/img1.png", "label": "2019"},
                                  "right": {"type": "image", "src": f"{_PROBE}/img0.png", "label": "NOW"}}},
}

THEMES = sorted(d.name for d in (REPO / "themes").iterdir()
                if d.is_dir() and (d / "theme.json").exists())

# ── layout-variant specimens (P3): render every variant of every variant-enabled block so the Samples
# tab shows a block's full arrangement range. Content is sized to each variant's sweet spot (a hero-single
# wants ONE figure, a two-col wants ~5 items) so each specimen reads at its best. ──
_VARIANT_BLOCKS = json.loads(
    (REPO / "themes" / "composition" / "layout_variants.json").read_text(encoding="utf-8")).get("blocks", {})
# a variant-enabled block's base SEEDS specimen is labelled by its archetype, not its block name — map so
# the variant specimens group under the SAME matrix cell as their cover (else stat matches but the
# hyphenated 'bullet-list' / the 'editorial-column' statement specimen would split into a second cell).
_BLOCK_TO_SPECIMEN = {"stat": "stat", "statement": "editorial-column", "bullet_list": "bullet-list",
                      "pull_quote": "pull-quote", "ledger": "ledger",
                      "comparison_table": "comparison-table", "timeline": "timeline", "comparison": "comparison",
                      "juxtaposition": "comparison"}   # split-screen sibling — group under the same specimen cell
_STAT_ITEMS = [{"value": "73%", "label": "of teams shipped faster", "underline": True,
                "delta": {"dir": "up", "value": "+12 pts"}},
               {"value": "2.4x", "label": "median throughput gain", "delta": {"dir": "down", "value": "-0.3x"}},
               {"value": "11k", "label": "projects rendered"}]
_BULLET_ITEMS = ["Models got cheaper and better", "Context windows grew to millions", "Agents can now use real tools",
                 "Latency dropped below a second", "Costs fell 10x in two years"]


def _variant_content(block, v):
    """Best-fit specimen content for a (block, variant) pair — sized so each arrangement reads well."""
    if block == "stat":
        n = 1 if v == "hero-single" else (3 if v == "stacked-list" else 2)
        return {"kicker": "By the numbers", "items": [dict(x) for x in _STAT_ITEMS[:n]], "variant": v}
    if block == "statement":
        return {"kicker": "The claim", "lines": ["The models are", "getting cheaper", "and better"],
                "operative": "cheaper", "variant": v}
    if block == "bullet_list":
        n = 5 if v == "two-col" else (4 if v == "numbered-rail" else 3)
        return {"kicker": "What changed", "title": "Three shifts that matter", "titleHi": "matter",
                "items": list(_BULLET_ITEMS[:n]), "variant": v}
    if block == "pull_quote":
        return {"kicker": "In their words", "hi": "invent it", "cite": "Alan Kay, 1971",
                "quote": "The best way to predict the future is to invent it.", "variant": v}
    if block == "ledger":
        rows = [{"title": "Ingest", "desc": "Source → beats, split by narration", "meta": "01 · 2 min"},
                {"title": "Author", "desc": "Scene plan against a chosen theme", "meta": "02 · 4 min"},
                {"title": "Acquire", "desc": "Assets per beat: library + stock + gen", "meta": "03 · 6 min"},
                {"title": "Render", "desc": "Compose frames, assemble to final", "meta": "04 · 8 min"},
                {"title": "Publish", "desc": "Captions, chapters, and the article", "meta": "05 · 3 min"},
                {"title": "Review", "desc": "Retention pass and a taste ledger", "meta": "06 · 2 min"}]
        n = 6 if v == "two-col" else 4
        return {"kicker": "Contents", "rows": rows[:n], "variant": v}
    if block == "comparison_table":
        return {"kicker": "How we compare",
                "columns": [{"label": "Manual"}, {"label": "NOLAN", "highlight": True}, {"label": "Others"}],
                "rows": [{"label": "Theme-aware", "cells": ["no", "yes", "partial"]},
                         {"label": "Auto-render", "cells": ["partial", "yes", "no"]},
                         {"label": "Editable", "cells": ["yes", "yes", "partial"]},
                         {"label": "Cost", "cells": ["$$$$", "$", "$$$"]}], "variant": v}
    if block == "timeline":
        return {"title": "A short history", "variant": v,
                "events": [{"year": "1969", "label": "First message"}, {"year": "1983", "label": "TCP / IP"},
                           {"year": "1991", "label": "The web"}, {"year": "2007", "label": "Mobile"}]}
    if block == "comparison":   # VISUAL contrast — two images (comparison is image/video only now)
        return {"kicker": "Before / after", "title": "The shift", "titleHi": "shift", "vs": True, "variant": v,
                "left": {"type": "image", "src": f"{_PROBE}/img1.png", "label": "2019"},
                "right": {"type": "image", "src": f"{_PROBE}/img0.png", "label": "NOW"}}
    if block == "juxtaposition":   # the NON-visual dialectic — text vs stat (no assets)
        return {"kicker": "THE SHIFT", "vs": "→", "variant": v,
                "left": {"type": "text", "kicker": "2019", "lines": ["Manual", "and slow"]},
                "right": {"type": "stat", "value": "3.2x", "label": "faster now"}}
    return {"variant": v}


# ── content-MODE showcase (2026-07-20): the layout-variant system covers the 8 text blocks' ARRANGEMENTS,
# but a block's content-MODE variety — chart bar/line/waterfall, pie vs donut, diagram tree/flow/radial,
# carousel/gallery/document/lower_third/code modes — is content-driven (not aesthetic) so it lives OUTSIDE
# layout_variants.json and was shown nowhere. Here we render each mode as a Samples-tab specimen tagged like
# a variant, so the click-through viewer browses a block's FULL look, not just its default.
_MODE_ARCH = {"chart": "framed", "pie": "centered-hero", "diagram": "swiss-grid", "lower_third": "focal-card",
              "code": "framed", "gallery": "swiss-grid", "carousel": "swiss-grid", "document": "focal-card"}
_MODE_HAS_SEED = {"chart"}      # chart's base (bar) is already a SEEDS specimen → its modes are pure variants


def _mode_showcase():
    A = _PROBE
    ser = [{"label": "'21", "value": 18}, {"label": "'22", "value": 34}, {"label": "'23", "value": 52}, {"label": "'24", "value": 73}]
    pie_segs = [{"label": "Manuscripts", "value": 42, "hl": True}, {"label": "Objects", "value": 26}, {"label": "Prints", "value": 18}, {"label": "Coins", "value": 14}]
    tree = {"label": "Archive", "children": [{"label": "Manuscripts", "children": [{"label": "Vellum"}, {"label": "Paper"}]},
                                             {"label": "Objects", "children": [{"label": "Ceramics"}, {"label": "Metal"}]}]}
    ltd = {"name": "Dr. Elena Fischer", "role": "Head of Manuscripts", "kicker": "Curator"}
    code_src = "def find(a, y):\n    return [x for x in a\n            if x.year == y]"
    return {
        "chart": [("line", {"type": "line", "kicker": "Adoption", "title": "Growth by year", "titleHi": "year", "suffix": "%", "series": ser}),
                  ("waterfall", {"type": "waterfall", "kicker": "The bridge", "title": "Revenue to profit", "titleHi": "profit", "prefix": "$", "suffix": "M",
                                 "series": [{"label": "Rev", "value": 120, "total": True}, {"label": "COGS", "value": -45}, {"label": "Opex", "value": -38}, {"label": "Profit", "value": 37, "total": True}]})],
        "pie": [("pie", {"kicker": "The collection", "title": "By medium", "titleHi": "medium", "segments": pie_segs}),
                ("donut", {"kicker": "The collection", "title": "By medium", "titleHi": "medium", "hole": 0.56, "center": "12,400", "segments": pie_segs})],
        "diagram": [("tree", {"layout": "tree", "kicker": "The archive", "title": "How it is kept", "titleHi": "kept", "root": tree}),
                    ("flow", {"layout": "flow", "kicker": "The pipeline", "title": "How it moves", "titleHi": "moves", "root": tree}),
                    ("radial", {"layout": "radial", "kicker": "The system", "title": "At the centre", "titleHi": "centre", "root": tree})],
        "lower_third": [("bar", {**ltd, "style": "bar"}), ("card", {**ltd, "style": "card"}),
                        ("underline", {**ltd, "style": "underline"}), ("block", {**ltd, "style": "block"})],
        "code": [("typing", {"mode": "typing", "title": "query.py", "filename": "query.py", "linenums": True, "theme": "vs-dark", "code": code_src}),
                 ("highlight", {"mode": "highlight", "title": "query.py", "filename": "query.py", "linenums": True, "theme": "vs-dark", "highlight": 2, "code": code_src})],
        "gallery": [("grid", {"layout": "grid", "kicker": "The collection", "title": "Recent", "captions": True,
                              "images": [{"src": f"{A}/img0.png"}, {"src": f"{A}/img1.png"}, {"src": f"{A}/img2.png"}, {"src": f"{A}/img4.png"}]}),
                    ("masonry", {"layout": "masonry", "kicker": "The collection", "title": "Recent",
                                 "images": [{"src": f"{A}/img0.png"}, {"src": f"{A}/img1.png"}, {"src": f"{A}/img2.png"}, {"src": f"{A}/img4.png"}]})],
        "carousel": [("slider", {"style": "slider", "kicker": "A closer look", "title": "The vase", "images": [{"src": f"{A}/img2.png"}, {"src": f"{A}/img0.png"}]}),
                     ("coverflow", {"style": "coverflow", "kicker": "A closer look", "title": "The vase", "images": [{"src": f"{A}/img2.png"}, {"src": f"{A}/img0.png"}, {"src": f"{A}/img4.png"}]})],
        "document": [("page", {"mode": "page", "kicker": "The source", "title": "Folio 12r", "source": f"{A}/img1.png"}),
                     ("artifact", {"mode": "artifact", "kicker": "The source", "title": "Folio 12r", "source": f"{A}/img1.png", "aged": True})],
    }


def theme_bg(theme):
    try:
        p = json.loads((REPO / "themes" / theme / "theme.json").read_text(encoding="utf-8")).get("preview", {})
        return p.get("shell") or p.get("surface") or "#111"
    except Exception:
        return "#111"


def mount(template, bg):
    inner = re.sub(r"</?template>", "", template)
    inner = inner.replace("https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js", "gsap.min.js")
    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<style>html,body{{margin:0;padding:0}}#stage{{position:relative;width:1920px;height:1080px;"
            f"overflow:hidden;background:{bg}}}</style></head><body><div id='stage'>{inner}</div></body></html>")


def main():
    # vendor gsap next to the mounted pages (empty-tl static seeds don't animate, but the compose output
    # registers a timeline; a present gsap makes the screenshotter fast — no per-cell timeout wait).
    import shutil
    for cand in (REPO / ".agents/skills/talking-head-recut/assets/vendor/gsap.min.js",
                 REPO / "agent/skills/talking-head-recut/assets/vendor/gsap.min.js"):
        if cand.exists():
            shutil.copyfile(cand, OUT / "gsap.min.js")
            break
    _ensure_probe_assets()                               # b-roll for the visual (comparison) variant samples
    manifest = []
    for label, seed in SEEDS.items():
        arche = seed.get("_arch", label)                 # real archetype for the scene meta
        body = {k: v for k, v in seed.items() if not k.startswith("_")}
        for theme in THEMES:
            scene = {"id": "s1", "start": 0.0, "dur": DUR, "meta": {"archetype": arche}, **body}
            tpl = compose.compose_frame(label, DUR, [scene], theme=theme)
            (OUT / f"{label}__{theme}.html").write_text(mount(tpl, theme_bg(theme)), encoding="utf-8")
            manifest.append({"archetype": label, "theme": theme,
                             "html": f"{label}__{theme}.html", "png": f"{label}__{theme}.png"})

    # ── layout-variant specimens (P3): one render per (block, variant, theme) so the Samples tab can show
    # the FULL range of a block's arrangements, not just the auto-picked one. Grouped under the block's
    # `archetype` label with a `variant` field the UI reads for its click-through viewer. ──
    # `timeline` variants (axis/dir) are real + authorable, but the block is a CINEMATIC camera-pan —
    # its static end-state shows only the last event on a fixed dark ground, a poor thumbnail. Its raw
    # archetype specimen (_TIMELINE, all events, theme-painted) is the sample; the axis variants aren't shot.
    _NO_STATIC_SPECIMEN = {"timeline"}
    nv = 0
    for block, reg in _VARIANT_BLOCKS.items():
        if block in _NO_STATIC_SPECIMEN:
            continue
        label = _BLOCK_TO_SPECIMEN.get(block, block)     # group under the base specimen's matrix cell
        for v in reg.get("variants", {}):
            data = _variant_content(block, v)
            for theme in THEMES:
                scene = {"id": "s1", "start": 0.0, "dur": DUR, "type": block, "data": dict(data)}
                tpl = compose.compose_frame(f"{block}~{v}", DUR, [scene], theme=theme)
                stem = f"{block}~{v}__{theme}"
                (OUT / f"{stem}.html").write_text(mount(tpl, theme_bg(theme)), encoding="utf-8")
                manifest.append({"archetype": label, "theme": theme, "variant": v,
                                 "html": f"{stem}.html", "png": f"{stem}.png"})
                nv += 1

    # ── content-mode showcases: a block's type/mode variety (chart bar/line/waterfall, pie/donut, diagram
    # tree/flow/radial, …) rendered + grouped under the block so the click-through viewer browses them. ──
    nm = 0
    for block, modes in _mode_showcase().items():
        arche = _MODE_ARCH.get(block, "framed")
        has_seed = block in _MODE_HAS_SEED
        for j, (mode, data) in enumerate(modes):
            is_variant = has_seed or j > 0
            stem_base = f"{block}~{mode}" if is_variant else block
            for theme in THEMES:
                scene = {"id": "s1", "start": 0.0, "dur": DUR, "type": block, "meta": {"archetype": arche}, "data": dict(data)}
                tpl = compose.compose_frame(stem_base, DUR, [scene], theme=theme)
                (OUT / f"{stem_base}__{theme}.html").write_text(mount(tpl, theme_bg(theme)), encoding="utf-8")
                entry = {"archetype": block, "theme": theme, "html": f"{stem_base}__{theme}.html", "png": f"{stem_base}__{theme}.png"}
                if is_variant:
                    entry["variant"] = mode
                manifest.append(entry)
                nm += 1

    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"composed {len(manifest)} cells ({len(SEEDS)} specimens + {nv} variant + {nm} mode specimens × {len(THEMES)} themes) → {OUT}")


if __name__ == "__main__":
    main()
