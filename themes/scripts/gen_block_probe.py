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
 "pie": {"kicker": "THE COLLECTION", "title": "By medium", "titleHi": "medium", "hole": 0.56, "center": "12,400",
         "segments": [{"label": "Manuscripts", "value": 42, "hl": True}, {"label": "Objects", "value": 26},
                      {"label": "Prints", "value": 18}, {"label": "Coins", "value": 14}]},
 "funnel": {"kicker": "ATTRIBUTION", "title": "How many survive the test", "titleHi": "survive", "unit": "",
            "stages": [{"label": "Claimed", "value": 1000}, {"label": "Catalogued", "value": 420},
                       {"label": "Authenticated", "value": 180, "hl": True}, {"label": "Masterworks", "value": 30}]},
 "spectrum": {"kicker": "DATING THE PIECE", "title": "Where it falls", "titleHi": "falls",
              "axis": {"lo": "Archaic", "hi": "Late"}, "zones": [{"x": 0, "x1": 0.33, "label": "Early"}, {"x0": 0.33, "x1": 0.66, "label": "Classical"}, {"x0": 0.66, "x1": 1, "label": "Late"}],
              "items": [{"x": 0.18, "label": "The vase", "sub": "480 BC", "hl": True}, {"x": 0.52, "label": "The relief"}, {"x": 0.82, "label": "The mosaic", "sub": "AD 200"}]},
 "cycle": {"kicker": "CONSERVATION", "title": "The care cycle", "titleHi": "cycle", "center": "Care",
           "steps": [{"label": "Survey"}, {"label": "Clean", "hl": True}, {"label": "Stabilise"}, {"label": "Store"}, {"label": "Monitor"}]},
 "detail_zoom": {"src": IMG(1), "kicker": "CLOSE READING", "title": "The brushwork", "titleHi": "brushwork",
                 "stops": [{"x": 0.34, "y": 0.32, "scale": 2.1, "caption": "The face, a later glaze", "sub": "note the impasto"},
                           {"x": 0.24, "y": 0.7, "scale": 2.4, "caption": "The gilt, worn thin"}]},
 "hero": {"src": IMG(0), "side": "left", "kicker": "PLATE I", "title": ["The sitter,", "unnamed"], "titleHi": "unnamed", "sub": "Oil on oak, c. 1530."},
 "chat_thread": {"kicker": "THE PROVENANCE", "subject": "Two curators", "messages": [
     {"from": "them", "text": "The seal doesn't match the 1780 inventory."},
     {"from": "me", "text": "Then where was it for a century?"},
     {"from": "them", "text": "That's the question, isn't it."}]},
 "connection_board": {"kicker": "THE TRAIL", "title": "Chain of custody", "titleHi": "custody", "nodes": [
     {"id": "a", "label": "The Workshop", "hl": True}, {"id": "b", "label": "A Duke", "sub": "1600s"},
     {"id": "c", "label": "The Auction"}, {"id": "d", "label": "The Museum"}],
     "links": [{"from": "a", "to": "b", "label": "commissioned"}, {"from": "b", "to": "c", "label": "sold"}, {"from": "c", "to": "d"}]},
 "spans": {"kicker": "THEY OVERLAPPED", "title": "Three workshops", "titleHi": "overlapped", "unit": "",
           "spans": [{"label": "Attic", "start": -530, "end": -320}, {"label": "Apulian", "start": -430, "end": -300, "hl": True}, {"label": "Campanian", "start": -400, "end": -320}]},
 # ── the dataset-bound data-viz forms (essay charts) ──
 "slope": {"kicker": "BY 1600", "title": "The press wins", "titleHi": "press", "cols": ["1500", "1600"], "suffix": "%", "highlight": 0,
           "series": [{"label": "Printed", "start": 8, "end": 71}, {"label": "Handwritten", "start": 88, "end": 22}, {"label": "Illuminated", "start": 30, "end": 6}]},
 "isotype": {"kicker": "THE HOLDINGS", "title": "Counted in folios", "titleHi": "folios", "per": 100, "unit": "folios",
             "items": [{"label": "Manuscripts", "value": 420}, {"label": "Prints", "value": 180}, {"label": "Maps", "value": 90}]},
 "dumbbell": {"kicker": "ATTRIBUTION", "title": "Claimed vs proven", "titleHi": "proven", "cols": ["Claimed", "Proven"], "sort": True,
              "items": [{"label": "Rembrandt", "start": 600, "end": 300}, {"label": "Hals", "start": 230, "end": 170}, {"label": "Vermeer", "start": 66, "end": 34}]},
 "small_multiples": {"kicker": "BY MEDIUM", "title": "The same climb, everywhere", "titleHi": "same climb",
                     "panels": [{"label": "Manuscripts", "series": [{"label": "'90", "value": 12}, {"label": "'00", "value": 28}, {"label": "'10", "value": 51}, {"label": "'20", "value": 86}]},
                                {"label": "Objects", "series": [{"label": "'90", "value": 8}, {"label": "'00", "value": 15}, {"label": "'10", "value": 30}, {"label": "'20", "value": 52}]},
                                {"label": "Prints", "series": [{"label": "'90", "value": 5}, {"label": "'00", "value": 12}, {"label": "'10", "value": 22}, {"label": "'20", "value": 40}]},
                                {"label": "Maps", "series": [{"label": "'90", "value": 3}, {"label": "'00", "value": 7}, {"label": "'10", "value": 14}, {"label": "'20", "value": 28}]},
                                {"label": "Coins", "series": [{"label": "'90", "value": 6}, {"label": "'00", "value": 9}, {"label": "'10", "value": 12}, {"label": "'20", "value": 20}]},
                                {"label": "Textiles", "series": [{"label": "'90", "value": 2}, {"label": "'00", "value": 5}, {"label": "'10", "value": 11}, {"label": "'20", "value": 24}]}]},
 "histogram": {"kicker": "DATING THE COLLECTION", "title": "Most pieces are recent", "titleHi": "recent", "unit": "years old",
               "marker": 580, "marker_label": "the press, 1440",
               "bins": [{"x0": 0, "x1": 80, "count": 52}, {"x0": 80, "x1": 160, "count": 74}, {"x0": 160, "x1": 240, "count": 63},
                        {"x0": 240, "x1": 320, "count": 48}, {"x0": 320, "x1": 400, "count": 31}, {"x0": 400, "x1": 480, "count": 22},
                        {"x0": 480, "x1": 560, "count": 14}, {"x0": 560, "x1": 640, "count": 9}, {"x0": 640, "x1": 720, "count": 5},
                        {"x0": 720, "x1": 800, "count": 3}]},
 "trajectory": {"title": "Value vs age", "xlabel": "Age (years)", "ylabel": "Value",
                "points": [{"x": 50, "y": 12, "label": "Print"}, {"x": 200, "y": 30}, {"x": 580, "y": 55, "label": "Folio"},
                           {"x": 1200, "y": 72}, {"x": 2500, "y": 96, "label": "Vase"}]},
 "stream": {"title": "The archive grows", "x": ["'90", "'00", "'10", "'20"],
            "series": [{"label": "Manuscripts", "values": [12, 20, 30, 42]}, {"label": "Objects", "values": [8, 14, 20, 26]},
                       {"label": "Prints", "values": [5, 10, 14, 18]}, {"label": "Coins", "values": [4, 7, 10, 14]}]},
 "bar_race": {"title": "Top medium by decade", "steps": ["'90", "'00", "'10", "'20"],
              "series": [{"label": "Manuscripts", "values": [12, 20, 30, 42]}, {"label": "Prints", "values": [18, 16, 22, 30]},
                         {"label": "Objects", "values": [8, 14, 26, 38]}, {"label": "Maps", "values": [3, 9, 14, 22]}]},
 "data_table": {"kicker": "THE CATALOGUE", "title": "By medium", "titleHi": "medium", "columns": ["Medium", "Count", "Oldest"],
                "rows": [["Manuscripts", "420", "1200s"], ["Objects", "260", "480 BC"], ["Prints", "180", "1470s"], ["Coins", "140", "300 BC"]],
                "highlight": {"row": 0}},
 "split_view": {"kicker": "READ ALONGSIDE", "paper": {"source": IMG(1), "page_size": [1000, 1294]}, "paper_side": "left", "split": 0.5,
                "right": {"kind": "stat", "kicker": "Folio 12r", "value": "1200s", "label": "vellum, ink, gold leaf"}},
 "gauge": {"kicker": "HOW MUCH SURVIVES", "title": "Condition on arrival", "titleHi": "Condition", "max": 100, "target": 75, "suffix": "%",
           "items": [{"label": "Manuscripts", "value": 68}, {"label": "Objects", "value": 84}, {"label": "Prints", "value": 41}]},
 "process": {"kicker": "CONSERVATION", "title": "From find to display", "titleHi": "display",
             "steps": [{"label": "Recover", "sub": "from the site"}, {"label": "Clean", "sub": "stabilise"},
                       {"label": "Catalogue", "sub": "provenance"}, {"label": "Display", "sub": "the gallery"}]},
 "layout": {"kicker": "THE HOLDINGS", "title": "The archive, in one look", "titleHi": "one look", "arrange": "split", "ratio": 0.6,
            "slots": [{"kind": "chart", "kicker": "Items catalogued", "series": [{"label": "'90", "value": 12}, {"label": "'00", "value": 28}, {"label": "'10", "value": 51}, {"label": "'20", "value": 86}]},
                      {"kind": "stat", "kicker": "Since 1990", "value": "7x", "label": "more items catalogued"}]},
}
# route-map demo on geo (adds arcs to the world map)
BLOCKS["geo"] = {**BLOCKS["geo"], "routes": [
    {"from": [12.5, 41.9], "to": [-0.1, 51.5], "label": "Rome → London", "hl": True},
    {"from": [23.7, 38.0], "to": [12.5, 41.9]}]}
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
 "pie": ("pass", "Accent slices at stepped opacity; legend + donut centre label themed."),
 "funnel": ("pass", "Accent trapezoids narrowing; labels with a surface halo."),
 "spectrum": ("pass", "Themed axis/zones/dots; a hl item uses --text."),
 "cycle": ("pass", "Surface node cards + accent loop arrows (marker arrowheads)."),
 "detail_zoom": ("pass", "Transformed camera over the image; surface caption cards per stop."),
 "hero": ("pass", "Full-bleed image + directional scrim; accent kicker/operative, white title."),
 "chat_thread": ("pass", "Accent (me) / surface (them) bubbles; themed header."),
 "connection_board": ("pass", "Surface node cards + accent links (dash-draw); hl accent border."),
 "spans": ("pass", "Accent duration bars (0.5 opacity so overlaps read); ticks + labels themed."),
 "slope": ("pass", "Drawn slope lines, accent highlight + muted rest; dual-axis labels themed."),
 "isotype": ("pass", "Accent unit-icon grid; legend + per-item labels themed."),
 "dumbbell": ("pass", "Accent gap bar + two dots; colour legend, values themed."),
 "small_multiples": ("pass", "Shared-scale mini bar grid; accent bars + panel titles themed."),
 "histogram": ("pass", "Accent distribution bars + marker line; axis labels themed."),
 "trajectory": ("pass", "Accent connected-scatter path (draws in order); ink + labels themed."),
 "stream": ("pass", "Accent stacked bands wipe in left→right; themed title."),
 "bar_race": ("pass", "Ranked accent bars + a period ticker; themed."),
 "data_table": ("pass", "Column headers, cells, highlighted row — surface + accent themed."),
 "split_view": ("pass", "Paper (aspect-preserving fit) + right panel; both slide in, themed."),
 "gauge": ("pass", "Accent radial arcs sweep to value; centre number + target tick themed."),
 "process": ("pass", "Accent step cards + numbered badges + drawn connectors; themed."),
 "layout": ("pass", "Curated arrangement of media/text/stat/chart cells; each cell theme-styled."),
}
VERDICTS["geo"] = ("pass", "Map ground + accent regions/leader; ROUTE ARCS (arrowheads, dash-draw) themed.")


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
