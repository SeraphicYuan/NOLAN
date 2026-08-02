"""Rawpixel search, collection routing, and bounded catalog crawling.

Rawpixel is two related sources for NOLAN:

* a high-recall live search provider over Free + Public Domain media; and
* a collection catalog whose descriptions/path tokens help route a query before
  item search.  Collections are hints, never a recall gate: callers should also
  run the broad media route.

The structured endpoint is the same endpoint documented by the Openverse
catalog. Rawpixel may put Cloudflare in front of it; that is surfaced as a
clear ``RawpixelAccessError`` rather than worked around. An authorised Chrome
session exposed over the local DevTools protocol can be used as the transport;
this preserves the real browser connection instead of replaying credentials.

The crawler is intentionally query/collection bounded.  Rawpixel's terms
require written permission for a comprehensive mirror; ``comprehensive=True``
therefore requires an explicit permission acknowledgement.
"""
from __future__ import annotations

import html
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlparse

import httpx

BASE = "https://www.rawpixel.com"
API = "https://www.rawpixel.com/api/v1/search"
_UA = "NOLAN-Rawpixel/1.0 (+collection-aware search)"
SORTS = frozenset({"curated", "popular", "new"})


class RawpixelAccessError(RuntimeError):
    """Rawpixel refused a request (normally its Cloudflare browser challenge)."""


@dataclass(frozen=True)
class RawpixelRoute:
    slug: str
    title: str
    path_tokens: tuple[str, ...]
    media_type: str = "image"
    description: str = ""
    url_path: str = "/search"
    parent_slug: Optional[str] = None
    collection_id: Optional[str] = None
    topics: tuple[str, ...] = ()

    @property
    def path(self) -> str:
        return "|".join(self.path_tokens)

    @property
    def url(self) -> str:
        return urljoin(BASE, self.url_path)

    def search_text(self) -> str:
        return " ".join((self.title, self.description, *self.topics)).casefold()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["path"] = self.path
        return d


# Stable top-level routes observed in Rawpixel's own navigation.  Sub-routes
# are learned from the collection/filter pages and stored alongside these.
TOP_ROUTES: Dict[str, RawpixelRoute] = {
    "images": RawpixelRoute(
        "images", "Images", ("1522",), "image",
        "Photos, transparent PNGs, vectors, illustrations, backgrounds, patterns and art.",
        "/search", topics=("photo", "illustration", "vector", "background", "pattern")),
    "videos": RawpixelRoute(
        "videos", "Videos", ("1604",), "video",
        "HD and 4K footage, transparent clips, GIFs, effects and live wallpapers.",
        "/videos", topics=("footage", "video", "motion", "gif", "live wallpaper")),
    "wallpapers": RawpixelRoute(
        "wallpapers", "Wallpapers", ("1636",), "image",
        "Mobile, HD desktop, aesthetic and live wallpapers.",
        "/wallpapers", topics=("wallpaper", "background", "desktop", "mobile")),
}

# Path-dependent choices read from Rawpixel's own Images and Videos navigation.
# These are maintained as collection-like routing records (title, description,
# exact parent+child path) and can be persisted into Visual Lab collections.
_IMAGE_FACETS = {
    "photos": ("search_tl-34", "Photography and photographic source images."),
    "transparent": ("search_tl-5", "Transparent PNG elements and cutouts."),
    "effects": ("search_tl-37", "Visual effects and compositing elements."),
    "stickers": ("search_tl-830", "PNG stickers, clipart and isolated design elements."),
    "vectors": ("search_tl-33", "Vector illustrations and scalable design artwork."),
    "wallpapers": ("search_tl-36", "Wallpaper images within the Images path."),
    "illustrations": ("search_tl-35", "Illustrations, drawings and graphic artwork."),
    "hd-wallpapers": ("search_tl-823", "High-definition desktop wallpapers."),
    "backgrounds": ("search_tl-834", "Background images and textures."),
    "patterns": ("search_tl-858", "Repeating patterns and decorative textures."),
    "styles": ("search_tl-865", "Images grouped by visual style."),
}
_VIDEO_FACETS = {
    "original-footage": ("search_tl-819", "Original stock footage and filmed scenes."),
    "transparent": ("search_tl-734", "Transparent video elements."),
    "effects": ("search_tl-735", "Motion effects and compositing clips."),
    "live-wallpapers": ("search_tl-736", "Live wallpaper videos."),
    "hd-wallpapers": ("search_tl-737", "HD video wallpapers."),
    "mockups": ("search_tl-826", "Animated and video mockups."),
    "stickers": ("search_tl-738", "Animated stickers and GIF-like elements."),
    "art-videos": ("search_tl-740", "Art-led motion and animated artwork."),
    "styles": ("search_tl-871", "Videos grouped by visual style."),
}


