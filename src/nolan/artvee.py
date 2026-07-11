"""Artvee search module — public-domain fine-art retrieval.

Artvee (https://artvee.com) is a curated aggregator of public-domain / CC0 fine
art (paintings, drawings, prints). It has NO public API, so this module scrapes
its WooCommerce/WoodMart HTML — but the markup is generous: every search-result
tile embeds the artist, category, title+year, image dimensions, file sizes and a
CDN file-key (``sk``) as ``data-*`` attributes, so a single page fetch yields
full metadata for 30 works WITHOUT visiting each detail page.

Layering (mirrors art_sourcing -> image_search):

  - This module is the rich, standalone retrieval + filter engine. It returns
    ``ArtveeResult`` objects carrying metadata that ``ImageSearchResult`` can't
    hold (year, genre/category, SD/HD dimensions, file sizes).
  - ``image_search.ArtveeProvider`` is a thin adapter that maps ArtveeResult ->
    ImageSearchResult so artvee plugs into the generic provider fan-out, the
    vision scorer, the asset gate and ``art_sourcing.ART_SOURCES``.

What it does:
  1. Keyword search   -> ``search(query)``           (?s=<query>)
  2. Artist search    -> ``search_artist(slug)``      (/artist/<slug>/)
  3. Pagination       -> both walk ``.../page/N/`` until max_results / exhausted
  4. Advanced search  -> ``advanced_search(...)`` filters & sorts the metadata
  5. Download low-res -> ``download(result, path)`` resolves the presigned SDL URL

The low-res ("SDL") download is a presigned S3 URL embedded in each detail page
(24h expiry, no login). The high-res ("HDL") tier requires an artvee membership
and is intentionally not fetched here.
"""

from __future__ import annotations

import html
import json
import re
import time
import unicodedata
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

BASE = "https://artvee.com"
CDN = "https://mdl.artvee.com"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
_PER_PAGE = 30  # artvee returns 30 tiles per search page (10 per artist page)


# --------------------------------------------------------------------------- #
# Result model
# --------------------------------------------------------------------------- #
@dataclass
class ArtveeResult:
    """One artwork from an artvee listing, with all listing-level metadata.

    Everything here is parsed from the search/artist grid tile — no detail-page
    fetch is required until you actually download (which needs the presigned SDL
    URL). ``resolved_sdl_url`` is filled in by ``ArtveeClient.resolve_download``.
    """
    sk: str                                   # CDN file-key, e.g. "406646mt"
    detail_url: str                           # https://artvee.com/dl/<slug>/
    title: str                                # cleaned title (year stripped)
    raw_title: str = ""                       # title exactly as shown
    year: Optional[int] = None                # parsed from a trailing "(1896)"
    artist: Optional[str] = None              # display name, e.g. "William Etty"
    artist_slug: Optional[str] = None         # e.g. "william-etty"
    category: Optional[str] = None            # genre/category, e.g. "Mythology"
    artvee_id: Optional[str] = None           # data-id attribute
    thumbnail_url: str = ""                    # https://mdl.artvee.com/ft/<sk>.jpg
    preview_url: str = ""                      # mid-size, https://artvee.com/mcnt/upl/<sk>.jpg
    sd_width: Optional[int] = None            # standard-download image dims
    sd_height: Optional[int] = None
    hd_width: Optional[int] = None            # high-res image dims (info only)
    hd_height: Optional[int] = None
    sd_filesize_mb: Optional[float] = None
    hd_filesize_mb: Optional[float] = None
    resolved_sdl_url: Optional[str] = None    # presigned low-res download URL

    # -- derived ---------------------------------------------------------- #
    @property
    def orientation(self) -> Optional[str]:
        """'portrait' | 'landscape' | 'square' from the SD dimensions."""
        if not self.sd_width or not self.sd_height:
            return None
        r = self.sd_width / self.sd_height
        if r > 1.15:
            return "landscape"
        if r < 0.87:
            return "portrait"
        return "square"

    @property
    def sd_pixels(self) -> Optional[int]:
        if self.sd_width and self.sd_height:
            return self.sd_width * self.sd_height
        return None

    def to_dict(self) -> Dict[str, Any]:
        d = {k: v for k, v in asdict(self).items() if v is not None}
        if self.orientation:
            d["orientation"] = self.orientation
        return d


