"""Tiny stdlib-only HTML collector for asset extraction.

Pulls the few things an extractor cares about — ``<img>`` (with its enclosing
``<a href>``), ``<meta>`` og:/twitter: tags, every ``<a href>``, and the page
title — using the standard library ``html.parser`` (no BeautifulSoup dep).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Dict, List, Optional


def _to_int(value: Optional[str]) -> Optional[int]:
    """Parse an HTML width/height attribute to an int (ignores % and px)."""
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    return int(digits) if digits else None


@dataclass
class ImgTag:
    """One ``<img>`` plus the href of its nearest enclosing ``<a>`` (if any)."""

    src: Optional[str] = None
    srcset: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    alt: Optional[str] = None
    anchor_href: Optional[str] = None


@dataclass
class PageElements:
    """Everything the extractors read out of a page."""

    title: Optional[str] = None
    images: List[ImgTag] = field(default_factory=list)
    links: List[str] = field(default_factory=list)
    meta: Dict[str, str] = field(default_factory=dict)


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._anchor_stack: List[Optional[str]] = []
        self._in_title = False
        self.elements = PageElements()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a":
            href = a.get("href")
            self._anchor_stack.append(href)
            if href:
                self.elements.links.append(href)
        elif tag == "img":
            self.elements.images.append(
                ImgTag(
                    src=a.get("src") or a.get("data-src") or a.get("data-original"),
                    srcset=a.get("srcset") or a.get("data-srcset"),
                    width=_to_int(a.get("width")),
                    height=_to_int(a.get("height")),
                    alt=a.get("alt"),
                    anchor_href=self._anchor_stack[-1] if self._anchor_stack else None,
                )
            )
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content"):
                self.elements.meta[key] = a["content"]
        elif tag == "title":
            self._in_title = True

    def handle_startendtag(self, tag, attrs):
        # Self-closing form (<img/>, <meta/>). Route to starttag; only non-void
        # tags need a matching endtag to keep the anchor stack balanced.
        self.handle_starttag(tag, attrs)
        if tag not in ("img", "meta", "br", "hr", "input", "link"):
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "a" and self._anchor_stack:
            self._anchor_stack.pop()
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and not self.elements.title:
            text = data.strip()
            if text:
                self.elements.title = text


def parse_html(html: str) -> PageElements:
    """Parse ``html`` into a :class:`PageElements` bundle."""
    collector = _Collector()
    try:
        collector.feed(html or "")
    except Exception:
        pass  # be lenient with malformed markup
    return collector.elements
