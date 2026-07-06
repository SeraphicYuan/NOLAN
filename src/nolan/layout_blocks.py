"""Remotion-first layout rendering — template params → flow-block props.

Phase 3 of the architecture consolidation: `render_layout` tries the curated
Remotion blocks library first (the same blocks FLOW's Chapter composition
uses), falling back to the legacy Python renderers on any failure or unmapped
template. Set NOLAN_LEGACY_RENDER=1 to force the Python renderers.

Mechanism: a one-step Chapter job (exactly how FLOW renders a single beat) via
`remotion_source.render`. Blocks degrade gracefully without narration timing —
`revealFrames: []` reveals at frame 0 and `words: []` disables word-sync — so
a layout scene renders standalone; the premium/FLOW path later supplies real
word timings through the same blocks.

Each adapter returns (block_name, props) or None — None means "no faithful
mapping for these params, use the Python renderer" (e.g. a non-numeric
`statistic` value).
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_Adapted = Optional[Tuple[str, Dict[str, Any]]]


def _clean(props: Dict[str, Any]) -> Dict[str, Any]:
    """Drop None/empty-string values so block defaults apply."""
    return {k: v for k, v in props.items() if v is not None and v != ""}


def _num(value) -> Optional[float]:
    """Best-effort numeric parse ('73%', '2,300', 12) -> float, else None."""
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"-?\d[\d,]*\.?\d*", str(value))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


# --- per-template adapters ---------------------------------------------------

def _quote(p) -> _Adapted:
    return "PullQuote", _clean({
        "mode": "quote", "quote": p.get("quote", ""),
        "attribution": p.get("attribution")})


def _pull_quote(p) -> _Adapted:
    accent = " ".join(p.get("highlight_words") or []) or None
    return "PullQuote", _clean({
        "mode": "quote", "quote": p.get("quote", ""),
        "attribution": p.get("attribution"), "accentPhrase": accent})


def _definition(p) -> _Adapted:
    return "PullQuote", _clean({
        "mode": "definition", "term": p.get("term", ""),
        "definition": p.get("definition", "")})


def _counter(p) -> _Adapted:
    value = _num(p.get("value"))
    if value is None:
        return None
    stat = _clean({"value": value, "word": "", "label": str(p.get("label") or ""),
                   "prefix": p.get("prefix"), "suffix": p.get("suffix")})
    stat.setdefault("word", "")
    stat.setdefault("label", "")
    # closer/accentPhrase default to SAMPLE text — suppress explicitly.
    return "StatCount", {"stats": [stat], "closer": " ", "accentPhrase": " "}


def _statistic(p) -> _Adapted:
    value = _num(p.get("value"))
    if value is None:
        # Non-numeric "statistic" (e.g. Roman numerals "XI ANNI"): a count-up
        # makes no sense — render as big display type instead.
        if not p.get("value"):
            return None
        lines = [{"text": str(p["value"]), "accent": True}]
        if p.get("label"):
            lines.append({"text": str(p["label"])})
        return "HeroStatement", {"lines": lines}
    raw = str(p.get("value", ""))
    m = re.search(r"-?\d[\d,]*\.?\d*", raw)
    prefix = p.get("prefix") or (raw[:m.start()].strip() if m else "")
    suffix = p.get("suffix") or (raw[m.end():].strip() if m else "")
    decimals = 1 if value != int(value) else 0
    stat = {"value": value, "word": "", "label": str(p.get("label") or ""),
            "decimals": decimals}
    if prefix:
        stat["prefix"] = prefix
    if suffix:
        stat["suffix"] = suffix
    return "StatCount", {"stats": [stat], "closer": " ", "accentPhrase": " "}


def _timeline(p) -> _Adapted:
    # The blocks library has NO general chronology block: its `Timeline` is a
    # bespoke rhetorical device (anchor far-left, ticks crowded far-right, the
    # gap is the argument) and long tick labels pile up unreadably. A dated
    # sequence maps faithfully to StepFlow: year = the node label, event text
    # = the detail line, connectors draw on in order. >5 events -> None
    # (the python TimelineRenderer wraps and scales for long chronologies).
    events = [e for e in (p.get("events") or [])
              if isinstance(e, dict) and (e.get("year") or e.get("label"))]
    if not events or len(events) > 5:
        return None
    steps = [{"label": str(e.get("year", "")).strip() or str(i + 1),
              "detail": str(e.get("label", "")).strip()}
             for i, e in enumerate(events)]
    return "StepFlow", _clean({"kicker": p.get("title"), "steps": steps})


def _ranking(p) -> _Adapted:
    # No [:6] slice here — a truncated ranking lies. The Ranking budget
    # rejects >6 items and the python renderer (which fits more) takes over.
    items = []
    for it in (p.get("items") or []):
        if isinstance(it, (list, tuple)) and len(it) >= 2:
            items.append({"name": str(it[0]), "value": str(it[1])})
        elif isinstance(it, dict):
            items.append({"name": str(it.get("label", it.get("name", ""))),
                          "value": str(it.get("value", ""))})
        else:
            items.append({"name": str(it)})
    if not items:
        return None
    return "Ranking", _clean({"title": p.get("title"), "items": items})


def _comparison(p) -> _Adapted:
    if not (p.get("left_text") and p.get("right_text")):
        return None
    left = _clean({"title": str(p["left_text"]),
                   "points": [p["left_subtitle"]] if p.get("left_subtitle") else None})
    right = _clean({"title": str(p["right_text"]),
                    "points": [p["right_subtitle"]] if p.get("right_subtitle") else None})
    return "ComparisonVS", _clean({"left": left, "right": right,
                                   "kicker": p.get("center_label")})


def _stat_comparison(p) -> _Adapted:
    required = ("left_value", "left_label", "right_value", "right_label")
    if not all(p.get(k) is not None for k in required):
        return None
    return "ComparisonVS", _clean({
        "kicker": p.get("title"),
        "left": {"title": str(p["left_value"]), "points": [str(p["left_label"])]},
        "right": {"title": str(p["right_value"]), "points": [str(p["right_label"])]},
    })


def _question(p) -> _Adapted:
    if not p.get("question"):
        return None
    return "QuestionCard", _clean({"question": str(p["question"]),
                                   "context": p.get("context")})


def _chapter_card(p) -> _Adapted:
    if not p.get("title"):
        return None
    return "ChapterCard", _clean({"title": str(p["title"]),
                                  "index": p.get("chapter_number"),
                                  "subtitle": p.get("subtitle")})


def _section_divider(p) -> _Adapted:
    if not p.get("title"):
        return None
    return "ChapterCard", _clean({"title": str(p["title"]),
                                  "subtitle": p.get("subtitle")})


def _title(p) -> _Adapted:
    if not p.get("title"):
        return None
    lines = [{"text": str(p["title"]), "accent": True}]
    if p.get("subtitle"):
        lines.append({"text": str(p["subtitle"])})
    return "HeroStatement", {"lines": lines}


def _list(p) -> _Adapted:
    items = [{"label": str(x), "tag": ""} for x in (p.get("items") or [])]
    if not items:
        return None
    return "ListReveal", _clean({"title": p.get("title"), "items": items})


def _lower_third(p) -> _Adapted:
    if not p.get("name"):
        return None
    return "LowerThird", _clean({"name": str(p["name"]), "title": p.get("title")})


def _source_citation(p) -> _Adapted:
    if not p.get("source_name"):
        return None
    return "SourceCitation", _clean({
        "sourceName": str(p["source_name"]), "publication": p.get("publication"),
        "date": p.get("date"), "author": p.get("author"), "url": p.get("url")})


def _verdict(p) -> _Adapted:
    if not p.get("verdict"):
        return None
    return "VerdictCard", _clean({
        "verdict": str(p["verdict"]), "supportingText": p.get("supporting_text"),
        "verdictType": p.get("verdict_type")})


def _location_stamp(p) -> _Adapted:
    if not p.get("location"):
        return None
    return "LocationStamp", _clean({
        "location": str(p["location"]), "date": p.get("date"),
        "sublocation": p.get("sublocation"), "coordinates": p.get("coordinates")})


def _progress_bar(p) -> _Adapted:
    progress = _num(p.get("progress"))
    if progress is None:
        return None
    return "ProgressBar", _clean({
        "progress": max(0.0, min(1.0, progress)), "label": p.get("label"),
        "showPercentage": p.get("show_percentage"),
        "milestones": p.get("milestone_labels")})


def _percentage_bar(p) -> _Adapted:
    pct = _num(p.get("percentage"))
    if pct is None or not p.get("label"):
        return None
    return "PercentBar", _clean({"percentage": pct, "label": str(p["label"]),
                                 "context": p.get("context")})


def _tweet_card(p) -> _Adapted:
    if not p.get("content"):
        return None
    return "TweetCard", _clean({
        "content": str(p["content"]), "username": p.get("username"),
        "handle": p.get("handle"), "timestamp": p.get("timestamp"),
        "retweets": str(p["retweets"]) if p.get("retweets") is not None else None,
        "likes": str(p["likes"]) if p.get("likes") is not None else None,
        "verified": p.get("verified")})


def _news_headline(p) -> _Adapted:
    if not p.get("headline"):
        return None
    return "NewsHeadline", _clean({
        "headline": str(p["headline"]), "source": p.get("source"),
        "newsType": p.get("news_type"), "label": p.get("custom_label")})


def _document_highlight(p) -> _Adapted:
    # PaperFigure needs an image; document_highlight is text-only. A quote card
    # with the highlight as the accent phrase is the faithful block rendering.
    if not p.get("text"):
        return None
    attribution = p.get("document_title") or p.get("source")
    return "PullQuote", _clean({
        "mode": "quote", "quote": str(p["text"]),
        "accentPhrase": p.get("highlight_text"),
        "attribution": f"— {attribution}" if attribution else None})


def _bar_chart(p) -> _Adapted:
    bars = p.get("bars")
    if not isinstance(bars, list) or len(bars) < 2:
        return None
    out = []
    for b in bars:
        if not isinstance(b, dict) or b.get("label") is None or _num(b.get("value")) is None:
            return None
        out.append(_clean({"label": str(b["label"]), "value": _num(b["value"]),
                           "accent": b.get("accent")}))
    return "BarChart", _clean({"bars": out, "title": p.get("title"),
                               "unit": p.get("unit"), "caption": p.get("caption")})


def _line_chart(p) -> _Adapted:
    pts = p.get("points")
    if not isinstance(pts, list) or len(pts) < 3:
        return None
    series_pts = []
    for it in pts:
        pair = it if isinstance(it, (list, tuple)) else (
            (it.get("x"), it.get("y")) if isinstance(it, dict) else None)
        if not pair or _num(pair[0]) is None or _num(pair[1]) is None:
            return None                      # LineChart plots numbers only
        series_pts.append({"x": _num(pair[0]), "y": _num(pair[1])})
    return "LineChart", _clean({
        "series": [{"points": series_pts}], "title": p.get("title"),
        "caption": p.get("caption"), "area": p.get("area", True),
        "yPrefix": p.get("y_prefix"), "ySuffix": p.get("y_suffix"),
        "yDecimals": p.get("y_decimals"), "xDecimals": p.get("x_decimals", 0)})


def _pie_percentage(p) -> _Adapted:
    pct = _num(p.get("percentage"))
    if pct is None or not (0 <= pct <= 100):
        return None
    return "PieCallout", _clean({
        "percentage": pct, "infoTitle": p.get("title"),
        "infoText": p.get("text"), "sliceLabel": p.get("slice_label")})


def _data_table(p) -> _Adapted:
    cols, rows = p.get("columns"), p.get("rows")
    if not (isinstance(cols, list) and cols and isinstance(rows, list) and rows):
        return None
    hl = p.get("highlight_row")
    return "DataTable", _clean({
        "columns": [str(c) for c in cols],
        "rows": [[str(c) for c in (r if isinstance(r, list) else [r])] for r in rows],
        "highlightRow": int(hl) if isinstance(hl, (int, float)) else None,
        "caption": p.get("caption")})


def _image_compare(p) -> _Adapted:
    def side(s):
        if not isinstance(s, dict) or not s.get("src"):
            return None
        return _clean({"src": str(s["src"]), "label": s.get("label"),
                       "caption": s.get("caption")})
    left, right = side(p.get("left")), side(p.get("right"))
    if not left or not right:
        return None
    return "ImageCompare", _clean({"left": left, "right": right,
                                   "kicker": p.get("kicker"),
                                   "verdict": p.get("verdict")})


def _kinetic_headline(p) -> _Adapted:
    if not p.get("text"):
        return None
    aw = p.get("accent_words")
    return "KineticHeadline", _clean({
        "text": str(p["text"]),
        "accentWords": [str(w) for w in aw] if isinstance(aw, list) else None,
        "align": p.get("align")})


def _detail_loupe(p) -> _Adapted:
    src, region = p.get("src"), p.get("region")
    if not src:
        return None
    if isinstance(region, (list, tuple)) and len(region) == 4:
        region = dict(zip("xywh", region))
    if not (isinstance(region, dict)
            and all(_num(region.get(k)) is not None for k in "xywh")):
        return None
    return "DetailLoupe", _clean({
        "src": str(src), "region": {k: _num(region[k]) for k in "xywh"},
        "label": p.get("label"), "caption": p.get("caption")})


def _loop_diagram(p) -> _Adapted:
    nodes = p.get("nodes")
    if not isinstance(nodes, list) or not 3 <= len(nodes) <= 6:
        return None
    return "LoopDiagram", _clean({
        "nodes": [str(n) for n in nodes], "title": p.get("title"),
        "centerLabel": p.get("center_label")})


ADAPTERS: Dict[str, Callable[[dict], _Adapted]] = {
    "quote": _quote,
    "pull_quote": _pull_quote,
    "definition": _definition,
    "counter": _counter,
    "statistic": _statistic,
    "timeline": _timeline,
    "ranking": _ranking,
    "comparison": _comparison,
    "stat_comparison": _stat_comparison,
    "question": _question,
    "chapter_card": _chapter_card,
    "section_divider": _section_divider,
    "title": _title,
    "list": _list,
    "lower_third": _lower_third,
    "source_citation": _source_citation,
    "verdict": _verdict,
    "location_stamp": _location_stamp,
    "progress_bar": _progress_bar,
    "percentage_bar": _percentage_bar,
    "tweet_card": _tweet_card,
    "news_headline": _news_headline,
    "document_highlight": _document_highlight,
    "bar_chart": _bar_chart,
    "line_chart": _line_chart,
    "pie_percentage": _pie_percentage,
    "data_table": _data_table,
    "image_compare": _image_compare,
    "kinetic_headline": _kinetic_headline,
    "detail_loupe": _detail_loupe,
    "loop_diagram": _loop_diagram,
}


# --- the blocks umbrella catalog (module contract) -------------------------------
# One entry per authoring template: purpose (what) + when_to_use (the craft
# guidance an agent needs to PICK it). Honesty-tested against ADAPTERS and the
# slide-designer skill doc, surfaced on /api/map and `nolan capabilities`.
TEMPLATES: Dict[str, Dict[str, str]] = {
    "quote": {"purpose": "Verbatim quotation card with attribution.",
              "when_to_use": "A quote the narration reads or references. Verbatim text is never trimmed — designed type tiers absorb length up to ~480 chars."},
    "pull_quote": {"purpose": "Quote with one accented phrase.",
                   "when_to_use": "When ONE phrase inside the quote is the point — the accent carries the argument."},
    "definition": {"purpose": "Term + definition card.",
                   "when_to_use": "First introduction of a term of art the rest of the essay leans on."},
    "counter": {"purpose": "Animated count-up number with caption.",
                "when_to_use": "A single inline stat. The CHEAPEST data moment — escalate to bar_chart/stat_comparison when comparison matters, or a stat-over motion when scale should be FELT."},
    "statistic": {"purpose": "One-to-three stat figures with labels.",
                  "when_to_use": "A cluster of related figures. NOT for every number in a stat run — vary with counter, percentage_bar, annotate treatments."},
    "timeline": {"purpose": "Chronology as a stepped flow (≤5 events).",
                 "when_to_use": "A sequence of dated events the narration walks through in order. More than 5 events won't fit — cut to the turning points."},
    "ranking": {"purpose": "Ordered list with values.",
                "when_to_use": "Top-N / league-table moments where ORDER is the message."},
    "comparison": {"purpose": "Two-sided VS card (text points).",
                   "when_to_use": "A binary argument with a few points per side. For imagery use image_compare; for two numbers use stat_comparison."},
    "stat_comparison": {"purpose": "Two headline numbers side by side.",
                        "when_to_use": "Before/after or us/them NUMBERS ('4.4% → 7-12%'). The numbers are the whole card."},
    "question": {"purpose": "Question card.",
                 "when_to_use": "A rhetorical pivot the narration poses — sparingly, as punctuation."},
    "chapter_card": {"purpose": "Chapter/section opener card.",
                     "when_to_use": "Section openers. At most one per section."},
    "section_divider": {"purpose": "Minimal divider card.",
                        "when_to_use": "A breath between arguments when a full chapter card is too heavy."},
    "title": {"purpose": "Title + subtitle statement.",
              "when_to_use": "A declarative statement standing alone ('WE ARE NOT UN-BUILDING THIS')."},
    "list": {"purpose": "Staggered list reveal.",
             "when_to_use": "3-6 parallel items the narration enumerates."},
    "lower_third": {"purpose": "Name/role caption band.",
                    "when_to_use": "Introducing a person or source while their footage/imagery stays on screen."},
    "source_citation": {"purpose": "Source/citation card.",
                        "when_to_use": "On-screen sourcing for a load-bearing claim."},
    "verdict": {"purpose": "Verdict/judgment card.",
                "when_to_use": "The essay's ruling on a question it set up — a conclusion moment."},
    "location_stamp": {"purpose": "Place-name stamp with sublocation.",
                       "when_to_use": "Grounding the narration in a named real place (datelines, site references) when no map asset exists."},
    "progress_bar": {"purpose": "0..1 progress with milestones.",
                     "when_to_use": "Progress toward a stated goal or capacity."},
    "percentage_bar": {"purpose": "One percentage as a labeled bar.",
                       "when_to_use": "A single share-of-whole figure ('43% of data centers…'). For a donut treatment use pie_percentage."},
    "tweet_card": {"purpose": "Social-post card.",
                   "when_to_use": "Quoting an actual post — content is verbatim (≤280)."},
    "news_headline": {"purpose": "News-style headline chyron.",
                      "when_to_use": "Reporting a dated event as coverage ('BREAKING' energy) — not for the essay's own claims."},
    "document_highlight": {"purpose": "Document excerpt with highlighted phrase.",
                           "when_to_use": "Reading from a real filing/report/permit — the highlight is the receipt."},
    "bar_chart": {"purpose": "Animated bar chart (2-6 bars, count-up).",
                  "when_to_use": "Comparing 2-6 quantities the narration names. If the story is one series over TIME, use line_chart."},
    "line_chart": {"purpose": "Single-series line/area chart (numeric x/y).",
                   "when_to_use": "A trend over time — rise, crash, 'going vertical'. Needs ≥3 numeric points; hedged projections belong in the caption."},
    "pie_percentage": {"purpose": "Donut sweep for one percentage + info panel.",
                       "when_to_use": "One share-of-whole with a sentence of context. For a bare figure percentage_bar is lighter."},
    "data_table": {"purpose": "Compact table with a highlight row.",
                   "when_to_use": "When the RECEIPTS are tabular (specs, results, filings) and one row is the point. ≤5 columns, ≤7 rows."},
    "image_compare": {"purpose": "Two images side by side with labels + verdict.",
                      "when_to_use": "A visual juxtaposition with an editorial ruling (claim vs reality). Needs both image paths (project-relative or absolute)."},
    "kinetic_headline": {"purpose": "Word-synced kinetic headline with accent words.",
                         "when_to_use": "Punch phrases the viewer should read AS they're spoken — hooks, thesis lines, the three-punch closer."},
    "detail_loupe": {"purpose": "Magnifier over one region of an image.",
                     "when_to_use": "When the evidence is a DETAIL inside a larger image (a clause, a face, a signature). Needs src + region x/y/w/h in 0..1."},
    "loop_diagram": {"purpose": "Nodes on a circle with cycle arrows.",
                     "when_to_use": "Feedback loops and self-reinforcing cycles (A feeds B feeds C feeds A) — 3-6 nodes."},
}


# --- content budgets ----------------------------------------------------------
# Every block has an implicit layout budget its designer assumed; violating it
# is how text piles up or escapes the frame. Budgets are declared ONCE here —
# at the same choke point every consumer routes through (render_layout, the
# motion "block" backend, premium mode) — so there is no second enforcement
# path to drift. Paths: "field", "parent.field", "list[]" (count),
# "list[].field". Policy: "trim" = ellipsize (safe for descriptive text);
# "reject" = no faithful truncation exists → adapter returns None and the
# scene falls back to the python renderer (which wraps/scales).
BLOCK_BUDGETS: Dict[str, Dict[str, tuple]] = {
    # quote is VERBATIM — the block adapts (designed type tiers down to
    # reading size at 480 chars); reject only past what reading size holds.
    "PullQuote": {"quote": (480, "reject"), "attribution": (70, "trim"),
                  "term": (40, "reject"), "definition": (240, "trim"),
                  "accentPhrase": (60, "trim")},
    "StatCount": {"stats[]": (3, "reject"), "stats[].label": (60, "trim"),
                  "stats[].prefix": (6, "trim"), "stats[].suffix": (8, "trim")},
    "StepFlow": {"steps[]": (5, "reject"), "steps[].label": (18, "trim"),
                 "steps[].detail": (80, "trim"), "kicker": (60, "trim")},
    "Ranking": {"items[]": (6, "reject"), "items[].name": (42, "trim"),
                "items[].value": (16, "trim"), "title": (70, "trim")},
    "ComparisonVS": {"left.title": (44, "reject"), "right.title": (44, "reject"),
                     "left.points[]": (3, "reject"), "right.points[]": (3, "reject"),
                     "kicker": (44, "trim"), "verdict": (110, "trim")},
    "QuestionCard": {"question": (160, "reject"), "context": (70, "trim"),
                     "accentPhrase": (60, "trim")},
    "ChapterCard": {"title": (60, "reject"), "subtitle": (110, "trim")},
    "HeroStatement": {"lines[]": (3, "reject"), "lines[].text": (60, "reject")},
    "ListReveal": {"items[]": (6, "reject"), "items[].label": (60, "trim"),
                   "title": (70, "trim")},
    "LowerThird": {"name": (44, "reject"), "title": (70, "trim")},
    "SourceCitation": {"sourceName": (80, "reject"), "publication": (60, "trim"),
                       "author": (60, "trim"), "url": (90, "trim")},
    "VerdictCard": {"verdict": (120, "reject"), "supportingText": (200, "trim")},
    "LocationStamp": {"location": (44, "reject"), "sublocation": (90, "trim"),
                      "coordinates": (44, "trim")},
    "ProgressBar": {"label": (70, "trim"), "milestones[]": (6, "reject"),
                    "milestones[].": (20, "trim")},
    "PercentBar": {"label": (60, "reject"), "context": (90, "trim")},
    "TweetCard": {"content": (280, "reject"), "username": (40, "trim"),
                  "handle": (30, "trim")},
    "NewsHeadline": {"headline": (110, "reject"), "source": (44, "trim"),
                     "label": (24, "trim")},
    "BarChart": {"bars[]": (6, "reject"), "bars[].label": (18, "trim"),
                 "title": (70, "trim"), "caption": (90, "trim"),
                 "unit": (8, "trim")},
    "LineChart": {"series[]": (2, "reject"), "title": (70, "trim"),
                  "caption": (90, "trim")},
    "PieCallout": {"infoTitle": (60, "trim"), "infoText": (160, "trim"),
                   "sliceLabel": (24, "trim")},
    "DataTable": {"columns[]": (5, "reject"), "columns[].": (16, "trim"),
                  "rows[]": (7, "reject"), "caption": (70, "trim")},
    "ImageCompare": {"kicker": (44, "trim"), "verdict": (110, "trim"),
                     "left.label": (32, "trim"), "right.label": (32, "trim"),
                     "left.caption": (80, "trim"), "right.caption": (80, "trim")},
    "KineticHeadline": {"text": (90, "reject"), "accentWords[]": (4, "reject")},
    "DetailLoupe": {"label": (40, "trim"), "caption": (90, "trim")},
    "LoopDiagram": {"nodes[]": (6, "reject"), "nodes[].": (22, "trim"),
                    "title": (70, "trim")},
}


def _trim(s: str, limit: int) -> str:
    s = str(s)
    return s if len(s) <= limit else s[: max(1, limit - 1)].rstrip() + "…"


def _budget_targets(props: dict, path: str):
    """Yield (container, key, kind) for a budget path. kind: 'text'|'count'.

    Supported forms: "field" · "parent.field" · "parent.list[]" ·
    "list[]" (count) · "list[].field" · "list[]." (bare string items).
    """
    parts = path.split(".")
    head = parts[0]
    if head.endswith("[]"):
        lst = props.get(head[:-2])
        if not isinstance(lst, list):
            return
        if len(parts) == 1:
            yield props, head[:-2], "count"
        elif parts[1] == "":                    # "list[]." — bare string items
            for i, v in enumerate(lst):
                if isinstance(v, str):
                    yield lst, i, "text"
        else:
            for item in lst:
                if isinstance(item, dict) and parts[1] in item:
                    yield item, parts[1], "text"
    elif len(parts) == 2:
        sub = props.get(head)
        if isinstance(sub, dict):
            if parts[1].endswith("[]"):
                if isinstance(sub.get(parts[1][:-2]), list):
                    yield sub, parts[1][:-2], "count"
            elif parts[1] in sub:
                yield sub, parts[1], "text"
    elif head in props:
        yield props, head, "text"


def _enforce_budgets(block: str, props: dict) -> Optional[dict]:
    """Apply the block's content budgets. None -> reject (use the fallback)."""
    budgets = BLOCK_BUDGETS.get(block)
    if not budgets:
        return props
    for path, (limit, policy) in budgets.items():
        # "a.b[]" count paths route through the two-part branch
        for container, key, kind in _budget_targets(props, path):
            value = container[key]
            if kind == "count":
                if len(value) > limit:
                    logger.info("budget reject: %s %s has %d items (max %d)",
                                block, path, len(value), limit)
                    return None
            else:
                if value is not None and len(str(value)) > limit:
                    if policy == "reject":
                        logger.info("budget reject: %s %s is %d chars (max %d)",
                                    block, path, len(str(value)), limit)
                        return None
                    container[key] = _trim(value, limit)
    return props