def _facet_routes() -> Dict[str, RawpixelRoute]:
    out: Dict[str, RawpixelRoute] = {}
    for parent_slug, facets in (("images", _IMAGE_FACETS), ("videos", _VIDEO_FACETS)):
        parent = TOP_ROUTES[parent_slug]
        for slug, (token, description) in facets.items():
            key = f"{parent_slug}-{slug}"
            out[key] = RawpixelRoute(
                slug=f"rawpixel-{key}", title=slug.replace("-", " ").title(),
                path_tokens=(*parent.path_tokens, token), media_type=parent.media_type,
                description=description, url_path=parent.url_path,
                parent_slug=parent_slug, topics=tuple(slug.split("-")))
    return out


FACET_ROUTES = _facet_routes()


@dataclass
class RawpixelResult:
    id: str
    title: str
    detail_url: str
    thumbnail_url: str
    preview_url: str
    width: Optional[int] = None
    height: Optional[int] = None
    creator: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    media_type: str = "image"
    image_type: Optional[str] = None
    tier: str = "free"
    license: str = "Rawpixel Free License"
    editorial_only: bool = False
    ai_generated: bool = False
    collection_slugs: List[str] = field(default_factory=list)
    primary_collection_slug: Optional[str] = None
    download_url: Optional[str] = None
    high_resolution_url: Optional[str] = None
    high_width: Optional[int] = None
    high_height: Optional[int] = None
    duration: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, [], {}, "")}


def _route_tag(route: RawpixelRoute) -> Optional[str]:
    """Translate a UI route to Rawpixel's current structured-search tag."""
    if route.slug == "wallpapers":
        return "$wallpapers"
    if not route.parent_slug:
        return None
    leaf = route.slug.removeprefix(f"rawpixel-{route.parent_slug}-")
    return "$" + leaf.replace("-", "") if leaf else None


def build_search_params(*, query: str = "", page: int = 1,
                        route: RawpixelRoute = TOP_ROUTES["images"],
                        sort: str = "curated", rights_tag: Optional[str] = None,
                        free_and_public_domain: bool = True) -> Dict[str, Any]:
    """Build Rawpixel's current same-origin structured search request.

    Free and Public Domain are separate current-UI requests (``$free`` and
    ``$publicdomain``). ``free_and_public_domain`` remains for compatibility;
    callers wanting the union issue both rights-tagged requests and merge them.
    """
    if sort not in SORTS:
        raise ValueError(f"unknown Rawpixel sort {sort!r}; choose {sorted(SORTS)}")
    p: Dict[str, Any] = {
        "image_type": "video" if route.media_type == "video" else "image",
        "lang": "en", "page": max(1, int(page)),
        "published_status": "published", "show_creative_brushes": "false",
        "sort": sort,
    }
    if query.strip():
        p["keys"] = query.strip()
        p["curated_tag"] = query.strip()
    tags = [x for x in (rights_tag, _route_tag(route)) if x]
    if tags:
        p["tags"] = ",".join(tags)
    return p


def build_web_search_url(query: str, *, page: int = 1,
                         route: RawpixelRoute = TOP_ROUTES["images"],
                         sort: str = "curated") -> str:
    """Human-reviewable URL equivalent of an API search."""
    stem = route.url_path.rstrip("/")
    if stem == "/search" and query.strip():
        stem += "/" + quote(query.strip(), safe="")
    params = {"page": max(1, int(page)), "path": route.path, "sort": sort}
    # The UI exposes Free and Public Domain as separate tokens; the exact union
    # is an API feature (`freecc0=1`). This review URL therefore shows the broad
    # route rather than inventing a non-existent UI token.
    return f"{BASE}{stem}?{urlencode(params)}"


