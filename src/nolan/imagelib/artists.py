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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from nolan.imagelib import harvest
from nolan.imagelib import wikidata as _wd
from nolan.imagelib.catalog import Artist, artist_key, folded_artist

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


# Anonymity words, as a lookup guard. `_is_anonymous` already refuses "Unknown" and "Artist
# Unknown", but it deliberately KEEPS "Anonymous, British, 19th century" and "Unknown Italian",
# because a school is a real narrowing even when the hand cannot be named. That is right for the
# facet and wrong for Wikidata: no maker is called "Anonymous, British, 19th century", so the
# search is free to return whatever it likes — and it does. Measured, "Anonymous" resolved to
# Q567633, the hacktivist collective, and would have stamped "b. 1999" onto 810 Met rows whose
# only claim is that the museum does not know who made them.
_ANON_LEADING = re.compile(r"^\s*(anonymous|unknown|unidentified|unattributed|artist unknown)\b",
                           re.I)


def _unsearchable(name: str, key: str) -> bool:
    """Is this attribution a statement of anonymity rather than a name worth looking up?"""
    return folded_artist(name) is None or bool(_ANON_LEADING.match(name or "")) \
        or bool(_ANON_LEADING.match(key or ""))


# How far a maker's known window may sit from the mean date of the works we hold before the
# binding is rejected. Generous on purpose: a print can be pulled from a plate long after the
# engraver died, an estate can issue casts for decades, and catalog dates are approximate. It only
# has to be tighter than the errors it exists to catch, which are centuries wide.
_DATE_SLACK = 120
# One dated work can be a bad parse. Three cannot all be.
_DATE_MIN_WORKS = 3


def _date_conflict(art: Artist, work_year: Optional[Tuple[float, int]]) -> Optional[str]:
    """A reason to reject this binding on the calendar, or None.

    Structural checks cannot catch a fuzzy-search hit that is a real, correctly-typed entity of
    the wrong identity — NASCAR is genuinely a business, so `maker_kind` waves it through for
    "Nasca". The dates are what disagree, and we already hold them.

    MEASURED OVER THE FIRST 500 ARTISTS: 7 rejections, of which 5 are true catches (Nasca→NASCAR;
    Chimú and Manchu, cultures the Met credits as makers, matched to unrelated modern entities;
    two people matched to namesakes born centuries later) and 2 are FALSE — Firdausi and
    Bhadrabahu, correctly identified authors whose surviving manuscripts were copied 400 and 1800
    years after they died.

    That asymmetry is deliberate and is why the gate stays. A false rejection loses one fact and
    leaves a note saying exactly what was refused and why, so it is auditable and reversible; a
    false acceptance publishes a wrong birth year onto every work that maker signed. There is no
    threshold that separates "author of a much-later manuscript" from "namesake born 400 years
    late" — both are a large gap between a person and their works — so the safe side is the one
    that keeps a note.
    """
    if not work_year or work_year[1] < _DATE_MIN_WORKS:
        return None
    span = art.active_years()
    if not span:
        return None
    mean, n = work_year
    lo, hi = span[0] - _DATE_SLACK, span[1] + _DATE_SLACK
    if lo <= mean <= hi:
        return None
    return (f"works average {mean:.0f} ({n} dated) but {art.name} is placed "
            f"{span[0]}–{span[1]}")


def _model_answered(a: Artist) -> bool:
    """Has an LLM already been asked about this artist?

    The row alone no longer proves it: the Wikidata pass creates rows for everyone it looks up,
    including its misses. So this asks whether any field carries a model's name as its source, or
    (for rows written before provenance existed) whether the legacy `source`/`note` pair says a
    model spoke. Getting this wrong in either direction costs real money: too loose and the LLM
    pass never fills style/subjects/palette; too strict and it re-buys answers it already has.
    """
    if a.note == "not recognised":
        return True
    if any(who not in ("wikidata", "wikipedia") for who in a.sources.values()):
        return True
    # Legacy rows: `source` is the model, and it only ever got set by an LLM run.
    return bool(a.source) and any((a.movement, a.period, a.style, a.subjects, a.palette))