@dataclass
class ArtveeFilter:
    """Declarative filter for ``advanced_search`` — every field is optional.

    All string matches are case-insensitive substring matches unless noted.
    A result must satisfy EVERY set field (logical AND).
    """
    artist: Optional[str] = None              # substring of artist display name
    title_contains: Optional[str] = None      # substring of title
    categories: Optional[List[str]] = None    # any-of, case-insensitive exact
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    orientation: Optional[str] = None         # portrait|landscape|square
    min_width: Optional[int] = None           # min SD width
    min_height: Optional[int] = None          # min SD height
    min_megapixels: Optional[float] = None    # min SD megapixels
    require_year: bool = False                # drop results with no parsed year
    exclude_anonymous: bool = False           # drop "Anonymous" / unattributed

    def matches(self, r: ArtveeResult) -> bool:
        if self.artist and (not r.artist or self.artist.lower() not in r.artist.lower()):
            return False
        if self.title_contains and self.title_contains.lower() not in r.title.lower():
            return False
        if self.categories:
            cats = {c.lower() for c in self.categories}
            if not r.category or r.category.lower() not in cats:
                return False
        if self.require_year and r.year is None:
            return False
        if self.year_min is not None and (r.year is None or r.year < self.year_min):
            return False
        if self.year_max is not None and (r.year is None or r.year > self.year_max):
            return False
        if self.orientation and r.orientation != self.orientation:
            return False
        if self.min_width is not None and (not r.sd_width or r.sd_width < self.min_width):
            return False
        if self.min_height is not None and (not r.sd_height or r.sd_height < self.min_height):
            return False
        if self.min_megapixels is not None:
            px = r.sd_pixels
            if px is None or px < self.min_megapixels * 1_000_000:
                return False
        if self.exclude_anonymous:
            if not r.artist or r.artist.strip().lower() in ("", "anonymous", "unknown"):
                return False
        return True


# --------------------------------------------------------------------------- #
# Parsing helpers (module-level so they're unit-testable without a network)
# --------------------------------------------------------------------------- #
_RE_ITEM = re.compile(r'class="product-grid-item\b.*?(?=class="product-grid-item\b|</main|<footer|$)', re.S)
_RE_TOP = re.compile(r'product-element-top[^>]*?data-id="(?P<id>\d+)"[^>]*?data-sk="(?P<sk>\{.*?\})"[^>]*?data-url="(?P<url>[^"]+)"', re.S)
_RE_TITLE = re.compile(r'<h3 class="product-title">\s*<a href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>', re.S)
_RE_ARTIST = re.compile(r'woodmart-product-brands-links[^>]*>\s*<a href="[^"]*?/artist/(?P<slug>[^/"]+)/?"[^>]*>(?P<name>[^<]+)</a>', re.S)
_RE_CAT = re.compile(r'woodmart-product-cats[^>]*>\s*<a href="[^"]*?/(?:c|t)/[^"]+"[^>]*>(?P<cat>[^<]+)</a>', re.S)
_RE_IMG_ALT = re.compile(r'<img[^>]*\balt="(?P<alt>[^"]*)"', re.S)
_RE_DIMS = re.compile(r'(\d[\d,]*)\s*[x×]\s*(\d[\d,]*)')
_RE_TRAIL_PAREN = re.compile(r'\s*\(([^()]*)\)\s*$')
_RE_YEAR_NUM = re.compile(r'\b(\d{3,4})\b')
# date-qualifier words allowed to surround a year inside the trailing parenthesis
_RE_DATE_WORDS = re.compile(
    r'\b(c|ca|circa|before|after|early|late|mid|about|approx|approximately'
    r'|century|centuries|bce?|ce|ad|dated|first|second|third|half|quarter|the|s)\b',
    re.I)
_RE_NEXT = re.compile(r'class="next page-numbers"')


def _to_mb(s: Optional[str]) -> Optional[float]:
    """'20.61 MB' / '918.44 KB' / '1.2 GB' -> float megabytes."""
    if not s:
        return None
    m = re.match(r'\s*([\d.]+)\s*([KMG]?B)', s, re.I)
    if not m:
        return None
    val, unit = float(m.group(1)), m.group(2).upper()
    return {"KB": val / 1024, "MB": val, "GB": val * 1024, "B": val / (1024 * 1024)}.get(unit, val)


def _parse_dims(s: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    if not s:
        return None, None
    m = _RE_DIMS.search(s)
    if not m:
        return None, None
    return int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))


