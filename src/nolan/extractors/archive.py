"""Internet Archive extractor — item page -> downloadable images.

archive.org item pages are JS shells; the real files live in the metadata API
(``archive.org/metadata/{id}``). We read the identifier from the URL, pull the
original image files, and build their ``archive.org/download/...`` URLs.

(The Internet Archive *search* provider in ``image_search.py`` covers archival
video; this covers grabbing the images off a specific item page.)
"""

from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urlparse

import httpx

from nolan.image_search import ImageSearchResult
from nolan.extractors.base import BaseExtractor, dedupe

_META = "https://archive.org/metadata"
_DOWNLOAD = "https://archive.org/download"
_IMAGE_FMT = ("jpeg", "jpg", "png", "tiff", "tif", "gif", "bmp")
_ID_RE = re.compile(r"/(?:details|download|embed)/([^/?#]+)")


class ArchiveExtractor(BaseExtractor):
    name = "archive"
    needs_html = False  # resolves via the metadata API

    def matches(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return host.endswith("archive.org") and bool(_ID_RE.search(url))

    def _identifier(self, url: str) -> str:
        m = _ID_RE.search(url)
        return m.group(1) if m else ""

    def extract(self, url: str, html: str) -> List[ImageSearchResult]:
        ident = self._identifier(url)
        if not ident:
            return []
        try:
            with httpx.Client(headers={"User-Agent": "NOLAN/1.0"}) as c:
                meta = c.get(f"{_META}/{ident}", timeout=25.0).json()
        except Exception:
            return []

        files = meta.get("files") or []
        title = (meta.get("metadata") or {}).get("title") or ident
        license_ = (meta.get("metadata") or {}).get("licenseurl") or "Internet Archive (see item page)"
        page = f"https://archive.org/details/{ident}"

        results: List[ImageSearchResult] = []
        for f in files:
            name = str(f.get("name", ""))
            fmt = str(f.get("format", "")).lower()
            low = name.lower()
            is_image = low.rsplit(".", 1)[-1] in _IMAGE_FMT or "image" in fmt
            if not is_image or "thumb" in low or low.endswith(".gif") and "anim" in fmt:
                continue
            # Skip IA's auto-generated derivative thumbnails.
            if "__ia_thumb" in low or low.endswith("_thumb.jpg"):
                continue
            results.append(ImageSearchResult(
                url=f"{_DOWNLOAD}/{ident}/{name}",
                title=title, source=self.name, source_url=page, license=license_,
            ))
        return dedupe(results)
