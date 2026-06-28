"""Image search providers for NOLAN."""

import json
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

import httpx


# --- Free-tier rate limits for keyed stock providers -------------------------
# (max_requests, window_seconds) per *account*. Providers that share one account
# (e.g. Pexels image + video use the same key) share a single bucket.
_RATE_LIMITS = {
    "unsplash": (50, 3600),    # 50 / hour  (tightest)
    "pexels": (200, 3600),     # 200 / hour (+ 20k / month, not tracked here)
    "pixabay": (100, 60),      # 100 / 60s  (burst)
}
# provider name -> rate-limit bucket (account). Unlisted providers are unthrottled.
_RATE_BUCKET = {
    "unsplash": "unsplash",
    "pexels": "pexels", "pexels_video": "pexels",
    "pixabay": "pixabay", "pixabay_video": "pixabay",
}
# Providers with a tight budget: queried only as a fallback tier in the default
# fan-out, after cheaper/keyless providers come up short. See _tier_sources.
_DEFER_LAST = {"unsplash"}


class _RateLimiter:
    """Thread-safe sliding-window limiter shared across providers and clients.

    Tracks request timestamps per account bucket and honors a cooldown set when
    a provider returns HTTP 429. Lets the fan-out skip a tapped-out provider
    instead of hammering (and getting blocked by) the API. A single module-level
    instance is shared, since callers create a fresh ImageSearchClient per request.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._hits: Dict[str, list] = {}
        self._cooldown: Dict[str, float] = {}

    def allow(self, name: str) -> bool:
        """Return True (and record a hit) if `name` is under its limit, else False."""
        bucket = _RATE_BUCKET.get(name)
        if not bucket:
            return True  # unthrottled provider
        limit, window = _RATE_LIMITS[bucket]
        now = time.monotonic()
        with self._lock:
            if now < self._cooldown.get(bucket, 0):
                return False
            hits = [t for t in self._hits.get(bucket, []) if now - t < window]
            if len(hits) >= limit:
                self._hits[bucket] = hits
                return False
            hits.append(now)
            self._hits[bucket] = hits
            return True

    def record(self, name: str) -> None:
        """Record a hit unconditionally (for explicit single-source calls)."""
        bucket = _RATE_BUCKET.get(name)
        if not bucket:
            return
        now = time.monotonic()
        _, window = _RATE_LIMITS[bucket]
        with self._lock:
            hits = [t for t in self._hits.get(bucket, []) if now - t < window]
            hits.append(now)
            self._hits[bucket] = hits

    def penalize(self, name: str) -> None:
        """Cool a bucket down after a 429 (capped at 5 min for hourly limits)."""
        bucket = _RATE_BUCKET.get(name)
        if not bucket:
            return
        _, window = _RATE_LIMITS[bucket]
        with self._lock:
            self._cooldown[bucket] = time.monotonic() + min(window, 300)


# Module-level singleton — shared across all ImageSearchClient instances.
_RATE_LIMITER = _RateLimiter()


@dataclass
class ImageSearchResult:
    """Unified search result for an image or a video clip."""
    url: str
    thumbnail_url: Optional[str] = None
    title: Optional[str] = None
    source: Optional[str] = None  # Provider name
    source_url: Optional[str] = None  # Original page URL
    width: Optional[int] = None
    height: Optional[int] = None
    photographer: Optional[str] = None
    license: Optional[str] = None
    media_type: str = "image"  # "image" | "video"
    duration: Optional[float] = None  # video length in seconds (if known)
    preview_image_url: Optional[str] = None  # poster/still for a video (for scoring/preview)
    ref: Optional[str] = None  # provider-internal handle for lazy resolution (e.g. IA id)
    score: Optional[float] = None  # Vision model relevance score (0-10)
    score_reason: Optional[str] = None  # Explanation for the score
    scored_by: Optional[str] = None  # Which vision model scored this
    quality_score: Optional[float] = None  # Image quality score (0-10)
    quality_reason: Optional[str] = None  # Explanation for quality score

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    def combined_score(self) -> float:
        """Get combined score (relevance + quality tiebreaker).

        Returns relevance score + (quality_score * 0.01) for tiebreaking.
        """
        relevance = self.score or 0.0
        quality = (self.quality_score or 0.0) * 0.01  # Quality as tiebreaker
        return relevance + quality


class ImageProvider(ABC):
    """Base class for image search providers."""

    name: str = "base"

    @abstractmethod
    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        """Search for images.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return.

        Returns:
            List of ImageSearchResult objects.
        """
        pass

    def is_available(self) -> bool:
        """Check if provider is available (has required credentials)."""
        return True

    def resolve(self, result: "ImageSearchResult") -> Optional["ImageSearchResult"]:
        """Resolve a lazily-returned result into a fully-usable one.

        Default: already usable. Video providers that defer the expensive
        per-item lookup (mp4 manifest fetch) override this and fill `url`/`duration`
        for the chosen result only. Return None if it can't be resolved.
        """
        return result


class DDGSProvider(ImageProvider):
    """DuckDuckGo image search provider using ddgs."""

    name = "ddgs"

    def __init__(self):
        """Initialize DDGS provider."""
        try:
            from ddgs import DDGS
            self._ddgs_class = DDGS
            self._available = True
        except ImportError:
            # Fallback to old package name
            try:
                from duckduckgo_search import DDGS
                self._ddgs_class = DDGS
                self._available = True
            except ImportError:
                self._available = False

    def is_available(self) -> bool:
        """Check if duckduckgo-search is installed."""
        return self._available

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        """Search DuckDuckGo for images.

        Args:
            query: Search query string.
            max_results: Maximum number of results.

        Returns:
            List of ImageSearchResult objects.
        """
        if not self._available:
            raise RuntimeError("duckduckgo-search package not installed")

        results = []
        with self._ddgs_class() as ddgs:
            for r in ddgs.images(query, max_results=max_results):
                results.append(ImageSearchResult(
                    url=r.get("image", ""),
                    thumbnail_url=r.get("thumbnail", ""),
                    title=r.get("title", ""),
                    source=self.name,
                    source_url=r.get("url", ""),
                    width=r.get("width"),
                    height=r.get("height"),
                ))
        return results


class PexelsProvider(ImageProvider):
    """Pexels API image search provider."""

    name = "pexels"
    BASE_URL = "https://api.pexels.com/v1"

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Pexels provider.

        Args:
            api_key: Pexels API key. Get one at https://www.pexels.com/api/
        """
        self.api_key = api_key

    def is_available(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        """Search Pexels for images.

        Args:
            query: Search query string.
            max_results: Maximum number of results.

        Returns:
            List of ImageSearchResult objects.
        """
        if not self.api_key:
            raise RuntimeError("Pexels API key not configured")

        headers = {"Authorization": self.api_key}
        params = {"query": query, "per_page": min(max_results, 80)}

        with httpx.Client() as client:
            response = client.get(
                f"{self.BASE_URL}/search",
                headers=headers,
                params=params,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for photo in data.get("photos", []):
            results.append(ImageSearchResult(
                url=photo.get("src", {}).get("original", ""),
                thumbnail_url=photo.get("src", {}).get("medium", ""),
                title=photo.get("alt", ""),
                source=self.name,
                source_url=photo.get("url", ""),
                width=photo.get("width"),
                height=photo.get("height"),
                photographer=photo.get("photographer", ""),
                license="Pexels License (free for commercial use)",
            ))
        return results


class PexelsVideoProvider(ImageProvider):
    """Pexels API VIDEO search (free stock video). Needs PEXELS_API_KEY."""

    name = "pexels_video"
    BASE_URL = "https://api.pexels.com/videos"
    media_type = "video"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        if not self.api_key:
            raise RuntimeError("Pexels API key not configured")
        headers = {"Authorization": self.api_key}
        params = {"query": query, "per_page": min(max_results, 80)}
        with httpx.Client() as client:
            resp = client.get(f"{self.BASE_URL}/search", headers=headers, params=params, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
        results = []
        for vid in data.get("videos", []):
            files = vid.get("video_files", []) or []
            # Prefer an HD-ish mp4 that isn't the huge 4K master.
            mp4s = [f for f in files if f.get("file_type") == "video/mp4" and f.get("link")]
            mp4s.sort(key=lambda f: (f.get("height") or 0))
            if not mp4s:
                continue
            chosen = next((f for f in mp4s if (f.get("height") or 0) >= 720), mp4s[-1])
            results.append(ImageSearchResult(
                url=chosen["link"],
                thumbnail_url=vid.get("image"),
                preview_image_url=vid.get("image"),
                title=(vid.get("user", {}) or {}).get("name", "Pexels video"),
                source=self.name,
                source_url=vid.get("url"),
                width=chosen.get("width"), height=chosen.get("height"),
                photographer=(vid.get("user", {}) or {}).get("name"),
                media_type="video",
                duration=vid.get("duration"),
                license="Pexels License (free for commercial use)",
            ))
        return results


class PixabayVideoProvider(ImageProvider):
    """Pixabay API VIDEO search (free stock video). Needs PIXABAY_API_KEY."""

    name = "pixabay_video"
    BASE_URL = "https://pixabay.com/api/videos/"
    media_type = "video"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        if not self.api_key:
            raise RuntimeError("Pixabay API key not configured")
        params = {"key": self.api_key, "q": query, "per_page": min(max(max_results, 3), 200)}
        with httpx.Client() as client:
            resp = client.get(self.BASE_URL, params=params, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
        results = []
        for hit in data.get("hits", []):
            streams = hit.get("videos", {}) or {}
            stream = streams.get("medium") or streams.get("large") or streams.get("small") or {}
            if not stream.get("url"):
                continue
            results.append(ImageSearchResult(
                url=stream["url"],
                thumbnail_url=stream.get("thumbnail"),
                preview_image_url=stream.get("thumbnail"),
                title=hit.get("tags", "Pixabay video"),
                source=self.name,
                source_url=hit.get("pageURL"),
                width=stream.get("width"), height=stream.get("height"),
                photographer=hit.get("user"),
                media_type="video",
                duration=hit.get("duration"),
                license="Pixabay License (free for commercial use)",
            ))
        return results


class PixabayProvider(ImageProvider):
    """Pixabay API image search provider."""

    name = "pixabay"
    BASE_URL = "https://pixabay.com/api/"

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Pixabay provider.

        Args:
            api_key: Pixabay API key. Get one at https://pixabay.com/api/docs/
        """
        self.api_key = api_key

    def is_available(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        """Search Pixabay for images.

        Args:
            query: Search query string.
            max_results: Maximum number of results.

        Returns:
            List of ImageSearchResult objects.
        """
        if not self.api_key:
            raise RuntimeError("Pixabay API key not configured")

        params = {
            "key": self.api_key,
            "q": query,
            "per_page": min(max_results, 200),
            "image_type": "photo",
        }

        with httpx.Client() as client:
            response = client.get(
                self.BASE_URL,
                params=params,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for hit in data.get("hits", []):
            results.append(ImageSearchResult(
                url=hit.get("largeImageURL", ""),
                thumbnail_url=hit.get("previewURL", ""),
                title=hit.get("tags", ""),
                source=self.name,
                source_url=hit.get("pageURL", ""),
                width=hit.get("imageWidth"),
                height=hit.get("imageHeight"),
                photographer=hit.get("user", ""),
                license="Pixabay License (free for commercial use)",
            ))
        return results


class WikimediaCommonsProvider(ImageProvider):
    """Wikimedia Commons image search provider."""

    name = "wikimedia"
    BASE_URL = "https://commons.wikimedia.org/w/api.php"

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        """Search Wikimedia Commons for images.

        Args:
            query: Search query string.
            max_results: Maximum number of results.

        Returns:
            List of ImageSearchResult objects.
        """
        # Search for files matching query
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrnamespace": "6",  # File namespace
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrlimit": min(max_results, 50),
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "iiurlwidth": 800,  # Get thumbnail
        }

        headers = {
            "User-Agent": "NOLAN-VideoEssayTool/1.0 (https://github.com/nolan; contact@example.com)"
        }

        with httpx.Client() as client:
            response = client.get(
                self.BASE_URL,
                params=params,
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()

        results = []
        pages = data.get("query", {}).get("pages", {})

        for page_id, page in pages.items():
            if page_id == "-1":
                continue

            imageinfo = page.get("imageinfo", [{}])[0]
            extmeta = imageinfo.get("extmetadata", {})

            # Get artist/photographer
            artist = extmeta.get("Artist", {}).get("value", "")
            # Strip HTML tags from artist
            if "<" in artist:
                import re
                artist = re.sub(r'<[^>]+>', '', artist).strip()

            # Get license
            license_info = extmeta.get("LicenseShortName", {}).get("value", "")

            results.append(ImageSearchResult(
                url=imageinfo.get("url", ""),
                thumbnail_url=imageinfo.get("thumburl", ""),
                title=page.get("title", "").replace("File:", ""),
                source=self.name,
                source_url=imageinfo.get("descriptionurl", ""),
                width=imageinfo.get("width"),
                height=imageinfo.get("height"),
                photographer=artist,
                license=license_info or "Wikimedia Commons",
            ))

        return results


class SmithsonianProvider(ImageProvider):
    """Smithsonian Open Access image search provider."""

    name = "smithsonian"
    BASE_URL = "https://api.si.edu/openaccess/api/v1.0/search"

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Smithsonian provider.

        Args:
            api_key: Smithsonian API key from api.data.gov
        """
        self.api_key = api_key

    def is_available(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        """Search Smithsonian Open Access for images.

        Args:
            query: Search query string.
            max_results: Maximum number of results.

        Returns:
            List of ImageSearchResult objects.
        """
        if not self.api_key:
            raise RuntimeError("Smithsonian API key not configured")

        params = {
            "api_key": self.api_key,
            "q": query,
            "rows": min(max_results, 100),
            "online_media_type": "Images",
        }

        with httpx.Client() as client:
            response = client.get(
                self.BASE_URL,
                params=params,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()

        results = []
        rows = data.get("response", {}).get("rows", [])

        for row in rows:
            content = row.get("content", {})
            desc = content.get("descriptiveNonRepeating", {})
            indexed = content.get("indexedStructured", {})

            # Get image URL from online_media
            online_media = desc.get("online_media", {}).get("media", [])
            if not online_media:
                continue

            media = online_media[0]
            image_url = media.get("content", "")
            thumbnail_url = media.get("thumbnail", "")

            # Get dimensions if available
            width = None
            height = None
            resources = media.get("resources", [])
            if resources:
                # Get largest image
                for res in resources:
                    if res.get("width"):
                        width = res.get("width")
                        height = res.get("height")

            results.append(ImageSearchResult(
                url=image_url,
                thumbnail_url=thumbnail_url,
                title=desc.get("title", {}).get("content", ""),
                source=self.name,
                source_url=desc.get("record_link", ""),
                width=width,
                height=height,
                photographer=indexed.get("name", [""])[0] if indexed.get("name") else "",
                license="CC0 (Public Domain)",
            ))

        return results


class LibraryOfCongressProvider(ImageProvider):
    """Library of Congress image search provider."""

    name = "loc"
    BASE_URL = "https://www.loc.gov/pictures/search/"

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        """Search Library of Congress Prints & Photographs for images.

        Args:
            query: Search query string.
            max_results: Maximum number of results.

        Returns:
            List of ImageSearchResult objects.
        """
        params = {
            "q": query,
            "fo": "json",
            "c": min(max_results, 100),
            "sp": 1,
        }

        headers = {
            "User-Agent": "NOLAN-VideoEssayTool/1.0"
        }

        with httpx.Client() as client:
            response = client.get(
                self.BASE_URL,
                params=params,
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()

        results = []
        items = data.get("results", [])

        for item in items:
            # Get image URLs
            image_info = item.get("image", {})
            # LoC provides multiple sizes: thumb, small, medium, large, full
            image_url = image_info.get("full", "") or image_info.get("large", "") or image_info.get("medium", "")
            thumbnail_url = image_info.get("thumb", "") or image_info.get("small", "")

            # Parse dimensions from image URL if available
            width = None
            height = None

            results.append(ImageSearchResult(
                url=image_url,
                thumbnail_url=thumbnail_url,
                title=item.get("title", ""),
                source=self.name,
                source_url=item.get("links", {}).get("item", ""),
                width=width,
                height=height,
                photographer=item.get("creator", ""),
                license="Public Domain (Library of Congress)",
            ))

        return results


class InternetArchiveProvider(ImageProvider):
    """Internet Archive (archive.org) — keyless archival VIDEO search.

    Best fit for historical/archival documentary footage. Searches movies,
    then resolves a downloadable mp4 per item via the metadata API.
    """

    name = "archive"
    SEARCH_URL = "https://archive.org/advancedsearch.php"
    META_URL = "https://archive.org/metadata"
    media_type = "video"

    def is_available(self) -> bool:
        return True  # no key required

    def _pick_mp4(self, identifier: str, client: "httpx.Client") -> Optional[Dict[str, Any]]:
        """Resolve a playable mp4 file + duration for an item."""
        try:
            meta = client.get(f"{self.META_URL}/{identifier}", timeout=20.0).json()
        except Exception:
            return None
        files = meta.get("files", []) or []
        mp4s = [f for f in files if str(f.get("name", "")).lower().endswith(".mp4")]
        if not mp4s:
            return None
        # Prefer a reasonably-sized h.264 derivative (not the largest master).
        def size(f):
            try:
                return int(f.get("size", 0))
            except (TypeError, ValueError):
                return 0
        mp4s.sort(key=size)
        chosen = mp4s[len(mp4s) // 2] if len(mp4s) > 2 else mp4s[0]
        dur = None
        try:
            dur = float(chosen.get("length")) if chosen.get("length") else None
        except (TypeError, ValueError):
            # length can be "MM:SS"
            ls = str(chosen.get("length", ""))
            if ":" in ls:
                parts = [float(p) for p in ls.split(":")]
                dur = sum(p * 60 ** i for i, p in enumerate(reversed(parts)))
        return {"name": chosen["name"], "duration": dur}

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        """Lazy search: returns candidates with posters (enough to vision-score) but
        does NOT fetch the per-item mp4 manifest. Call resolve() on the winner only."""
        params = {
            "q": f'({query}) AND mediatype:(movies)',
            "fl[]": ["identifier", "title", "year", "licenseurl"],
            "rows": min(max_results, 20),
            "page": 1,
            "output": "json",
            "sort[]": "downloads desc",
        }
        headers = {"User-Agent": "NOLAN-VideoEssayTool/1.0"}
        results: List[ImageSearchResult] = []
        try:
            with httpx.Client() as client:
                resp = client.get(self.SEARCH_URL, params=params, headers=headers, timeout=30.0)
                resp.raise_for_status()
                docs = resp.json().get("response", {}).get("docs", [])
        except Exception:
            return results
        for doc in docs[:max_results]:
            ident = doc.get("identifier")
            if not ident:
                continue
            results.append(ImageSearchResult(
                url="",  # deferred — resolved for the winner via resolve()
                ref=ident,
                thumbnail_url=f"https://archive.org/services/img/{ident}",
                preview_image_url=f"https://archive.org/services/img/{ident}",
                title=doc.get("title", ident),
                source=self.name,
                source_url=f"https://archive.org/details/{ident}",
                media_type="video",
                license=doc.get("licenseurl") or "Internet Archive (see item page)",
            ))
        return results

    def resolve(self, result):
        if result.url or not result.ref:
            return result
        try:
            with httpx.Client(headers={"User-Agent": "NOLAN-VideoEssayTool/1.0"}) as client:
                picked = self._pick_mp4(result.ref, client)
        except Exception:
            return None
        if not picked:
            return None
        result.url = f"https://archive.org/download/{result.ref}/{picked['name']}"
        result.duration = picked.get("duration")
        return result


class NASAImageProvider(ImageProvider):
    """NASA Image Library — keyless, public domain images."""
    name = "nasa"
    URL = "https://images-api.nasa.gov/search"

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        results = []
        try:
            with httpx.Client() as c:
                data = c.get(self.URL, params={"q": query, "media_type": "image"},
                             timeout=30.0, headers={"User-Agent": "NOLAN/1.0"}).json()
        except Exception:
            return results
        for item in data.get("collection", {}).get("items", [])[:max_results]:
            d = (item.get("data") or [{}])[0]
            links = item.get("links") or []
            if not links:
                continue
            results.append(ImageSearchResult(
                url=links[0].get("href", ""), thumbnail_url=links[-1].get("href", ""),
                title=d.get("title", ""), source=self.name,
                source_url=f"https://images.nasa.gov/details/{d.get('nasa_id','')}",
                photographer=d.get("center"), license="Public Domain (NASA)",
            ))
        return results


class NASAVideoProvider(ImageProvider):
    """NASA Image Library — keyless, public domain VIDEO."""
    name = "nasa_video"
    URL = "https://images-api.nasa.gov/search"
    media_type = "video"

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        """Lazy: return candidates with a poster but defer the per-item asset
        manifest fetch (the mp4 URL) to resolve()."""
        results = []
        try:
            with httpx.Client(headers={"User-Agent": "NOLAN/1.0"}) as c:
                data = c.get(self.URL, params={"q": query, "media_type": "video"}, timeout=30.0).json()
        except Exception:
            return results
        for item in data.get("collection", {}).get("items", [])[:max_results]:
            d = (item.get("data") or [{}])[0]
            href = item.get("href")  # asset manifest (fetched lazily in resolve)
            if not href:
                continue
            poster = (item.get("links") or [{}])[0].get("href")
            results.append(ImageSearchResult(
                url="", ref=href, thumbnail_url=poster, preview_image_url=poster,
                title=d.get("title", ""), source=self.name,
                source_url=f"https://images.nasa.gov/details/{d.get('nasa_id','')}",
                media_type="video", license="Public Domain (NASA)",
            ))
        return results

    def resolve(self, result):
        if result.url or not result.ref:
            return result
        try:
            with httpx.Client(headers={"User-Agent": "NOLAN/1.0"}) as c:
                assets = c.get(result.ref, timeout=20.0).json()
        except Exception:
            return None
        mp4 = next((a for a in assets if str(a).lower().endswith(".mp4")), None)
        if not mp4:
            return None
        result.url = mp4
        return result


class OpenverseProvider(ImageProvider):
    """Openverse — keyless CC image aggregator (Flickr, museums, …)."""
    name = "openverse"
    URL = "https://api.openverse.org/v1/images/"

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        results = []
        try:
            with httpx.Client(headers={"User-Agent": "NOLAN/1.0"}) as c:
                data = c.get(self.URL, params={"q": query, "page_size": min(max_results, 20)}, timeout=30.0).json()
        except Exception:
            return results
        for r in data.get("results", []):
            lic = " ".join(x for x in [r.get("license", "").upper(), r.get("license_version", "")] if x)
            results.append(ImageSearchResult(
                url=r.get("url", ""), thumbnail_url=r.get("thumbnail"),
                title=r.get("title", ""), source=f"{self.name}:{r.get('source', '')}",
                source_url=r.get("foreign_landing_url"), photographer=r.get("creator"),
                license=f"CC {lic}".strip(),
            ))
        return results


class MetMuseumProvider(ImageProvider):
    """The Met — keyless, CC0 public-domain art/historical objects."""
    name = "met"
    SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1/search"
    OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects"

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        results = []
        try:
            with httpx.Client(headers={"User-Agent": "NOLAN/1.0"}) as c:
                ids = c.get(self.SEARCH, params={"q": query, "hasImages": "true"}, timeout=30.0).json().get("objectIDs") or []
                for oid in ids[: max_results * 2]:
                    if len(results) >= max_results:
                        break
                    try:
                        o = c.get(f"{self.OBJECT}/{oid}", timeout=20.0).json()
                    except Exception:
                        continue
                    if not o.get("primaryImage") or not o.get("isPublicDomain"):
                        continue
                    results.append(ImageSearchResult(
                        url=o.get("primaryImage"), thumbnail_url=o.get("primaryImageSmall"),
                        title=o.get("title", ""), source=self.name, source_url=o.get("objectURL"),
                        photographer=o.get("artistDisplayName"), license="CC0 (The Met)",
                    ))
        except Exception:
            return results
        return results


class ArtInstituteProvider(ImageProvider):
    """Art Institute of Chicago — keyless, CC0 art (IIIF images)."""
    name = "artic"
    URL = "https://api.artic.edu/api/v1/artworks/search"
    IIIF = "https://www.artic.edu/iiif/2"

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        results = []
        try:
            with httpx.Client(headers={"User-Agent": "NOLAN/1.0"}) as c:
                data = c.get(self.URL, params={"q": query, "limit": min(max_results, 20),
                                                "fields": "id,title,image_id,artist_title"}, timeout=30.0).json()
        except Exception:
            return results
        for a in data.get("data", []):
            img = a.get("image_id")
            if not img:
                continue
            results.append(ImageSearchResult(
                url=f"{self.IIIF}/{img}/full/1686,/0/default.jpg",
                thumbnail_url=f"{self.IIIF}/{img}/full/400,/0/default.jpg",
                title=a.get("title", ""), source=self.name,
                source_url=f"https://www.artic.edu/artworks/{a.get('id')}",
                photographer=a.get("artist_title"), license="CC0 (Art Institute of Chicago)",
            ))
        return results


class ClevelandArtProvider(ImageProvider):
    """Cleveland Museum of Art — keyless, CC0 art/historical."""
    name = "cleveland"
    URL = "https://openaccess-api.clevelandart.org/api/artworks/"

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        results = []
        try:
            with httpx.Client(headers={"User-Agent": "NOLAN/1.0"}) as c:
                data = c.get(self.URL, params={"q": query, "limit": min(max_results, 20),
                                                "has_image": 1}, timeout=30.0).json()
        except Exception:
            return results
        for a in data.get("data", []):
            imgs = a.get("images") or {}
            web = (imgs.get("web") or {}).get("url")
            if not web:
                continue
            results.append(ImageSearchResult(
                url=(imgs.get("print") or {}).get("url") or web,
                thumbnail_url=web, title=a.get("title", ""), source=self.name,
                source_url=a.get("url"), license=a.get("share_license_status", "CC0"),
            ))
        return results


class WellcomeProvider(ImageProvider):
    """Wellcome Collection — keyless, mostly CC/PD historical & medical imagery (IIIF).

    Strong for documentary work: science, medicine, history, ephemera. The Images
    API returns an IIIF image-service ``info.json`` per result; we build the
    full-resolution image URL from it.
    """
    name = "wellcome"
    URL = "https://api.wellcomecollection.org/catalogue/v2/images"

    def is_available(self) -> bool:
        return True  # no key required

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        results = []
        try:
            with httpx.Client(headers={"User-Agent": "NOLAN/1.0"}) as c:
                data = c.get(self.URL, params={"query": query, "pageSize": min(max_results, 100)},
                             timeout=30.0).json()
        except Exception:
            return results
        for r in data.get("results", []):
            locs = r.get("locations") or []
            info = locs[0].get("url") if locs else None
            if not info:
                continue
            base = info[: -len("/info.json")] if info.endswith("/info.json") else info
            lic = (locs[0].get("license") or {}).get("label")
            src = r.get("source") or {}
            work_id = src.get("id")
            results.append(ImageSearchResult(
                url=f"{base}/full/full/0/default.jpg",
                thumbnail_url=f"{base}/full/!400,400/0/default.jpg",  # IIIF-sized, displayable
                title=src.get("title", ""), source=self.name,
                source_url=f"https://wellcomecollection.org/works/{work_id}" if work_id else None,
                license=lic or "Wellcome Collection (see item)",
            ))
        return results


class EuropeanaProvider(ImageProvider):
    """Europeana — EU cultural heritage (image + video). Needs free API key."""
    name = "europeana"
    URL = "https://api.europeana.eu/record/v2/search.json"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        results = []
        params = {"wskey": self.api_key, "query": query, "media": "true",
                  "rows": min(max_results, 50), "profile": "rich"}
        try:
            with httpx.Client(headers={"User-Agent": "NOLAN/1.0"}) as c:
                data = c.get(self.URL, params=params, timeout=30.0).json()
        except Exception:
            return results
        for it in data.get("items", []):
            url = (it.get("edmIsShownBy") or it.get("edmObject") or [None])
            url = url[0] if isinstance(url, list) else url
            if not url:
                continue
            etype = (it.get("type") or "IMAGE").upper()
            results.append(ImageSearchResult(
                url=url,
                thumbnail_url=(it.get("edmPreview") or [None])[0] if isinstance(it.get("edmPreview"), list) else it.get("edmPreview"),
                title=(it.get("title") or [""])[0] if isinstance(it.get("title"), list) else it.get("title", ""),
                source=self.name, source_url=(it.get("guid") or it.get("link")),
                license=(it.get("rights") or [None])[0] if isinstance(it.get("rights"), list) else it.get("rights"),
                media_type="video" if etype == "VIDEO" else "image",
                preview_image_url=(it.get("edmPreview") or [None])[0] if isinstance(it.get("edmPreview"), list) else None,
            ))
        return results


class DPLAProvider(ImageProvider):
    """Digital Public Library of America — US archives/museums. Needs free API key."""
    name = "dpla"
    URL = "https://api.dp.la/v2/items"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        results = []
        params = {"api_key": self.api_key, "q": query, "page_size": min(max_results, 50)}
        try:
            with httpx.Client(headers={"User-Agent": "NOLAN/1.0"}) as c:
                data = c.get(self.URL, params=params, timeout=30.0).json()
        except Exception:
            return results
        for doc in data.get("docs", []):
            obj = doc.get("object")
            if not obj:
                continue
            sr = doc.get("sourceResource", {}) or {}
            title = sr.get("title")
            results.append(ImageSearchResult(
                url=obj, thumbnail_url=obj,
                title=title[0] if isinstance(title, list) else (title or ""),
                source=self.name, source_url=doc.get("isShownAt"),
                license=doc.get("rights") or "see source",
            ))
        return results


class FlickrProvider(ImageProvider):
    """Flickr — CC-licensed images. Needs free API key."""
    name = "flickr"
    URL = "https://api.flickr.com/services/rest/"
    CC_LICENSES = "1,2,3,4,5,6,9,10"  # Creative Commons license ids

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        results = []
        params = {"method": "flickr.photos.search", "api_key": self.api_key, "text": query,
                  "license": self.CC_LICENSES, "extras": "url_l,owner_name,license",
                  "format": "json", "nojsoncallback": 1, "per_page": min(max_results, 50)}
        with httpx.Client(headers={"User-Agent": "NOLAN/1.0"}) as c:
            data = c.get(self.URL, params=params, timeout=30.0).json()
        for ph in data.get("photos", {}).get("photo", []):
            if not ph.get("url_l"):
                continue
            results.append(ImageSearchResult(
                url=ph["url_l"], thumbnail_url=ph.get("url_l"),
                title=ph.get("title", ""), source=self.name,
                source_url=f"https://www.flickr.com/photos/{ph.get('owner')}/{ph.get('id')}",
                photographer=ph.get("ownername"), license="Creative Commons (Flickr)",
            ))
        return results


class UnsplashProvider(ImageProvider):
    """Unsplash — premium modern stock images. Needs free Access Key."""
    name = "unsplash"
    URL = "https://api.unsplash.com/search/photos"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        results = []
        headers = {"Authorization": f"Client-ID {self.api_key}", "User-Agent": "NOLAN/1.0"}
        with httpx.Client(headers=headers) as c:
            data = c.get(self.URL, params={"query": query, "per_page": min(max_results, 30)}, timeout=30.0).json()
        for p in data.get("results", []):
            urls = p.get("urls", {})
            results.append(ImageSearchResult(
                url=urls.get("full") or urls.get("regular", ""), thumbnail_url=urls.get("small"),
                title=p.get("description") or p.get("alt_description", ""), source=self.name,
                source_url=(p.get("links", {}) or {}).get("html"),
                photographer=(p.get("user", {}) or {}).get("name"),
                license="Unsplash License (free for commercial use)",
            ))
        return results


class RijksmuseumProvider(ImageProvider):
    """Rijksmuseum — Dutch art/historical. Needs free API key."""
    name = "rijksmuseum"
    URL = "https://www.rijksmuseum.nl/api/en/collection"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        results = []
        params = {"key": self.api_key, "q": query, "imgonly": "true", "ps": min(max_results, 50)}
        with httpx.Client(headers={"User-Agent": "NOLAN/1.0"}) as c:
            data = c.get(self.URL, params=params, timeout=30.0).json()
        for a in data.get("artObjects", []):
            img = (a.get("webImage") or {}).get("url")
            if not img:
                continue
            results.append(ImageSearchResult(
                url=img, thumbnail_url=(a.get("headerImage") or {}).get("url") or img,
                title=a.get("title", ""), source=self.name, source_url=a.get("links", {}).get("web"),
                photographer=a.get("principalOrFirstMaker"), license="Public Domain (Rijksmuseum)",
            ))
        return results


class HarvardArtProvider(ImageProvider):
    """Harvard Art Museums — art/historical. Needs free API key."""
    name = "harvard"
    URL = "https://api.harvardartmuseums.org/object"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        results = []
        params = {"apikey": self.api_key, "q": query, "size": min(max_results, 50), "hasimage": 1}
        with httpx.Client(headers={"User-Agent": "NOLAN/1.0"}) as c:
            data = c.get(self.URL, params=params, timeout=30.0).json()
        for r in data.get("records", []):
            if not r.get("primaryimageurl"):
                continue
            results.append(ImageSearchResult(
                url=r["primaryimageurl"], thumbnail_url=r.get("primaryimageurl"),
                title=r.get("title", ""), source=self.name, source_url=r.get("url"),
                photographer=r.get("people", [{}])[0].get("name") if r.get("people") else None,
                license=r.get("creditline") or "see source",
            ))
        return results


class CoverrVideoProvider(ImageProvider):
    """Coverr — free modern stock VIDEO. Needs API key."""
    name = "coverr_video"
    URL = "https://api.coverr.co/videos"
    media_type = "video"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> List[ImageSearchResult]:
        results = []
        headers = {"Authorization": f"Bearer {self.api_key}", "User-Agent": "NOLAN/1.0"}
        params = {"query": query, "page_size": min(max_results, 30)}
        with httpx.Client(headers=headers) as c:
            data = c.get(self.URL, params=params, timeout=30.0).json()
        for v in data.get("hits", data.get("videos", [])):
            urls = v.get("urls", {}) or {}
            mp4 = urls.get("mp4") or urls.get("mp4_download")
            if not mp4:
                continue
            results.append(ImageSearchResult(
                url=mp4, thumbnail_url=v.get("poster") or v.get("thumbnail"),
                preview_image_url=v.get("poster") or v.get("thumbnail"),
                title=v.get("title", ""), source=self.name, source_url=v.get("urls", {}).get("page"),
                media_type="video", duration=v.get("duration"),
                license="Coverr License (free for commercial use)",
            ))
        return results


class ImageSearchClient:
    """Client for searching images across multiple providers."""

    def __init__(
        self,
        pexels_api_key: Optional[str] = None,
        pixabay_api_key: Optional[str] = None,
        smithsonian_api_key: Optional[str] = None,
        keys: Optional[Dict[str, str]] = None,
    ):
        """Initialize image search client.

        Args:
            pexels_api_key / pixabay_api_key / smithsonian_api_key: legacy explicit keys.
            keys: dict of extra provider keys (europeana, dpla, flickr, unsplash,
                rijksmuseum, harvard, coverr) — typically from config.image_sources.
        """
        k = keys or {}
        self.providers: Dict[str, ImageProvider] = {
            "ddgs": DDGSProvider(),
            "pexels": PexelsProvider(api_key=pexels_api_key),
            "pixabay": PixabayProvider(api_key=pixabay_api_key),
            "wikimedia": WikimediaCommonsProvider(),
            "smithsonian": SmithsonianProvider(api_key=smithsonian_api_key),
            "loc": LibraryOfCongressProvider(),
            # Keyless extras (image)
            "nasa": NASAImageProvider(),
            "openverse": OpenverseProvider(),
            "met": MetMuseumProvider(),
            "artic": ArtInstituteProvider(),
            "cleveland": ClevelandArtProvider(),
            "wellcome": WellcomeProvider(),
            # Key-needed (image) — available once the key is set
            "europeana": EuropeanaProvider(api_key=k.get("europeana")),
            "dpla": DPLAProvider(api_key=k.get("dpla")),
            "flickr": FlickrProvider(api_key=k.get("flickr")),
            "unsplash": UnsplashProvider(api_key=k.get("unsplash")),
            "rijksmuseum": RijksmuseumProvider(api_key=k.get("rijksmuseum")),
            "harvard": HarvardArtProvider(api_key=k.get("harvard")),
            # Video providers
            "archive": InternetArchiveProvider(),                 # keyless archival video
            "nasa_video": NASAVideoProvider(),                    # keyless PD video
            "pexels_video": PexelsVideoProvider(api_key=pexels_api_key),
            "pixabay_video": PixabayVideoProvider(api_key=pixabay_api_key),
            "coverr_video": CoverrVideoProvider(api_key=k.get("coverr")),
        }
        self._limiter = _RATE_LIMITER

    def _provider_search(self, name: str, query: str, max_results: int,
                         *, fanout: bool) -> List[ImageSearchResult]:
        """Run one provider's search with 429-aware cooldown.

        A 429 cools the provider's bucket and yields [] (never raises). Other
        errors are swallowed to [] in `fanout` mode but propagate for an explicit
        single-source call (preserving the original behavior of `search`).
        """
        provider = self.providers.get(name)
        if not provider or not provider.is_available():
            return []
        try:
            return provider.search(query, max_results)
        except httpx.HTTPStatusError as e:
            if getattr(e.response, "status_code", None) == 429:
                self._limiter.penalize(name)
                print(f"Warning: {name} rate-limited (429); cooling down")
                return []
            if fanout:
                print(f"Warning: {name} search failed: {e}")
                return []
            raise
        except Exception as e:
            if fanout:
                print(f"Warning: {name} search failed: {e}")
                return []
            raise

    @staticmethod
    def _tier_sources(sources: List[str]) -> List[List[str]]:
        """Split sources into priority tiers: cheap/keyless first, deferred last.

        Tight-budget providers (`_DEFER_LAST`, e.g. Unsplash 50/hr) form a
        fallback tier queried only if earlier tiers come up short.
        """
        first = [n for n in sources if n not in _DEFER_LAST]
        last = [n for n in sources if n in _DEFER_LAST]
        return [t for t in (first, last) if t]

    def video_providers(self) -> List[str]:
        """Names of available providers that return video."""
        return [n for n, p in self.providers.items()
                if getattr(p, "media_type", "image") == "video" and p.is_available()]

    def get_available_providers(self) -> List[str]:
        """Get list of available provider names."""
        return [name for name, p in self.providers.items() if p.is_available()]

    def search(
        self,
        query: str,
        source: str = "ddgs",
        max_results: int = 10
    ) -> List[ImageSearchResult]:
        """Search for images using specified provider.

        Args:
            query: Search query string.
            source: Provider name ('ddgs', 'pexels', 'pixabay', 'all').
            max_results: Maximum results per provider.

        Returns:
            List of ImageSearchResult objects.
        """
        if source == "all":
            results = []
            for name, provider in self.providers.items():
                if not provider.is_available():
                    continue
                if not self._limiter.allow(name):
                    print(f"Warning: {name} rate-limited; skipping")
                    continue
                results.extend(self._provider_search(name, query, max_results, fanout=True))
            return results

        if source not in self.providers:
            raise ValueError(f"Unknown provider: {source}. Available: {list(self.providers.keys())}")

        provider = self.providers[source]
        if not provider.is_available():
            raise RuntimeError(f"Provider '{source}' is not available (missing API key or package)")

        # Explicit single-source call: honor the request but keep the bucket count
        # accurate and stay 429-safe.
        self._limiter.record(source)
        return self._provider_search(source, query, max_results, fanout=False)

    def search_assets(self, query: str, media_type: Optional[str] = None,
                      sources: Optional[List[str]] = None,
                      max_results: int = 5) -> List[ImageSearchResult]:
        """Search across multiple providers, optionally filtered by media type.

        Args:
            query: search string.
            media_type: "video" | "image" | None (any).
            sources: explicit provider names; default = all available providers
                matching media_type.
            max_results: results per provider.
        """
        explicit = sources is not None
        if sources is None:
            sources = [n for n, p in self.providers.items()
                       if p.is_available()
                       and (media_type is None or getattr(p, "media_type", "image") == media_type)]
        if not sources:
            return []

        # Default fan-out is tiered so tight-budget providers (Unsplash) are only
        # queried when cheaper/keyless ones come up short. An explicit `sources`
        # list is honored as a single tier in the order given.
        tiers = [sources] if explicit else self._tier_sources(sources)

        from concurrent.futures import ThreadPoolExecutor
        merged: List[ImageSearchResult] = []
        for tier in tiers:
            # Rate-limit gate: only query providers currently under their limit.
            ready = [n for n in tier if self._limiter.allow(n)]
            if not ready:
                continue
            with ThreadPoolExecutor(max_workers=min(8, len(ready))) as ex:
                for r in ex.map(
                    lambda n: self._provider_search(n, query, max_results, fanout=True),
                    ready,
                ):
                    merged.extend(r)
            # Enough from a higher-priority tier — don't spend the next tier's quota.
            if len(merged) >= max_results:
                break
        return merged

    def resolve_video(self, result: ImageSearchResult) -> Optional[ImageSearchResult]:
        """Resolve a lazily-returned video result (fill its mp4 url) via its provider."""
        provider = self.providers.get(result.source)
        if provider and hasattr(provider, "resolve"):
            return provider.resolve(result)
        return result

    def search_to_json(
        self,
        query: str,
        output_path: Path,
        source: str = "ddgs",
        max_results: int = 10
    ) -> List[ImageSearchResult]:
        """Search and save results to JSON file.

        Args:
            query: Search query string.
            output_path: Path to save JSON results.
            source: Provider name.
            max_results: Maximum results per provider.

        Returns:
            List of ImageSearchResult objects.
        """
        results = self.search(query, source, max_results)

        output_data = {
            "query": query,
            "source": source,
            "count": len(results),
            "results": [r.to_dict() for r in results],
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        return results

    def download_image(
        self,
        result: ImageSearchResult,
        output_path: Path,
        prefer_large: bool = True,
        timeout: float = 30.0
    ) -> Optional[Path]:
        """Download an image to disk.

        Args:
            result: ImageSearchResult to download.
            output_path: Path to save the image (with extension).
            prefer_large: If True, download full-size image; else thumbnail.
            timeout: Request timeout in seconds.

        Returns:
            Path to downloaded file, or None if failed.
        """
        url = result.url if prefer_large else (result.thumbnail_url or result.url)

        # Browser-like headers to avoid blocks
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
        }

        try:
            with httpx.Client(follow_redirects=True, headers=headers, timeout=timeout) as client:
                response = client.get(url)
                response.raise_for_status()

                # Determine file extension from content-type or URL
                content_type = response.headers.get("content-type", "")
                if "jpeg" in content_type or "jpg" in content_type:
                    ext = ".jpg"
                elif "png" in content_type:
                    ext = ".png"
                elif "webp" in content_type:
                    ext = ".webp"
                elif "gif" in content_type:
                    ext = ".gif"
                else:
                    # Try to get from URL
                    url_lower = url.lower()
                    if ".png" in url_lower:
                        ext = ".png"
                    elif ".webp" in url_lower:
                        ext = ".webp"
                    elif ".gif" in url_lower:
                        ext = ".gif"
                    else:
                        ext = ".jpg"  # Default

                # Ensure output path has correct extension
                if not output_path.suffix:
                    output_path = output_path.with_suffix(ext)

                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(response.content)

                return output_path

        except Exception as e:
            # Try fallback URL if main fails
            if prefer_large and result.thumbnail_url and result.thumbnail_url != url:
                try:
                    with httpx.Client(follow_redirects=True, headers=headers, timeout=timeout) as client:
                        response = client.get(result.thumbnail_url)
                        response.raise_for_status()

                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        if not output_path.suffix:
                            output_path = output_path.with_suffix(".jpg")
                        output_path.write_bytes(response.content)
                        return output_path
                except Exception:
                    pass
            return None


class ImageScorer:
    """Score images using vision models for relevance to query."""

    def __init__(self, vision_provider: str = "gemini", vision_config: Optional[Dict] = None):
        """Initialize image scorer.

        Args:
            vision_provider: Vision provider to use ('gemini' or 'ollama').
            vision_config: Configuration for vision provider.
        """
        self.vision_provider = vision_provider
        self.vision_config = vision_config or {}

    def _download_image(self, url: str, timeout: float = 10.0) -> Optional[bytes]:
        """Download image from URL.

        Args:
            url: Image URL.
            timeout: Request timeout.

        Returns:
            Image bytes or None if failed.
        """
        # Local file (e.g. a picture-library asset) — read directly.
        if url and "://" not in url:
            try:
                return Path(url).read_bytes()
            except Exception:
                return None
        # Use browser-like headers to avoid being blocked
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
        }
        try:
            with httpx.Client(follow_redirects=True, headers=headers) as client:
                response = client.get(url, timeout=timeout)
                response.raise_for_status()
                return response.content
        except Exception:
            return None

    def _score_with_gemini(
        self,
        image_data: bytes,
        query: str,
        context: Optional[str] = None
    ) -> tuple[float, str]:
        """Score image using Gemini vision model.

        Args:
            image_data: Image bytes.
            query: Search query.
            context: Additional context for scoring.

        Returns:
            Tuple of (score, reason).
        """
        import google.generativeai as genai
        from PIL import Image
        import io

        api_key = self.vision_config.get("api_key")
        if not api_key:
            raise RuntimeError("Gemini API key not configured")

        genai.configure(api_key=api_key)
        model_name = self.vision_config.get("model", "gemini-3-flash-preview")
        model = genai.GenerativeModel(model_name)

        # Load image
        image = Image.open(io.BytesIO(image_data))

        context_text = f"\nContext: {context}" if context else ""
        prompt = f"""Score this image for relevance to the search query.

Search query: "{query}"{context_text}

Rate the image from 0-10 where:
- 10 = Perfect match, exactly what was searched for
- 7-9 = Good match, clearly related to the query
- 4-6 = Partial match, somewhat related
- 1-3 = Poor match, barely related
- 0 = Not relevant at all

Respond in this exact format:
SCORE: [number]
REASON: [brief explanation in one sentence]"""

        response = model.generate_content([prompt, image])
        text = response.text.strip()

        # Parse response
        score = 5.0
        reason = "Unable to parse response"

        for line in text.split("\n"):
            if line.startswith("SCORE:"):
                try:
                    score = float(line.replace("SCORE:", "").strip())
                    score = max(0, min(10, score))  # Clamp to 0-10
                except ValueError:
                    pass
            elif line.startswith("REASON:"):
                reason = line.replace("REASON:", "").strip()

        return score, reason

    def _score_with_ollama(
        self,
        image_data: bytes,
        query: str,
        context: Optional[str] = None
    ) -> tuple[float, str]:
        """Score image using Ollama vision model.

        Args:
            image_data: Image bytes.
            query: Search query.
            context: Additional context for scoring.

        Returns:
            Tuple of (score, reason).
        """
        import base64

        host = self.vision_config.get("host", "127.0.0.1")
        port = self.vision_config.get("port", 11434)
        model = self.vision_config.get("model", "qwen2.5-vl:7b")

        # Encode image to base64
        image_b64 = base64.b64encode(image_data).decode("utf-8")

        context_text = f"\nContext: {context}" if context else ""
        prompt = f"""Score this image for relevance to the search query.

Search query: "{query}"{context_text}

Rate the image from 0-10 where:
- 10 = Perfect match, exactly what was searched for
- 7-9 = Good match, clearly related to the query
- 4-6 = Partial match, somewhat related
- 1-3 = Poor match, barely related
- 0 = Not relevant at all

Respond in this exact format:
SCORE: [number]
REASON: [brief explanation in one sentence]"""

        # Use chat API for vision models (not generate)
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64]
                }
            ],
            "stream": False
        }

        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"http://{host}:{port}/api/chat",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            result = response.json()
            # Extract content from chat response
            message = result.get("message", {})
            text = message.get("content", "").strip()

        # Parse response
        score = 5.0
        reason = "Unable to parse response"

        for line in text.split("\n"):
            if line.startswith("SCORE:"):
                try:
                    score = float(line.replace("SCORE:", "").strip())
                    score = max(0, min(10, score))  # Clamp to 0-10
                except ValueError:
                    pass
            elif line.startswith("REASON:"):
                reason = line.replace("REASON:", "").strip()

        return score, reason

    def _score_with_openrouter(
        self,
        image_data: bytes,
        query: str,
        context: Optional[str] = None
    ) -> tuple[float, str]:
        """Score image using an OpenRouter vision model (OpenAI-compatible).

        Args:
            image_data: Image bytes.
            query: Search query.
            context: Additional context for scoring.

        Returns:
            Tuple of (score, reason).
        """
        import base64

        api_key = self.vision_config.get("api_key")
        if not api_key:
            raise RuntimeError("OpenRouter API key not configured")
        model = self.vision_config.get("model", "qwen/qwen3.7-plus")
        base_url = self.vision_config.get("base_url", "https://openrouter.ai/api/v1").rstrip("/")
        reasoning_enabled = self.vision_config.get("reasoning_enabled", False)
        reasoning_max_tokens = self.vision_config.get("reasoning_max_tokens")

        # Sniff mime type so the data URL matches the downloaded bytes.
        mime = "image/jpeg"
        if image_data[:4] == b"\x89PNG":
            mime = "image/png"
        elif image_data[:4] == b"RIFF" and image_data[8:12] == b"WEBP":
            mime = "image/webp"
        elif image_data[:3] == b"GIF":
            mime = "image/gif"
        image_b64 = base64.b64encode(image_data).decode("utf-8")

        context_text = f"\nContext: {context}" if context else ""
        prompt = f"""Score this image for relevance to the search query.

Search query: "{query}"{context_text}

Rate the image from 0-10 where:
- 10 = Perfect match, exactly what was searched for
- 7-9 = Good match, clearly related to the query
- 4-6 = Partial match, somewhat related
- 1-3 = Poor match, barely related
- 0 = Not relevant at all

Respond in this exact format:
SCORE: [number]
REASON: [brief explanation in one sentence]"""

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                    ],
                }
            ],
        }
        # Reasoning off by default for speed (non-reasoning models ignore this).
        if not reasoning_enabled:
            payload["reasoning"] = {"enabled": False}
        elif reasoning_max_tokens:
            payload["reasoning"] = {"max_tokens": reasoning_max_tokens}

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/nolan",
            "X-Title": "NOLAN",
        }
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            result = response.json()
            text = (result["choices"][0]["message"].get("content") or "").strip()

        # Parse response
        score = 5.0
        reason = "Unable to parse response"

        for line in text.split("\n"):
            if line.startswith("SCORE:"):
                try:
                    score = float(line.replace("SCORE:", "").strip())
                    score = max(0, min(10, score))  # Clamp to 0-10
                except ValueError:
                    pass
            elif line.startswith("REASON:"):
                reason = line.replace("REASON:", "").strip()

        return score, reason

    def calculate_quality_score(self, result: ImageSearchResult) -> tuple[float, str]:
        """Calculate image quality score based on resolution and aspect ratio.

        Args:
            result: Image search result with width/height.

        Returns:
            Tuple of (quality_score, reason).
        """
        width = result.width or 0
        height = result.height or 0

        if width == 0 or height == 0:
            return 0.0, "Unknown dimensions"

        # Calculate total pixels
        pixels = width * height

        # Calculate aspect ratio (always >= 1)
        aspect = max(width, height) / min(width, height)

        # Resolution score (0-6 points)
        # < 100K pixels = 0, 100K-500K = 2, 500K-1M = 4, 1M-2M = 5, > 2M = 6
        if pixels < 100_000:
            res_score = 0
            res_reason = "very low resolution"
        elif pixels < 500_000:
            res_score = 2
            res_reason = "low resolution"
        elif pixels < 1_000_000:
            res_score = 4
            res_reason = "medium resolution"
        elif pixels < 2_000_000:
            res_score = 5
            res_reason = "good resolution"
        else:
            res_score = 6
            res_reason = "high resolution"

        # Aspect ratio score (0-4 points)
        # Standard ratios (16:9=1.78, 4:3=1.33, 3:2=1.5) get bonus
        # Extreme ratios (> 3:1) get penalty
        standard_ratios = [1.0, 1.33, 1.5, 1.78, 1.91]  # 1:1, 4:3, 3:2, 16:9, 2:1

        # Find closest standard ratio
        closest_diff = min(abs(aspect - sr) for sr in standard_ratios)

        if closest_diff < 0.1:
            aspect_score = 4
            aspect_reason = "standard aspect ratio"
        elif closest_diff < 0.3:
            aspect_score = 3
            aspect_reason = "near-standard aspect ratio"
        elif aspect > 3.0:
            aspect_score = 1
            aspect_reason = "extreme aspect ratio"
        else:
            aspect_score = 2
            aspect_reason = "unusual aspect ratio"

        total_score = res_score + aspect_score
        reason = f"{width}x{height} ({res_reason}, {aspect_reason})"

        return total_score, reason

    def score_image(
        self,
        image_url: str,
        query: str,
        context: Optional[str] = None,
        fallback_url: Optional[str] = None
    ) -> tuple[float, str]:
        """Score a single image.

        Args:
            image_url: Primary URL to try (usually thumbnail).
            query: Search query.
            context: Additional context for scoring.
            fallback_url: Fallback URL if primary fails (usually main image).

        Returns:
            Tuple of (score, reason).
        """
        # Try primary URL first
        image_data = self._download_image(image_url)

        # If primary fails and we have a fallback, try that
        if not image_data and fallback_url and fallback_url != image_url:
            image_data = self._download_image(fallback_url)

        if not image_data:
            return 0.0, "Failed to download image"

        if self.vision_provider == "gemini":
            return self._score_with_gemini(image_data, query, context)
        elif self.vision_provider == "ollama":
            return self._score_with_ollama(image_data, query, context)
        elif self.vision_provider == "openrouter":
            return self._score_with_openrouter(image_data, query, context)
        else:
            raise ValueError(f"Unknown vision provider: {self.vision_provider}")

    def score_results(
        self,
        results: List[ImageSearchResult],
        query: str,
        context: Optional[str] = None,
        progress_callback: Optional[callable] = None,
        include_quality: bool = True
    ) -> List[ImageSearchResult]:
        """Score all search results and sort by score.

        Args:
            results: List of search results.
            query: Search query.
            context: Additional context for scoring.
            progress_callback: Optional callback(current, total, result) for progress.
            include_quality: Whether to calculate quality scores (default True).

        Returns:
            List of results sorted by combined score (relevance + quality tiebreaker).
        """
        # Quality scores need no network — compute up front.
        if include_quality:
            for result in results:
                quality_score, quality_reason = self.calculate_quality_score(result)
                result.quality_score = quality_score
                result.quality_reason = quality_reason

        def _score_one(result):
            primary_url = result.thumbnail_url or result.url
            fallback_url = result.url if result.thumbnail_url else None
            try:
                score, reason = self.score_image(primary_url, query, context, fallback_url)
                result.score = score
                result.score_reason = reason
            except Exception as e:
                result.score = 0.0
                result.score_reason = f"Scoring failed: {str(e)}"
            result.scored_by = self.vision_provider
            return result

        # Score candidates concurrently (each call is network-bound).
        scored_results = []
        if results:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(8, len(results))) as pool:
                scored_results = list(pool.map(_score_one, results))

        if progress_callback:
            progress_callback(len(scored_results), len(results), None)

        # Sort by combined score (relevance + quality as tiebreaker)
        scored_results.sort(key=lambda r: r.combined_score(), reverse=True)

        return scored_results