def adapt(template: str, params: dict) -> _Adapted:
    """(block_name, props) for a template's layout params, or None.

    Budget-enforced: over-limit descriptive text is ellipsized; content whose
    truncation would lie (quotes, headlines, counts over a block's capacity)
    rejects the mapping and the caller falls back to the python renderer.
    """
    fn = ADAPTERS.get(template)
    if fn is None:
        return None
    try:
        adapted = fn(params or {})
        if not adapted:
            return None
        block, props = adapted
        props = _enforce_budgets(block, props)
        if props is None:
            return None
        return block, props
    except Exception as exc:
        logger.warning("layout->block adaptation failed for %s: %s", template, exc)
        return None


def render_layout_block(
    template: str,
    params: dict,
    duration: float,
    output_path: Path,
    fps: int = 30,
    scene_id: str = "",
) -> Optional[Path]:
    """Render a layout scene through its Remotion block. None -> no mapping."""
    adapted = adapt(template, params)
    if not adapted:
        return None
    block, props = adapted

    frames = max(int(round(duration * fps)), fps)
    step = {"block": block, "props": props, "revealFrames": [],
            "words": [], "durationInFrames": frames}

    from nolan import remotion_source
    out_name = f"layout_{scene_id or template}_{uuid.uuid4().hex[:8]}.mp4"
    rendered = remotion_source.render(
        "Chapter", {"steps": [step], "captions": False},
        out_name=out_name, duration_frames=frames)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy(str(rendered), str(output_path))
    Path(rendered).unlink(missing_ok=True)
    return output_path
