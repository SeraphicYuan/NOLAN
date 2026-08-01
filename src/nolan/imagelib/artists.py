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
import re
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


# Separators a model reaches for when it wants to give more than one answer in a one-answer field.
_MOVEMENT_SPLIT = re.compile(r"\s*[,;/]\s*|\s+(?:and|&)\s+", re.I)
# Non-answers that survived `_clean` because they are phrased as prose rather than as a null.
_MOVEMENT_NONVALUE = re.compile(
    r"^(none|n/?a|unknown|unclear|various|multiple|no\s+(?:known|particular|specific)\b|"
    r"not\s+(?:applicable|associated)\b)", re.I)


def normalise_movement(raw: Optional[str]) -> Optional[str]:
    """One movement, or None — the canonical form stored in `assets.movement`.

    The field was written by a model answering "what movement?", and models answer that question
    generously. Over the live table, 106 distinct strings for 188 artists, of which case is the
    SMALLEST problem (it merges only 5). The rest:

        "aestheticism, tonalism"                          -> two movements in a one-movement cell
        "early photography, topographical photography"  \\
        "early photography / topographic"                >- one movement, written three ways
        "early photography"                             /
        "none; primarily a documentarian"                 -> not a movement at all

    So: take the FIRST clause (the primary attribution — a model lists the strongest first), and
    refuse the non-answers. Taking the first loses Whistler's tonalism, which is a real loss and
    the honest trade for a facet whose counts add up; a multi-valued movement needs its own table,
    not a comma.

    Case is preserved here. `backfill_movements` groups on the casefolded form and writes back the
    dominant spelling, so "ukiyo-e" (14 artists) and "Ukiyo-e" (10) become one facet entry without
    this function having to guess whether "Dutch Golden Age" wants title case.
    """
    s = (raw or "").strip()
    if not s:
        return None
    # The WHOLE string is tested for a non-answer before it is split, because the separators
    # overlap: "n/a" splits into "n", which no longer looks like a refusal and would be stored as
    # a movement named "n".
    if _MOVEMENT_NONVALUE.match(s):
        return None
    first = _MOVEMENT_SPLIT.split(s)[0].strip(" .;:-—")
    if not first or _MOVEMENT_NONVALUE.match(first):
        return None
    # A clause long enough to be a sentence is a description, not a movement name.
    return first if len(first) <= 48 and len(first.split()) <= 5 else None


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
    # Push what was just learned DOWN onto the rows. `assets.movement` is a denormalised copy, so
    # without this the facet keeps reporting yesterday's coverage and the new artists are
    # invisible to the filter that exists to find them — an authored field with a stale consumer,
    # which is the same bug as one with no consumer. Idempotent; skipped when nothing was learned.
    if out["learned"]:
        out["movement_backfill"] = library.backfill_movements(collection_id=collection_id)
    return out


def artist_context(library, creator: Optional[str]) -> str:
    """The one-line context a caption pass gets handed. Empty when we know nothing."""
    if not creator:
        return ""
    a = library.catalog.get_artist(creator)
    return a.context_line() if a else ""