def _bool(d: Dict[str, Any], *names: str) -> bool:
    for n in names:
        if n in d:
            v = d[n]
            if isinstance(v, str):
                return v.strip().lower() in {"1", "true", "yes", "on"}
            return bool(v)
    return False


def _int(v) -> Optional[int]:
    try:
        return int(str(v).replace(",", "")) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _float(v) -> Optional[float]:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _plain(v: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(v or "")))).strip()


def _collections(d: Dict[str, Any]) -> List[str]:
    values: List[Any] = []
    for key in ("collections", "collection", "boards", "board", "galleries", "categories"):
        v = d.get(key)
        if isinstance(v, list):
            values.extend(v)
        elif v:
            values.append(v)
    out: List[str] = []
    for v in values:
        if isinstance(v, dict):
            v = v.get("slug") or v.get("name") or v.get("title") or v.get("id")
        s = re.sub(r"[^a-z0-9]+", "-", _plain(v).casefold()).strip("-")
        if s and s not in out:
            out.append(s)
    return out


def _url_value(d: Dict[str, Any], names: Sequence[str]) -> Optional[str]:
    """First direct or nested media URL under a known field name."""
    for name in names:
        v = d.get(name)
        if isinstance(v, str) and v.startswith(("http://", "https://")):
            return v
        if isinstance(v, dict):
            for key in ("url", "src", "download", "file"):
                u = v.get(key)
                if isinstance(u, str) and u.startswith(("http://", "https://")):
                    return u
    files = d.get("files") or d.get("downloads")
    if isinstance(files, list):
        for item in files:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or item.get("quality") or item.get("type") or "").lower()
            if any(n.lower().replace("video_", "") in label for n in names):
                u = item.get("url") or item.get("download") or item.get("src")
                if isinstance(u, str) and u.startswith(("http://", "https://")):
                    return u
    return None


