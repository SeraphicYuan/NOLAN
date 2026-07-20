"""Block x theme FIDELITY probe — the /themes "Blocks" tab source.

gen_samples.py exercises ~10 blocks with theme-NEUTRAL placeholder content; it can't show whether the
media-heavy blocks (gallery / carousel / collage / document / spotlight / comparison / …) actually pick
up a theme's tokens. This drives EVERY compose.py block with REAL content + real NOLAN assets under EVERY
theme, so the hub can render an all-blocks-x-theme QA grid with a per-block fidelity verdict.

Run:  python -X utf8 themes/scripts/gen_block_probe.py            (all blocks x all themes)
      python -X utf8 themes/scripts/gen_block_probe.py <theme>    (one theme)
then the node shooter on themes/_samples (it reads manifest.json — swap _block_probe_manifest.json in).
Assets live in themes/_samples/_probe/ (sample b-roll + a cutout, copied from projects/_library on first run).
Output: themes/_samples/probe_<block>__<theme>.{html,png} + _block_probe_manifest.json. (_samples is gitignored.)
"""
import json, re, sys, shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge"
sys.path.insert(0, str(BRIDGE)); sys.path.insert(0, str(REPO / "src"))
import compose  # noqa: E402

OUT = REPO / "themes" / "_samples"
A = "_probe"
DUR = 5.0
THEMES = ([sys.argv[1]] if len(sys.argv) > 1 else
          sorted(d.name for d in (REPO / "themes").iterdir() if (d / "theme.json").exists()))


def _ensure_assets():
    ap = OUT / A; ap.mkdir(parents=True, exist_ok=True)
    if not (ap / "img0.png").exists():
        broll = sorted((REPO / "projects" / "_library" / "_broll_generated").glob("*.png"))[:8]
        for i, f in enumerate(broll):
            shutil.copyfile(f, ap / f"img{i}.png")
        cut = REPO / "projects" / "aidc-2beat-test" / "assets" / "generated" / "scene_018.fg.png"
        if cut.exists():
            shutil.copyfile(cut, ap / "cutout0.png")
    (OUT / "vendor").mkdir(exist_ok=True)
    for f in (BRIDGE / "vendor").glob("*.js"):
        shutil.copyfile(f, OUT / "vendor" / f.name)
    for cand in (REPO / ".agents/skills/talking-head-recut/assets/vendor/gsap.min.js",
                 REPO / "agent/skills/talking-head-recut/assets/vendor/gsap.min.js"):
        if cand.exists():
            shutil.copyfile(cand, OUT / "gsap.min.js"); break


def bg(theme):
    try:
        p = json.loads((REPO / "themes" / theme / "theme.json").read_text(encoding="utf-8")).get("preview", {})
        return p.get("shell") or p.get("surface") or "#111"
    except Exception:
        return "#111"


def mount(template, bgc):
    inner = re.sub(r"</?template>", "", template)
    inner = inner.replace("https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js", "gsap.min.js")
    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<style>html,body{{margin:0;padding:0}}#stage{{position:relative;width:1920px;height:1080px;"
            f"overflow:hidden;background:{bgc}}}</style></head><body><div id='stage'>{inner}</div></body></html>")


