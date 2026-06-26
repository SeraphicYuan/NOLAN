"""Project Gutenberg extractor.

Gutenberg HTML books embed a small thumbnail that links to the full-resolution
illustration::

    <a href="images/illus-048.jpg"><img src="images/p048-t.png" width="275"></a>

The generic href-over-src heuristic already picks the full-res ``illus-*.jpg``;
this extractor just tags the source/license correctly.
"""

from __future__ import annotations

from typing import List
from urllib.parse import urlparse

from nolan.image_search import ImageSearchResult
from nolan.extractors.base import BaseExtractor, results_from_page


class GutenbergExtractor(BaseExtractor):
    name = "gutenberg"

    def matches(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return host.endswith("gutenberg.org")

    def extract(self, url: str, html: str) -> List[ImageSearchResult]:
        return results_from_page(
            self.parse(html), url,
            source=self.name,
            license="Public domain (Project Gutenberg)",
        )
