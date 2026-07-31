"""Artist world-knowledge — one LLM call per PERSON, spent across every work they made.

The caption design's cheapest win. Movement, period, style and typical palette are facts about
an artist's whole output, so asking a vision model for them per artwork pays fifty times for one
answer *and* invites a confident guess where world knowledge already has a real one. Monet has
~50 works in a mid-sized harvest and needs ONE call.

The saving is exactly the corpus's works-per-artist ratio, and it compounds as the library grows,
which is why the enrichment is ordered by `creator_histogram`: the commonest creators first, so a
bounded budget covers the most rows rather than an arbitrary slice.

WHAT THIS MAY NOT DO. It may not touch `identity_source`, and it may not write anything into a
row's own identity columns. An artist's movement is context ABOUT the maker; it is not a claim
about which artwork this is. Keeping those apart is the same invariant that stops a caption
becoming an identity.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from nolan.imagelib.catalog import Artist, artist_key

_LOG = logging.getLogger(__name__)

SYSTEM = (
    "You are an art historian. Answer ONLY with facts you are confident about for the named "
    "artist. If you do not recognise the name, or are unsure, return nulls — a null is correct "
    "and useful, an invented movement is a factual error that will end up on screen."
)

PROMPT = """Artist: {name}
{hint}
Return STRICT JSON, no prose, with exactly these keys:

{{
  "recognised": true|false,
  "movement": "art movement or school, or null",
  "period": "active period, e.g. 'late 19th century', or null",
  "style": "one short clause on their visual manner, or null",
  "subjects": "typical subjects, comma separated, or null",
  "palette": "characteristic palette in words (not hex), or null"
}}

Rules:
- If "recognised" is false, every other field MUST be null.
- No hedging inside the values ("possibly", "likely") — use null instead.
- "palette" is words an editor would write ("ochre and slate"), never hex codes."""


def _parse(raw: str) -> Optional[Dict[str, Any]]:
    """Pull the JSON object out of a model reply, tolerating code fences and stray prose."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text.strip("`")
        text = text.split("\n", 1)[1] if text.lower().startswith("json") else text
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(text[start:end + 1])
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _clean(v: Any) -> Optional[str]:
    """Null-ish answers stay NULL. A model that writes "unknown" into a text column has made the
    column useless — you can no longer tell "we asked and it did not know" from "it knows this
    artist is unknown"."""
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in {"null", "none", "n/a", "na", "unknown", "unclear", "-"}:
        return None
    return s


async def enrich_artists(library, *, limit: int = 25, llm=None, model: str = "llm",
                         collection_id: Optional[int] = None,
                         min_works: int = 1, progress=None) -> Dict[str, Any]:
    """Fill in artist knowledge for the creators that cover the most rows.

    Bounded by `limit` CALLS, not rows — the point of the table is that one call serves many
    works, and the report says how many rows each call bought so that leverage is visible rather
    than assumed.
    """
    if llm is None:
        raise ValueError("enrich_artists needs an llm with async generate(prompt, system_prompt)")

    hist = library.catalog.creator_histogram(held=0, collection_id=collection_id)
    todo = []
    for key, name, works in hist:
        if works < min_works:
            continue
        if library.catalog.get_artist(key) is not None:
            continue                                  # already known — never pay twice
        todo.append((key, name, works))
        if len(todo) >= limit:
            break

    out: Dict[str, Any] = {"called": 0, "learned": 0, "unrecognised": 0, "failed": 0,
                           "rows_covered": 0, "artists": []}
    for key, name, works in todo:
        qid = None
        for a in library.catalog.list(status="active", held=0, limit=5,
                                      collection_id=collection_id):
            if artist_key(a.creator) == key and a.wikidata_qid:
                qid = a.wikidata_qid
                break
        hint = f"(the catalog also records Wikidata id {qid})" if qid else ""
        out["called"] += 1
        try:
            raw = await llm.generate(PROMPT.format(name=name, hint=hint), system_prompt=SYSTEM)
            data = _parse(raw)
        except Exception as e:
            _LOG.warning("artist enrichment failed for %s: %s", name, e)
            out["failed"] += 1
            continue
        if not data:
            out["failed"] += 1
            continue
        if not data.get("recognised"):
            # Record the MISS so we never pay for this name again. An unrecognised artist is a
            # real, cacheable answer; re-asking every run is how a bounded budget gets eaten by
            # the same forty obscure names.
            library.catalog.upsert_artist(Artist(
                name=name, name_key=key, note="not recognised", source=model))
            out["unrecognised"] += 1
            continue
        art = library.catalog.upsert_artist(Artist(
            name=name, name_key=key,
            movement=_clean(data.get("movement")), period=_clean(data.get("period")),
            style=_clean(data.get("style")), subjects=_clean(data.get("subjects")),
            palette=_clean(data.get("palette")), source=model))
        out["learned"] += 1
        out["rows_covered"] += works
        out["artists"].append({"name": name, "works": works,
                               "movement": art.movement, "period": art.period})
        if progress:
            progress(out)

    out["leverage"] = round(out["rows_covered"] / out["learned"], 1) if out["learned"] else 0.0
    return out


def artist_context(library, creator: Optional[str]) -> str:
    """The one-line context a caption pass gets handed. Empty when we know nothing."""
    if not creator:
        return ""
    a = library.catalog.get_artist(creator)
    return a.context_line() if a else ""
