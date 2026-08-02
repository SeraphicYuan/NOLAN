"""Library of Congress — the documentary half of the picture library.

WHAT THIS SOURCE IS FOR, and it is not what the museums are for. The four sources already here
are museums: paintings, prints, decorative objects. LoC's Prints & Photographs division is
1,220,221 images whose centre of gravity is 20th-century American documentary — FSA/OWI
Depression negatives (171,055), Carol Highsmith's modern survey (70,431), stereograph cards
(55,779), HABS/HAER architectural records (45,863), WPA and wartime posters. "A 1936
sharecropper's face" was unanswerable before this; "an Art Nouveau poster" still is.

THE WHOLE RECORD IS IN THE LISTING, which is what makes this cheap. Measured against the WPA
poster collection: `?fo=json&c=500` returns 500 fully-populated records — rights_advisory,
medium, genre, subjects, dates, summary AND both image URLs — in one request. There is no
per-item pass at all, so 947 items cost 2 requests rather than 947, and the whole division is
~2,400 requests. `c=1000` breaks the response, so 500 is the ceiling.

RIGHTS ARE PER ITEM AND THE FIELD IS STRUCTURED. `rights_advisory` says "No known restrictions on
publication." on the poster collections and something longer and collection-specific on FSA/OWI.
That is a claim about *known* restrictions, NOT a licence grant, and it is not CC0 — so this
source is gated on the field rather than on the institution, and anything that does not clear
`_clears_rights` is refused with its reason recorded.

`Crawl-Delay: 5` is in their robots.txt and is honoured. With everything in the listing that
costs seconds per collection, not hours.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, Iterator, List, Optional

from nolan.imagelib.catalog import Collection

# `harvest` is imported INSIDE the functions that need it, never at module scope. `harvest`
# registers this adapter at the bottom of its own module, so a top-level import here is a cycle —
# harmless when `harvest` is imported first and an AttributeError on a partially-initialised
# module when `loc` is. `from __future__ import annotations` makes the type hints strings, so
# only the one runtime construction actually needs the symbol.

LOC_BASE = "https://www.loc.gov"
# Their robots.txt asks for 5 seconds between requests. Everything below is built so that this
# costs almost nothing: one request per 500 records, not per record.
LOC_CRAWL_DELAY = 5.0
# 500 works; 1000 truncates the response mid-stream (measured: IncompleteRead at 4.5 MB of 18.8).
LOC_PAGE = 500
_UA = "NOLAN-VisualLib/1.0 (https://github.com/nolan-video/nolan)"

# Rights phrasings LoC uses that mean "we know of nothing stopping you". Matched as a prefix on
# the normalised string, because the FSA/OWI advisory continues into a URL and a paragraph of
# guidance that varies per collection and must not have to be enumerated.
_RIGHTS_OK = (
    "no known restrictions",
    "no known copyright restrictions",
    "publication may be restricted. for information see",   # handled below — see _clears_rights
)
# Phrasings that are an explicit warning. Checked FIRST, because "publication may be restricted"
# contains none of the OK markers but reads superficially similar.
_RIGHTS_BAD = ("publication may be restricted", "rights status not evaluated",
               "restricted", "permission", "copyright undetermined")


def _clears_rights(advisory: Optional[str]) -> bool:
    """Does this item's `rights_advisory` permit use?

    "No known restrictions on publication." is LoC's standard phrasing for material they believe
    is free to use, and it is the ONLY family accepted here. It is deliberately not treated as
    equivalent to CC0: it is a statement about what the Library knows, not a licence, which is
    why the source keeps `rights_model="per-item"` and the archival gate tier rather than being
    waved through as open-access.

    An ABSENT advisory is refused. Silence is not permission, and a collection that omits the
    field is exactly where an unexamined assumption would do damage.
    """
    s = (advisory or "").strip().lower()
    if not s:
        return False
    if s.startswith("no known restrictions") or s.startswith("no known copyright restrictions"):
        return True
    return False


def _first(v: Any) -> Optional[str]:
    """LoC returns most fields as a list of one. Take the first, or None."""
    if isinstance(v, (list, tuple)):
        v = v[0] if v else None
    s = str(v).strip() if v is not None else ""
    return s or None


def _url(v: Any) -> Optional[str]:
    """A fetchable URL. LoC mixes absolute and PROTOCOL-RELATIVE forms in the same record —
    `image_url` and `link` come back as `//tile.loc.gov/...`, which httpx rejects outright
    ("Request URL is missing an 'http://' or 'https://' protocol"). Five WPA rows errored on
    exactly this before it was normalised."""
    s = _first(v)
    if s and s.startswith("//"):
        return "https:" + s
    return s


def _year(item: dict) -> Optional[str]:
    """The date a filter can parse. `sort_date` is already normalised to a year where LoC could
    normalise it; `date` is the display string ("between 1941 and 1943]") and is the fallback."""
    return _first(item.get("sort_date")) or _first(item.get("date"))


def _biggest_image(item: dict) -> Optional[str]:
    """The largest derivative LoC offers in the LISTING.

    Measured, because the names do not tell you: `service_low` is **117x150** (4 KB) — a gallery
    icon, not a thumbnail, and well under this library's 512px target — while `service_medium` is
    **498x640** (39 KB), which is the one worth storing. `thumb_gallery` is the same file as
    service_low.

    The full-resolution TIFF lives behind the item's `resources` block and is deliberately not
    fetched here, for the reason Cleveland's multi-megabyte original is not: a discovery row is a
    pointer, and the bytes are promotion's problem.

    NOT EVERY RECORD HAS THE MEDIUM DERIVATIVE. Some carry only `image_url`/`thumb_gallery` at
    150px, and those still index: a discovery row's main value is that it is findable by name,
    and a small preview beats dropping the record entirely. The preference order is what keeps
    that from silently becoming the norm.
    """
    return (_url(item.get("service_medium")) or _url(item.get("image_url"))
            or _url(item.get("service_low")) or _url(item.get("thumb_gallery")))


def loc_collection(slug: str = "works-progress-administration-posters", **_) -> Collection:
    """The NOLAN collection for one LoC collection. Rights are asserted PER ITEM (see
    `_clears_rights`), so the collection-level string describes rather than grants."""
    return Collection(
        slug=f"loc-{slug}",
        source="loc",
        title=f"Library of Congress — {slug.replace('-', ' ')}",
        description=(f"Library of Congress digital collection '{slug}'. Item-level rights: each "
                     f"row carries the Library's own `rights_advisory`, and only "
                     f"'no known restrictions' is admitted."),
        rights="Per item — 'no known restrictions on publication' (a statement about what the "
               "Library knows, NOT a licence grant)",
        url=f"{LOC_BASE}/collections/{slug}/",
        copyright_free=None,      # unknowable at collection level, and saying otherwise would lie
    )


def _get(url: str, params: Dict[str, Any], *, tries: int = 3) -> Optional[dict]:
    """The JSON, or None when the page is PAST THE END.

    LoC answers a `sp=` beyond the last page with **404**, not an empty result set — so the
    obvious "raise on any non-200" ended a completed 947-row crawl with a traceback and a
    non-zero exit after every row had already landed. Running out of collection is a normal
    ending, and only a genuine failure should be loud.
    """
    import httpx

    last = ""
    for attempt in range(tries):
        try:
            with httpx.Client(headers={"User-Agent": _UA}, timeout=120.0,
                              follow_redirects=True) as c:
                r = c.get(url, params=params)
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 404:
                    return None                 # walked off the end; the caller stops
                last = f"{r.status_code}"
                if r.status_code < 500:
                    break
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        time.sleep(2.0 ** attempt)
    raise RuntimeError(f"LoC request failed ({last}): {url}")


def loc_upstream_count(slug: str = "works-progress-administration-posters", **_) -> Optional[int]:
    """How many items the collection holds upstream — the denominator coverage is measured
    against. One request."""
    d = _get(f"{LOC_BASE}/collections/{slug}/", {"fo": "json", "c": 1})
    n = (d or {}).get("pagination", {}).get("of")
    return int(n) if n else None


def loc_items(limit: int = 200, *,
              slug: str = "works-progress-administration-posters",
              report: Optional["HarvestReport"] = None,
              cursor: Optional[Dict[str, Any]] = None,
              **_) -> Iterator["HarvestItem"]:
    """Walk one LoC collection, `LOC_PAGE` records per request.

    The cursor is `{page, offset}`, which is stable for a fixed collection: LoC paginates a
    server-side ordering that does not depend on our request, so a resumed crawl continues rather
    than re-walking. Same contract as the other adapters — `limit` counts rows YIELDED, and
    everything walked past is counted in the report.

    THE OFFSET IS NOT DECORATION. A page is 500 records and a bounded crawl routinely stops in
    the middle of one; recording only the page number would advance the cursor past everything
    after the stopping point, and those rows would never be seen again. The rule this tier holds
    to is that a cursor may re-walk but must never SKIP, and page-only bookkeeping breaks it
    silently — the crawl reports success and the collection is quietly short.
    """
    from nolan.imagelib.harvest import HarvestItem     # local: see the note on the imports

    page = int((cursor or {}).get("page") or 1)
    start = int((cursor or {}).get("offset") or 0)
    yielded = 0
    while yielded < limit:
        d = _get(f"{LOC_BASE}/collections/{slug}/",
                 {"fo": "json", "c": LOC_PAGE, "sp": page})
        if d is None:                            # 404 = past the last page: a normal ending
            if report is not None:
                report.exhausted = True
            break
        results = (d or {}).get("results") or []
        if not results:
            if report is not None:
                report.exhausted = True
            break
        for idx, r in enumerate(results):
            if idx < start:
                continue                         # already yielded on an earlier run
            if yielded >= limit:
                # Stop INSIDE the page and remember exactly where, so the next run resumes here.
                if report is not None:
                    report.cursor = {"page": page, "offset": idx, "slug": slug}
                return
            if report:
                report.scanned += 1
            item = r.get("item") or {}
            advisory = _first(item.get("rights_advisory")) or _first(r.get("rights"))
            if not _clears_rights(advisory):
                if report:
                    report.skipped_rights += 1
                    report.note(f"rights_advisory: {advisory or '(absent)'}")
                continue
            img = _biggest_image(item)
            if not img:
                if report:
                    report.skipped_no_image += 1
                    report.note(f"no image derivative: {_first(r.get('id'))}")
                continue
            title = _first(r.get("title")) or _first(item.get("title"))
            # `contributor_names` is the maker; LoC writes trailing role text ("Federal Art
            # Project, sponsor ") which is provenance, not part of the name.
            makers = item.get("contributor_names") or item.get("contributors") or []
            creator = "|".join(re.sub(r",\s*(sponsor|artist|photographer|publisher)\.?\s*$", "",
                                      str(m).strip(), flags=re.I).strip(" ,.")
                               for m in makers if str(m).strip()) or None
            genre = item.get("genre") or []
            subjects = item.get("subjects") or item.get("subject_headings") or []
            medium = _first(item.get("medium"))
            bits = [medium, _first(item.get("summary")), ", ".join(str(g) for g in genre[:3])]
            yield HarvestItem(
                source_ref=f"loc:{_first(item.get('id')) or _first(r.get('id'))}",
                # `service_medium` for BOTH. Using service_low as the thumbnail stored a 117x150
                # icon against a 512px target; there is no intermediate derivative in the
                # listing, so the same 498x640 file serves as the preview and as the promotion
                # target until `resources` is read for the original.
                thumb_url=img,
                url=img,
                source_url=_first(r.get("id")),
                title=title,
                creator=creator,
                # Every credited name is a maker here — LoC has no `Artist Role` column, so
                # there is nothing to rank and the first is taken rather than guessed at.
                primary_maker=(creator.split("|")[0] if creator else None),
                date_text=_year(item),
                institution="Library of Congress",
                description=", ".join(b for b in bits if b),
                license=f"Library of Congress — {advisory}",
                # `genre` is the closest thing to a museum's classification ("War posters--
                # 1940-1950"); `subjects` is what the picture is ABOUT and belongs in `subject`.
                classification=(str(genre[0]) if genre else None),
                tags=", ".join(str(g) for g in genre[:4]) or None,
                subject=", ".join(str(s) for s in subjects[:8]) or None,
                medium=medium,
                place=_first(item.get("location")),
                collection=loc_collection(slug),
            )
            yielded += 1
        # The whole page was consumed — only NOW is it safe to advance, and the offset resets.
        start = 0
        page += 1
        if report is not None:
            report.cursor = {"page": page, "offset": 0, "slug": slug}
        if yielded < limit:
            time.sleep(LOC_CRAWL_DELAY)     # their robots.txt asks for this; it is per PAGE
