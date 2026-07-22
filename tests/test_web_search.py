"""Unit tests for the general web (text) search provider — the research-stage substrate.

Pure/offline: fake providers exercise the client's selection, fan-out, dedup, and degradation
logic without touching the network. The keyless ddgs baseline and keyed HTTP backends are
integration-only (live deps), so we test the parts that must never regress: provider ordering,
availability gating, preferred-first vs greedy, URL dedup, and error containment.
"""
import pytest

from nolan.web_search import (WebSearchClient, WebSearchProvider, WebSearchResult,
                              DDGSTextProvider, TavilyProvider, SearXNGProvider)


class _Fake(WebSearchProvider):
    def __init__(self, name, results, available=True, raises=False):
        self.name = name
        self._results = results
        self._available = available
        self._raises = raises

    def is_available(self):
        return self._available

    def search(self, query, max_results=10):
        if self._raises:
            raise RuntimeError("boom")
        return list(self._results)


def _r(url, name="x"):
    return WebSearchResult(url=url, title=url, source=name)


def test_result_to_dict_drops_empty():
    d = WebSearchResult(url="http://a", title="A").to_dict()
    assert d == {"url": "http://a", "title": "A"}          # empty snippet/source/rank omitted


def test_unavailable_providers_dropped_and_priority_ordered():
    # tavily is keyed-but-unavailable → dropped; ddgs (baseline) + a fake keyed sort by _PRIORITY
    c = WebSearchClient([
        _Fake("ddgs", [_r("http://d", "ddgs")]),
        TavilyProvider(""),                                # no key → not available
        _Fake("brave", [_r("http://b", "brave")]),
    ])
    assert c.get_available_providers() == ["brave", "ddgs"]  # brave before ddgs (priority)


def test_search_preferred_first_returns_single_backend():
    c = WebSearchClient([
        _Fake("brave", [_r("http://b", "brave")]),
        _Fake("ddgs", [_r("http://d", "ddgs")]),
    ])
    got = c.search("q")
    assert [r.source for r in got] == ["brave"]            # first backend with results wins; ddgs not called-through


def test_search_falls_through_empty_backend():
    c = WebSearchClient([
        _Fake("brave", []),                                # available but yields nothing
        _Fake("ddgs", [_r("http://d", "ddgs")]),
    ])
    got = c.search("q")
    assert [r.source for r in got] == ["ddgs"]


def test_explicit_prefer_overrides_priority():
    c = WebSearchClient([
        _Fake("brave", [_r("http://b", "brave")]),
        _Fake("ddgs", [_r("http://d", "ddgs")]),
    ], prefer="ddgs")
    assert [r.source for r in c.search("q")] == ["ddgs"]


def test_search_all_merges_and_dedupes_by_url():
    c = WebSearchClient([
        _Fake("brave", [_r("http://a", "brave"), _r("http://B/", "brave")]),
        _Fake("ddgs", [_r("http://a/", "ddgs"), _r("http://c", "ddgs")]),   # http://a dup (trailing slash/case)
    ])
    got = c.search_all("q")
    assert [r.url for r in got] == ["http://a", "http://B/", "http://c"]     # a from brave kept, ddgs dup dropped


def test_client_contains_a_raising_provider():
    # a backend that throws must be swallowed by the client's fan-out, and the others still return
    c = WebSearchClient([
        _Fake("brave", [], raises=True),                   # explodes on every call
        _Fake("ddgs", [_r("http://d", "ddgs")]),
    ])
    assert [r.source for r in c.search_all("q")] == ["ddgs"]
    assert [r.source for r in c.search("q")] == ["ddgs"]   # preferred-first skips the raiser too


def test_real_providers_swallow_errors_return_list():
    # the SHIPPED providers must never raise out of .search — contract for the fan-out
    assert TavilyProvider("").search("q") == []            # no key → []
    d = DDGSTextProvider()
    out = d.search("") if d.is_available() else []
    assert isinstance(out, list)


def test_empty_query_short_circuits():
    c = WebSearchClient([_Fake("ddgs", [_r("http://d")])])
    assert c.search("   ") == []
    assert c.search_all("") == []


def test_from_config_registers_baseline_only_without_keys():
    from nolan.config import NolanConfig
    c = WebSearchClient.from_config(NolanConfig())          # no keys set
    assert c.get_available_providers() == ["ddgs"]          # keyed backends inert, baseline present


def test_searxng_unavailable_without_url():
    p = SearXNGProvider("")
    assert p.is_available() is False
    assert p.search("q") == []                             # no instance → no call, empty


def test_searxng_url_trimmed_and_available():
    p = SearXNGProvider("  https://searx.example/  ")
    assert p.is_available() is True
    assert p.base_url == "https://searx.example"           # trailing slash + whitespace stripped


def test_from_config_registers_searxng_first_when_url_set():
    from nolan.config import NolanConfig
    cfg = NolanConfig()
    cfg.web_search.searxng_url = "http://localhost:8888"
    c = WebSearchClient.from_config(cfg)
    assert c.get_available_providers() == ["searxng", "ddgs"]   # searxng leads priority, then baseline