def _split_year(raw_title: str) -> tuple[str, Optional[int]]:
    """Split a trailing date parenthesis off a title.

    'Depiction ... amphora (1896)'        -> ('Depiction ... amphora', 1896)
    'Die Geburt der Athena (before 1842)' -> ('Die Geburt der Athena', 1842)
    'Athena ... (ca. 1832)'               -> ('Athena ...', 1832)
    'Still Life (recto)'                  -> ('Still Life (recto)', None)   [not a date]

    Only strips the parenthesis when its contents are a plausible date: it holds
    a 3-4 digit year (1000-2099) and nothing but date-qualifier words/punctuation
    around it. A non-date parenthetical (e.g. '(recto)', '(No. 12)') is left in
    the title and yields no year, avoiding false positives.
    """
    t = raw_title.strip()
    m = _RE_TRAIL_PAREN.search(t)
    if not m:
        return t, None
    inner = m.group(1)
    ym = _RE_YEAR_NUM.search(inner)
    if not ym:
        return t, None
    year = int(ym.group(1))
    if not (1000 <= year <= 2099):
        return t, None
    # Whatever remains after removing the year (+ optional range), date words and
    # punctuation must be empty for this to count as a pure date parenthesis.
    residue = re.sub(r'\d{3,4}(?:\s*[-–/]\s*\d{2,4})?', '', inner)
    residue = _RE_DATE_WORDS.sub('', residue)
    residue = re.sub(r"[.\-–—/,;:'’\s]", '', residue)
    if residue:
        return t, None
    clean = t[: m.start()].strip()
    return (clean or t), year


def parse_listing(page_html: str) -> List[ArtveeResult]:
    """Parse one search/artist results page into ArtveeResult objects.

    Pure function over HTML — no network. Robust to missing fields: a tile that
    lacks the ``data-sk``/``data-url`` core is skipped; artist/category/year are
    optional. Order is preserved (artvee returns relevance order for search).
    """
    out: List[ArtveeResult] = []
    seen: set[str] = set()
    for block in _RE_ITEM.findall(page_html):
        top = _RE_TOP.search(block)
        if not top:
            continue
        try:
            sk_json = json.loads(html.unescape(top.group("sk")))
        except (ValueError, TypeError):
            sk_json = {}
        sk = (sk_json.get("sk") or "").strip()
        if not sk or sk in seen:
            continue
        seen.add(sk)

        data_url = top.group("url")
        detail_url = data_url if data_url.startswith("http") else f"{BASE}{data_url}"
        if not detail_url.endswith("/"):
            detail_url += "/"

        tm = _RE_TITLE.search(block)
        raw_title = html.unescape(re.sub(r"\s+", " ", tm.group("title")).strip()) if tm else ""
        if tm and tm.group("href"):
            detail_url = tm.group("href")
        if not raw_title:
            am = _RE_IMG_ALT.search(block)
            raw_title = html.unescape(am.group("alt").strip()) if am else sk
        title, year = _split_year(raw_title)

        art = _RE_ARTIST.search(block)
        cat = _RE_CAT.search(block)
        sdw, sdh = _parse_dims(sk_json.get("sdlimagesize"))
        hdw, hdh = _parse_dims(sk_json.get("hdlimagesize"))

        out.append(ArtveeResult(
            sk=sk,
            detail_url=detail_url,
            title=title,
            raw_title=raw_title,
            year=year,
            artist=html.unescape(art.group("name").strip()) if art else None,
            artist_slug=art.group("slug") if art else None,
            category=html.unescape(cat.group("cat").strip()) if cat else None,
            artvee_id=top.group("id"),
            thumbnail_url=f"{CDN}/ft/{sk}.jpg",
            preview_url=f"{BASE}/mcnt/upl/{sk}.jpg",
            sd_width=sdw, sd_height=sdh, hd_width=hdw, hd_height=hdh,
            sd_filesize_mb=_to_mb(sk_json.get("sdlfilesize")),
            hd_filesize_mb=_to_mb(sk_json.get("hdlfilesize")),
        ))
    return out


def _has_next_page(page_html: str) -> bool:
    return bool(_RE_NEXT.search(page_html))


