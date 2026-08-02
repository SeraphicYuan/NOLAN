import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from nolan.config import NolanConfig
from nolan.hub import create_hub_app
from nolan.image_search import ImageSearchClient
from nolan.source_control import build_source_rows, loopback_cdp_url
from nolan.source_registry import (ACQUISITION_TIERS, HYBRID_PROVIDER_TIERS,
                                   KEY_ASSET_SOURCE_PREFERENCES, all_source_ids,
                                   source_roles, source_tier_positions)


def _pool_module():
    path = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge" / "pool.py"
    spec = importlib.util.spec_from_file_location("source_control_pool", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_canonical_tiers_drive_all_three_consumers():
    from nolan.acquire import engine
    from nolan.keyassets import resolve
    pool = _pool_module()
    assert engine.TIERS is ACQUISITION_TIERS
    assert engine._CURATED is not None
    assert pool._PROVIDER_TIERS is HYBRID_PROVIDER_TIERS
    assert resolve._SOURCE_PREF is KEY_ASSET_SOURCE_PREFERENCES


def test_registry_covers_provider_roster_and_has_unique_tiers():
    roster = set(ImageSearchClient().providers)
    assert not (roster - set(all_source_ids()))
    for table in (ACQUISITION_TIERS, HYBRID_PROVIDER_TIERS, KEY_ASSET_SOURCE_PREFERENCES):
        for intent, order in table.items():
            assert len(order) == len(set(order)), f"duplicate in {intent}"
    assert source_tier_positions("rawpixel")["hybrid"]["art"] == 1
    assert "key_asset" in source_roles("rawpixel")


def test_source_payload_is_secret_free_and_reports_auth_state():
    config = NolanConfig()
    config.image_sources.rawpixel_cookie = "SSESS-do-not-leak"
    config.image_sources.rawpixel_user_agent = "Chrome Test"
    config.image_sources.rawpixel_cdp_url = "http://127.0.0.1:9222"
    payload = build_source_rows(config, probe_cdp=False)
    encoded = json.dumps(payload)
    assert "SSESS-do-not-leak" not in encoded
    raw = next(x for x in payload["sources"] if x["id"] == "rawpixel")
    assert raw["configured"] and raw["config_state"]["rawpixel_cookie"] is True
    assert raw["actions"] == ["refresh_session"]
    assert payload["tiers"]["hybrid"]["general"][0] == "rawpixel"


def test_cdp_action_refuses_non_loopback_targets():
    assert loopback_cdp_url("http://127.0.0.1:9222") == "http://127.0.0.1:9222"
    assert loopback_cdp_url("http://[::1]:9222") == "http://[::1]:9222"
    with pytest.raises(ValueError):
        loopback_cdp_url("https://127.0.0.1:9222")
    with pytest.raises(ValueError):
        loopback_cdp_url("http://example.com:9222")


def test_sources_page_api_and_local_only_refresh(monkeypatch):
    import nolan.source_control as control
    import nolan.source_sessions as sessions
    import nolan.webui.routes.sources as route

    monkeypatch.setattr(control, "cdp_status", lambda _url: {"connected": True, "browser": "Chrome/Test"})
    client = TestClient(create_hub_app(db_path=None, projects_dir=None))
    page = client.get("/sources")
    assert page.status_code == 200 and "Resolved source tiers" in page.text
    response = client.get("/api/sources")
    assert response.status_code == 200
    data = response.json()
    assert data["tiers"]["key_asset"]["footage"][0] == "rawpixel_video"
    assert "RAWPIXEL_COOKIE" in next(x for x in data["sources"] if x["id"] == "rawpixel")["env_fields"]

    # Starlette TestClient is deliberately non-loopback: mutation is refused.
    assert client.post("/api/sources/rawpixel/refresh", json={}).status_code == 403

    # Exercise the successful route with both security gates controlled.
    monkeypatch.setattr(route, "_is_loopback_request", lambda _request: True)
    monkeypatch.setattr(sessions, "refresh_rawpixel_session", lambda **_kw: SimpleNamespace(
        cookie_count=4, has_session_cookie=True, search_rows=100, search_total=10201))
    refreshed = client.post("/api/sources/rawpixel/refresh", json={})
    assert refreshed.status_code == 200
    assert refreshed.json() == {
        "ok": True, "cookie_count": 4, "session_cookie": True,
        "search_rows": 100, "search_total": 10201,
        "message": "Rawpixel session refreshed; secret values were not returned.",
    }
