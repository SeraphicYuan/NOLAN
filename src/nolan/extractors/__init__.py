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
]