def _download_choices(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    choices: List[Dict[str, Any]] = []
    for group in metadata.get("download_options") or []:
        if isinstance(group, dict):
            choices.extend(x for x in group.get("choices") or [] if isinstance(x, dict))
    return choices


def _download_url(choice: Optional[Dict[str, Any]]) -> Optional[str]:
    if not choice:
        return None
    value = choice.get("apiUrl") or choice.get("url")
    if not value:
        return None
    return urljoin(f"{BASE}/api/v1/", str(value))


def parse_result(d: Dict[str, Any], *, expected_media_type: Optional[str] = None) -> Optional[RawpixelResult]:
    rid = d.get("id") or d.get("nid")
    detail = d.get("url") or d.get("pinterest_share_url") or ""
    if not rid or not detail:
        return None
    detail = urljoin(BASE, str(detail))
    route_type = "video" if "/video/" in urlparse(detail).path else "image"
    declared = str(d.get("media_type") or d.get("type") or d.get("view_mode") or "").lower()
    media_type = "video" if (route_type == "video" or "video" in declared) else "image"
    if expected_media_type and media_type != expected_media_type:
        return None

    metadata = d.get("metadata") if isinstance(d.get("metadata"), dict) else {}
    source_license = str(metadata.get("license") or d.get("license") or "").casefold()
    is_pd = source_license in {"cc0", "publicdomain", "public_domain"} or _bool(
        d, "freecc0", "public_domain", "cc0")
    is_free = source_license == "free" or _bool(d, "free_image", "free", "free_or_cc0")
    tier = "public_domain" if is_pd else ("free" if is_free else "premium")
    license_text = ("CC0 / Public Domain" if is_pd else
                    "Rawpixel Free License" if is_free else "Rawpixel Premium License")
    live_tags = metadata.get("popular_keywords") or []
    tags = ([_plain(x) for x in live_tags if _plain(x)] if isinstance(live_tags, list) else
            [_plain(x) for x in str(d.get("keywords_raw") or "").split(",") if _plain(x)])
    description = _plain(
        metadata.get("description_text") or metadata.get("description") or
        metadata.get("image_alt") or d.get("image_alt") or d.get("description") or
        d.get("pinterest_description"))
    title = _plain(
        metadata.get("title") or d.get("image_title") or d.get("title") or description
    ) or f"Rawpixel {rid}"
    thumb = (d.get("image_400") or d.get("google_teaser") or d.get("image") or
             d.get("thumbnail") or d.get("poster") or "")
    preview = (d.get("image_1600") or d.get("image_1400") or d.get("image_1200") or
               d.get("image_opengraph") or d.get("pinterestImage") or d.get("preview") or thumb)
    choices = _download_choices(metadata)
    permitted = [x for x in choices if not _bool(x, "isPremium")]
    # API derivatives are non-watermarked unless the URL explicitly carries Rawpixel's mark.
    if media_type == "video":
        download = _url_value(d, ("video_sd", "sd", "mp4", "download_url", "download"))
        high = _url_value(d, ("video_4k", "4k", "video_hd", "hd", "mov"))
    else:
        download = _download_url(permitted[0] if permitted else None)
        download = download or d.get("download_url") or d.get("download") or preview
        high = _download_url(permitted[-1] if permitted else None)
        high = high or d.get("high_resolution_url") or d.get("image_2500") or d.get("image_2000")
    memberships = _collections(d)
    artists = metadata.get("artist_names") or d.get("artist_names") or d.get("artists") or d.get("creator")
    creator = ", ".join(_plain(x) for x in artists) if isinstance(artists, list) else _plain(artists)
    return RawpixelResult(
        id=str(rid), title=title, detail_url=detail,
        thumbnail_url=str(thumb or preview), preview_url=str(preview or thumb),
        width=_int(d.get("original_width") or d.get("width")),
        height=_int(d.get("original_height") or d.get("height")),
        creator=creator or None,
        description=description or None, tags=tags, media_type=media_type,
        image_type=_plain(metadata.get("image_type") or d.get("image_type") or
                          d.get("image_type_machine_name")) or None,
        tier=tier, license=license_text,
        editorial_only=_bool(metadata, "editorial_only", "editorial", "isEditorialOnly") or
                       _bool(d, "editorial_only", "editorial"),
        ai_generated=_bool(metadata, "isAIGenerated", "ai_generated", "is_ai") or
                     _bool(d, "ai_generated", "is_ai", "generated_ai"),
        collection_slugs=memberships,
        primary_collection_slug=(memberships[0] if memberships else None),
        download_url=str(download) if download else None,
        high_resolution_url=str(high) if high else None,
        high_width=_int(d.get("high_width") or d.get("original_width")),
        high_height=_int(d.get("high_height") or d.get("original_height")),
        duration=_float(d.get("duration")), raw=d)


def parse_search_payload(payload: Dict[str, Any], *, expected_media_type: Optional[str] = None,
                         allowed_tiers: Sequence[str] = ("free", "public_domain")) -> List[RawpixelResult]:
    """Normalise one API page, retaining AI/editorial flags without filtering them."""
    rows = payload.get("results") or payload.get("items") or []
    allowed = set(allowed_tiers)
    out, seen = [], set()
    for d in rows if isinstance(rows, list) else []:
        if not isinstance(d, dict):
            continue
        r = parse_result(d, expected_media_type=expected_media_type)
        if r and r.tier in allowed and r.id not in seen:
            seen.add(r.id)
            out.append(r)
    return out


_CATEGORY_LINK = re.compile(
    r'<a[^>]+href=["\'](?P<href>[^"\']*(?:/category/\d+/|group_tl=)[^"\']*)["\'][^>]*>(?P<body>.*?)</a>',
    re.I | re.S)


def parse_collection_page(page_html: str, *, parent: RawpixelRoute = TOP_ROUTES["images"]) -> List[RawpixelRoute]:
    """Parse collection/category cards and their source-authored descriptions.

    The parser also accepts hydration JSON: links/titles are still present as
    strings inside the document even when the visual card is client-rendered.
    """
    out: Dict[str, RawpixelRoute] = {}
    for m in _CATEGORY_LINK.finditer(page_html or ""):
        href = html.unescape(m.group("href")).replace("\\/", "/")
        title = _plain(m.group("body"))
        cm = re.search(r"/category/(\d+)/([^/?#]+)", href)
        gm = re.search(r"group_tl[=-](\d+)", href)
        ident = (cm.group(1) if cm else gm.group(1) if gm else None)
        slug = (cm.group(2) if cm else re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-"))
        if not ident or not slug or not title:
            continue
        # Text directly after the anchor is often the card blurb. Bound it at
        # the next anchor/card so one collection cannot consume the page.
        tail = page_html[m.end():m.end() + 700]
        desc = _plain(re.split(r"<a\b|class=[\"'](?:card|collection)", tail, maxsplit=1,
                               flags=re.I)[0])[:500]
        query_path = parse_qs(urlparse(urljoin(BASE, href)).query).get("path", [""])[0]
        tokens = tuple(x for x in query_path.split("|") if x) or parent.path_tokens
        out[slug] = RawpixelRoute(
            slug=f"rawpixel-{slug}", title=title, path_tokens=tokens,
            media_type=parent.media_type, description=desc, url_path=urlparse(urljoin(BASE, href)).path,
            parent_slug=parent.slug, collection_id=ident)
    return list(out.values())


def rank_routes(query: str, routes: Iterable[RawpixelRoute], *, media_type: str = "image",
                limit: int = 3) -> List[RawpixelRoute]:
    """Cheap text routing over collection descriptions; broad route is handled separately."""
    toks = {t for t in re.findall(r"[a-z0-9]+", query.casefold()) if len(t) > 2}
    scored = []
    for r in routes:
        if r.media_type != media_type:
            continue
        text = r.search_text()
        hit = sum(3 if t in r.title.casefold() else 1 for t in toks if t in text)
        if hit:
            scored.append((hit, len(r.path_tokens), r))
    scored.sort(key=lambda x: (-x[0], -x[1], x[2].title.casefold()))
    return [x[2] for x in scored[:limit]]


class RawpixelClient:
    def __init__(self, *, transport: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
                 timeout: float = 30.0, page_delay: float = 0.35,
                 collection_routes: Iterable[RawpixelRoute] = (),
                 cookie: Optional[str] = None, user_agent: Optional[str] = None,
                 cdp_url: Optional[str] = None):
        self.transport = transport
        self.timeout = timeout
        self.page_delay = max(0.0, page_delay)
        self.cookie = cookie if cookie is not None else os.getenv("RAWPIXEL_COOKIE", "")
        self.user_agent = user_agent or os.getenv("RAWPIXEL_USER_AGENT", "") or _UA
        self.cdp_url = cdp_url if cdp_url is not None else os.getenv("RAWPIXEL_CDP_URL", "")
        supplied = list(collection_routes)
        self.collection_routes = supplied if supplied else list(FACET_ROUTES.values())

    def _request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if self.transport:
            return self.transport(API, params)
        if self.cdp_url:
            return self._request_via_chrome(params)
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        if self.cookie:
            headers["Cookie"] = self.cookie
        with httpx.Client(headers=headers,
                          follow_redirects=True, timeout=self.timeout) as client:
            response = client.get(API, params=params)
        ctype = response.headers.get("content-type", "")
        if response.status_code in (403, 429) or "application/json" not in ctype:
            raise RawpixelAccessError(
                f"Rawpixel API returned {response.status_code} {ctype!r}; use an authorised "
                "browser/partner transport rather than bypassing its challenge")
        response.raise_for_status()
        return response.json()

    def _request_via_chrome(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Navigate the API in the user's authorised Chrome CDP session.

        A fresh tab is opened in Chrome's existing default context, so Chrome
        supplies its own cookies and browser/TLS fingerprint. Only that tab is
        closed; disconnecting Playwright never closes the user's browser.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - environment diagnostic
            raise RawpixelAccessError(
                "RAWPIXEL_CDP_URL is set but Playwright is not installed") from exc

        request_url = f"{API}?{urlencode(params)}"
        pw = sync_playwright().start()
        page = None
        try:
            browser = pw.chromium.connect_over_cdp(self.cdp_url, timeout=self.timeout * 1000)
            if not browser.contexts:
                raise RawpixelAccessError("Chrome CDP has no reusable browser context")
            page = browser.contexts[0].new_page()
            response = page.goto(
                request_url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
            status = response.status if response else 0
            body = page.locator("body").inner_text(timeout=self.timeout * 1000).strip()
            if status in (403, 429) or not body:
                raise RawpixelAccessError(
                    f"Rawpixel API returned {status} through the authorised Chrome session")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                raise RawpixelAccessError(
                    f"Rawpixel returned non-JSON content through Chrome (HTTP {status})") from exc
            if not isinstance(payload, dict):
                raise RawpixelAccessError("Rawpixel Chrome response was not a JSON object")
            return payload
        except RawpixelAccessError:
            raise
        except Exception as exc:
            raise RawpixelAccessError(
                f"Could not use authorised Chrome at {self.cdp_url}: {exc}") from exc
        finally:
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass
            pw.stop()

    def search_route(self, query: str, *, route: RawpixelRoute, page: int = 1,
                     sort: str = "curated") -> tuple[List[RawpixelResult], Optional[int]]:
        rows: List[RawpixelResult] = []
        seen = set()
        totals: List[int] = []
        # Rawpixel's current UI implements the requested union as two explicit
        # searches. Keep this split so premium records cannot leak into either.
        for rights_tag in ("$free", "$publicdomain"):
            payload = self._request(build_search_params(
                query=query, page=page, route=route, sort=sort, rights_tag=rights_tag))
            total = _int(payload.get("total"))
            if total is not None:
                totals.append(total)
            for result in parse_search_payload(payload, expected_media_type=route.media_type):
                if result.id not in seen:
                    seen.add(result.id)
                    rows.append(result)
        return rows, (sum(totals) if totals else None)

    def search(self, query: str, *, media_type: str = "image", max_results: int = 10,
               sort: str = "curated", collection_aware: bool = True) -> List[RawpixelResult]:
        broad = TOP_ROUTES["videos" if media_type == "video" else "images"]
        routes = ([*rank_routes(query, self.collection_routes, media_type=media_type), broad]
                  if collection_aware else [broad])
        buckets: List[List[RawpixelResult]] = []
        for route in routes:
            rows, _ = self.search_route(query, route=route, sort=sort)
            for r in rows:
                if route is not broad and not r.primary_collection_slug:
                    r.primary_collection_slug = route.slug
                    r.collection_slugs.insert(0, route.slug)
            buckets.append(rows)
        # Interleave routed and broad results. A strong collection should guide
        # the search, not monopolise it; the broad safety route always gets a
        # chance to contribute before truncation.
        out, seen = [], set()
        while any(buckets) and len(out) < max_results:
            for bucket in buckets:
                while bucket and bucket[0].id in seen:
                    bucket.pop(0)
                if bucket and len(out) < max_results:
                    r = bucket.pop(0)
                    seen.add(r.id)
                    out.append(r)
        return out[:max_results]

    def crawl(self, *, query: str = "", route: RawpixelRoute = TOP_ROUTES["images"],
              max_pages: Optional[int] = 1, sort: str = "curated",
              comprehensive: bool = False, written_permission: bool = False) -> Iterator[RawpixelResult]:
        """Walk a bounded query/collection, resumable by the caller's page cursor."""
        if comprehensive and not written_permission:
            raise PermissionError(
                "Rawpixel requires express written permission for a comprehensive database; "
                "set written_permission=True only after obtaining it")
        page, seen = 1, set()
        while max_pages is None or page <= max_pages:
            rows, total = self.search_route(query, route=route, page=page, sort=sort)
            if not rows:
                return
            for r in rows:
                if r.id not in seen:
                    seen.add(r.id)
                    yield r
            if total is not None and len(seen) >= total:
                return
            page += 1
            if self.page_delay:
                time.sleep(self.page_delay)
