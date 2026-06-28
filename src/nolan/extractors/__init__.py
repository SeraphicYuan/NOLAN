"""Link -> assets extraction.

A registry of parsers that, given a page URL, return high-definition image
assets as :class:`~nolan.image_search.ImageSearchResult` objects. Site-specific
extractors run first; :class:`GenericExtractor` is the universal fallback.

    from nolan.extractors import extract_from_url
    assets = extract_from_url("https://www.gutenberg.org/files/21790/21790-h/21790-h.htm")

Adding a site = drop a new ``BaseExtractor`` subclass in this package and list
it in :data:`EXTRACTORS` before the generic fallback.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote, urlparse

import httpx

from nolan.image_search import ImageSearchResult
from nolan.extractors.archive import ArchiveExtractor
from nolan.extractors.base import BaseExtractor, dedupe
from nolan.extractors.generic import GenericExtractor
from nolan.extractors.gutenberg import GutenbergExtractor
from nolan.extractors.iiif import IIIFExtractor
from nolan.extractors.loc import LoCExtractor
from nolan.extractors.met import MetExtractor
from nolan.extractors.wikimedia import WikimediaExtractor

# Order matters: site extractors first, generic fallback last.
EXTRACTORS: List[BaseExtractor] = [
    GutenbergExtractor(),
    WikimediaExtractor(),
    MetExtractor(),
    ArchiveExtractor(),
    LoCExtractor(),
    IIIFExtractor(),
    GenericExtractor(),
]

_UA = "NOLAN-AssetExtractor/1.0 (+https://github.com/; contact: nolan)"


def get_extractor(url: str) -> BaseExtractor:
    """Return the first extractor that matches ``url`` (generic always matches)."""
    for ex in EXTRACTORS:
        if ex.matches(url):
            return ex
    return EXTRACTORS[-1]


def fetch_html(url: str, timeout: float = 30.0, retries: int = 2) -> str:
    """Fetch a page's HTML with a descriptive User-Agent (retries on timeout)."""
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            with httpx.Client(headers={"User-Agent": _UA}, follow_redirects=True) as c:
                resp = c.get(url, timeout=timeout)
                resp.raise_for_status()
                return resp.text
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last_exc = e
    raise last_exc  # type: ignore[misc]


def extract_from_url(
    url: str,
    *,
    html: Optional[str] = None,
    fetch: bool = True,
    limit: Optional[int] = None,
) -> List[ImageSearchResult]:
    """Extract image assets from ``url``.

    Args:
        url: Page URL to extract from.
        html: Pre-fetched HTML (skips the network fetch when provided).
        fetch: Fetch the page when ``html`` is None and the extractor needs it.
        limit: Cap the number of results returned.
    """
    ex = get_extractor(url)
    if html is None and fetch and ex.needs_html:
        html = fetch_html(url)
    results = dedupe(ex.extract(url, html or ""))
    return results[:limit] if limit else results


def _best_candidate(
    found: List[ImageSearchResult], original: ImageSearchResult
) -> Optional[ImageSearchResult]:
    """Pick the best full-res candidate from a source page.

    Prefer the largest by known dimensions; otherwise the first (extractors order
    best-first — site extractors return the canonical image, generic puts
    ``og:image`` first). Skip a candidate identical to what we already have.
    """
    fresh = [f for f in found if f.url and f.url != original.url]
    if not fresh:
        return None
    sized = [f for f in fresh if f.width and f.height]
    if sized:
        return max(sized, key=lambda f: f.width * f.height)
    return fresh[0]


# Known thumbnail-URL -> full-resolution rewrites (deterministic, no JS needed).
# ContentDM (OCLC) powers a large share of DPLA and exposes IIIF.
_CONTENTDM_RE = re.compile(
    r"(https?://[^/]+)/(?:utils/getthumbnail|digital/api/singleitem/image)/collection/([^/]+)/id/(\d+)",
    re.IGNORECASE,
)


def _rewrite_thumbnail(url: Optional[str]) -> Optional[str]:
    """Map a known thumbnail URL to its full-resolution equivalent, else None."""
    if not url:
        return None
    m = _CONTENTDM_RE.search(url)
    if m:
        host, collection, cid = m.groups()
        return f"{host}/digital/iiif/{collection}/{cid}/full/max/0/default.jpg"
    return None


