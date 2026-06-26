"""The Met Museum extractor.

Met object pages are JS-rendered, so scraping HTML is unreliable. Instead we
read the object ID from the URL and call the public collection API, which
returns ``primaryImage`` (full resolution) plus any ``additionalImages``.
"""

from __future__ import annotations

import re
from typing import List
from urllib.parse import urlparse

import httpx

from nolan.image_search import ImageSearchResult
from nolan.extractors.base import BaseExtractor

_OBJECT_API = "https://collectionapi.metmuseum.org/public/collection/v1/objects"
_ID_RE = re.compile(r"/(\d+)(?:[/?#]|$)")


class MetExtractor(BaseExtractor):
    name = "met"
    needs_html = False  # resolves via API, not page HTML

    def matches(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return host.endswith("metmuseum.org") and "/art/collection" in url

    def _object_id(self, url: str) -> str:
        m = _ID_RE.search(urlparse(url).path)
        return m.group(1) if m else ""

    def extract(self, url: str, html: str) -> List[ImageSearchResult]:
        oid = self._object_id(url)
        if not oid:
            return []
        try:
            with httpx.Client(headers={"User-Agent": "NOLAN/1.0"}) as c:
                obj = c.get(f"{_OBJECT_API}/{oid}", timeout=20.0).json()
        except Exception:
            return []

        primary = obj.get("primaryImage")
        if not primary:
            return []
        license_ = "CC0 (The Met)" if obj.get("isPublicDomain") else "See The Met object page"
        title = obj.get("title") or f"Met object {oid}"

        results = [ImageSearchResult(
            url=primary, thumbnail_url=obj.get("primaryImageSmall"),
            title=title, source=self.name, source_url=obj.get("objectURL") or url,
            photographer=obj.get("artistDisplayName") or None, license=license_,
        )]
        for extra in obj.get("additionalImages") or []:
            results.append(ImageSearchResult(
                url=extra, title=title, source=self.name,
                source_url=obj.get("objectURL") or url, license=license_,
            ))
        return results
