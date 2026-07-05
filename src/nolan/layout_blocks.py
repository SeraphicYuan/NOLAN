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
        return None                      # e.g. "2.3M" with odd formatting → Python renderer
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
    events = [e for e in (p.get("events") or [])
              if isinstance(e, dict) and (e.get("year") or e.get("label"))]
    if not events:
        return None
    ticks = [{"label": " — ".join(x for x in (str(e.get("year", "")).strip(),
                                              str(e.get("label", "")).strip()) if x)}
             for e in events]
    return "Timeline", {
        "headline": p.get("title") or None,
        "anchor": {"label": str(events[0].get("year", "")) or ticks[0]["label"]},
        "ticks": ticks,
        "note": str(p.get("title") or ""),
        "moneyNote": "",
    }


def _ranking(p) -> _Adapted:
    items = []
    for it in (p.get("items") or [])[:6]:
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
}


def adapt(template: str, params: dict) -> _Adapted:
    """(block_name, props) for a template's layout params, or None."""
    fn = ADAPTERS.get(template)
    if fn is None:
        return None
    try:
        return fn(params or {})
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
