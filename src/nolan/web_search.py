"""General web (TEXT) search for NOLAN — a standardized, multi-backend provider.

The image stack (`image_search.py`) resolves a query to PICTURES; this resolves a query to
WEB RESULTS (title · url · snippet) — the substrate for the key-assets research stage
(decompose → consolidate → GREEDY harvest: a web result's URL is what `extractors/` then pulls
real hi-def assets out of).

Same idiom as `image_search`, deliberately: a provider ABC, ONE keyless baseline (DuckDuckGo via
`ddgs`, already a dependency) plus keyed upgrades (Tavily / Brave / SerpAPI) registered from config,
and a client that picks the best available backend (or fans out) and de-dupes by URL.

Degrades cleanly at every layer — a provider that errors or lacks a key is skipped, and
`WebSearchClient.search` never raises to the caller (returns [] when nothing is reachable). Keys
come from `cfg.web_search` (single source of truth); nothing is hardcoded here.

    from nolan.web_search import WebSearchClient
    client = WebSearchClient.from_config(load_config())
    for r in client.search("De Beers company history", max_results=8):
        print(r.title, r.url)
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Preference order when provider="auto": our own SearXNG instance first (free, unlimited, keyless),
# then research-grade keyed backends, keyless DuckDuckGo baseline last.
_PRIORITY = ("searxng", "tavily", "brave", "serpapi", "ddgs")
_HTTP_TIMEOUT = 20.0


@dataclass
class WebSearchResult:
    """One web result. `url` is the page (the handle `extractors/` harvests from); `snippet` is the
    text excerpt the research LLM reads. `raw` keeps the provider payload for anything we didn't map."""
    url: str
    title: str = ""
    snippet: str = ""
    source: str = ""                                 # provider name (ddgs / tavily / brave / serpapi)
    rank: int = 0                                    # position within its provider's result list
    published: Optional[str] = None                  # ISO date if the provider gives one
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, "", {}, 0)}


class WebSearchProvider(ABC):
    """Base class for a web-search backend. `search` must NOT raise on a bad query/response — it
    returns [] and logs, so one flaky backend never sinks the fan-out."""
    name: str = "base"

    @abstractmethod
    def search(self, query: str, max_results: int = 10) -> List[WebSearchResult]:
        ...

    def is_available(self) -> bool:
        return True


# --- keyless baseline -----------------------------------------------------------------------------
class DDGSTextProvider(WebSearchProvider):
    """DuckDuckGo text search via `ddgs` (no key). The always-on floor under the keyed backends."""
    name = "ddgs"

    def __init__(self):
        self._ddgs_class = None
        try:
            from ddgs import DDGS
            self._ddgs_class = DDGS
        except ImportError:                          # older package name
            try:
                from duckduckgo_search import DDGS
                self._ddgs_class = DDGS
            except ImportError:
                self._ddgs_class = None

    def is_available(self) -> bool:
        return self._ddgs_class is not None

    def search(self, query: str, max_results: int = 10) -> List[WebSearchResult]:
        if not self._ddgs_class:
            return []
        out: List[WebSearchResult] = []
        try:
            with self._ddgs_class() as ddgs:
                for i, r in enumerate(ddgs.text(query, max_results=max_results) or []):
                    url = r.get("href") or r.get("url") or r.get("link") or ""
                    if not url:
                        continue
                    out.append(WebSearchResult(
                        url=url, title=r.get("title", ""),
                        snippet=r.get("body") or r.get("snippet") or "",
                        source=self.name, rank=i, raw=dict(r)))
        except Exception as e:                       # network / parse — degrade, don't raise
            logger.warning("ddgs text search failed for %r: %s: %s", query, type(e).__name__, e)
        return out