IMG = lambda i: f"{A}/img{i}.png"
# ── one scene of REAL content per block (an archives/history essay — suits the sample b-roll) ──
BLOCKS = {
 "stat": {"kicker": "By the record", "items": [
     {"value": "1440", "label": "movable type, the press", "underline": True, "delta": {"dir": "up", "value": "+210% literacy"}},
     {"value": "3.2x", "label": "books per decade after"}]},
 "statement": {"kicker": "The thesis", "lines": ["History is written", "by those who", "keep the records"], "operative": "keep the records"},
 "bullet_list": {"kicker": "What survived", "title": "Three fragile things", "titleHi": "fragile",
                 "items": ["Letters, burned for warmth", "Ledgers, eaten by damp", "Portraits, sold for the frame"]},
 "pull_quote": {"kicker": "In the margin", "hi": "foreign country", "cite": "L. P. Hartley, 1953",
                "quote": "The past is a foreign country; they do things differently there."},
 "ledger": {"kicker": "The catalogue", "rows": [
     {"title": "Manuscripts", "desc": "Vellum, ink, gold leaf", "meta": "01 · 1200s"},
     {"title": "Portraits", "desc": "Oil on oak panel", "meta": "02 · 1530s"},
     {"title": "Ceramics", "desc": "Red-figure, Attic", "meta": "03 · 480 BC"}]},
 "comparison_table": {"kicker": "By medium", "columns": [{"label": "Vellum"}, {"label": "Paper", "highlight": True}, {"label": "Digital"}],
                      "rows": [{"label": "Survives fire", "cells": ["partial", "no", "yes"]},
                               {"label": "Survives damp", "cells": ["yes", "no", "partial"]},
                               {"label": "Cost", "cells": ["$$$$", "$$", "$"]}]},
 "chart": {"kicker": "Holdings", "title": "Items catalogued", "suffix": "k", "highlight": 3,
           "series": [{"label": "'90", "value": 12}, {"label": "'00", "value": 28}, {"label": "'10", "value": 51}, {"label": "'20", "value": 86}]},
 "timeline": {"title": "A short history", "events": [
     {"year": "1440", "label": "Movable type", "image": IMG(1)}, {"year": "1476", "label": "First English press"},
     {"year": "1605", "label": "The newspaper", "image": IMG(0)}]},
 "geo": {"kind": "world", "highlight": ["276", "826", "250"], "primary": "276", "kicker": "Provenance",
         "title": "Where it was made", "sub": "Three <b>European</b> workshops"},
 "diagram": {"kicker": "The archive", "title": "How it is kept",
             "root": {"label": "Archive", "children": [
                 {"label": "Manuscripts", "children": [{"label": "Vellum"}, {"label": "Paper"}]},
                 {"label": "Objects", "children": [{"label": "Ceramics"}, {"label": "Metal"}]}]}},
 "code": {"kicker": "The finding aid", "title": "query.py", "filename": "query.py", "linenums": True, "theme": "vs-dark",
          "code": "def find(archive, year):\n    return [x for x in archive\n            if x.year == year\n            and x.medium == 'vellum']"},
 "gallery": {"kicker": "The collection", "title": "Recent acquisitions", "captions": True,
             "images": [{"src": IMG(0), "caption": "The Elder"}, {"src": IMG(1), "caption": "Portrait, c.1530"},
                        {"src": IMG(2), "caption": "Attic vase"}, {"src": IMG(4), "caption": "The Penitent"}]},
 "carousel": {"kicker": "A closer look", "title": "The vase", "style": "coverflow",
              "images": [{"src": IMG(2)}, {"src": IMG(0)}, {"src": IMG(4)}]},
 "collage": {"kicker": "The cast", "layout": "heroes", "backdrop": "var(--shell)", "subjects": [{"src": f"{A}/cutout0.png"}]},
 "comparison": {"kicker": "Before / after", "title": "Restoration", "vs": True,
                "left": {"type": "image", "src": IMG(1), "label": "BEFORE"}, "right": {"type": "image", "src": IMG(0), "label": "AFTER"}},
 "document": {"kicker": "The source", "title": "Folio 12r", "source": IMG(1), "mode": "artifact", "aged": True},
 "spotlight": {"subject": f"{A}/cutout0.png", "words": ["THE", "SUBJECT"], "kicker": "In focus", "position": "center"},
 "lower_third": {"kicker": "Curator", "name": "Dr. Elena Fischer", "role": "Head of Manuscripts, The British Library",
                 "style": "bar", "backdrop": IMG(4)},
 "newshead": {"date": "Nov 12, 2025", "source": "The Chronicle", "headline": ["A lost folio", "returns home"],
              "highlight": "returns home", "subhead": "After two centuries, a manuscript resurfaces.",
              "image": IMG(0), "caption": "The recovered folio", "arrow": True},
 "social_card": {"platform": "x", "name": "The Archive", "handle": "archive", "verified": True,
                 "text": "After 200 years, folio 12r is home. A thread on what it took to bring it back.",
                 "likes": 1240, "reposts": 330, "replies": 88},
 "linedraw": {"kicker": "The drawing", "viewBox": "0 0 100 100", "paths": ["M20 82 L50 18 L80 82 Z", "M34 82 L66 82", "M50 18 L50 60"]},
 "juxtaposition": {"kicker": "TWO ACCOUNTS", "vs": "OR",
                   "left": {"type": "text", "kicker": "The victor", "lines": ["We freed", "the city."], "highlight": "freed"},
                   "right": {"type": "text", "kicker": "The vanquished", "lines": ["They burned", "our home."], "highlight": "burned"}},
 "annotate": {"src": IMG(1), "kicker": "THE FOLIO", "title": "What the page tells us", "titleHi": "tells",
              "callouts": [{"x": 0.3, "y": 0.3, "text": "Marginalia, a later hand"},
                           {"x": 0.66, "y": 0.42, "text": "Gold-leaf initial"},
                           {"x": 0.4, "y": 0.7, "text": "Water damage, 1600s"}]},
 "quadrant": {"kicker": "THE COLLECTION", "title": "Value vs fragility", "titleHi": "fragility",
              "x": {"label": "Fragility", "lo": "Robust", "hi": "Fragile"}, "y": {"label": "Value", "lo": "Low", "hi": "High"},
              "quadrants": {"tl": "Insure", "tr": "Vault", "bl": "Store", "br": "Handle freely"},
              "items": [{"x": 0.8, "y": 0.85, "label": "Manuscripts", "hl": True}, {"x": 0.3, "y": 0.68, "label": "Bronzes"},
                        {"x": 0.74, "y": 0.3, "label": "Ceramics"}, {"x": 0.26, "y": 0.26, "label": "Prints"}]},
 "venn": {"kicker": "WHAT MAKES IT MATTER", "title": "A true treasure", "titleHi": "treasure", "overlap": "Priceless",
          "sets": [{"sub": "old", "label": "Ancient"}, {"sub": "whole", "label": "Intact"}, {"sub": "known", "label": "Provenanced"}]},
 "sankey": {"kicker": "THE ARCHIVE", "title": "What it holds", "titleHi": "holds", "unit": "%",
            "source": {"label": "Collection", "value": 100},
            "targets": [{"label": "Manuscripts", "value": 42, "hl": True}, {"label": "Objects", "value": 26},
                        {"label": "Prints", "value": 18}, {"label": "Correspondence", "value": 14}]},
 "scale": {"kicker": "A SENSE OF TIME", "title": "Ages apart", "titleHi": "apart", "unit": " yrs", "ratio": "4x older",
           "items": [{"label": "The press", "value": 580}, {"label": "The vase", "value": 2500, "hl": True}]},
}
# per-block fidelity verdict shown in the hub (theme-independent judgement; 'flag' is dark-theme-specific)
VERDICTS = {
 "stat": ("pass", "Ground, italic numerals, accent stub — full token pickup."),
 "statement": ("pass", "Display lines + operative-sweep in the theme's type + accent."),
 "bullet_list": ("pass", "Title, highlight, per-theme bullet marker."),
 "pull_quote": ("pass", "Quote-mark + highlight + body all tokenised."),
 "ledger": ("pass", "Row titles, ordinals, mono meta."),
 "comparison_table": ("pass", "Labels, state chips, highlighted-column tint."),
 "chart": ("pass", "Accent bar + muted rest; ground via _page_bg()."),
 "geo": ("pass", "Map ground + accent-filled regions + leader."),
 "carousel": ("pass", "Title + field read as themed."),
 "collage": ("pass", "Backdrop honours var(--shell)."),
 "lower_third": ("pass", "Surface card + accent tab + themed name."),
 "linedraw": ("pass", "Stroke inherits the theme ink; accent kicker."),
 "code": ("own", "Chrome is themed; the SYNTAX palette is deliberately its own."),
 "social_card": ("own", "Backdrop themed; the card is the platform's brand chrome by design."),
 "newshead": ("own", "A newspaper identity; accent highlight comes through."),
 "timeline": ("cine", "Cinematic camera-pan on a fixed dark ground; accent picked up."),
 "spotlight": ("cine", "Cinematic dark stage; type + accent themed, ground generic."),
 "diagram": ("pass", "Ground, nodes, links, root all theme-token driven (theme-faithful fix)."),
 "comparison": ("pass", "Gap/ground via _page_bg(); chips + VS themed (theme-faithful fix)."),
 "document": ("pass", "Ground via _page_bg() on both polarities (theme-faithful fix)."),
 "gallery": ("pass", "Backdrop defaults to var(--shell); framed images + themed title."),
 "juxtaposition": ("pass", "Two paper zones, display type + operative sweep, themed rule + VS pivot."),
 "annotate": ("pass", "Image ground + accent markers/leader lines + surface label pills."),
 "quadrant": ("pass", "Themed axes/arrows/dots/labels; ground via _page_bg()."),
 "venn": ("pass", "Accent-tinted circles (color-mix, overlaps darken); surface overlap pill."),
 "sankey": ("pass", "Accent ribbons proportional to value; source/target nodes + labels themed."),
 "scale": ("pass", "Area-proportional accent circles; themed values, labels, ratio callout."),
}


def main():
    _ensure_assets()
    manifest = []
    for name, data in BLOCKS.items():
        v, note = VERDICTS.get(name, ("pass", ""))
        for theme in THEMES:
            sc = {"id": "s1", "start": 0.0, "dur": DUR, "type": name, "data": dict(data)}
            try:
                tpl = compose.compose_frame(f"probe_{name}", DUR, [sc], theme=theme)
                (OUT / f"probe_{name}__{theme}.html").write_text(mount(tpl, bg(theme)), encoding="utf-8")
                manifest.append({"block": name, "theme": theme, "verdict": v, "note": note,
                                 "html": f"probe_{name}__{theme}.html", "png": f"probe_{name}__{theme}.png"})
            except Exception as e:
                print(f"COMPOSE-FAIL {name}/{theme}: {e}")
    (OUT / "_block_probe_manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"composed {len(manifest)} block-probe cells ({len(BLOCKS)} blocks x {len(THEMES)} themes) -> _block_probe_manifest.json")


if __name__ == "__main__":
    main()
