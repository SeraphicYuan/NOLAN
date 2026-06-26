"""Wikimedia Commons / Wikipedia extractor.

Wikimedia serves thumbnails from ``upload.wikimedia.org/.../thumb/<a>/<ab>/<Name>/<NNNpx>-<Name>``
and the full original from the same path **without** the ``/thumb/`` segment and
the ``NNNpx-`` rendition. We collect every upload URL on the page and map each to
its original — the highest definition available.
"""

from __future__ import annotations

from typing import List
from urllib.parse import unquote, urlparse

from nolan.image_search import ImageSearchResult
from nolan.extractors.base import BaseExtractor, dedupe, is_image_url, looks_like_junk

_UPLOAD_HOST = "upload.wikimedia.org"


def original_upload_url(url: str) -> str:
    """Map a Wikimedia thumbnail URL to its full-resolution original."""
    if "/thumb/" not in url:
        return url
    pre, _, post = url.partition("/thumb/")
    # post == "<a>/<ab>/<Name.ext>/<NNNpx>-<Name.ext>"  -> drop the rendition segment
    segs = post.split("/")
    if len(segs) >= 2:
        post = "/".join(segs[:-1])
    return f"{pre}/{post}"


class WikimediaExtractor(BaseExtractor):
    name = "wikimedia"

    def matches(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return host.endswith("wikimedia.org") or host.endswith("wikipedia.org")

    def extract(self, url: str, html: str) -> List[ImageSearchResult]:
        page = self.parse(html)
        candidates = list(page.links) + [img.src for img in page.images if img.src]

        results: List[ImageSearchResult] = []
        for raw in candidates:
            if not raw:
                continue
            full = raw[2:] if raw.startswith("//") else raw
            if not full.startswith("http"):
                full = "https:" + raw if raw.startswith("//") else raw
            if _UPLOAD_HOST not in full or not is_image_url(full):
                continue
            full = original_upload_url(full).split("?")[0]
            if looks_like_junk(full):
                continue
            name = unquote(full.rsplit("/", 1)[-1])
            results.append(ImageSearchResult(
                url=full, title=name, source=self.name, source_url=url,
                license="See Wikimedia Commons file page",
            ))
        return dedupe(results)