# --- self-hosted metasearch (keyless, our own instance) -------------------------------------------
class SearXNGProvider(WebSearchProvider):
    """SearXNG metasearch over a self-hosted (or public) instance — keyless, aggregates 70+ engines
    (Google/Bing/DuckDuckGo/…) behind a single `format=json` endpoint. `base_url` points at the
    instance (e.g. https://searx.be or http://localhost:8888). Unavailable if no URL is set; an
    instance that disables the JSON API (returns HTML / 403) degrades to [] like any other backend."""
    name = "searxng"

    def __init__(self, base_url: str):
        self.base_url = (base_url or "").strip().rstrip("/")

    def is_available(self) -> bool:
        return bool(self.base_url)

    def search(self, query: str, max_results: int = 10) -> List[WebSearchResult]:
        if not self.is_available():
            return []
        out: List[WebSearchResult] = []
        try:
            import httpx
            with httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True) as c:
                resp = c.get(f"{self.base_url}/search",
                             params={"q": query, "format": "json",
                                     "categories": "general", "safesearch": 0},
                             headers={"Accept": "application/json",
                                      "User-Agent": "Mozilla/5.0 (NOLAN web_search)"})
                resp.raise_for_status()
                for i, r in enumerate((resp.json().get("results") or [])[:max_results]):
                    url = r.get("url", "")
                    if not url:
                        continue
                    out.append(WebSearchResult(
                        url=url, title=r.get("title", ""), snippet=r.get("content", ""),
                        source=self.name, rank=i, published=r.get("publishedDate"),
                        raw={k: r[k] for k in ("engine", "engines", "score", "category") if k in r}))
        except Exception as e:                       # network / JSON-disabled / parse — degrade, don't raise
            logger.warning("searxng search failed for %r @ %s: %s: %s",
                           query, self.base_url, type(e).__name__, e)
        return out


# --- keyed upgrades (same interface) --------------------------------------------------------------
class _HttpProvider(WebSearchProvider):
    """Shared httpx plumbing for the keyed HTTP backends."""

    def __init__(self, api_key: str):
        self.api_key = (api_key or "").strip()

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _client(self):
        import httpx
        return httpx.Client(timeout=_HTTP_TIMEOUT)


class TavilyProvider(_HttpProvider):
    """Tavily search API — research-grade, returns clean title/url/content."""
    name = "tavily"

    def search(self, query: str, max_results: int = 10) -> List[WebSearchResult]:
        if not self.is_available():
            return []
        out: List[WebSearchResult] = []
        try:
            with self._client() as c:
                resp = c.post("https://api.tavily.com/search", json={
                    "api_key": self.api_key, "query": query,
                    "max_results": max_results, "search_depth": "basic"})
                resp.raise_for_status()
                for i, r in enumerate(resp.json().get("results", []) or []):
                    url = r.get("url", "")
                    if not url:
                        continue
                    out.append(WebSearchResult(
                        url=url, title=r.get("title", ""), snippet=r.get("content", ""),
                        source=self.name, rank=i, published=r.get("published_date"), raw=dict(r)))
        except Exception as e:
            logger.warning("tavily search failed for %r: %s: %s", query, type(e).__name__, e)
        return out


class BraveProvider(_HttpProvider):
    """Brave Search API — web/news results behind an X-Subscription-Token header."""
    name = "brave"

    def search(self, query: str, max_results: int = 10) -> List[WebSearchResult]:
        if not self.is_available():
            return []
        out: List[WebSearchResult] = []
        try:
            with self._client() as c:
                resp = c.get("https://api.search.brave.com/res/v1/web/search",
                             params={"q": query, "count": max_results},
                             headers={"Accept": "application/json",
                                      "X-Subscription-Token": self.api_key})
                resp.raise_for_status()
                for i, r in enumerate((resp.json().get("web", {}) or {}).get("results", []) or []):
                    url = r.get("url", "")
                    if not url:
                        continue
                    out.append(WebSearchResult(
                        url=url, title=r.get("title", ""), snippet=r.get("description", ""),
                        source=self.name, rank=i, published=r.get("age"), raw=dict(r)))
        except Exception as e:
            logger.warning("brave search failed for %r: %s: %s", query, type(e).__name__, e)
        return out


class SerpApiProvider(_HttpProvider):
    """SerpAPI — Google organic results."""
    name = "serpapi"

    def search(self, query: str, max_results: int = 10) -> List[WebSearchResult]:
        if not self.is_available():
            return []
        out: List[WebSearchResult] = []
        try:
            with self._client() as c:
                resp = c.get("https://serpapi.com/search.json",
                             params={"engine": "google", "q": query,
                                     "num": max_results, "api_key": self.api_key})
                resp.raise_for_status()
                for i, r in enumerate(resp.json().get("organic_results", []) or []):
                    url = r.get("link", "")
                    if not url:
                        continue
                    out.append(WebSearchResult(
                        url=url, title=r.get("title", ""), snippet=r.get("snippet", ""),
                        source=self.name, rank=i, published=r.get("date"), raw=dict(r)))
        except Exception as e:
            logger.warning("serpapi search failed for %r: %s: %s", query, type(e).__name__, e)
        return out


