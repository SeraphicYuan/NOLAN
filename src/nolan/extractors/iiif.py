"""IIIF extractor — one parser for a whole class of GLAM archives.

IIIF (International Image Interoperability Framework) is the standard digital
libraries/museums use to serve high-resolution images. This handles both:

* **Presentation API** manifests (v2 ``sequences``/``canvases`` and v3 ``items``)
  — every page/canvas of an object.
* **Image API** ``info.json`` — a single image, served at max resolution.

Given an HTML viewer page it also tries to *discover* the manifest URL embedded
in the page. Builds ``{image-base}/full/{max|full}/0/default.jpg`` per image.
"""

from __future__ import annotations

import json
import re
from typing import Any, List, Optional
from urllib.parse import urljoin

import httpx

from nolan.image_search import ImageSearchResult
from nolan.extractors.base import BaseExtractor, dedupe, is_image_url

_MANIFEST_RE = re.compile(
    r'https?://[^\s"\'<>\\]+?(?:manifest(?:\.json)?|info\.json)', re.IGNORECASE
)


def _first(value: Any) -> Any:
    """First element if a list, else the value itself."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _label(value: Any) -> Optional[str]:
    """Normalise a IIIF label (v2 string/list or v3 language map) to text."""
    if not value:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return _label(value[0])
    if isinstance(value, dict):
        # v2 {"@value": "..."} or v3 {"en": ["..."]}
        if "@value" in value:
            return value["@value"]
        for vals in value.values():
            got = _label(vals)
            if got:
                return got
    return None


def _rights(data: dict) -> Optional[str]:
    """Pull a license/rights string from a manifest (v2 or v3)."""
    return (
        data.get("rights")
        or data.get("license")
        or _label(data.get("attribution"))
        or "See IIIF source"
    )


def _is_v2(context_blob: str) -> bool:
    """Heuristic: does the @context indicate IIIF Image/Presentation API 2.x?"""
    return "/2/context.json" in context_blob or "/api/image/2" in context_blob \
        or "/api/presentation/2" in context_blob


def _build_full(base: str, service: Optional[dict]) -> str:
    """Construct the max-resolution Image API URL from a service base."""
    base = base.rstrip("/")
    ctx = json.dumps(service.get("@context", "")).lower() if isinstance(service, dict) else ""
    # v2.0 requires 'full'; 2.1+/3.0 support 'max' (and 3.0 deprecates 'full').
    size = "full" if _is_v2(ctx) else "max"
    return f"{base}/full/{size}/0/default.jpg"


class IIIFExtractor(BaseExtractor):
    name = "iiif"

    def matches(self, url: str) -> bool:
        low = url.lower()
        return (
            "/iiif/" in low
            or low.endswith("manifest.json")
            or low.endswith("/manifest")
            or low.endswith("info.json")
            or "manifest=" in low
        )

    # ------------------------------------------------------------------ extract
    def extract(self, url: str, html: str) -> List[ImageSearchResult]:
        data = self._as_iiif_json(html)
        source = url
        if data is None:
            # An HTML viewer page — discover the manifest URL and fetch it.
            manifest_url = self._discover_manifest(html, url)
            if not manifest_url:
                return []
            try:
                from nolan.extractors import fetch_html
                data = json.loads(fetch_html(manifest_url))
            except Exception:
                return []
            source = manifest_url

        return dedupe(self._parse(data, source))

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _as_iiif_json(text: str) -> Optional[dict]:
        try:
            data = json.loads(text)
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        ctx = json.dumps(data.get("@context", "")).lower()
        looks_iiif = (
            "iiif.io" in ctx
            or "sequences" in data
            or "items" in data
            or data.get("protocol") == "http://iiif.io/api/image"
            or str(data.get("@type", "")).lower().endswith("manifest")
            or str(data.get("type", "")).lower() == "manifest"
        )
        return data if looks_iiif else None

    @staticmethod
    def _discover_manifest(html: str, base_url: str) -> Optional[str]:
        for match in _MANIFEST_RE.findall(html or ""):
            if "manifest" in match.lower():
                return match
        # JSON-ish "manifest": "..." references on the page
        m = re.search(r'["\']manifest["\']\s*:\s*["\']([^"\']+)["\']', html or "")
        if m:
            return urljoin(base_url, m.group(1))
        any_match = _MANIFEST_RE.findall(html or "")
        return any_match[0] if any_match else None

    def _parse(self, data: dict, source_url: str) -> List[ImageSearchResult]:
        # Image API info.json -> a single full-resolution image.
        if "width" in data and "height" in data and ("@id" in data or "id" in data):
            base = data.get("@id") or data.get("id")
            ctx = json.dumps(data.get("@context", "")).lower()
            size = "full" if _is_v2(ctx) else "max"
            url = f"{base.rstrip('/')}/full/{size}/0/default.jpg"
            return [ImageSearchResult(
                url=url, source=self.name, source_url=source_url,
                width=data.get("width"), height=data.get("height"),
                license="See IIIF source",
            )]

        # Presentation manifest -> one image per canvas.
        label = _label(data.get("label"))
        rights = _rights(data)
        results: List[ImageSearchResult] = []
        for canvas in self._canvases(data):
            img = self._canvas_image(canvas)
            if img:
                results.append(ImageSearchResult(
                    url=img, source=self.name, source_url=source_url,
                    title=_label(canvas.get("label")) or label, license=rights,
                ))
        return results

    @staticmethod
    def _canvases(data: dict) -> List[dict]:
        if "sequences" in data:  # v2
            canvases: List[dict] = []
            for seq in data.get("sequences") or []:
                canvases.extend(seq.get("canvases") or [])
            return canvases
        if "items" in data:  # v3
            return [c for c in data.get("items") or [] if isinstance(c, dict)]
        return []

    def _canvas_image(self, canvas: dict) -> Optional[str]:
        resource = self._resource(canvas)
        if not isinstance(resource, dict):
            return None
        service = _first(resource.get("service"))
        if isinstance(service, dict):
            base = service.get("@id") or service.get("id")
            if base:
                return _build_full(base, service)
        direct = resource.get("@id") or resource.get("id")
        return direct if direct and isinstance(direct, str) else None

    @staticmethod
    def _resource(canvas: dict) -> Optional[dict]:
        # v2: canvas.images[0].resource
        if "images" in canvas:
            ann = _first(canvas.get("images"))
            if isinstance(ann, dict):
                return ann.get("resource")
        # v3: canvas.items[0].items[0].body
        page = _first(canvas.get("items"))
        if isinstance(page, dict):
            ann = _first(page.get("items"))
            if isinstance(ann, dict):
                return _first(ann.get("body")) if isinstance(ann.get("body"), list) else ann.get("body")
        return None
