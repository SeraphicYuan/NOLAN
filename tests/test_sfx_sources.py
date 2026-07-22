"""SFX source-adapter registry + curation core + the /sfx routes.

The control tab is data-driven off the adapter registry (nolan.sound.sources) — so these honesty-test
that the registry describes the REAL ops (crawl/add/remove), that its cue-kind choices come from the
registry (not a hardcoded copy), that the shared curation core is importable + validates before any
network call, and that the routes register + serve the sources through the ASGI layer."""
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_freesound_source_registered_and_described():
    from nolan.sound.registry import KINDS
    from nolan.sound.sources import get_source, list_sources
    fs = get_source("freesound")
    assert fs is not None
    assert "freesound" in [s.id for s in list_sources()]
    d = fs.describe()
    assert d["id"] == "freesound" and d["label"] == "Freesound"
    assert d["description"], "a tile needs a one-line description"   # drives the Control-tab tile
    ops = {c["op"] for c in d["controls"]}
    assert ops == {"crawl", "add", "remove"}, ops
    # the Add form's cue-kind choices MUST equal the live registry (no hardcoded fork)
    add = next(c for c in d["controls"] if c["op"] == "add")
    kind_field = next(f for f in add["fields"] if f["name"] == "kind")
    assert kind_field["choices"] == list(KINDS)
    assert kind_field["required"] is True
    assert get_source("does-not-exist") is None


def test_run_rejects_unknown_op():
    from nolan.sound.sources import get_source
    with pytest.raises(ValueError):
        get_source("freesound").run("nonsense", {}, lambda _m: None)


def test_curate_core_importable_and_validates_kind_first():
    """add_sound validates the cue-kind BEFORE any network fetch — an unknown kind raises CurateError
    immediately (so a typo never hits Freesound)."""
    from nolan.sound.curate import CurateError, add_sound, remove_sound
    assert callable(add_sound) and callable(remove_sound)
    assert issubclass(CurateError, Exception)
    with pytest.raises(CurateError):
        add_sound("12345", "not-a-real-cue-kind")


def test_catalog_stats_and_empty_search(tmp_path):
    from nolan.sound.catalog import SoundCatalog
    cat = SoundCatalog(db_path=tmp_path / "cat.db")
    try:
        stats = cat.stats()
        assert set(stats) >= {"total", "in_library"}
        assert cat.search("", limit=5) == []          # empty catalog → no rows (no crash)
    finally:
        cat.close()


def test_sfx_routes_register_and_serve_sources():
    """Register the route module on a bare app and hit /api/sfx/sources THROUGH the ASGI layer
    (a route that 500s on a missing import wouldn't be caught by importing the function alone)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from nolan.webui.jobs import get_job_manager
    from nolan.webui.routes import sfx as sfx_routes
    app = FastAPI()
    ctx = SimpleNamespace(templates_dir=Path("src/nolan/templates"), job_manager=get_job_manager())
    sfx_routes.register(app, ctx)
    client = TestClient(app)
    r = client.get("/api/sfx/sources")
    assert r.status_code == 200
    src = r.json()["sources"]
    assert any(s["id"] == "freesound" for s in src)
    # kinds endpoint is registry-backed and must not be empty
    assert client.get("/api/sfx/kinds").json()["kinds"]