_KEYED_PROVIDERS = {"tavily": TavilyProvider, "brave": BraveProvider, "serpapi": SerpApiProvider}


class WebSearchClient:
    """Fan-out over the available web-search backends. `search` (preferred-first, cheap) returns the
    best single backend's results; `search_all` (greedy) merges every available backend, de-duped by
    URL. Build with `from_config` (reads keys from cfg.web_search) or pass explicit `providers`."""

    def __init__(self, providers: Optional[List[WebSearchProvider]] = None, *, prefer: str = "auto"):
        # keep only available backends, in _PRIORITY order (unknown names sort last but are kept)
        avail = [p for p in (providers or []) if p.is_available()]
        self.providers = sorted(avail, key=lambda p: _PRIORITY.index(p.name) if p.name in _PRIORITY
                                else len(_PRIORITY))
        self.prefer = prefer

    @classmethod
    def from_config(cls, cfg, *, include_baseline: bool = True) -> "WebSearchClient":
        ws = getattr(cfg, "web_search", None)
        keys = ws.keys() if ws else {}
        prefer = getattr(ws, "provider", "auto") if ws else "auto"
        providers: List[WebSearchProvider] = []
        searxng_url = getattr(ws, "searxng_url", "") if ws else ""
        if searxng_url:                              # our own instance leads the priority order
            providers.append(SearXNGProvider(searxng_url))
        providers += [cls_(keys.get(name, "")) for name, cls_ in _KEYED_PROVIDERS.items()]
        if include_baseline:
            providers.append(DDGSTextProvider())
        return cls(providers, prefer=prefer)

    def get_available_providers(self) -> List[str]:
        """Honest roster — staleness/misconfig shows as a missing name."""
        return [p.name for p in self.providers]

    def _ordered(self) -> List[WebSearchProvider]:
        """Providers in the order `search` should try them (an explicit `prefer` wins if present)."""
        if self.prefer and self.prefer != "auto":
            named = [p for p in self.providers if p.name == self.prefer]
            return named + [p for p in self.providers if p.name != self.prefer]
        return list(self.providers)

    @staticmethod
    def _safe(p: WebSearchProvider, query: str, max_results: int) -> List[WebSearchResult]:
        """Call a backend, containing ANY exception here too — providers swallow their own errors,
        but a third-party backend shouldn't be able to sink the whole fan-out either."""
        try:
            return p.search(query, max_results=max_results) or []
        except Exception as e:
            logger.warning("web-search provider %r raised: %s: %s", p.name, type(e).__name__, e)
            return []

    def search(self, query: str, max_results: int = 10) -> List[WebSearchResult]:
        """Preferred-first: return the first available backend that yields results (cheap default —
        one API call). Falls through to the next backend only when one returns nothing."""
        if not (query or "").strip():
            return []
        for p in self._ordered():
            res = self._safe(p, query, max_results)
            if res:
                return res
        return []

    def search_all(self, query: str, max_results: int = 10) -> List[WebSearchResult]:
        """Greedy: merge EVERY available backend, de-duped by URL (first/highest-priority wins),
        each backend's own rank preserved. For the research stage where recall > cost."""
        if not (query or "").strip():
            return []
        seen: set = set()
        out: List[WebSearchResult] = []
        for p in self.providers:                     # already in priority order
            for r in self._safe(p, query, max_results):
                key = r.url.rstrip("/").lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(r)
        return out


def web_search(query: str, cfg=None, *, max_results: int = 10, greedy: bool = False) -> List[WebSearchResult]:
    """Convenience one-shot: build a client from cfg (loads config if omitted) and search."""
    if cfg is None:
        from nolan.config import load_config
        cfg = load_config()
    client = WebSearchClient.from_config(cfg)
    return client.search_all(query, max_results) if greedy else client.search(query, max_results)