def fill_artists_wikidata(library, *, limit: int = 500, min_works: int = 1,
                          collection_id: Optional[int] = None,
                          use_met_dump: bool = True, refresh: bool = False,
                          workers: int = 4, progress=None) -> Dict[str, Any]:
    """Fill the artist table from Wikidata, commonest creators first.

    RUNS BEFORE THE MODEL, AND THE MODEL NEVER OVERWRITES IT. Birth year, death year, nationality
    and the English Wikipedia link are facts with a citation; asking an LLM for them buys a
    plausible guess at 29,766 chances to be wrong. `enrich_artists` still supplies what Wikidata
    has no column for — style, typical subjects, palette — and now skips what this pass filled,
    with `sources_json` recording which authority said what.

    TWO WAYS TO GET A QID, IN COST ORDER:

      1. THE MET DUMP, free. `Artist Wikidata URL` is already on disk beside every Met row and
         resolves 7,242 of our artists (90,693 rows) with no request at all — see
         `harvest.met_artist_qids`. The museum did the disambiguation; we are reading it.
      2. A NAME SEARCH, one to six requests. Only for whoever is left, and only accepted when the
         entity is a human (`wikidata.search_qid`), because searching an artist's name returns
         paintings and museums too.

    `refresh=False` never re-asks about an artist already checked — a miss is a real answer and
    caching it is what stops a bounded budget being eaten by the same obscure names every run. A
    lookup that could not be MADE (`LookupUnavailable`: a 403, a timeout) is not a miss and is not
    cached, so a bad half-hour of network does not permanently mark thousands of artists unknown.

    Fetches run `workers`-wide and writes stay on this thread — measured 0.81 s per artist with a
    QID and 1.42 s without, which serial is ~8 hours for the whole corpus. Four is deliberately
    modest for a keyless public endpoint we do not own.
    """
    from concurrent.futures import ThreadPoolExecutor
    from nolan.imagelib import wikidata as wd

    met_map: Dict[str, str] = {}
    if use_met_dump:
        try:
            met_map = harvest.met_artist_qids()
        except FileNotFoundError:
            met_map = {}                       # no dump on this machine; search path still works

    hist = library.catalog.creator_histogram(held=0, collection_id=collection_id)
    work_years = library.catalog.artist_work_years(held=0)
    out: Dict[str, Any] = {"considered": 0, "from_met_dump": 0, "searched": 0, "found": 0,
                           "not_found": 0, "failed": 0, "anonymous": 0, "rejected_dates": 0,
                           "rows_covered": 0, "met_map": len(met_map),
                           "artists": [], "rejections": []}

    todo: List[tuple] = []
    for key, name, works in hist:
        if len(todo) >= limit:
            break
        # The histogram is sorted by work count, so the first artist under the floor means every
        # remaining one is too.
        if works < min_works:
            break
        if _unsearchable(name, key):
            out["anonymous"] += 1
            continue
        prev = library.catalog.get_artist(key)
        if prev is not None and prev.checked_at and not refresh:
            continue                           # already asked Wikidata about this one
        qid = (prev.wikidata_qid if prev else None) or met_map.get(key)
        todo.append((key, name, works, prev, qid))
    out["considered"] = len(todo)
    out["from_met_dump"] = sum(1 for t in todo if t[4])
    out["searched"] = len(todo) - out["from_met_dump"]

    def _look(job):
        key, name, works, prev, qid = job
        try:
            return job, wd.artist_facts(name, qid=qid), None
        except Exception as e:                 # network trouble is not a "not found"
            return job, None, e

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for (key, name, works, prev, qid), facts, err in pool.map(_look, todo):
            if err is not None:
                _LOG.warning("wikidata lookup failed for %s: %s", name, err)
                out["failed"] += 1
                continue
            now = datetime.now(timezone.utc).isoformat()
            if not facts:
                # Record the MISS, so the next run spends its budget on someone else.
                library.catalog.upsert_artist(Artist(name=name, name_key=key, checked_at=now,
                                                     source=(prev.source if prev else None)))
                out["not_found"] += 1
                continue
            vals, prov = wd.facts_to_artist_fields(facts)
            mv = normalise_movement(vals.get("movement"))
            if mv:
                vals["movement"] = mv
            else:
                vals.pop("movement", None)
                prov.pop("movement", None)
            # Check the calendar BEFORE writing. A rejected binding is recorded as checked (so the
            # budget moves on) but keeps none of the facts — half a wrong identity is still wrong.
            candidate = Artist(name=name, name_key=key, **vals)
            clash = _date_conflict(candidate, work_years.get(key))
            if clash:
                _LOG.info("rejected wikidata binding for %s: %s", name, clash)
                library.catalog.upsert_artist(Artist(
                    name=name, name_key=key, checked_at=now,
                    note=f"wikidata rejected: {clash}"))
                out["rejected_dates"] += 1
                out["rejections"].append({"name": name, "works": works,
                                          "qid": facts.get("wikidata_qid"), "why": clash})
                continue
            art = library.catalog.upsert_artist(Artist(
                name=name, name_key=key, checked_at=now, **vals,
                sources_json=wd.merge_sources(prev.sources_json if prev else None, prov)))
            out["found"] += 1
            out["rows_covered"] += works
            out["artists"].append({"name": name, "works": works, "qid": art.wikidata_qid,
                                   "lifespan": art.lifespan(), "movement": art.movement})
            if progress:
                progress(out)

    out["leverage"] = round(out["rows_covered"] / out["found"], 1) if out["found"] else 0.0
    # Same reason `enrich_artists` does it: `assets.movement` is a denormalised copy, and a
    # movement learned here that never reaches the rows is invisible to the facet that exists to
    # find it.
    if out["found"]:
        out["movement_backfill"] = library.backfill_movements(collection_id=collection_id)
    return out