def slugify_artist(name: str) -> str:
    """Best-effort artvee artist slug: NFKD-fold diacritics, lower, hyphenate.

    Matches artvee's scheme for most names (e.g. 'William Etty' -> 'william-etty',
    'Narcisse-Virgile Diaz de La Peña' -> 'narcisse-virgile-diaz-de-la-pena').
    Use ``find_artist_slug`` when you need certainty.
    """
    n = unicodedata.normalize("NFKD", name)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = n.lower().strip()
    n = re.sub(r"[^a-z0-9]+", "-", n)
    return n.strip("-")


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #
class ArtveeClient:
    """Scraping client for artvee search, artist pages and downloads.

    A fresh ``httpx.Client`` is created lazily and reused. ``page_delay`` throttles
    multi-page walks to stay a polite scraper. Nothing here mutates global state.
    """

    def __init__(self, *, timeout: float = 30.0, page_delay: float = 0.4,
                 user_agent: str = _UA):
        self.timeout = timeout
        self.page_delay = page_delay
        self.user_agent = user_agent
        self._client: Optional[httpx.Client] = None

    # -- lifecycle ------------------------------------------------------- #
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={"User-Agent": self.user_agent,
                         "Accept-Language": "en-US,en;q=0.9",
                         # Detail pages embed a presigned (24h) S3 URL. Ask edges
                         # not to serve a cached page, so we always parse a
                         # freshly-generated link (a stale cached one can 403).
                         "Cache-Control": "no-cache", "Pragma": "no-cache"},
                follow_redirects=True, timeout=self.timeout,
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "ArtveeClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- low level ------------------------------------------------------- #
    def _get(self, url: str, params: Optional[dict] = None) -> Optional[str]:
        try:
            resp = self.client.get(url, params=params)
        except httpx.HTTPError:
            return None
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.text

    def _walk_pages(self, page_url, *, max_results: int,
                    max_pages: Optional[int]) -> List[ArtveeResult]:
        """Fetch successive pages via ``page_url(n)`` until enough results.

        Stops at ``max_results``, when a page yields no items, when the pager
        shows no 'next', or after ``max_pages``. De-dupes on ``sk`` across pages.
        """
        results: List[ArtveeResult] = []
        seen: set[str] = set()
        page = 1
        while len(results) < max_results:
            if max_pages is not None and page > max_pages:
                break
            html_text = self._get(page_url(page))
            if not html_text:
                break
            items = parse_listing(html_text)
            new = [r for r in items if r.sk not in seen]
            for r in new:
                seen.add(r.sk)
            results.extend(new)
            if not new or not _has_next_page(html_text):
                break
            page += 1
            if self.page_delay:
                time.sleep(self.page_delay)
        return results[:max_results]

    # -- public search --------------------------------------------------- #
    def search(self, query: str, *, max_results: int = 30,
               max_pages: Optional[int] = None) -> List[ArtveeResult]:
        """Keyword search across artvee (title, artist, tags). Paginated."""
        q = query.strip()

        def page_url(n: int) -> str:
            return f"{BASE}/main/?s={httpx.QueryParams({'s': q})['s']}" if n == 1 \
                else f"{BASE}/main/page/{n}/?s={httpx.QueryParams({'s': q})['s']}"

        return self._walk_pages(page_url, max_results=max_results, max_pages=max_pages)

    def search_artist(self, artist_or_slug: str, *, max_results: int = 60,
                      max_pages: Optional[int] = None) -> List[ArtveeResult]:
        """All works on an artist's canonical page. Accepts a slug or a name.

        A name is slugified first (``slugify_artist``); if that page 404s, falls
        back to ``find_artist_slug`` (a keyword search), then to keyword search.
        """
        slug = artist_or_slug if re.fullmatch(r"[a-z0-9-]+", artist_or_slug) \
            else slugify_artist(artist_or_slug)

        def page_url(n: int) -> str:
            return f"{BASE}/artist/{slug}/" if n == 1 \
                else f"{BASE}/artist/{slug}/page/{n}/"

        # Probe page 1: if the slug is wrong, discover it or fall back to keyword.
        first = self._get(page_url(1))
        if first is None:
            discovered = self.find_artist_slug(artist_or_slug)
            if discovered and discovered != slug:
                slug = discovered
                first = self._get(page_url(1))
            if first is None:
                return self.search(artist_or_slug, max_results=max_results,
                                   max_pages=max_pages)

        results = parse_listing(first)
        seen = {r.sk for r in results}
        if _has_next_page(first) and len(results) < max_results:
            page = 2
            while len(results) < max_results:
                if max_pages is not None and page > max_pages:
                    break
                if self.page_delay:
                    time.sleep(self.page_delay)
                nxt = self._get(page_url(page))
                if not nxt:
                    break
                new = [r for r in parse_listing(nxt) if r.sk not in seen]
                for r in new:
                    seen.add(r.sk)
                results.extend(new)
                if not new or not _has_next_page(nxt):
                    break
                page += 1
        return results[:max_results]

    def find_artist_slug(self, name: str) -> Optional[str]:
        """Discover an artist's canonical slug by keyword-searching their name.

        Returns the most common ``artist_slug`` among results whose display name
        contains the query — robust when ``slugify_artist`` guesses wrong.
        """
        hits = self.search(name, max_results=30, max_pages=1)
        low = name.lower()
        counts: Dict[str, int] = {}
        for r in hits:
            if r.artist_slug and r.artist and low in r.artist.lower():
                counts[r.artist_slug] = counts.get(r.artist_slug, 0) + 1
        if not counts:
            return None
        return max(counts, key=counts.get)

    def advanced_search(self, query: Optional[str] = None, *,
                        artist: Optional[str] = None,
                        filters: Optional[ArtveeFilter] = None,
                        sort_by: str = "relevance", descending: bool = False,
                        max_results: int = 30, scan_limit: int = 120,
                        max_pages: Optional[int] = None) -> List[ArtveeResult]:
        """Search then filter+sort on metadata — the advanced-search surface.

        Provide ``query`` (keyword) and/or ``artist`` (canonical artist page).
        ``scan_limit`` is how many raw results to pull *before* filtering (so a
        picky filter still has candidates to work with); ``max_results`` caps the
        filtered output.

        ``sort_by``: 'relevance' (source order) | 'year' | 'title' | 'artist' |
        'pixels' (SD resolution) | 'filesize'.
        """
        if not query and not artist:
            raise ValueError("advanced_search needs a query and/or an artist")

        if artist:
            pool = self.search_artist(artist, max_results=scan_limit, max_pages=max_pages)
            if query:
                ql = query.lower()
                pool = [r for r in pool if ql in r.title.lower()
                        or (r.category and ql in r.category.lower())]
        else:
            pool = self.search(query, max_results=scan_limit, max_pages=max_pages)

        flt = filters or ArtveeFilter()
        kept = [r for r in pool if flt.matches(r)]

        keymap = {
            "year": lambda r: (r.year is None, r.year or 0),
            "title": lambda r: r.title.lower(),
            "artist": lambda r: (r.artist or "").lower(),
            "pixels": lambda r: r.sd_pixels or 0,
            "filesize": lambda r: r.sd_filesize_mb or 0.0,
        }
        if sort_by in keymap:
            kept.sort(key=keymap[sort_by], reverse=descending)
        elif descending:
            kept.reverse()
        return kept[:max_results]

    # -- download -------------------------------------------------------- #
    def resolve_download(self, result: ArtveeResult, *, refresh: bool = False) -> Optional[str]:
        """Fetch the detail page and extract the presigned low-res (SDL) URL.

        Caches the URL on ``result.resolved_sdl_url``. Pass ``refresh=True`` to
        bypass the cache and re-parse a freshly-generated link (used to recover
        from a stale/expired presigned URL). Returns None if the page or link
        can't be found (e.g. a work with no free SDL tier).
        """
        if result.resolved_sdl_url and not refresh:
            return result.resolved_sdl_url
        page = self._get(result.detail_url)
        if not page:
            return None
        m = re.search(r'href="(https://mdl\.artvee\.com/sdl/[^"]+)"', page)
        if not m:
            # Fallback: any sdl link referencing this sk.
            m = re.search(rf'(https://mdl\.artvee\.com/sdl/{re.escape(result.sk)}[^"\s]+)', page)
        if not m:
            return None
        result.resolved_sdl_url = html.unescape(m.group(1))
        return result.resolved_sdl_url

    def _stream_to(self, url: str, out_path: Path) -> bool:
        """GET an image URL and stream it to ``out_path``. False on any failure
        (network error, non-image content-type, empty body)."""
        try:
            with self.client.stream("GET", url) as resp:
                resp.raise_for_status()
                if "image" not in resp.headers.get("content-type", ""):
                    return False
                with open(out_path, "wb") as fh:
                    for chunk in resp.iter_bytes(65536):
                        fh.write(chunk)
        except httpx.HTTPError:
            return False
        if out_path.stat().st_size == 0:
            out_path.unlink(missing_ok=True)
            return False
        return True

    def download(self, result: ArtveeResult, out_path, *, size: str = "sd") -> Optional[Path]:
        """Download an artwork to ``out_path``.

        ``size='sd'`` (default) resolves and downloads the presigned low-res JPEG;
        ``size='thumb'`` grabs the small CDN thumbnail (no detail fetch);
        ``size='preview'`` grabs the mid-size preview. Returns the written path,
        or None on failure. Never raises on a network error.
        """
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if size == "thumb":
            return out_path if self._stream_to(result.thumbnail_url, out_path) else None
        if size == "preview":
            return out_path if self._stream_to(result.preview_url, out_path) else None
        # size == "sd": presigned low-res. A stale/expired presigned link 403s —
        # re-resolve a fresh one and retry once before giving up.
        url = self.resolve_download(result)
        if url and self._stream_to(url, out_path):
            return out_path
        url = self.resolve_download(result, refresh=True)
        if url and self._stream_to(url, out_path):
            return out_path
        return None