# A IIIF Image API request: .../full/<size>/<rotation>/<quality>.<format>
_IIIF_SIZE_RE = re.compile(
    r"(?P<pre>.+?/full/)"
    r"(?P<size>\d+,|,\d+|\d+,\d+|pct:\d+(?:\.\d+)?|!\d+,\d+)"
    r"(?P<post>/\d+/(?:default|native|color|gray|grey|bitonal)\.\w+)$",
    re.IGNORECASE,
)


def _maximize_iiif(url: Optional[str]) -> Optional[str]:
    """Bump a sized IIIF image URL (e.g. ``/full/730,/``) to ``/full/max/``."""
    if not url or "/full/max/" in url or "/full/full/" in url:
        return url
    m = _IIIF_SIZE_RE.search(url)
    return f"{m.group('pre')}max{m.group('post')}" if m else url


def _verify_image(url: str, timeout: float = 15.0) -> bool:
    """True if the URL serves an image (streamed GET, body not downloaded)."""
    try:
        with httpx.Client(headers={"User-Agent": _UA}, follow_redirects=True) as c:
            with c.stream("GET", url, timeout=timeout) as r:
                return r.status_code == 200 and \
                    r.headers.get("content-type", "").startswith("image/")
    except Exception:
        return False


def _apply_upgrade(result: ImageSearchResult, new_url: str,
                   width=None, height=None) -> None:
    """Swap in a full-res URL, demoting the old image to thumbnail."""
    maxed = _maximize_iiif(new_url)
    if maxed != new_url:
        width = height = None  # dims described the sized rendition, not max
        new_url = maxed
    if not result.thumbnail_url:
        result.thumbnail_url = result.url
    result.url = new_url
    if width:
        result.width = width
    if height:
        result.height = height
    result.source = f"{result.source}+resolved" if result.source else "resolved"


def resolve_result(result: ImageSearchResult) -> ImageSearchResult:
    """Upgrade a search result to full-res. Two tiers, both best-effort:

    1. **Deterministic URL rewrite** of the thumbnail itself (e.g. ContentDM
       ``getthumbnail`` → IIIF ``full/max``), verified to actually serve an image.
    2. **Source-page extraction** — follow ``source_url`` (an item landing page,
       e.g. DPLA's ``isShownAt``) through the extractor registry and take the best
       image found.

    On any failure the result is returned unchanged — resolve never loses data.
    """
    rewritten = _rewrite_thumbnail(result.url)
    if rewritten and rewritten != result.url and _verify_image(rewritten):
        _apply_upgrade(result, rewritten)
        return result

    page = result.source_url
    if not page or not page.startswith("http"):
        return result
    try:
        found = extract_from_url(page, limit=8)
    except Exception:
        return result
    best = _best_candidate(found, result)
    if best and best.url:
        _apply_upgrade(result, best.url, best.width, best.height)
    return result


def resolve_results(
    results: List[ImageSearchResult], *, max_workers: int = 6
) -> List[ImageSearchResult]:
    """Resolve many results concurrently (see :func:`resolve_result`)."""
    from concurrent.futures import ThreadPoolExecutor

    if not results:
        return results
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(resolve_result, results))


def _filename_for(result: ImageSearchResult, index: int) -> str:
    """Derive a safe local filename for a downloaded asset."""
    path = urlparse(result.url).path
    name = unquote(Path(path).name) or f"asset_{index:03d}"
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    if not Path(name).suffix:
        name += ".jpg"
    return f"{index:03d}_{name}"


async def download_assets(
    results: List[ImageSearchResult], out_dir: Path
) -> List[dict]:
    """Download each asset's full-res URL into ``out_dir``.

    Returns one record per asset: its dict plus ``local_path`` / ``bytes`` on
    success or ``error`` on failure.
    """
    from nolan.http_client import download_file_async

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    records: List[dict] = []
    for i, r in enumerate(results):
        rec = r.to_dict()
        dest = out_dir / _filename_for(r, i)
        try:
            n = await download_file_async(
                r.url, str(dest), headers={"User-Agent": _UA}
            )
            rec["local_path"] = str(dest)
            rec["bytes"] = n
        except Exception as e:  # noqa: BLE001 - report, keep going
            rec["error"] = str(e)
        records.append(rec)
    return records


__all__ = [
    "EXTRACTORS",
    "BaseExtractor",
    "extract_from_url",
    "get_extractor",
    "fetch_html",
    "download_assets",
    "resolve_result",
    "resolve_results",
]
