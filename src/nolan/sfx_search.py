"""SFX search + fetch — a pluggable provider layer for sourcing sound effects.

The audio-mix stage (`audio_mix.py`) currently only *synthesizes* a transition
whoosh; every other sound effect has to be found + downloaded by hand and dropped
into ``projects/_library/sfx/``. This module automates that search-and-download
step behind a provider interface that mirrors ``image_search.py``.

Providers (swappable — Freesound is the recommended primary):
  - **FreesoundProvider** — the official Freesound APIv2 (real full-text search,
    tagged CC-licensed library, token auth). Downloads the HQ *preview* mp3, which
    is directly fetchable; the lossless original needs OAuth2 and is left as a TODO.
    Requires ``FREESOUND_API_KEY`` (get one free at https://freesound.org/apiv2/apply/).
  - **MixkitProvider** — best-effort scrape of mixkit.co's category pages (Mixkit
    has no API). Mixkit's free license permits using its SFX *inside* a produced
    video, so embedding is fine; this is unofficial/fragile by nature and is a
    secondary. "Search" maps a query to a category page (/free-sound-effects/<slug>/).

Typical use:
    from nolan.sfx_search import source_sfx
    path = source_sfx("whoosh transition", provider="freesound")  # -> _library/sfx/...

Results cache into ``projects/_library/sfx/`` with a ``sfx.json`` manifest so the
same effect is reused and its license/attribution is recorded.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Same library dir audio_mix.py reads from.
SFX_LIBRARY = Path("projects/_library/sfx")
_MANIFEST = "sfx.json"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124 Safari/537.36")


@dataclass
class SFXResult:
    """One sound-effect candidate from any provider."""
    provider: str
    id: str
    title: str
    download_url: str                 # directly fetchable audio (preview-grade)
    preview_url: str = ""             # audition URL (often == download_url)
    duration: float = 0.0             # seconds, 0 if unknown
    tags: List[str] = field(default_factory=list)
    license: str = ""                 # license name or URL
    attribution: str = ""             # credit line to surface if required
    page_url: str = ""                # human-facing source page
    query: str = ""                   # the query that surfaced it (semantic tag)


# --- shared HTTP -------------------------------------------------------------

def _get(url: str, headers: Optional[Dict[str, str]] = None,
         timeout: float = 30.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _slug(s: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")


# --- provider interface ------------------------------------------------------

class SFXProvider(ABC):
    name: str = "base"

    def available(self) -> bool:
        """True if the provider is usable (e.g. key present)."""
        return True

    @abstractmethod
    def search(self, query: str, max_results: int = 10) -> List[SFXResult]:
        ...


# --- Freesound (primary; official API) ---------------------------------------

class FreesoundProvider(SFXProvider):
    """Freesound APIv2 full-text search. Token auth; HQ-preview download.

    The preview mp3 (``previews['preview-hq-mp3']``) is public and fetchable with
    the token; the lossless original requires OAuth2 (TODO). ``max_duration``
    keeps results short, which is what SFX usually wants.
    """
    name = "freesound"
    BASE = "https://freesound.org/apiv2/search/text/"

    def __init__(self, api_key: Optional[str] = None, max_duration: float = 15.0):
        self.api_key = api_key or os.getenv("FREESOUND_API_KEY", "")
        if not self.api_key:
            # the key lives in .env — don't depend on the caller having run
            # load_config() first (standalone source_sfx calls silently fell
            # back to "provider unavailable" without this)
            try:
                from dotenv import load_dotenv
                load_dotenv()
                self.api_key = os.getenv("FREESOUND_API_KEY", "")
            except ImportError:
                pass
        self.max_duration = max_duration

    def available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> List[SFXResult]:
        if not self.api_key:
            raise RuntimeError(
                "FREESOUND_API_KEY not set — get one at "
                "https://freesound.org/apiv2/apply/ and put it in .env")
        params = {
            "query": query,
            "fields": "id,name,tags,duration,license,username,previews,url",
            "page_size": str(max(1, min(max_results, 150))),
            "token": self.api_key,
        }
        if self.max_duration:
            params["filter"] = f"duration:[0 TO {self.max_duration}]"
        url = self.BASE + "?" + urllib.parse.urlencode(params)
        try:
            data = json.loads(_get(url))
        except Exception as exc:  # noqa: BLE001
            logger.warning("freesound search failed: %s", exc)
            return []
        out: List[SFXResult] = []
        for r in data.get("results", [])[:max_results]:
            prev = r.get("previews", {}) or {}
            dl = prev.get("preview-hq-mp3") or prev.get("preview-lq-mp3") or ""
            if not dl:
                continue
            lic = r.get("license", "")
            user = r.get("username", "")
            out.append(SFXResult(
                provider=self.name, id=str(r.get("id")), title=r.get("name", ""),
                download_url=dl, preview_url=dl,
                duration=float(r.get("duration") or 0.0),
                tags=list(r.get("tags", []))[:12],
                license=lic,
                attribution=f'"{r.get("name","")}" by {user} — {lic} (Freesound)',
                page_url=r.get("url", ""), query=query))
        return out

    def download_headers(self) -> Dict[str, str]:
        # Previews are public, but sending the token avoids the odd 403.
        return {"Authorization": f"Token {self.api_key}"} if self.api_key else {}


# --- Mixkit (secondary; scrape, no API) --------------------------------------

class MixkitProvider(SFXProvider):
    """Best-effort scrape of mixkit.co category pages. No API; fragile by design.

    Query -> category path (/free-sound-effects/<slug>/). Items are parsed from the
    ``data-audio-player-preview-url-value`` attributes; the preview mp3 IS the usable
    effect. Titles are derived (Mixkit cards don't expose a clean name attribute).
    Returns [] on any failure so it never breaks the caller.
    """
    name = "mixkit"
    ROOT = "https://mixkit.co/free-sound-effects"
    _ITEM = re.compile(
        r'data-audio-player-preview-url-value="'
        r'(https://assets\.mixkit\.co/active_storage/sfx/(\d+)/\2-preview\.mp3)"')

    def search(self, query: str, max_results: int = 10) -> List[SFXResult]:
        slug = _slug(query)
        # try the query as a category, then the first word, then the root listing
        candidates = [f"{self.ROOT}/{slug}/"]
        first = slug.split("-")[0] if slug else ""
        if first and first != slug:
            candidates.append(f"{self.ROOT}/{first}/")
        candidates.append(f"{self.ROOT}/")
        html = ""
        used = ""
        for url in candidates:
            try:
                html = _get(url).decode("utf-8", "replace")
                used = url
                if self._ITEM.search(html):
                    break
            except Exception as exc:  # noqa: BLE001
                logger.debug("mixkit fetch %s failed: %s", url, exc)
        out: List[SFXResult] = []
        seen = set()
        for m in self._ITEM.finditer(html):
            prev_url, sid = m.group(1), m.group(2)
            if sid in seen:
                continue
            seen.add(sid)
            out.append(SFXResult(
                provider=self.name, id=sid,
                title=f"{query.strip().title()} (Mixkit #{sid})",
                download_url=prev_url, preview_url=prev_url,
                tags=[t for t in _slug(query).split("-") if t],
                license="Mixkit Free License (https://mixkit.co/license/)",
                attribution="",  # Mixkit requires no attribution
                page_url=used or f"{self.ROOT}/{slug}/", query=query))
            if len(out) >= max_results:
                break
        if not out:
            logger.info("mixkit: no items for %r (tried %d category pages)",
                        query, len(candidates))
        return out


# --- registry ----------------------------------------------------------------

_PROVIDERS = {"freesound": FreesoundProvider, "mixkit": MixkitProvider}


def get_provider(name: str, **kw) -> SFXProvider:
    if name not in _PROVIDERS:
        raise ValueError(f"unknown sfx provider {name!r}; have {list(_PROVIDERS)}")
    return _PROVIDERS[name](**kw)


def search_sfx(query: str, provider: str = "freesound",
               max_results: int = 10, **kw) -> List[SFXResult]:
    """Search one provider. Convenience over ``get_provider(...).search(...)``."""
    return get_provider(provider, **kw).search(query, max_results=max_results)


# --- library cache + manifest ------------------------------------------------

def _load_manifest(library: Path) -> List[Dict[str, Any]]:
    mpath = library / _MANIFEST
    if mpath.exists():
        try:
            return json.loads(mpath.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s unreadable: %s", _MANIFEST, exc)
    return []


def fetch_to_library(result: SFXResult, library: Path = None,
                     provider: Optional[SFXProvider] = None) -> Optional[Path]:
    """Download ``result`` into the SFX library and record it in ``sfx.json``.

    Idempotent: an already-cached (provider,id) is returned without re-downloading.
    """
    library = Path(library) if library else SFX_LIBRARY
    library.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(library)
    for e in manifest:
        if e.get("provider") == result.provider and str(e.get("id")) == result.id:
            p = library / e["file"]
            if p.exists():
                logger.info("sfx cached: %s", e["file"])
                return p
    ext = ".mp3" if ".mp3" in result.download_url.lower() else \
          (".wav" if ".wav" in result.download_url.lower() else ".mp3")
    fname = f"{result.provider}-{_slug(result.query or result.title)[:40]}-{result.id}{ext}"
    dest = library / fname
    headers = provider.download_headers() if hasattr(provider, "download_headers") else {}
    try:
        dest.write_bytes(_get(result.download_url, headers=headers))
    except Exception as exc:  # noqa: BLE001
        logger.warning("sfx download failed (%s): %s", result.download_url, exc)
        return None
    entry = asdict(result)
    entry["file"] = fname
    manifest = [e for e in manifest
                if not (e.get("provider") == result.provider and str(e.get("id")) == result.id)]
    manifest.append(entry)
    (library / _MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info("sfx saved: %s (%s, %s)", fname, result.provider, result.license)
    return dest


def source_sfx(query: str, provider: str = "freesound",
               library: Path = None, **kw) -> Optional[Path]:
    """One-call: search a provider and cache the top hit into the SFX library."""
    prov = get_provider(provider, **kw)
    if not prov.available():
        logger.warning("sfx provider %r unavailable (missing key?)", provider)
        return None
    results = prov.search(query, max_results=5)
    if not results:
        logger.info("sfx: no results for %r via %s", query, provider)
        return None
    return fetch_to_library(results[0], library=library, provider=prov)
