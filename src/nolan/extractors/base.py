"""Base extractor + shared high-definition selection logic.

Extractors take a page URL (and usually its HTML) and emit
:class:`~nolan.image_search.ImageSearchResult` objects — the same unified type
the API-provider search uses — so extracted assets flow straight into the
existing scoring / download / materialize paths.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional
from urllib.parse import urljoin, urlparse

from nolan.image_search import ImageSearchResult
from nolan.extractors.html_utils import ImgTag, PageElements, parse_html

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff", ".bmp", ".avif"}

# Substrings in a URL path that mark it as chrome rather than content.
JUNK_TOKENS = (
    "icon", "logo", "sprite", "avatar", "button", "spacer", "blank",
    "pixel", "emoji", "badge", "favicon", "loading", "placeholder",
    "/ads/", "doubleclick",
)

# An <img> with no anchor upgrade whose largest declared side is below this is
# treated as decorative chrome.
MIN_DECLARED_DIM = 100


def is_image_url(url: Optional[str]) -> bool:
    """True if ``url``'s path ends in a known raster image extension."""
    if not url:
        return False
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in IMAGE_EXTS)


def looks_like_junk(url: str) -> bool:
    """True if the URL path looks like an icon/logo/sprite/ad."""
    low = url.lower()
    return any(tok in low for tok in JUNK_TOKENS)


def srcset_largest(srcset: Optional[str]) -> Optional[str]:
    """Pick the highest-resolution candidate from a ``srcset`` attribute."""
    if not srcset:
        return None
    best_url, best_weight = None, -1.0
    for part in srcset.split(","):
        bits = part.strip().split()
        if not bits:
            continue
        url = bits[0]
        weight = 1.0
        if len(bits) > 1:
            d = bits[1].strip().lower()
            try:
                weight = float(d[:-1]) if d[-1] in ("w", "x") else float(d)
            except ValueError:
                weight = 1.0
        if weight > best_weight:
            best_url, best_weight = url, weight
    return best_url


def resolve(base_url: str, url: Optional[str]) -> Optional[str]:
    """Resolve ``url`` against the page URL; return None for non-http targets."""
    if not url:
        return None
    url = url.strip()
    if url.startswith("data:") or url.startswith("javascript:"):
        return None
    resolved = urljoin(base_url, url)
    if not resolved.startswith(("http://", "https://")):
        return None
    return resolved


def _img_to_result(
    img: ImgTag, base_url: str, source: str, license: Optional[str]
) -> Optional[ImageSearchResult]:
    """Choose the highest-def URL for one ``<img>`` and build a result.

    Priority: an enclosing ``<a href>`` that points at an image (the
    thumbnail-links-to-full pattern) > the largest ``srcset`` candidate > ``src``.
    """
    anchor = img.anchor_href
    upgraded = bool(anchor and is_image_url(anchor))
    chosen = anchor if upgraded else (srcset_largest(img.srcset) or img.src)

    full = resolve(base_url, chosen)
    if not full or not is_image_url(full) or looks_like_junk(full):
        return None

    thumb = resolve(base_url, img.src)
    if thumb == full:
        thumb = None

    # Tiny-image filter only applies when we did NOT upgrade to a linked full-res
    # (a 275px thumbnail that links to a full illustration must survive).
    if not upgraded and img.width and img.height:
        if max(img.width, img.height) < MIN_DECLARED_DIM:
            return None

    return ImageSearchResult(
        url=full,
        thumbnail_url=thumb,
        title=(img.alt or None),
        source=source,
        source_url=base_url,
        license=license,
        width=None if upgraded else img.width,
        height=None if upgraded else img.height,
    )


def results_from_page(
    page: PageElements, base_url: str, source: str, license: Optional[str] = None
) -> List[ImageSearchResult]:
    """Generic high-def extraction shared by the generic + site extractors."""
    results: List[ImageSearchResult] = []

    # Page hero from social meta first — usually a large, representative image.
    for key in ("og:image", "og:image:url", "twitter:image", "twitter:image:src"):
        hero = resolve(base_url, page.meta.get(key))
        if hero and is_image_url(hero) and not looks_like_junk(hero):
            results.append(ImageSearchResult(
                url=hero, title=page.title, source=source,
                source_url=base_url, license=license,
            ))
            break

    for img in page.images:
        r = _img_to_result(img, base_url, source, license)
        if r:
            results.append(r)

    return dedupe(results)


def dedupe(results: List[ImageSearchResult]) -> List[ImageSearchResult]:
    """Drop duplicate URLs, keeping first occurrence (merging a thumbnail in)."""
    seen = {}
    ordered: List[ImageSearchResult] = []
    for r in results:
        if r.url in seen:
            kept = seen[r.url]
            if not kept.thumbnail_url and r.thumbnail_url:
                kept.thumbnail_url = r.thumbnail_url
            continue
        seen[r.url] = r
        ordered.append(r)
    return ordered


class BaseExtractor(ABC):
    """A site (or generic) asset extractor."""

    name: str = "base"
    needs_html: bool = True

    @abstractmethod
    def matches(self, url: str) -> bool:
        """Whether this extractor handles ``url``."""

    @abstractmethod
    def extract(self, url: str, html: str) -> List[ImageSearchResult]:
        """Extract image assets from the page."""

    # convenience for subclasses
    @staticmethod
    def parse(html: str) -> PageElements:
        return parse_html(html)
