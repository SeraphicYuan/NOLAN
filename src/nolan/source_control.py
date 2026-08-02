"""Read-only source status model for the Asset Sources control plane."""
from __future__ import annotations

import ipaddress
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

from nolan.source_registry import (all_source_ids, source_roles, source_spec,
                                   source_surface, source_tier_positions, tier_payload)


def loopback_cdp_url(value: str) -> str:
    """Validate that a CDP endpoint is local; never turn the action into SSRF."""
    parsed = urlparse((value or "").strip())
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Chrome CDP URL must be a plain local http:// URL")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError as exc:
        if parsed.hostname.casefold() != "localhost":
            raise ValueError("Chrome CDP URL must resolve to localhost") from exc
    else:
        if not address.is_loopback:
            raise ValueError("Chrome CDP URL must use a loopback address")
    return value.rstrip("/")


def cdp_status(cdp_url: str) -> Dict[str, Any]:
    """Cheap local-only Chrome health probe; no provider request is made."""
    if not cdp_url:
        return {"connected": False, "reason": "not configured"}
    try:
        safe = loopback_cdp_url(cdp_url)
        response = httpx.get(f"{safe}/json/version", timeout=0.8)
        response.raise_for_status()
        data = response.json()
        return {"connected": True, "browser": data.get("Browser")}
    except Exception as exc:
        return {"connected": False, "reason": str(exc)}


def _coverage(library) -> Dict[str, dict]:
    if library is None:
        return {}
    try:
        counts = library.catalog.collection_counts(held=0)
        out: Dict[str, dict] = {}
        for collection in library.catalog.list_collections():
            row = out.setdefault(collection.source, {
                "indexed": 0, "collections": 0, "upstream": None, "last_crawled": None})
            row["indexed"] += counts.get(collection.id or -1, {}).get("indexed", 0)
            row["collections"] += 1
            if collection.upstream_count:
                row["upstream"] = (row["upstream"] or 0) + collection.upstream_count
            if collection.last_crawled and (row["last_crawled"] or "") < collection.last_crawled:
                row["last_crawled"] = collection.last_crawled
        out["visuallib"] = {
            "indexed": library.catalog.count("active", held=0),
            "collections": len(library.catalog.list_collections()),
            "upstream": None, "last_crawled": None,
        }
        out["library"] = {
            "indexed": library.catalog.count("active", held=1),
            "collections": None, "upstream": None, "last_crawled": None,
        }
        return out
    except Exception:
        return {}


def build_source_rows(config, *, library=None, probe_cdp: bool = True) -> dict:
    """Return secret-free source rows and resolved tier matrices."""
    from nolan.acquire.shared import build_search_client
    from nolan.imagelib.harvest import SOURCES as HARVEST_SOURCES

    image_cfg = config.image_sources
    client = build_search_client(config)
    providers = client.providers
    ids = set(all_source_ids()) | set(providers) | set(HARVEST_SOURCES)
    coverage = _coverage(library)
    raw_health = (cdp_status(image_cfg.rawpixel_cdp_url)
                  if probe_cdp else {"connected": bool(image_cfg.rawpixel_cdp_url)})
    rows = []
    for source_id in sorted(ids, key=lambda x: source_spec(x).title.casefold()):
        spec = source_spec(source_id)
        fields = {name: bool(getattr(image_cfg, name, "")) for name in spec.config_fields}
        if spec.auth in {"none", "local"}:
            configured = True
        elif spec.auth == "api_key":
            configured = bool(fields) and all(fields.values())
        else:
            configured = bool(fields.get("rawpixel_cdp_url") or fields.get("rawpixel_cookie"))

        provider = providers.get(source_id)
        provider_available = bool(provider and provider.is_available()) if provider else None
        if spec.auth == "browser_session":
            if raw_health.get("connected"):
                health = "connected"
            elif configured:
                health = "attention"
            else:
                health = "missing"
        elif spec.auth == "api_key" and not configured:
            health = "missing"
        elif provider_available is False:
            health = "unavailable"
        else:
            health = "ready"

        row = spec.to_dict()
        row.update({
            "roles": source_roles(source_id),
            "tiers": source_tier_positions(source_id),
            "configured": configured,
            "config_state": fields,  # booleans only; never values
            "provider_available": provider_available,
            "health": health,
            "coverage": coverage.get(source_id),
            "harvest": source_id in HARVEST_SOURCES,
            # Where this source's rows actually live. /sources is CONFIGURATION (credentials,
            # priority); the library pages are INVENTORY. The link is what makes them one system
            # rather than three pages that happen to say "source". None for a live provider that
            # has no local tier to browse.
            "surface": source_surface(source_id),
            # Rawpixel Video shares the same browser session; expose one action,
            # on the parent source, so the UI cannot imply two credentials.
            "actions": (["refresh_session"] if source_id == "rawpixel" else []),
        })
        if spec.auth == "browser_session":
            row["browser_session"] = raw_health
        rows.append(row)
    return {"sources": rows, "tiers": tier_payload()}
