"""Library of Congress extractor — item page -> highest-resolution image(s).

LoC item pages hide their download sizes behind JS, but appending ``?fo=json``
returns structured data. ``item.image_url`` is a list of progressively larger
renditions (last = largest); collection/resource pages list multiple items.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from nolan.image_search import ImageSearchResult
from nolan.extractors.base import BaseExtractor, dedupe, is_image_url

_LICENSE = "Library of Congress (rights vary — see item page)"


def _https(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return "https:" + url if url.startswith("//") else url


def _split_dims(url: str) -> Tuple[str, Optional[int], Optional[int]]:
    """LoC appends ``#h=2721&w=1789`` to encode the image size — strip + parse it."""
    clean, _, frag = url.partition("#")
    h = re.search(r"h=(\d+)", frag)
    w = re.search(r"w=(\d+)", frag)
    return clean, (int(h.group(1)) if h else None), (int(w.group(1)) if w else None)


def _largest(urls) -> Optional[str]:
    """Last entry of an image_url list is the biggest LoC rendition."""
    if isinstance(urls, list) and urls:
        return _https(urls[-1])
    if isinstance(urls, str):
        return _https(urls)
    return None


class LoCExtractor(BaseExtractor):
    name = "loc"
    needs_html = False  # resolves via the ?fo=json API

    def matches(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        if not host.endswith("loc.gov"):
            return False
        path = urlparse(url).path
        return any(seg in path for seg in ("/item/", "/resource/", "/pictures/", "/collections/"))

    def extract(self, url: str, html: str) -> List[ImageSearchResult]:
        api = url + ("&" if "?" in url else "?") + "fo=json"
        try:
            with httpx.Client(headers={"User-Agent": "NOLAN-VideoEssayTool/1.0"},
                              follow_redirects=True) as c:
                data = c.get(api, timeout=30.0).json()
        except Exception:
            return []

        results: List[ImageSearchResult] = []

        # Single item page.
        item = data.get("item")
        if isinstance(item, dict):
            big = _largest(item.get("image_url"))
            if big:
                clean, h, w = _split_dims(big)
                if is_image_url(clean):
                    results.append(ImageSearchResult(
                        url=clean, width=w, height=h, source=self.name, source_url=url,
                        title=item.get("title"), photographer=_creator(item),
                        license=_rights(item) or _LICENSE,
                    ))

        # Search / collection results -> one image per result.
        for res in data.get("results") or []:
            big = _largest(res.get("image_url"))
            if big:
                clean, h, w = _split_dims(big)
                if is_image_url(clean):
                    results.append(ImageSearchResult(
                        url=clean, width=w, height=h, source=self.name,
                        source_url=(res.get("id") or url), title=res.get("title"),
                        license=_LICENSE,
                    ))

        return dedupe(results)


def _creator(item: dict) -> Optional[str]:
    c = item.get("creators") or item.get("contributor")
    if isinstance(c, list) and c:
        first = c[0]
        return first.get("title") if isinstance(first, dict) else str(first)
    return None


def _rights(item: dict) -> Optional[str]:
    r = item.get("rights") or item.get("rights_information")
    if isinstance(r, list) and r:
        return str(r[0])
    return r if isinstance(r, str) else None
