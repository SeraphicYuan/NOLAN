"""Offline contract tests for Rawpixel search, routing and Visual Lab wiring."""
import json

import pytest

from nolan.rawpixel import (
    FACET_ROUTES, RawpixelClient, RawpixelRoute, TOP_ROUTES, build_search_params,
    parse_collection_page, parse_search_payload, rank_routes,
)


def _row(rid="3864349", **extra):
    row = {
        "id": int(rid),
        "image_title": "Ocean fluid art wallpaper",
        "image_alt": "Abstract ocean wallpaper and fluid art background",
        "url": f"https://www.rawpixel.com/image/{rid}/ocean-wallpaper",
        "artist_names": "Wikimedia Commons (Source)",
        "keywords_raw": "ocean, wave, wallpaper, public domain",
        "original_width": 4853,
        "original_height": 2730,
        "image_400": "https://img.rawpixel.com/ocean.jpg?w=400",
        "image_1600": "https://img.rawpixel.com/ocean.jpg?w=1600",
        "image_2500": "https://img.rawpixel.com/ocean.jpg?w=2500",
        "free_image": True,
        "freecc0": True,
        "free_or_cc0": True,
        "collections": [{"slug": "ocean-art"}, {"slug": "blue-backgrounds"}],
    }
    row.update(extra)
    return row


def test_search_params_are_free_plus_pd_and_route_aware():
    p = build_search_params(query="wave", route=TOP_ROUTES["images"], sort="popular",
                            rights_tag="$publicdomain")
    assert p == {"image_type": "image", "lang": "en", "page": 1,
                 "published_status": "published", "show_creative_brushes": "false",
                 "sort": "popular", "keys": "wave", "curated_tag": "wave",
                 "tags": "$publicdomain"}
    assert TOP_ROUTES["videos"].path == "1604"
    assert TOP_ROUTES["wallpapers"].path == "1636"
    assert FACET_ROUTES["images-illustrations"].path == "1522|search_tl-35"
    assert FACET_ROUTES["videos-original-footage"].path == "1604|search_tl-819"


def test_parse_public_domain_keeps_ai_editorial_and_collections():
    rows = parse_search_payload({"results": [_row(ai_generated=True, editorial_only=True)]})
    assert len(rows) == 1
    r = rows[0]
    assert r.tier == "public_domain"
    assert r.license == "CC0 / Public Domain"
    assert r.ai_generated is True and r.editorial_only is True  # flags, not exclusions
    assert r.collection_slugs == ["ocean-art", "blue-backgrounds"]
    assert r.primary_collection_slug == "ocean-art"
    assert (r.width, r.height) == (4853, 2730)


def test_parse_free_and_reject_premium_from_union_contract():
    free = _row("2", freecc0=False, free_image=True, keywords_raw="wave")
    premium = _row("3", freecc0=False, free_image=False, free_or_cc0=False)
    rows = parse_search_payload({"results": [free, premium]})
    assert [r.id for r in rows] == ["2"]
    assert rows[0].tier == "free"
    assert rows[0].license == "Rawpixel Free License"


def test_parse_current_nested_schema_and_basic_download():
    live = {
        "id": 2796300, "type": "image", "url": "/image/2796300/great-wave",
        "width": 4000, "height": 2667,
        "google_teaser": "https://images.rawpixel.com/image_800/wave.jpg",
        "metadata": {
            "license": "free", "title": "The Great Wave | Free PNG - rawpixel",
            "description_text": "A Japanese wave", "artist_names": ["Hokusai"],
            "image_type": "PNG", "isAIGenerated": False,
            "popular_keywords": ["wave", "Japanese art"],
            "download_options": [{"choices": [
                {"apiUrl": "image/download/2796300/png?width=800"},
                {"apiUrl": "image/download/2796300/original", "isPremium": True},
            ]}],
        },
    }
    row = parse_search_payload({"results": [live]})[0]
    assert row.tier == "free" and row.creator == "Hokusai" and row.image_type == "PNG"
    assert row.download_url == "https://www.rawpixel.com/api/v1/image/download/2796300/png?width=800"
    assert row.high_resolution_url == row.download_url


def test_video_route_only_returns_real_video_records():
    video = _row("4", url="https://www.rawpixel.com/video/4/lone-runner",
                 media_type="video", duration=8.5,
                 video_sd="https://media.rawpixel.com/runner.mp4")
    image = _row("5")
    rows = parse_search_payload({"results": [image, video]}, expected_media_type="video")
    assert [r.id for r in rows] == ["4"]
    assert rows[0].media_type == "video" and rows[0].duration == 8.5
    assert rows[0].download_url.endswith("runner.mp4")


