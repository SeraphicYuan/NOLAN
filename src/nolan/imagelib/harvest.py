"""Collection harvest — fill the not-held (Visual Lib) tier from a source's own catalog.

A HARVEST is the picture analogue of the transcript library's channel crawl: walk a collection's
catalog API, write one discovery row per item (identity + rights + a 512px thumbnail), and leave
the bytes where they are. What you get is a searchable index over a corpus far larger than any
library you would download — the Art Institute alone publishes ~132k artworks — for the price of
a thumbnail each.

THREE KNOWLEDGE TIERS, and a harvest only produces the middle one:

  T0  collection-only  — the `Collection` row: title, blurb, rights, count. Searchable before a
                         single member is indexed; a hit says "this collection probably has it".
  T1  shallow item     — what this module writes: the source's OWN catalog metadata (title,
                         creator, date, medium, place) + thumbnail + stable id. No model calls.
  T2  captioned item   — a VLM description (and one day labelled regions) on top. DEMAND-DRIVEN,
                         never bulk: captioning 132k items is not a plan. `describe_discovery`
                         enriches what retrieval or a human actually surfaced, and
                         `discovery_stats` reports the coverage so a 3%-captioned collection can
                         never look complete.

ADAPTERS. `SOURCES` maps a source id to a function yielding `HarvestItem`s. Add a museum by
adding one adapter — the gate, the thumbnail handling, the identity columns and the dedup are
shared. Every adapter MUST supply a stable `source_ref` ('<source>:<their id>'), because a
not-held row keyed on a CDN url cannot survive that url rotating.

Identity is CATALOG-DERIVED here by construction (`identity_source='catalog'`) — these fields
come from the institution's own record, never from a model looking at the picture.

`limit` means ROWS INDEXED, never records fetched — one meaning across adapters. It mattered: as
"ids fetched" a request for 12 Met rows silently delivered 2, because the Met's listing is
unfiltered and most ids in some departments carry no image.

CLI:  python -X utf8 -m nolan.imagelib.harvest artic --limit 500 [--query "..."] [--dept "..."]
      python -X utf8 -m nolan.imagelib.harvest met --limit 250 --dept "European Paintings"
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

from nolan.imagelib.catalog import Collection

_UA = "NOLAN-VisualLib/1.0"


@dataclass
class HarvestItem:
    """One catalog record, normalised. `thumb_url` is fetched; `url` is what promotion fetches."""
    source_ref: str
    thumb_url: str
    url: Optional[str] = None
    source_url: Optional[str] = None
    title: Optional[str] = None
    creator: Optional[str] = None
    date_text: Optional[str] = None
    institution: Optional[str] = None
    description: Optional[str] = None       # catalog prose (medium/place), NOT a model caption
    license: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    wikidata_qid: Optional[str] = None
    tags: Optional[str] = None
    # The catalog tier as FIELDS rather than as prose. `description` keeps the joined sentence
    # (it is what BGE embeds); these are what a filter can actually act on.
    medium: Optional[str] = None
    classification: Optional[str] = None
    department: Optional[str] = None
    culture: Optional[str] = None
    place: Optional[str] = None


@dataclass
class HarvestReport:
    """What a harvest did — and, loudly, what it dropped. A bounded crawl that reports only its
    successes reads as full coverage; every refusal is counted and the first few are quoted."""
    collection: str
    scanned: int = 0
    added: int = 0
    refreshed: int = 0
    skipped_no_image: int = 0
    skipped_rights: int = 0
    refused_gate: int = 0
    errors: int = 0
    reasons: List[str] = field(default_factory=list)
    # Where the next run should start. An adapter advances this as it walks; `harvest` persists
    # it onto the collection row. Shape is the adapter's business — see ENUMERATION.
    cursor: Optional[Dict[str, Any]] = None
    # What the source says EXISTS, when it can be asked. The denominator for coverage.
    upstream_count: Optional[int] = None
    # True when the adapter walked to the end of the enumeration rather than stopping on `limit`.
    exhausted: bool = False

    def note(self, reason: str) -> None:
        if len(self.reasons) < 12:
            self.reasons.append(reason)

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


# --------------------------------------------------------------------- enumeration strategies
#
# HOW a source can be walked is the per-source knowledge worth saving, and it has consequences a
# caller must be able to see BEFORE starting a job measured in hours. Each strategy is a registry
# entry (purpose + when_to_use + its constraint), and every adapter declares one.
ENUMERATION = {
    "bulk-listing": {
        "purpose": "Walk the institution's own paginated listing of everything it holds.",
        "when_to_use": "The listing returns full records and has no depth cap.",
        "constraint": "Usually unfiltered, so rights are decided per row and some pages are "
                      "mostly refusals. Cheap per record and resumable by page.",
    },
    "search-ranked": {
        "purpose": "Walk a relevance-ranked search endpoint for a themed slice.",
        "when_to_use": "The caller asked for a subject rather than the whole collection.",
        "constraint": "DEPTH-CAPPED — this is the trap. The Art Institute's search 403s past "
                      "1,000 records ('You have requested too many results'), which is why an "
                      "841-row harvest looked like a budget choice and was a ceiling. Never use "
                      "for full enumeration.",
    },
    "bulk-dump": {
        "purpose": "Download the institution's published data dump, select offline, then fetch "
                   "only the selected records.",
        "when_to_use": "Per-record fetches are expensive AND a dump exists.",
        "constraint": "One large download up front, cached. Turns a 500k-request walk into a "
                      "filter plus N requests, and usually hands over the denominator for free.",
    },
    "per-object": {
        "purpose": "Fetch each object by id, because the listing returns ids only.",
        "when_to_use": "No dump and no listing with metadata.",
        "constraint": "One HTTP request PER ROW. Resumable only by remembering how far into the "
                      "id list we got — without that, a re-crawl pays a request per already-"
                      "indexed object just to rediscover it is a duplicate.",
    },
    "curated-collection": {
        "purpose": "Walk named, hand-picked collections rather than the whole institution.",
        "when_to_use": "RIGHTS ARE NOT UNIFORM across the institution.",
        "constraint": "The Library of Congress trap: `asset_gate.OPEN_ACCESS_SOURCES` already "
                      "trusts `loc` wholesale, but LoC is not uniformly public domain. An "
                      "adapter like this must assert rights per collection, and that table has "
                      "to be written before the adapter exists.",
    },
}


@dataclass(frozen=True)
class SourceAdapter:
    """One institution, and everything a crawl needs to know about it.

    This used to be `{"collection": fn, "items": fn}` — two functions and no room for the part
    that actually differs between museums. The Art Institute wants bulk-listing pagination, the
    Met wants dump-then-fetch, the Library of Congress will want per-curated-collection, and
    that choice had nowhere to live, so it survived only as prose in a docstring (where it was
    also WRONG: the docstring claimed the unfiltered listing wasted 11 of every 12 records; the
    measured figure is 52.2% usable, so it bought ~1.9x and paid a 1,000-row ceiling for it).
    """
    id: str
    collection: Callable[..., Collection]
    items: Callable[..., Iterator[HarvestItem]]
    enumeration: str
    # Ask the source how much exists. Returns None when it cannot be asked — a guessed
    # denominator is worse than an absent one, because it makes coverage look measured.
    upstream_count: Optional[Callable[..., Optional[int]]] = None
    resumable: bool = False
    # Does the catalog publish PIXEL dimensions? Decides whether the gate's resolution floor can
    # run at index time or must wait for promotion. (The Met publishes physical size.)
    publishes_pixel_dims: bool = False
    # 'per-item'      — the record carries its own rights flag (artic, met)
    # 'per-collection'— rights must be asserted for a curated set (LoC)
    rights_model: str = "per-item"
    notes: str = ""

    def __post_init__(self):
        if self.enumeration not in ENUMERATION:
            raise ValueError(
                f"{self.id}: unknown enumeration {self.enumeration!r} "
                f"(known: {sorted(ENUMERATION)})")


# ---------------------------------------------------------------- Art Institute of Chicago

ARTIC_API = "https://api.artic.edu/api/v1/artworks"
ARTIC_SEARCH = "https://api.artic.edu/api/v1/artworks/search"
ARTIC_IIIF = "https://www.artic.edu/iiif/2"
# The catalog fields worth indexing. `thumbnail` carries the SOURCE image's real dimensions, which
# is what the gate's resolution floor must judge — the 512px derivative we store would fail it.
ARTIC_FIELDS = ("id,title,artist_title,date_display,image_id,is_public_domain,medium_display,"
                "place_of_origin,department_title,classification_title,thumbnail,artwork_type_title")


def artic_collection(dept: Optional[str] = None, query: Optional[str] = None) -> Collection:
    """The T0 row for an Art Institute harvest. Rights are asserted at COLLECTION level and are
    sticky: we harvest only `is_public_domain` items, so CC0 is a property of the harvest, not a
    guess a later pass may overwrite."""
    slug = "artic-public-domain" + (f"-{dept.lower().replace(' ', '-')}" if dept else "") \
                                 + (f"-{query.lower().replace(' ', '-')[:24]}" if query else "")
    title = "Art Institute of Chicago — public-domain artworks"
    if dept:
        title += f" ({dept})"
    return Collection(
        slug=slug, source="artic", title=title,
        description=("Open-access artworks from the Art Institute of Chicago: paintings, prints, "
                     "drawings, photographs, textiles and objects from antiquity to the present, "
                     "each with catalogued title, artist, date, medium and place of origin. "
                     "Images are served over IIIF, so any region can be requested at any size."),
        rights="CC0 (Art Institute of Chicago) — public-domain artworks only",
        copyright_free=True, url="https://www.artic.edu/open-access",
        topics="art, painting, print, drawing, photography, historical object")


def artic_upstream_count(dept: Optional[str] = None, query: Optional[str] = None) -> Optional[int]:
    """How many public-domain artworks the Art Institute actually holds — the denominator.

    Measured live at 61,568 against 132,018 total, which is what makes "841 indexed" legible as
    1.4% rather than as a finished job.
    """
    import httpx
    try:
        with httpx.Client(headers={"User-Agent": _UA}, timeout=30.0) as c:
            params: Dict[str, Any] = {"query[term][is_public_domain]": "true", "limit": 1}
            if query:
                params["q"] = query
            r = c.get(ARTIC_SEARCH, params=params)
            r.raise_for_status()
            return int((r.json().get("pagination") or {}).get("total") or 0) or None
    except Exception:
        return None                      # unknown is an honest answer; a guess is not


def artic_items(limit: int = 200, *, dept: Optional[str] = None, query: Optional[str] = None,
                page_size: int = 100, report: Optional[HarvestReport] = None,
                cursor: Optional[Dict[str, Any]] = None) -> Iterator[HarvestItem]:
    """Walk the Art Institute catalog. Keyless, ~100 records per request, RESUMABLE by page.

    TWO ENUMERATIONS, and picking the wrong one costs a ceiling:

    * **No query → the bulk `/artworks` listing.** Unfiltered, so rights are decided per row, but
      it has NO DEPTH CAP: probed live to page 1,320 (132,018 records in) still returning 200.
      This is the only way to enumerate the whole collection.
    * **A query → `/artworks/search`.** Relevance-ranked and server-side filtered, but it HARD-
      STOPS at 1,000 records (403, "You have requested too many results"). Fine for a themed
      slice; useless for full coverage, and the report says so rather than stopping quietly.

    The listing used to be rejected on a docstring claim that it "spent 11 of every 12 records on
    items we must refuse on rights → a 12x saving". That does not reproduce. Measured twice over
    pages spread across the whole catalog: **52.2% usable** over 1,500 rows, and **48.1%** over a
    fresh 800-row probe (385 usable, 409 not public domain, 6 public domain without an image).
    So the filter bought ~1.9x and cost a 1,000-row ceiling — the trade was backwards. Per-page
    variance is enormous (probed pages ran 0%, 0%, 32%, 52%, 66%, 67%, 69%, 99% — public-domain-
    ness clusters hard by id), which is how a small contiguous sample produced "11 of 12".

    The listing also carries `thumbnail.width/height`, verified live, so the gate's resolution
    floor still runs at INDEX time here rather than being deferred to promotion.

    `limit` counts ROWS INDEXED (the shared contract, see `harvest`).
    """
    import httpx

    yielded = 0
    page = int((cursor or {}).get("page") or 1)
    skip_in_page = int((cursor or {}).get("offset") or 0)
    endpoint = ARTIC_SEARCH if query else ARTIC_API
    if report is not None:
        if query:
            report.note("themed slice via search: capped at 1,000 records upstream — "
                        "not a full enumeration")
        if page > 1 or skip_in_page:
            report.note(f"resuming at page {page}, offset {skip_in_page}")
    with httpx.Client(headers={"User-Agent": _UA}, timeout=45.0) as c:
        while yielded < limit:
            n = page_size
            params: Dict[str, Any] = {"limit": n, "page": page, "fields": ARTIC_FIELDS}
            if query:
                # The search endpoint can filter server-side; the bulk listing cannot, so there
                # `is_public_domain` is enforced per row in the loop below.
                params["query[term][is_public_domain]"] = "true"
                params["q"] = query
            try:
                r = c.get(endpoint, params=params)
                r.raise_for_status()
                data = r.json().get("data") or []
            except Exception as e:
                if report:
                    report.errors += 1
                    report.note(f"page {page}: {type(e).__name__}: {e}")
                return
            if not data:
                if report:
                    report.exhausted = True
                return
            for idx, a in enumerate(data):
                if idx < skip_in_page:            # resuming into the middle of a page
                    continue
                if yielded >= limit:
                    return
                img = a.get("image_id")
                if not img:
                    if report:
                        report.skipped_no_image += 1
                    continue
                if not a.get("is_public_domain"):
                    if report:
                        report.skipped_rights += 1
                    continue
                if dept and (a.get("department_title") or "") != dept:
                    continue
                thumb = a.get("thumbnail") or {}
                bits = [a.get("medium_display"), a.get("place_of_origin"),
                        a.get("classification_title") or a.get("artwork_type_title"),
                        a.get("department_title")]
                yield HarvestItem(
                    source_ref=f"artic:{a.get('id')}",
                    thumb_url=f"{ARTIC_IIIF}/{img}/full/600,/0/default.jpg",
                    url=f"{ARTIC_IIIF}/{img}/full/1686,/0/default.jpg",
                    source_url=f"https://www.artic.edu/artworks/{a.get('id')}",
                    title=a.get("title"), creator=a.get("artist_title"),
                    date_text=a.get("date_display"),
                    institution="Art Institute of Chicago",
                    description=", ".join(b for b in bits if b),
                    license="CC0 (Art Institute of Chicago)",
                    width=thumb.get("width"), height=thumb.get("height"),
                    tags=a.get("classification_title") or a.get("artwork_type_title"),
                    medium=a.get("medium_display"),
                    classification=(a.get("classification_title")
                                    or a.get("artwork_type_title")),
                    department=a.get("department_title"),
                    place=a.get("place_of_origin"))
                yielded += 1
                # Advance the cursor to just past the row the CONSUMER has finished with. This
                # line runs when the generator is resumed, i.e. after the caller indexed the
                # yielded item, so a crash can only ever re-walk a row, never skip one.
                #
                # It must be WITHIN-PAGE, not per-page: a page-granular cursor never advances at
                # all when `limit` is satisfied inside the first page, so repeated small harvests
                # re-walk page 1 forever and coverage never grows. The smoke test caught exactly
                # that — four runs of limit=4 produced four rows and no progress.
                if report is not None:
                    report.cursor = {"page": page, "offset": idx + 1}
            page += 1
            skip_in_page = 0
            if report is not None:
                report.cursor = {"page": page, "offset": 0}
            time.sleep(0.2)                                   # be a good citizen on a keyless API


# ---------------------------------------------------------------- The Metropolitan Museum of Art

MET_API = "https://collectionapi.metmuseum.org/public/collection/v1"
# Department id → name. The Met's listing endpoint is per-department, and a department is the
# natural harvest unit: "Photographs" and "Arms and Armor" are different visual worlds, and a
# harvest that mixes them can't be reasoned about at collection level.
MET_DEPARTMENTS = {
    1: "American Decorative Arts", 3: "Ancient Near Eastern Art", 4: "Arms and Armor",
    5: "Arts of Africa, Oceania, and the Americas", 6: "Asian Art", 7: "The Cloisters",
    8: "The Costume Institute", 9: "Drawings and Prints", 10: "Egyptian Art",
    11: "European Paintings", 12: "European Sculpture and Decorative Arts",
    13: "Greek and Roman Art", 14: "Islamic Art", 15: "The Robert Lehman Collection",
    16: "The Libraries", 17: "Medieval Art", 18: "Musical Instruments", 19: "Photographs",
    21: "Modern Art",
}


def _met_dept_id(dept: Optional[str]) -> Optional[int]:
    """Accept an id ('19') or a name ('Photographs', case-insensitive)."""
    if dept in (None, ""):
        return None
    s = str(dept).strip()
    if s.isdigit():
        return int(s)
    for did, name in MET_DEPARTMENTS.items():
        if name.lower() == s.lower():
            return did
    raise ValueError(f"unknown Met department {dept!r} (known: {sorted(MET_DEPARTMENTS.values())})")


def met_collection(dept: Optional[str] = None, query: Optional[str] = None) -> Collection:
    """The T0 row for a Met harvest. As with artic, only `isPublicDomain` objects are harvested,
    so the CC0 assertion is a property of the harvest rather than a guess about the institution —
    the Met holds plenty of in-copyright work and the API says which is which."""
    did = _met_dept_id(dept)
    name = MET_DEPARTMENTS.get(did) if did else None
    slug = "met-public-domain" + (f"-{name.lower().replace(' ', '-').replace(',', '')}" if name else "") \
                               + (f"-{query.lower().replace(' ', '-')[:24]}" if query else "")
    return Collection(
        slug=slug, source="met",
        title="The Metropolitan Museum of Art — public-domain objects"
              + (f" ({name})" if name else ""),
        description=("Open-access objects from the Metropolitan Museum of Art"
                     + (f", {name} department" if name else "")
                     + ": paintings, photographs, prints, sculpture, arms and armour, costume and "
                       "objects across five millennia, each catalogued with title, artist, date, "
                       "medium, culture and — where the Met has linked it — a Wikidata id."),
        rights="CC0 (The Metropolitan Museum of Art) — public-domain objects only",
        copyright_free=True, url="https://www.metmuseum.org/about-the-met/policies-and-documents/open-access",
        topics=(name.lower() if name else "art, photography, print, sculpture, historical object"))


def _met_qid(url: Optional[str]) -> Optional[str]:
    """The Q-number out of a Wikidata URL. THE reason the column exists: the Met hands the entity
    id over for free, so recording it costs one column and no extra call — and that is the
    difference between switching entity-linking on later and re-harvesting the whole collection."""
    import re
    m = re.search(r"/(Q\d+)\s*$", (url or "").strip())
    return m.group(1) if m else None


# ---------------------------------------------------------------- the Met's bulk dump
#
# The Met publishes its whole catalog as one CSV, and it changes what a Met crawl can be.
# Verified live: 317,650,992 bytes, 54 columns, carrying `Is Public Domain`, `Object ID`,
# `Department`, `Object Wikidata URL`, `Tags Wikidata URL` — and, past what this enumerator
# strictly needs, `Artist Wikidata URL`, `Artist Display Bio`, `Classification`, `Culture` and
# `Medium`, which is the artist- and catalog-knowledge the caption design deliberately refuses to
# spend a vision call on.
#
# WHAT IT ACTUALLY BUYS, measured over the real dump (484,956 rows parsed in 3.5s):
#
#   * 248,472 of 484,956 objects are public domain — **51.2%**. So enumerating blind spends
#     about TWO requests per usable row; the dump makes it one. That is a 2.0x saving, not an
#     order of magnitude, and saying so matters: the artic adapter carried an unreproducible
#     "11 of every 12" claim for months and it is what sent that crawl into a 1,000-row ceiling.
#   * THE DENOMINATOR, per department, exactly — 65,413 public-domain rows in Drawings and
#     Prints, 5,286 Paintings. Coverage stops being a guess.
#   * A department slice WITHOUT a request. The live listing cannot filter by rights at all.
#   * Free identity extras on the public-domain subset: Tags Wikidata URL on 56%, **Artist
#     Wikidata URL on 35% (85,944 rows)** — the artist-knowledge key that would otherwise cost a
#     lookup per artist — and Object Wikidata URL on 19%.
#
# The saving is modest; the denominator and the offline rights filter are the reasons to do it.
MET_CSV_URL = ("https://media.githubusercontent.com/media/metmuseum/openaccess/master/"
               "MetObjects.csv")
# The dump is SOURCE data, not library data: one copy serves every scope and project, so it is
# cached beside the global library rather than inside whichever scope asked for it.
_DUMPS_DIR = Path(__file__).resolve().parents[3] / "_library" / "images" / "_dumps"


def _met_csv_path() -> Path:
    return _DUMPS_DIR / "MetObjects.csv"


def met_download_csv(*, force: bool = False, progress=None) -> Path:
    """Fetch (once) the Met's bulk CSV. Streamed to a temp file and renamed only on success, so
    an interrupted download can never be mistaken for a complete one."""
    import httpx

    dest = _met_csv_path()
    if dest.exists() and not force:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    got = 0
    with httpx.Client(headers={"User-Agent": _UA}, timeout=120.0,
                      follow_redirects=True) as c:
        with c.stream("GET", MET_CSV_URL) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 0)
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
                    got += len(chunk)
                    if progress:
                        progress(got, total)
    tmp.replace(dest)
    return dest


def met_csv_rows(dept: Optional[str] = None, *, public_domain_only: bool = True
                 ) -> Iterator[Dict[str, str]]:
    """Stream the dump, yielding the rows worth fetching. Never loads 317 MB into memory.

    `utf-8-sig` is not decoration: the file carries a BOM, and without it the first column name
    reads as '\\ufeffObject Number' and every lookup of it silently misses.
    """
    import csv as _csv

    path = _met_csv_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Met bulk CSV not downloaded yet ({path}). Run met_download_csv() first, or "
            f"`nolan images dump met`.")
    did = _met_dept_id(dept)
    want_dept = MET_DEPARTMENTS.get(did) if did else None
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for row in _csv.DictReader(f):
            if public_domain_only and (row.get("Is Public Domain") or "").strip() != "True":
                continue
            if want_dept and (row.get("Department") or "").strip() != want_dept:
                continue
            yield row


def met_public_domain_ids(dept: Optional[str] = None) -> List[int]:
    """The object ids worth spending a request on — the whole point of the dump."""
    out = []
    for row in met_csv_rows(dept):
        try:
            out.append(int((row.get("Object ID") or "").strip()))
        except ValueError:
            continue
    return out


def met_upstream_count(dept: Optional[str] = None, query: Optional[str] = None) -> Optional[int]:
    """How many objects the listing offers for this slice — the denominator.

    Honest about what it counts: the Met's `/objects` listing is UNFILTERED, so this is objects
    in the department, not public-domain objects with images. The public-domain subset is only
    knowable from the bulk CSV (see `met_public_domain_ids`), which is exactly why that
    enumeration exists. When the CSV is already cached we use it and get the real number.
    """
    import httpx
    did = _met_dept_id(dept)
    cached = _met_csv_path()
    if cached.exists() and not query:
        try:
            ids = met_public_domain_ids(dept=dept)
            return len(ids) or None
        except Exception:
            pass
    try:
        with httpx.Client(headers={"User-Agent": _UA}, timeout=30.0) as c:
            if query:
                params: Dict[str, Any] = {"q": query, "hasImages": "true",
                                          "isPublicDomain": "true"}
                if did:
                    params["departmentId"] = did
                ids = c.get(f"{MET_API}/search", params=params).json().get("objectIDs") or []
            else:
                params = {"departmentIds": did} if did else {}
                ids = c.get(f"{MET_API}/objects", params=params).json().get("objectIDs") or []
            return len(ids) or None
    except Exception:
        return None


def met_items(limit: int = 200, *, dept: Optional[str] = None, query: Optional[str] = None,
              report: Optional[HarvestReport] = None,
              cursor: Optional[Dict[str, Any]] = None, **_ignored) -> Iterator[HarvestItem]:
    """Walk the Met catalog. Keyless, one request PER OBJECT, RESUMABLE by offset into the id list.

    The Met's endpoints return ids only, so the record costs a request. Which ids we spend those
    requests on is the whole game, and there are two answers:

    * **The bulk dump, when it is cached** (`met_download_csv`). `Is Public Domain` is a column,
      so the ~half of the catalog we must refuse on rights is filtered OFFLINE and never costs a
      request. This is the difference between walking 500k ids blind and fetching only rows we
      want — and it supplies the coverage denominator for free.
    * **The live listing, otherwise.** Unfiltered, so most of the scan is spent discovering that
      an object is not public domain or has no image.

    The search endpoint cannot substitute for either: `departmentId` combined with
    `isPublicDomain`/`hasImages` returns 0 for whole departments (probed live — dept 19 → 0 for
    every query form, dept 11 → 22).

    `limit` counts ROWS INDEXED, not ids fetched (the shared contract — see `harvest`). It
    mattered: as "ids fetched", a request for 12 Met rows silently delivered 2.
    """
    import httpx

    did = _met_dept_id(dept)
    start = int((cursor or {}).get("offset") or 0)
    from_dump = False
    with httpx.Client(headers={"User-Agent": _UA}, timeout=45.0) as c:
        try:
            if query:
                params: Dict[str, Any] = {"q": query, "hasImages": "true",
                                          "isPublicDomain": "true"}
                if did:
                    params["departmentId"] = did
                ids = c.get(f"{MET_API}/search", params=params).json().get("objectIDs") or []
            elif _met_csv_path().exists():
                ids = met_public_domain_ids(dept=dept)
                from_dump = True
            else:
                params = {"departmentIds": did} if did else {}
                ids = c.get(f"{MET_API}/objects", params=params).json().get("objectIDs") or []
        except Exception as e:
            if report:
                report.errors += 1
                report.note(f"met listing: {type(e).__name__}: {e}")
            return
        if report is not None:
            report.upstream_count = len(ids) or None
            report.note(
                f"enumerated {len(ids)} ids from "
                + ("the bulk dump (public-domain filtered offline)" if from_dump
                   else "the live listing (unfiltered — most scans will be refusals)"))
            if start:
                report.note(f"resuming at offset {start} of {len(ids)}")
            if len(ids) - start > limit:
                # NO SILENT CAPS: say how much of the collection this bounded harvest leaves.
                report.note(f"indexing up to {limit} of {len(ids) - start} remaining")
        # A scan cap so a barren department cannot walk 40k ids in silence. Unnecessary when the
        # ids came from the dump (every one of them is already known public domain), so it is
        # raised out of the way there rather than throttling a pre-filtered walk.
        scanned = yielded = 0
        scan_cap = len(ids) if from_dump else max(limit * 20, 200)
        for pos, oid in enumerate(ids[start:], start=start):
            if yielded >= limit or scanned >= scan_cap:
                break
            scanned += 1
            try:
                o = c.get(f"{MET_API}/objects/{oid}", timeout=30.0).json()
            except Exception as e:
                if report:
                    report.errors += 1
                    report.note(f"met:{oid}: {type(e).__name__}: {e}")
                continue
            # A skipped id is CONSUMED — it must not be re-examined on the next run, or a
            # department full of imageless objects re-pays for them every time.
            if not o.get("primaryImage"):
                if report:
                    report.skipped_no_image += 1
                    report.cursor = {"offset": pos + 1}
                continue
            if not o.get("isPublicDomain"):
                if report:
                    report.skipped_rights += 1
                    report.cursor = {"offset": pos + 1}
                continue
            bits = [o.get("medium"), o.get("culture"), o.get("country"),
                    o.get("classification"), o.get("department")]
            yield HarvestItem(
                source_ref=f"met:{o.get('objectID')}",
                # `primaryImageSmall` is the Met's own web-large derivative (~800px) — the right
                # thing to fetch for a thumbnail; the full original can be tens of megabytes.
                thumb_url=o.get("primaryImageSmall") or o.get("primaryImage"),
                url=o.get("primaryImage"),
                source_url=o.get("objectURL"),
                title=o.get("title"), creator=o.get("artistDisplayName") or None,
                date_text=o.get("objectDate") or None,
                institution="The Metropolitan Museum of Art",
                description=", ".join(b for b in bits if b),
                license="CC0 (The Metropolitan Museum of Art)",
                # width/height stay UNKNOWN: the Met publishes physical measurements, not pixel
                # dimensions, and inventing them from the thumbnail would be a false claim about
                # the source. Consequence, stated rather than hidden: the gate's resolution floor
                # cannot run at index time for met rows (`check_candidate` skips it when dims are
                # absent) and lands at promotion instead, where `check_file` measures real bytes.
                wikidata_qid=_met_qid(o.get("objectWikidata_URL")),
                tags=o.get("classification") or None,
                medium=o.get("medium") or None,
                classification=o.get("classification") or None,
                department=o.get("department") or None,
                culture=o.get("culture") or None,
                place=o.get("country") or o.get("region") or None)
            yielded += 1
            # After the yield: the consumer has finished with this id, so it is safe to move
            # past it. Advancing BEFORE the yield would skip a row on a crash mid-index.
            if report is not None:
                report.cursor = {"offset": pos + 1}
            time.sleep(0.05)                                  # be a good citizen on a keyless API
        if report is not None:
            if start + scanned >= len(ids):
                report.exhausted = True
            if yielded < limit:
                report.note(
                    f"scanned {scanned} of {len(ids) - start} remaining ids for {yielded} "
                    f"indexable rows"
                    + (" (scan cap reached)" if scanned >= scan_cap else " (listing exhausted)"))


# ---------------------------------------------------------------- Cleveland Museum of Art

CMA_API = "https://openaccess-api.clevelandart.org/api/artworks"


def cleveland_collection(dept: Optional[str] = None, query: Optional[str] = None) -> Collection:
    """The T0 row for a Cleveland harvest. As with the others, only CC0 items are harvested, so
    the rights assertion is a property of THIS harvest rather than a claim about the museum."""
    slug = "cleveland-cc0" + (f"-{dept.lower().replace(' ', '-')}" if dept else "") \
                           + (f"-{query.lower().replace(' ', '-')[:24]}" if query else "")
    return Collection(
        slug=slug, source="cleveland",
        title="Cleveland Museum of Art — CC0 artworks" + (f" ({dept})" if dept else ""),
        description=("Open-access artworks from the Cleveland Museum of Art: paintings, prints, "
                     "drawings, photographs, textiles, sculpture and decorative arts across the "
                     "collection, each catalogued with title, creator, date, technique, culture "
                     "and department. Images are served at web, print and full-TIFF sizes."),
        rights="CC0 (Cleveland Museum of Art) — share_license_status=CC0 only",
        copyright_free=True, url="https://www.clevelandart.org/open-access",
        topics="art, painting, print, drawing, photography, textile, sculpture")


def cleveland_upstream_count(dept: Optional[str] = None,
                             query: Optional[str] = None) -> Optional[int]:
    """Probed live: 42,255 CC0 of 68,770 total."""
    import httpx
    try:
        with httpx.Client(headers={"User-Agent": _UA}, timeout=30.0) as c:
            params: Dict[str, Any] = {"limit": 1, "cc0": "1", "has_image": "1"}
            if dept:
                params["department"] = dept
            if query:
                params["q"] = query
            r = c.get(CMA_API, params=params)
            r.raise_for_status()
            return int((r.json().get("info") or {}).get("total") or 0) or None
    except Exception:
        return None


def cleveland_items(limit: int = 200, *, dept: Optional[str] = None,
                    query: Optional[str] = None, page_size: int = 100,
                    report: Optional[HarvestReport] = None,
                    cursor: Optional[Dict[str, Any]] = None, **_ignored
                    ) -> Iterator[HarvestItem]:
    """Walk the Cleveland catalog. Keyless, `skip`/`limit` paginated, RESUMABLE by offset.

    The best-shaped of the three sources, and the 7-question probe is why we know that before
    writing a line of it:

      1. ENUMERATION   — `skip`/`limit`, no depth cap inside the result set (probed skip=20,000).
      2. RIGHTS        — a PER-ITEM flag (`share_license_status`) *and* a server-side `cc0=1`
                         filter, so unlike artic we get both filtering and depth.
      3. STABLE ID     — numeric `id`, namespaced here as `cleveland:94979`.
      4. IMAGE URLS    — three fixed derivatives: `web` (~750px), `print` (~2850px), `full`
                         (a multi-megabyte TIFF). We thumbnail `web` and promote `print`; the
                         TIFF is deliberately not our problem.
      5. PIXEL DIMS    — published per derivative, so the gate's resolution floor runs at INDEX
                         time rather than being deferred to promotion (the Met's weakness).
      6. AUTH          — keyless.
      7. FREE EXTRAS   — `creators` with biographical descriptions, `technique`, `culture`,
                         `department`, `tombstone`.

    One observed property worth knowing: the listing order is NOT perfectly stable across calls,
    so a skip-based cursor occasionally re-sees a row it has already indexed (measured: 1 of 4 on
    a resumed run). `source_ref` dedup turns that into a refresh rather than a duplicate, which
    is precisely why the cursor is allowed to re-walk but never to skip.
    """
    import httpx

    yielded = 0
    skip = int((cursor or {}).get("offset") or 0)
    if report is not None and skip:
        report.note(f"resuming at offset {skip}")
    with httpx.Client(headers={"User-Agent": _UA}, timeout=45.0) as c:
        while yielded < limit:
            params: Dict[str, Any] = {"limit": page_size, "skip": skip, "cc0": "1",
                                      "has_image": "1"}
            if dept:
                params["department"] = dept
            if query:
                params["q"] = query
            try:
                r = c.get(CMA_API, params=params)
                r.raise_for_status()
                data = r.json().get("data") or []
            except Exception as e:
                if report:
                    report.errors += 1
                    report.note(f"skip {skip}: {type(e).__name__}: {e}")
                return
            if not data:
                if report:
                    report.exhausted = True
                return
            for idx, a in enumerate(data):
                if yielded >= limit:
                    return
                imgs = a.get("images") or {}
                web = imgs.get("web") or {}
                pr = imgs.get("print") or web
                if not web.get("url"):
                    if report:
                        report.skipped_no_image += 1
                    continue
                if (a.get("share_license_status") or "").upper() != "CC0":
                    if report:
                        report.skipped_rights += 1
                    continue
                creators = a.get("creators") or []
                creator = (creators[0].get("description") if creators else None) or None
                # The biographical tail ("(American, 1738-1815)") is real information, but it
                # belongs to the ARTIST rather than to this row — `artist_key` strips it so the
                # per-person knowledge still folds correctly.
                culture = a.get("culture")
                if isinstance(culture, list):
                    culture = ", ".join(str(x) for x in culture if x) or None
                bits = [a.get("technique"), culture, a.get("type"), a.get("department")]
                try:
                    w = int(pr.get("width") or 0) or None
                    h = int(pr.get("height") or 0) or None
                except (TypeError, ValueError):
                    w = h = None
                yield HarvestItem(
                    source_ref=f"cleveland:{a.get('id')}",
                    thumb_url=web.get("url"),
                    url=pr.get("url") or web.get("url"),
                    source_url=a.get("url"),
                    title=a.get("title"), creator=creator,
                    date_text=a.get("creation_date"),
                    institution="Cleveland Museum of Art",
                    description=", ".join(str(b) for b in bits if b),
                    license="CC0 (Cleveland Museum of Art)",
                    width=w, height=h,
                    tags=a.get("type"),
                    medium=a.get("technique"), classification=a.get("type"),
                    department=a.get("department"), culture=culture)
                yielded += 1
                # Just past the row the consumer has finished with — NOT the end of the page.
                # The first version advanced to skip+len(data) here, so a harvest of 4 rows left
                # the cursor at 100 and the next run skipped 96 rows it had never seen. Same
                # class as the artic within-page fix: re-walking is free, skipping loses rows.
                if report is not None:
                    report.cursor = {"offset": skip + idx + 1}
            skip += len(data)
            if report is not None:
                report.cursor = {"offset": skip}
            time.sleep(0.15)                              # be a good citizen on a keyless API


SOURCES: Dict[str, SourceAdapter] = {
    "artic": SourceAdapter(
        id="artic",
        collection=artic_collection,
        items=artic_items,
        enumeration="bulk-listing",
        upstream_count=artic_upstream_count,
        resumable=True,
        publishes_pixel_dims=True,
        rights_model="per-item",
        notes="Keyless. The bulk /artworks listing has no depth cap (probed to page 1,320) and "
              "carries thumbnail pixel dimensions, so the resolution floor runs at index time. "
              "A --query switches to the relevance-ranked search endpoint, which is HARD-CAPPED "
              "at 1,000 records — fine for a themed slice, never for full coverage.",
    ),
    "met": SourceAdapter(
        id="met",
        collection=met_collection,
        items=met_items,
        enumeration="bulk-dump",
        upstream_count=met_upstream_count,
        resumable=True,
        publishes_pixel_dims=False,
        rights_model="per-item",
        notes="Keyless, one request PER OBJECT because the endpoints return ids only. The bulk "
              "CSV (318 MB, 54 columns, 484,956 rows) carries `Is Public Domain`, so the rights "
              "filter runs OFFLINE: 248,472 rows are public domain (51.2%), a 2.0x request "
              "saving — modest, and the real wins are an exact per-department denominator and a "
              "rights-filtered department slice the live listing cannot produce at all. "
              "Publishes physical measurements rather than pixel dimensions, so the resolution "
              "floor lands at promotion instead of at index time. Hands over Wikidata ids free "
              "(tags 56%, artist 35%, object 19% of the public-domain subset).",
    ),
    "cleveland": SourceAdapter(
        id="cleveland",
        collection=cleveland_collection,
        items=cleveland_items,
        enumeration="bulk-listing",
        upstream_count=cleveland_upstream_count,
        resumable=True,
        publishes_pixel_dims=True,
        rights_model="per-item",
        notes="Keyless, skip/limit paginated, no depth cap inside the result set. The best-"
              "shaped of the three: a server-side cc0=1 filter AND full depth (artic makes you "
              "choose), plus published pixel dimensions per derivative so the resolution floor "
              "runs at index time. Three fixed derivatives — web (~750px, thumbnailed), print "
              "(~2850px, promoted) and a multi-megabyte full TIFF we deliberately ignore. "
              "Denominator probed live: 42,255 CC0 of 68,770.",
    ),
}


# ------------------------------------------------------------------------------ the harvest loop

def harvest(source: str, *, limit: int = 200, scope: str = "global",
            project: Optional[str] = None, library=None, progress=None,
            resume: bool = True, pixels: bool = True, **source_kwargs) -> HarvestReport:
    """Harvest into the discovery tier. Idempotent: a re-run refreshes rows by `source_ref`
    instead of duplicating them, and RESUMES from where the last run stopped.

    `limit` counts ROWS INDEXED, not records fetched — the one contract every adapter honours, so
    "give me 200" means 200 usable rows whether the source's listing is pre-filtered (artic) or
    full of imageless entries (met). Whatever it walked past to get there is in the report.

    `resume=False` restarts the enumeration from the beginning (a re-crawl to refresh identity
    rather than to extend coverage).

    `pixels=False` runs PHASE A only — the catalog record, no thumbnail fetch, no CLIP vector.
    Benchmarked at 87 ms/row against 470 ms/row with pixels (5.4x), which over the 62,035-row
    artic public-domain catalog is 1.5 h against 9.6 h. The rows are immediately searchable by
    IDENTITY (named 94.7/100/100 with no pixels at all) and gain LOOK ranking as
    `ImageLibrary.backfill_pixels` works through them.
    """
    if source not in SOURCES:
        raise ValueError(f"unknown harvest source {source!r} (known: {sorted(SOURCES)})")
    import json as _json

    from nolan.imagelib import ImageLibrary

    adapter = SOURCES[source]
    lib = library or ImageLibrary(scope=scope, project=project)
    col_kwargs = {k: v for k, v in source_kwargs.items() if k in ("dept", "query")}
    collection = lib.upsert_collection(adapter.collection(**col_kwargs))
    report = HarvestReport(collection=collection.slug)

    # RESUME. Without this every run restarts at page 1 / id 0 and leans on source_ref dedup to
    # skip — which for the Met costs one HTTP request per already-indexed object just to
    # rediscover it is a duplicate, and makes a job measured in hours one that never finishes.
    start_cursor = None
    if resume and adapter.resumable and collection.cursor:
        try:
            start_cursor = _json.loads(collection.cursor)
        except Exception:
            report.note(f"ignoring unreadable cursor {collection.cursor!r}")

    def _persist_cursor() -> None:
        # FLUSH FIRST, ALWAYS. The identity index is batched, so rows can be in SQLite while
        # their embeddings are still buffered. Advancing the cursor past them would mean a resume
        # never revisits them AND a refresh never re-embeds them (unchanged identity skips the
        # work by design) — a permanent hole in identity search. Flushing here makes the cursor
        # unable to run ahead of the index.
        lib.flush_index()
        if report.cursor is None or not adapter.resumable:
            return
        lib.upsert_collection(Collection(
            slug=collection.slug, source=source, title=collection.title,
            cursor=_json.dumps(report.cursor),
            cursor_at=time.strftime("%Y-%m-%dT%H:%M:%S")))

    items_kwargs = dict(source_kwargs)
    if adapter.resumable:
        items_kwargs["cursor"] = start_cursor

    for item in adapter.items(limit=limit, report=report, **items_kwargs):
        report.scanned += 1
        try:
            # RETRY transient CDN failures. Measured on a 899-record crawl: 44 items (~5%) were
            # lost to 502/504 from the IIIF host under our own request rate — noise, not a
            # property of the item, and a harvest that drops 5% of a collection for noise silently
            # under-covers it. A gate refusal (ValueError) is a VERDICT and never retried.
            for attempt in range(3):
                try:
                    asset, created = lib.add_discovery(
                        source_ref=item.source_ref, thumb_url=item.thumb_url, url=item.url,
                        source=source, source_url=item.source_url, title=item.title,
                        creator=item.creator, date_text=item.date_text,
                        institution=item.institution, description=item.description,
                        license=item.license, width=item.width, height=item.height,
                        wikidata_qid=item.wikidata_qid, tags=item.tags,
                        collection_id=collection.id, identity_source="catalog",
                        pixels=pixels,
                        medium=item.medium, classification=item.classification,
                        department=item.department, culture=item.culture,
                        place=item.place)
                    break
                except ValueError:
                    raise
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(1.5 * (attempt + 1))
            report.added += int(created)
            report.refreshed += int(not created)
        except ValueError as e:                     # a gate refusal — counted, quoted, never silent
            report.refused_gate += 1
            report.note(str(e))
        except Exception as e:
            report.errors += 1
            report.note(f"{item.source_ref}: {type(e).__name__}: {e}")
        if progress:
            progress(report)
        # Checkpoint the cursor periodically, not only at the end: a crawl killed after four
        # hours must not resume from where it started four hours ago.
        if report.scanned % 50 == 0:
            _persist_cursor()

    # THE DENOMINATOR. Ask the source how much exists, so coverage can be stated as a share
    # rather than as a bare count — "841 indexed" reads as complete, "841 of 62,035 (1.4%)"
    # cannot. Only overwritten when the source actually answers: a None here leaves the previous
    # figure alone, and a collection that has never been able to answer reports coverage as
    # unknown rather than as full.
    upstream = report.upstream_count
    if upstream is None and adapter.upstream_count is not None:
        try:
            upstream = adapter.upstream_count(**col_kwargs)
        except Exception as e:
            report.note(f"upstream count unavailable: {type(e).__name__}: {e}")
    report.upstream_count = upstream

    lib.flush_index()                       # nothing may be left buffered when a crawl returns
    indexed = lib.catalog.count("active", held=0, collection_id=collection.id)
    if upstream:
        report.note(f"coverage: {indexed} of {upstream} upstream "
                    f"({indexed / upstream * 100:.1f}%)")
    lib.upsert_collection(Collection(
        slug=collection.slug, source=source, title=collection.title,
        item_count=indexed,
        upstream_count=upstream,
        cursor=(_json.dumps(report.cursor) if report.cursor and adapter.resumable else None),
        cursor_at=(time.strftime("%Y-%m-%dT%H:%M:%S") if report.cursor else None),
        last_crawled=time.strftime("%Y-%m-%dT%H:%M:%S")))
    return report


def describe_discovery(library, *, limit: int = 25, collection_id: Optional[int] = None,
                       describer=None, model: str = "vlm", progress=None,
                       only_ids=None) -> int:
    """T2, on demand: caption not-held rows that lack a description, from their THUMBNAIL.

    Bounded by `limit` on purpose — this is the expensive tier and it is spent on what retrieval
    or a human surfaced, not on the whole catalog. The collection's own blurb is prepended as
    context, the same trick that makes video-frame captions entity-aware by feeding them the
    transcript window: a describer told "these are Art Institute open-access artworks" writes a
    materially better caption than one shown a bare image.

    A caption NEVER becomes an identity: `identity_source` is untouched, and the generated text
    lands in `description` only. Returns the number described.
    """
    from nolan.imagelib.artists import artist_context
    from nolan.imagelib.caption import (CAPTION_SCHEMA, PROMPT, build_context,
                                        caption_text, parse_caption)

    describer = describer or library.describer
    if describer is None:
        raise ValueError("no describer provided")
    blurb = ""
    if collection_id is not None:
        for c in library.catalog.list_collections():
            if c.id == collection_id:
                blurb = c.description or ""
                break
    done = 0
    for a in library.catalog.list(status="active", held=0, collection_id=collection_id,
                                  limit=max(limit * 8, 200)):
        if done >= limit:
            break
        if only_ids is not None and a.id not in only_ids:
            continue                       # a caller chose these rows deliberately (the dialect
                                           # sample spans image_kind rather than taking the head)
        # Never pay twice. A row already carrying THIS schema version is done; one carrying an
        # older version is a re-caption candidate, which is the whole reason the version exists.
        if (a.description_source or "catalog") != "catalog" and \
                (a.caption_schema or 0) >= CAPTION_SCHEMA:
            continue
        thumb = (library.base / (a.thumb_path or "")).resolve()
        if not a.thumb_path or not thumb.exists():
            continue                       # a Phase-A row has no pixels yet — backfill first

        # Context, from the three FREE knowledge sources. Deliberately excludes the title: hand
        # the model the answer and it describes the title instead of the picture.
        ctx = build_context(collection=blurb or None,
                            artist=artist_context(library, a.creator) or a.creator,
                            kind=a.classification or a.image_kind)
        prompt = PROMPT.format(context=ctx)
        try:
            raw = (describer(thumb, prompt=prompt) if _takes_prompt(describer)
                   else describer(thumb, context=ctx) if _takes_context(describer)
                   else describer(thumb))
        except Exception:
            continue
        cap = parse_caption(raw or "")
        if not cap:
            continue
        text = caption_text(cap)
        if not text:
            continue
        library.catalog.set_description(a.id, text)
        library.catalog.update(a.id, description_source=model,
                               caption_json=json.dumps(cap, ensure_ascii=False),
                               caption_schema=CAPTION_SCHEMA)
        library._index_discovery(library.catalog.get(a.id), thumb)
        done += 1
        if progress:
            progress(done, limit)
    library.flush_index()
    return done


def learn_collection_dialect(library, collection_id: int, *, n: int = 12,
                             describer=None, model: str = "vlm") -> Dict[str, Any]:
    """Caption a SPANNING sample of a collection and store the consensus as its visual dialect.

    Cheap and high-leverage: a dozen calls give every row in the collection something useful to
    say about how the collection looks, long before that row is individually worth a vision call.
    It is also not throwaway work — the sampled rows keep their own full captions.

    The sample spans `image_kind` rather than following the corpus's skew, for the reason the
    original 50-row validation did: a proportional sample of a 60%-painting corpus says almost
    nothing about the coins, textiles and object photography that carry the hard cases.
    """
    from nolan.imagelib.caption import consensus, spanning_sample

    rows = [a for a in library.catalog.list(status="active", held=0,
                                            collection_id=collection_id, limit=2000)
            if a.thumb_path]
    picks = spanning_sample(rows, n=n)
    if not picks:
        return {"n": 0, "note": "no rows with pixels — run backfill first"}

    # Caption exactly the picks, reusing the one caption path (never a second implementation).
    wanted = {a.id for a in picks}
    described = describe_discovery(
        library, limit=len(picks), collection_id=collection_id,
        describer=describer, model=model,
        only_ids=wanted)
    caps = [c for c in (library.catalog.get(i).caption() for i in wanted) if c]
    d = consensus(caps)
    col = library.catalog.get_collection_by_id(collection_id)
    library.catalog.upsert_collection(Collection(
        slug=col.slug, source=col.source, title=col.title,
        dialect_json=json.dumps(d, ensure_ascii=False)))
    d["captioned_now"] = described
    d["kinds_sampled"] = sorted({a.image_kind or "unknown" for a in picks})
    return d


def _takes_prompt(fn) -> bool:
    import inspect
    try:
        return "prompt" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def _takes_context(fn) -> bool:
    import inspect
    try:
        return "context" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def _main(argv=None) -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(prog="nolan.imagelib.harvest",
                                 description="Harvest a collection into the Visual Lib tier")
    ap.add_argument("source", choices=sorted(SOURCES))
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--query", default=None, help="themed slice (search endpoint)")
    ap.add_argument("--dept", default=None, help="filter to one department")
    ap.add_argument("--scope", default="global", choices=("global", "project"))
    ap.add_argument("--project", default=None)
    args = ap.parse_args(argv)

    kw = {k: v for k, v in (("query", args.query), ("dept", args.dept)) if v}
    rep = harvest(args.source, limit=args.limit, scope=args.scope, project=args.project, **kw)
    print(json.dumps(rep.to_dict(), indent=2, ensure_ascii=False))
    return 0 if rep.added or rep.refreshed else 1


if __name__ == "__main__":
    raise SystemExit(_main())