async def enrich_artists(library, *, limit: int = 25, llm=None, model: str = "llm",
                         collection_id: Optional[int] = None,
                         min_works: int = 1, progress=None) -> Dict[str, Any]:
    """Fill in artist knowledge for the creators that cover the most rows.

    Bounded by `limit` CALLS, not rows — the point of the table is that one call serves many
    works, and the report says how many rows each call bought so that leverage is visible rather
    than assumed.

    IT FILLS THE GAPS WIKIDATA LEAVES, AND ONLY THOSE. `fill_artists_wikidata` runs first and
    creates a row for everyone it looked up — including the ones it could not identify. So
    "already known" cannot mean "has a row" any more, or the model pass would skip every artist
    Wikidata touched and `style`/`subjects`/`palette` would stay empty forever. It means: a model
    has already answered for this person. And a field Wikidata filled is never overwritten here —
    `sources_json` says who asserted what, and a looked-up date outranks a generated one.
    """
    if llm is None:
        raise ValueError("enrich_artists needs an llm with async generate(prompt, system_prompt)")

    hist = library.catalog.creator_histogram(held=0, collection_id=collection_id)
    todo = []
    for key, name, works in hist:
        if works < min_works:
            break                                     # histogram is sorted; the rest are smaller
        prev = library.catalog.get_artist(key)
        if prev is not None and _model_answered(prev):
            continue                                  # a model already spoke — never pay twice
        todo.append((key, name, works, prev))
        if len(todo) >= limit:
            break

    out: Dict[str, Any] = {"called": 0, "learned": 0, "unrecognised": 0, "failed": 0,
                           "rows_covered": 0, "artists": []}
    for key, name, works, prev in todo:
        # The artist's OWN Wikidata id, off the artist row — not `assets.wikidata_qid`, which for
        # Met rows identifies the ARTWORK. Handing a model an artwork's id as "this artist's id"
        # is worse than handing it nothing.
        qid = prev.wikidata_qid if prev else None
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
        vals = {"movement": _clean(data.get("movement")), "period": _clean(data.get("period")),
                "style": _clean(data.get("style")), "subjects": _clean(data.get("subjects")),
                "palette": _clean(data.get("palette"))}
        # Wikidata wins. Dropping the key entirely (rather than passing None) matters because
        # `upsert_artist` only overwrites with asserted values — this keeps the looked-up movement
        # AND keeps `sources_json` truthful about who said it.
        held_by_lookup = {f for f, who in (prev.sources if prev else {}).items()
                          if who == "wikidata"}
        vals = {f: v for f, v in vals.items() if v and f not in held_by_lookup}
        art = library.catalog.upsert_artist(Artist(
            name=name, name_key=key, source=model, **vals,
            sources_json=_wd.merge_sources(prev.sources_json if prev else None,
                                           {f: model for f in vals})))
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
