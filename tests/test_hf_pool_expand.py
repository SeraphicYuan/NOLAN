"""Honesty tests for the HyperFrames asset-pool deepening (query-variant expansion + super-search + gap-fill).

Covers the two pure recall mechanisms without hitting the network / LLM / ComfyUI:
  - derive_asset_needs emits per-need `queries` (variants) + `evocative` + `gen_prompt`, back-compatibly.
  - pool._gather_candidates runs multi-query retrieval and DE-DUPES across variants by source_url.
The async super-search (expand_needs) and krea2 gap-fill (gen_fill) are integration-only (live deps).
"""
import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
POOL_PATH = REPO / "render-service" / "_lab_hyperframes" / "bridge" / "pool.py"


def _load_pool():
    """pool.py is a bridge script (nolan imports live inside functions) — import it by path."""
    spec = importlib.util.spec_from_file_location("hf_pool_bridge", POOL_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_empty_needs_finds_cull_emptied():
    """POST-CULL GAP-FILL targets exactly the needs the cull emptied (no surviving pool asset)."""
    pool = _load_pool()
    needs = [{"id": "a1"}, {"id": "a2"}, {"id": "a3"}]
    survived = [{"id": "a1", "file": "x.jpg"}]           # a2 + a3 emptied by the VLM cull
    empties = pool._empty_needs(needs, survived)
    assert {e["id"] for e in empties} == {"a2", "a3"}


def test_empty_needs_none_when_all_covered():
    pool = _load_pool()
    assert pool._empty_needs([{"id": "a1"}], [{"id": "a1", "file": "x.jpg"}]) == []


def test_enhance_gen_prompts_disambiguates_via_domain():
    """A terse 'Homer' prompt gets rewritten to the domain-correct entity (fixes Homer Simpson)."""
    import asyncio
    pool = _load_pool()

    class FakeLLM:
        async def generate(self, user, system_prompt=""):
            assert "Homer" in user and "ancient Greek" in user   # subject + domain reach the LLM
            return '"Homer, the blind ancient Greek epic poet, neoclassical oil painting, chiaroscuro"'

    needs = [{"id": "a1", "query": "Homer", "gen_prompt": "headshot of Homer"}]
    asyncio.run(pool.enhance_gen_prompts(None, needs, essay_context="Homer Did Not Exist — ancient Greek epic",
                                         theme="dark-botanical", llm=FakeLLM()))
    assert "blind ancient Greek" in needs[0]["gen_prompt"]           # enriched + disambiguated
    assert '"' not in needs[0]["gen_prompt"]                          # surrounding quotes stripped


def test_enhance_gen_prompts_contained_on_dead_llm():
    import asyncio
    pool = _load_pool()

    class DeadLLM:
        async def generate(self, user, system_prompt=""):
            raise RuntimeError("llm down")

    needs = [{"id": "a1", "query": "x", "gen_prompt": "raw prompt"}]
    asyncio.run(pool.enhance_gen_prompts(None, needs, llm=DeadLLM()))
    assert needs[0]["gen_prompt"] == "raw prompt"                     # unchanged — contained


class _FakeLLM:
    def __init__(self, raw):
        self.raw = raw

    async def generate(self, user, system_prompt=None):
        return self.raw


def test_derive_asset_needs_expands_variants():
    from nolan.hyperframes.edit import derive_asset_needs
    raw = json.dumps([
        {"id": "a1", "query": "roman soldier",
         "queries": ["roman legionary", "centurion marching", "ancient roman army", "roman legionary"],
         "media_type": "image", "n": 2, "evocative": False, "category": "archival",
         "gen_prompt": "a roman centurion on a rampart, cinematic"},
        {"id": "a2", "query": "freedom", "media_type": "image", "evocative": True},
    ])
    needs = asyncio.run(derive_asset_needs("script text", _FakeLLM(raw)))
    assert len(needs) == 2
    a1, a2 = needs
    # primary phrasing is present, duplicates collapsed, capped
    assert a1["query"] == "roman soldier"
    assert a1["queries"][0] == "roman soldier"           # primary prepended (wasn't in list)
    assert "roman legionary" in a1["queries"]
    assert len(a1["queries"]) == len(set(q.lower() for q in a1["queries"]))  # de-duped
    assert a1["evocative"] is False
    assert a1["category"] == "archival"
    assert a1["gen_prompt"].startswith("a roman centurion")
    # back-compat: a plain need with no `queries`/`category` gets sane defaults
    assert a2["queries"] == ["freedom"]
    assert a2["evocative"] is True
    assert a2["category"] == "general"                   # default when unspecified
    assert a2["gen_prompt"] == "freedom"
    assert a2["n"] == 3


class _Res:
    def __init__(self, url):
        self.source_url = url
        self.url = url


class _FakeSearchClient:
    """Each query returns a unique hit + one shared hit, so dedupe is observable."""
    def __init__(self):
        self.calls = []

    def search_assets(self, q, media_type=None, sources=None, max_results=9):
        self.calls.append(q)
        return [_Res(f"{q}-uniq"), _Res("SHARED-URL")]


def test_gather_candidates_dedupes_across_variants():
    pool = _load_pool()
    client = _FakeSearchClient()
    queries = ["q1", "q2", "q3"]
    cands = pool._gather_candidates(client, "image", queries, None, want=3)
    urls = [c.source_url for c in cands]
    assert client.calls == queries                      # every phrasing searched (recall)
    assert urls.count("SHARED-URL") == 1                # shared hit kept exactly once (precision)
    assert set(urls) == {"q1-uniq", "q2-uniq", "q3-uniq", "SHARED-URL"}


def test_need_queries_fallback_to_plain():
    pool = _load_pool()
    assert pool._need_queries({"query": "sea"}) == ["sea"]
    assert pool._need_queries({"query": "sea", "queries": ["sea", "ocean", "SEA"]}) == ["sea", "ocean"]


def test_diversify_by_source_round_robins():
    pool = _load_pool()
    cands = [_Res("a"), _Res("b"), _Res("c"), _Res("d")]
    for c, s in zip(cands, ["ddgs", "ddgs", "ddgs", "artvee"]):
        c.source = s
    out = pool._diversify_by_source(cands)
    # the buried artvee hit is lifted to 2nd — no longer drowned behind three ddgs hits
    assert [c.source for c in out] == ["ddgs", "artvee", "ddgs", "ddgs"]


class _FakeSources:
    pexels_api_key = ""
    pixabay_api_key = ""
    smithsonian_api_key = ""

    def provider_keys(self):
        return {"europeana": "", "dpla": "", "flickr": "", "unsplash": "",
                "rijksmuseum": "", "harvard": "", "coverr": ""}


class _FakeCfg:
    image_sources = _FakeSources()


# the FULL registry pool.py must inherit — if image_search adds a provider and the pool goes
# stale, this set stops matching and the test fails (docs claim, tests enforce).
_FULL_ROSTER = {
    "ddgs", "pexels", "pexels_video", "pixabay", "pixabay_video", "wikimedia", "smithsonian",
    "loc", "archive", "archive_image", "nasa", "nasa_video", "openverse", "met", "artic",
    "cleveland", "wellcome", "europeana", "dpla", "flickr", "unsplash", "rijksmuseum",
    "harvard", "coverr_video", "artvee",
}


def test_pool_client_wires_full_provider_registry():
    pool = _load_pool()
    roster = set(pool._client(_FakeCfg()).providers)
    missing = _FULL_ROSTER - roster
    assert not missing, f"pool client is missing providers (stale wiring): {missing}"


def test_pool_client_surfaces_keyless_archival_and_art_sources():
    """artvee + archive.org (stills & movies) + museums are keyless — the pool must query them
    without any key, so a video essay actually gets fine-art and archival footage, not just ddgs."""
    pool = _load_pool()
    avail = set(pool._client(_FakeCfg()).get_available_providers())
    for name in ("artvee", "archive", "archive_image", "met", "nasa_video"):
        assert name in avail, f"{name} should be available (keyless) in the pool fan-out"


def test_provider_tiers_reference_real_providers_only():
    """A curated tier that names a provider the registry doesn't have is a silent dead entry —
    catch typos / stale names against the true roster."""
    pool = _load_pool()
    for category, order in pool._PROVIDER_TIERS.items():
        assert len(order) == len(set(order)), f"duplicate provider in tier {category!r}"
        stale = set(order) - _FULL_ROSTER
        assert not stale, f"tier {category!r} names non-existent providers: {stale}"


def test_source_rank_matches_curated_intent():
    """The quality intent the user specified: art -> artvee/wikicommons first; archival ->
    archive.org first; general -> pexels/pixabay stock first."""
    pool = _load_pool()
    r = pool._source_rank
    assert r("art", "artvee") < r("art", "pexels")          # fine art beats generic stock
    assert r("art", "wikimedia") < r("art", "ddgs")
    assert r("archival", "archive") < r("archival", "pexels_video")   # archive.org movies first
    assert r("archival", "archive_image") < r("archival", "ddgs")
    assert r("general", "pexels") < r("general", "artvee")   # modern stock beats paintings here
    # unknown category falls back to general ordering (never crashes)
    assert r("nonsense", "pexels") == r("general", "pexels")


def test_diversify_orders_buckets_by_category():
    pool = _load_pool()
    cands = [_Res("d1"), _Res("d2"), _Res("w1"), _Res("a1")]
    for c, s in zip(cands, ["ddgs", "ddgs", "wikimedia", "artvee"]):
        c.source = s
    # for an ART need, artvee + wikimedia outrank ddgs -> they lead the round-robin
    out = pool._diversify_by_source(cands, "art")
    assert [c.source for c in out][:3] == ["artvee", "wikimedia", "ddgs"]
    # for a GENERAL need, ddgs outranks both -> it leads
    out_g = pool._diversify_by_source(cands, "general")
    assert out_g[0].source == "ddgs"
