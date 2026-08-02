"""Artist facts from Wikidata — looked up, not guessed.

WHY THIS COMES BEFORE THE LLM. `enrich_artists` asks a language model what movement a painter
belonged to, which is the right tool for a judgement and the wrong one for a birth year. A date
from Wikidata is a citable fact with a QID behind it; a date from a model is a plausible guess,
and at 29,766 artists the difference is thousands of quiet errors nobody can audit. So this runs
first and the model only fills what it leaves empty — recorded per field, so the two are never
mistaken for each other afterwards.

IT IS ALSO FREE IN A WAY THE MODEL IS NOT. The Met's bulk CSV publishes `Artist Wikidata URL` on
35% of its public-domain rows: for that slice there is no lookup at all, just a QID we already
have on disk and never harvested. Everything else costs one keyless API call per artist, cached
by `checked_at`.

THE USER-AGENT IS LOAD-BEARING, NOT DECORATION. Wikimedia's robot policy rejects any request
whose UA lacks a contact, with a 403 and an HTML-ish body — measured:

    "NOLAN-VisualLib/1.0 (https://…)"   -> 200
    "NOLAN-VisualLib/1.0"               -> 403
    "python-requests/2.31"              -> 403
    a browser UA                        -> 403   (pretending to be Chrome is not the fix)

Set `NOLAN_CONTACT` to your own email or project URL if you want them to be able to reach you;
the default is a project identifier, which satisfies the policy without publishing anyone's
address to a third party.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional

_CONTACT = os.environ.get("NOLAN_CONTACT") or "https://github.com/nolan-video/nolan"
_UA = f"NOLAN-VisualLib/1.0 ({_CONTACT}) python-httpx"
_API = "https://www.wikidata.org/w/api.php"
_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData"


class LookupUnavailable(RuntimeError):
    """The question could not be ASKED — throttling, a 403, a dead link, a timeout.

    Distinct from a `None` answer, which means Wikidata was asked and does not know. Collapsing
    the two is how a whole run of 403s gets cached as 29,766 artists who "aren't on Wikidata", a
    verdict nothing would ever revisit. Callers count these as failures and write nothing.
    """

# The properties worth reading. Deliberately short: a field nobody filters or displays is a field
# that costs a parse and earns nothing.
P_INSTANCE_OF = "P31"
P_SUBCLASS_OF = "P279"
P_HUMAN = "Q5"
P_BIRTH = "P569"
P_DEATH = "P570"
P_OCCUPATION = "P106"
P_NATIONALITY = "P27"
P_MOVEMENT = "P135"
P_INCEPTION = "P571"
P_DISSOLVED = "P576"
P_COUNTRY = "P17"

# BUSINESS, not "organization" — and the difference is measured, not stylistic.
#
# The biggest creators in this library are FIRMS, not people: Allen & Ginter (2,959 rows),
# Goodwin & Company (2,648), Kinney Brothers (2,506), W. Duke, Sons & Co. (2,247), Brewster & Co.
# (1,656) — the tobacco-card publishers whose output the Met holds in bulk. A human-only filter
# throws all of that away, so organizations are accepted too, with `inception` standing in for a
# birth year.
#
# But `organization (Q43229)` is too generous: in Wikidata's ontology a COUNTRY subclasses it, so
# an org test admits "Ancient Roman" — a historical country the Met uses as a maker attribution —
# and its description ("country that began growing on the Italian Peninsula") would be filed as an
# artist biography. Measured reachability:
#
#     Allen & Ginter / W. Duke / Currier & Ives / Brewster  ->  Q4830453 (business)   ACCEPT
#     Ancient Roman                                         ->  Q43229 only           REJECT
#
# So the root is `business`. Museums and countries do not reach it, and neither do artworks.
_BUSINESS = "Q4830453"
_SUBCLASS_DEPTH = 2
_type_cache: Dict[str, set] = {}


_client = None
_client_lock = threading.Lock()
# One entity is asked for many times over a run — every subclass walk revisits the same handful of
# types, and a search inspects candidates other searches already inspected. Without this the type
# check alone triples the request count, which is what earned a wall of 429s the first time.
_entity_cache: "OrderedDict[str, Optional[dict]]" = OrderedDict()
_ENTITY_CACHE_MAX = 4096
_RETRY_STATUS = {429, 500, 502, 503, 504}


def _session():
    global _client
    if _client is None:
        import httpx
        with _client_lock:
            if _client is None:
                _client = httpx.Client(
                    headers={"User-Agent": _UA}, timeout=30.0, follow_redirects=True,
                    # Connection reuse. A fresh client per request means a TLS handshake per
                    # request, which is both slower and a worse citizen than one kept-alive pool.
                    limits=__import__("httpx").Limits(max_connections=8,
                                                      max_keepalive_connections=8))
    return _client


def _get(url: str, params: Dict[str, Any], *, tries: int = 4) -> Optional[dict]:
    """The JSON, None for a genuine 404, `LookupUnavailable` when it could not be asked.

    Returning None on every exception is what made a 403 look like "this artist is not on
    Wikidata" — 100% of lookups failed and the report cheerfully said `not_found`.

    THROTTLING IS RETRIED, NOT REPORTED. A 429 means "ask me more slowly", and treating it as a
    verdict would mark artists unknown for a reason that has nothing to do with them. Backoff is
    exponential and honours `Retry-After` when the server sends one.
    """
    last = ""
    for attempt in range(tries):
        try:
            r = _session().get(url, params=params)
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        else:
            if r.status_code == 404:
                return None                    # no such entity: a real answer
            if r.status_code == 200:
                try:
                    return r.json()
                except Exception as e:
                    raise LookupUnavailable(f"unparseable JSON from {url}: {e}") from e
            last = f"{r.status_code} from {url}: {r.text[:120]}"
            if r.status_code not in _RETRY_STATUS:
                break
            wait = float(r.headers.get("Retry-After") or 0) or (2.0 ** attempt)
            time.sleep(min(wait, 30.0))
            continue
        time.sleep(2.0 ** attempt)
    raise LookupUnavailable(last or f"gave up on {url}")


def qid_from_url(url: Optional[str]) -> Optional[str]:
    """`https://www.wikidata.org/wiki/Q123` -> `Q123`. What the Met dump hands over free."""
    m = re.search(r"/(Q\d+)\b", url or "")
    return m.group(1) if m else None


def search_qid(name: str) -> Optional[str]:
    """Find a maker's QID by name — the first hit that is a person or a firm.

    ONLY RETURNS MAKERS. `wbsearchentities` happily returns a painting, a country, a museum or an
    encyclopedia article for an artist's name, and binding one into the artist table would attach
    its dates and description to every picture that creator made. The `maker_kind` check is what
    makes this safe to run unattended over 29,766 names.
    """
    d = _get(_API, {"action": "wbsearchentities", "search": name, "language": "en",
                    "type": "item", "limit": 5, "format": "json"})
    for hit in (d or {}).get("search") or []:
        qid = hit.get("id")
        if not qid:
            continue
        ent = fetch_entity(qid)
        if ent and maker_kind(ent):
            return qid
    return None


def fetch_entity(qid: str) -> Optional[dict]:
    """One entity, memoised for the process. See `_entity_cache` for why the memo matters."""
    with _client_lock:
        if qid in _entity_cache:
            _entity_cache.move_to_end(qid)
            return _entity_cache[qid]
    d = _get(f"{_ENTITY}/{qid}.json", {})
    ent = ((d or {}).get("entities") or {}).get(qid)
    with _client_lock:
        _entity_cache[qid] = ent
        while len(_entity_cache) > _ENTITY_CACHE_MAX:
            _entity_cache.popitem(last=False)
    return ent


def _claims(ent: dict, prop: str) -> List[dict]:
    return (ent.get("claims") or {}).get(prop) or []


def _is_human(ent: dict) -> bool:
    return P_HUMAN in _linked(ent, P_INSTANCE_OF)


def _ancestors(qid: str, depth: int = _SUBCLASS_DEPTH) -> set:
    """The `subclass of` closure above a type, to `depth` hops. Cached for the process — the
    same handful of types recurs across thousands of artists, and re-walking them would be most
    of the run."""
    if qid in _type_cache:
        return _type_cache[qid]
    if depth < 0:
        return set()
    ent = fetch_entity(qid)
    parents = set(_linked(ent, P_SUBCLASS_OF)) if ent else set()
    out = set(parents)
    for p in parents:
        out |= _ancestors(p, depth - 1)
    if depth == _SUBCLASS_DEPTH:
        _type_cache[qid] = out
    return out


def maker_kind(ent: dict) -> Optional[str]:
    """`"person"`, `"organization"`, or None for something that cannot have made a picture.

    None is the important return: it is what stops a search for "Ancient Roman" or "The Great
    Wave" from binding a country or an artwork into the artist table, where its description would
    read as a biography on every row it touched.
    """
    types = _linked(ent, P_INSTANCE_OF)
    if P_HUMAN in types:
        return "person"
    for t in types:
        if t == _BUSINESS or _BUSINESS in _ancestors(t):
            return "organization"
    return None


def _year(ent: dict, prop: str) -> Optional[int]:
    """A four-digit year, or None. Wikidata times are ISO-ish with a leading sign and a precision
    field; anything coarser than a year (precision < 9) is NOT a year and must not be rounded
    into one."""
    for c in _claims(ent, prop):
        snak = (c.get("mainsnak") or {}).get("datavalue") or {}
        v = snak.get("value") or {}
        t, prec = v.get("time"), v.get("precision")
        if not t or (prec is not None and prec < 9):
            continue
        m = re.match(r"([+-])(\d{4})", t)
        if m:
            y = int(m.group(2))
            return -y if m.group(1) == "-" else y
    return None


def _labels(qids: List[str]) -> Dict[str, str]:
    if not qids:
        return {}
    d = _get(_API, {"action": "wbgetentities", "ids": "|".join(qids[:40]),
                    "props": "labels", "languages": "en", "format": "json"})
    out = {}
    for qid, ent in ((d or {}).get("entities") or {}).items():
        lab = ((ent.get("labels") or {}).get("en") or {}).get("value")
        if lab:
            out[qid] = lab
    return out


def _linked(ent: dict, prop: str) -> List[str]:
    ids = []
    for c in _claims(ent, prop):
        v = (((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {})
        if v.get("id"):
            ids.append(v["id"])
    return ids


def artist_facts(name: str, *, qid: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Everything Wikidata will tell us about one artist, or None if it does not know them.

    `qid` skips the search when a source already handed one over — which for 35% of the Met's
    public-domain rows it did, in a CSV column we have had on disk all along.

    Returns only fields it actually found: an absent key means "Wikidata did not say", which the
    caller records as such and the LLM pass may then fill. A None value would be indistinguishable
    from "asked and got nothing", and those are different.
    """
    qid = qid or search_qid(name)
    if not qid:
        return None
    ent = fetch_entity(qid)
    kind = maker_kind(ent) if ent else None
    if not kind:
        return None

    out: Dict[str, Any] = {"wikidata_qid": qid, "kind": kind}
    # A firm has no birth year; it has an inception. Mapping them onto the same two columns is
    # what lets one era filter cover both — "active in the 1880s" is the same question whether
    # the maker was a person or a tobacco company.
    born, died = ((P_BIRTH, P_DEATH) if kind == "person" else (P_INCEPTION, P_DISSOLVED))
    for key, prop in (("birth_year", born), ("death_year", died)):
        y = _year(ent, prop)
        if y is not None:
            out[key] = y
    nat_prop = P_NATIONALITY if kind == "person" else P_COUNTRY
    want = _linked(ent, nat_prop)[:2] + _linked(ent, P_MOVEMENT)[:2]
    labels = _labels(want)
    nat = [labels[q] for q in _linked(ent, nat_prop)[:2] if q in labels]
    mov = [labels[q] for q in _linked(ent, P_MOVEMENT)[:2] if q in labels]
    if nat:
        # ONE country, like the single-line label it feeds. People who outlived a state carry
        # several citizenships, and joining them produced "United Kingdom of Great Britain and
        # Ireland, Kingdom of Great Britain" on every Rowlandson card — 62 characters saying
        # "British". The shortest is the least ceremonial name for the same place.
        out["nationality"] = min(nat, key=len)
    if mov:
        out["movement"] = mov[0]              # one movement, like the column it feeds
    en = ((ent.get("sitelinks") or {}).get("enwiki") or {}).get("title")
    if en:
        out["wikipedia_url"] = "https://en.wikipedia.org/wiki/" + en.replace(" ", "_")
    desc = ((ent.get("descriptions") or {}).get("en") or {}).get("value")
    if desc:
        out["biography"] = desc               # one line, e.g. "Japanese ukiyo-e artist"
    return out


def facts_to_artist_fields(facts: Dict[str, Any]) -> "tuple[Dict[str, Any], Dict[str, str]]":
    """Split a fact dict into (column values, per-field provenance)."""
    vals = {k: v for k, v in facts.items() if k != "_source"}
    return vals, {k: "wikidata" for k in vals}


def merge_sources(existing: Optional[str], new: Dict[str, str]) -> str:
    """Merge per-field provenance, keeping what an earlier, better-sourced pass recorded.

    WIKIDATA IS NEVER OVERWRITTEN BY A MODEL. That is the whole reason provenance is per field:
    a later LLM pass filling the gaps must not quietly relabel a looked-up birth year as a
    guessed one, and must not overwrite the value either (the caller checks this map first).
    """
    try:
        cur = json.loads(existing) if existing else {}
    except Exception:
        cur = {}
    for k, v in new.items():
        if cur.get(k) == "wikidata" and v != "wikidata":
            continue
        cur[k] = v
    return json.dumps(cur, sort_keys=True)
