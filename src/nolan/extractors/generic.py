"""Generic HTML asset extractor — the registry fallback.

Handles any page using universal heuristics: ``<a href>``-wraps-``<img>``
(thumbnail links to full-res), largest ``srcset`` candidate, ``og:image`` hero,
relative-URL resolution, and icon/sprite filtering.
"""

from __future__ import annotations

from typing import List

from nolan.image_search import ImageSearchResult
from nolan.extractors.base import BaseExtractor, results_from_page


class GenericExtractor(BaseExtractor):
    name = "web"

    def matches(self, url: str) -> bool:
        return True  # fallback — registry places it last

    def extract(self, url: str, html: str) -> List[ImageSearchResult]:
        return results_from_page(self.parse(html), url, source=self.name)