def test_client_searches_matching_collection_then_broad_and_dedupes():
    ocean = RawpixelRoute("rawpixel-images-ocean", "Ocean Art", ("1522", "search_tl-35"),
                          description="waves sea marine", parent_slug="images", topics=("wave",))
    calls = []

    def transport(_url, params):
        calls.append(params.copy())
        return {"total": 1, "results": [_row()]}

    got = RawpixelClient(transport=transport, collection_routes=[ocean]).search(
        "wave", max_results=3)
    assert [r.id for r in got] == ["3864349"]
    assert calls[0]["tags"] == "$free,$ocean"
    assert calls[1]["tags"] == "$publicdomain,$ocean"
    assert calls[2]["tags"] == "$free"  # broad safety route still runs
    assert calls[3]["tags"] == "$publicdomain"


def test_client_prefers_configured_chrome_transport(monkeypatch):
    client = RawpixelClient(cdp_url="http://127.0.0.1:9222")
    seen = []

    def via_chrome(params):
        seen.append(params)
        return {"total": 1, "results": [_row()]}

    monkeypatch.setattr(client, "_request_via_chrome", via_chrome)
    rows, total = client.search_route("wave", route=TOP_ROUTES["images"])
    assert total == 2 and [r.id for r in rows] == ["3864349"]
    assert [x["tags"] for x in seen] == ["$free", "$publicdomain"]


def test_rank_routes_uses_description_and_media_type():
    rs = [
        RawpixelRoute("ocean", "Ocean", ("1522", "x"), description="wave sea"),
        RawpixelRoute("office", "Office", ("1522", "y"), description="business desk"),
        RawpixelRoute("surf-video", "Surf", ("1604", "z"), "video", description="wave"),
    ]
    assert [r.slug for r in rank_routes("ocean wave", rs)] == ["ocean"]
    assert [r.slug for r in rank_routes("wave", rs, media_type="video")] == ["surf-video"]


def test_parse_collection_cards_preserves_description():
    page = '''<a href="/category/191/artist-collections">Artist Collections</a>
              <p>High resolution free CC0 public domain paintings.</p>'''
    got = parse_collection_page(page)
    assert got[0].slug == "rawpixel-artist-collections"
    assert got[0].collection_id == "191"
    assert "public domain paintings" in got[0].description.lower()


def test_comprehensive_crawl_requires_permission():
    with pytest.raises(PermissionError):
        next(RawpixelClient(transport=lambda *_: {}).crawl(
            query="wave", comprehensive=True, written_permission=False))


def test_generic_provider_maps_flags_and_is_registered(monkeypatch):
    import nolan.rawpixel as mod
    from nolan.image_search import ImageSearchClient, RawpixelProvider

    class Fake:
        def search(self, *a, **k):
            return parse_search_payload({"results": [_row(ai_generated=True)]})

    p = RawpixelProvider()
    p._cli = Fake()
    r = p.search("wave")[0]
    assert r.source == "rawpixel"
    assert r.metadata["ai_generated"] is True
    assert r.metadata["collections"] == ["ocean-art", "blue-backgrounds"]
    c = ImageSearchClient()
    assert "rawpixel" in c.providers and "rawpixel_video" in c.providers


def test_visual_lab_adapter_is_fast_metadata_plus_raw_thumbnail():
    from nolan.imagelib.harvest import SOURCES
    a = SOURCES["rawpixel"]
    assert a.fast_thumbnails and a.gate_tier == "indexed"
    assert a.thumbnail_concurrency == 4


def test_asset_collection_many_to_many(tmp_path):
    from nolan.imagelib.catalog import Asset, AssetCatalog, Collection
    cat = AssetCatalog(tmp_path / "catalog.db")
    c1 = cat.upsert_collection(Collection("one", "rawpixel", "One"))
    c2 = cat.upsert_collection(Collection("two", "rawpixel", "Two"))
    a = cat.add(Asset("hash", "", source="rawpixel", collection_id=c1.id, held=0))
    cat.link_asset_collection(a.id, c2.id, position=1, source="rawpixel")
    assert [c.slug for c in cat.collections_for_asset(a.id)] == ["one", "two"]
    assert cat.count(held=0, collection_id=c2.id) == 1


def test_hf_provider_tiers_put_rawpixel_first():
    import importlib.util
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge" / "pool.py"
    spec = importlib.util.spec_from_file_location("rawpixel_hf_pool", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for order in mod._PROVIDER_TIERS.values():
        assert order[:2] == ["rawpixel", "rawpixel_video"]
