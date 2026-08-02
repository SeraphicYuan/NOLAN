"""Hub picture-library endpoints (in-process, no CLIP / no network).

library_paths is redirected to a tmp dir and the library is populated with a
color-based FakeEmbedder, so list/raw/reject/page are exercised without loading
the real CLIP model. (Semantic search via /api/images/search needs CLIP and is
covered at the library level in test_imagelib.py.)
"""

from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

import nolan.imagelib.store as store_mod
from nolan.imagelib import ImageLibrary
from nolan.hub import create_hub_app


class FakeEmbedder:
    def embed_image(self, path):
        from PIL import Image
        with Image.open(path) as im:
            r, g, b = im.convert("RGB").resize((1, 1)).getpixel((0, 0))
        m = max(r, g, b) or 1
        return [r / m, g / m, b / m]

    def embed_text(self, text):
        return [0.33, 0.33, 0.33]


def _png(path, color):
    from PIL import Image
    Image.new("RGB", (800, 600), color).save(path)  # floor-passing: ingest gate rejects tiny files
    return path


def test_hub_image_endpoints(tmp_path):
    root = tmp_path / "lib"

    def fake_paths(scope="global", project=None):
        return root / (f"project_{project}" if scope == "project" and project else "global")

    with patch.object(store_mod, "library_paths", side_effect=fake_paths):
        lib = ImageLibrary("global", embedder=FakeEmbedder())
        asset, _ = lib.add_file(_png(tmp_path / "r.png", (255, 0, 0)),
                                title="red one", source="test", license="CC0")

        client = TestClient(create_hub_app(db_path=None, projects_dir=None))

        # page renders
        assert client.get("/images").status_code == 200

        # list returns the asset
        data = client.get("/api/images/list?scope=global").json()
        assert len(data["results"]) == 1
        rec = data["results"][0]
        assert rec["title"] == "red one" and rec["license"] == "CC0"

        # raw serves the actual image bytes
        raw = client.get(rec["raw"])
        assert raw.status_code == 200 and raw.headers["content-type"].startswith("image/")

        # reject hides it
        assert client.post(f"/api/images/{asset.id}/reject", json={"scope": "global"}).json()["ok"]
        assert client.get("/api/images/list?scope=global").json()["results"] == []

    # raw 404 for missing asset
    with patch.object(store_mod, "library_paths", side_effect=fake_paths):
        client = TestClient(create_hub_app(db_path=None, projects_dir=None))
        assert client.get("/api/images/raw?scope=global&id=9999").status_code == 404


def test_hub_discovery_tier_endpoints(tmp_path):
    """Visual Lib over the hub: a not-held row is browsable (its thumbnail is what `raw` serves),
    it does NOT appear in the held list, and `fetch` promotes it into the held library."""
    root = tmp_path / "lib"
    blob = _png(tmp_path / "src.png", (0, 0, 255)).read_bytes()

    def fake_paths(scope="global", project=None):
        return root / "global"

    def fake_dl(url, out, **kw):
        Path(out).write_bytes(blob)
        return len(blob)

    with patch.object(store_mod, "library_paths", side_effect=fake_paths), \
         patch.object(store_mod, "ClipEmbedder", FakeEmbedder), \
         patch("nolan.http_client.download_file_sync", side_effect=fake_dl):
        lib = ImageLibrary("global", embedder=FakeEmbedder())
        a, created = lib.add_discovery(
            source_ref="artic:42", thumb_url="https://www.artic.edu/iiif/2/x/full/600,/0/d.jpg",
            url="https://www.artic.edu/iiif/2/x/full/1686,/0/d.jpg", source="artic",
            title="Water Lilies", creator="Claude Monet", date_text="1906",
            license="CC0 (Art Institute of Chicago)", width=3000, height=2000)
        assert created

        client = TestClient(create_hub_app(db_path=None, projects_dir=None))

        # the held list must NOT see it
        assert client.get("/api/images/list?scope=global").json()["results"] == []

        # the discovery endpoint does, with its catalog identity and honest coverage
        d = client.get("/api/images/discover?scope=global").json()
        assert [r["title"] for r in d["results"]] == ["Water Lilies"]
        assert d["results"][0]["creator"] == "Claude Monet" and d["results"][0]["held"] == 0
        assert d["stats"]["discovery"] == 1 and d["stats"]["described_pct"] == 0.0

        # raw serves the stored thumbnail, so the tier is browsable
        assert client.get(d["results"][0]["raw"]).status_code == 200

        # fetch promotes it: it leaves the discovery tier and joins the held one
        r = client.post(f"/api/images/{a.id}/fetch", json={"scope": "global", "tier": "stock"})
        assert r.status_code == 200 and r.json()["promoted"]
        assert client.get("/api/images/discover?scope=global").json()["results"] == []
        assert len(client.get("/api/images/list?scope=global").json()["results"]) == 1


def test_hub_visual_lib_page_and_registry_endpoints(tmp_path):
    """The Visual Lib page and its TIER-level endpoints. The source picker is served from the
    harvest registry so the UI cannot drift from the adapters (pitfall #5)."""
    root = tmp_path / "lib"

    def fake_paths(scope="global", project=None):
        return root / "global"

    with patch.object(store_mod, "library_paths", side_effect=fake_paths), \
         patch.object(store_mod, "ClipEmbedder", FakeEmbedder):
        client = TestClient(create_hub_app(db_path=None, projects_dir=None))

        assert client.get("/visual-lib").status_code == 200

        from nolan.imagelib.harvest import SOURCES
        srcs = client.get("/api/visuallib/sources").json()["sources"]
        assert {s["id"] for s in srcs} == set(SOURCES), "the picker must come from the registry"
        assert all(s["rights"] for s in srcs), "every source states its rights"
        met = [s for s in srcs if s["id"] == "met"][0]
        assert "Photographs" in met["departments"]

        cols = client.get("/api/visuallib/collections").json()
        assert cols["collections"] == [] and cols["stats"]["discovery"] == 0

        # an unknown source is refused rather than started
        r = client.post("/api/visuallib/harvest", json={"source": "louvre", "limit": 5})
        assert r.status_code == 400 and "louvre" in r.json()["detail"]
        # an explicit limit of 0 is refused, never silently widened to the default batch
        assert client.post("/api/visuallib/harvest",
                           json={"source": "artic", "limit": 0}).status_code == 400
        assert client.post("/api/visuallib/caption", json={"limit": 0}).status_code == 400
        assert client.post("/api/visuallib/harvest",
                           json={"source": "artic", "limit": "many"}).status_code == 400
        # Artist-scoped sources fail at the request boundary, not later in a background job.
        missing_artist = client.post(
            "/api/visuallib/harvest", json={"source": "artvee", "limit": 5})
        assert missing_artist.status_code == 400 and "artist" in missing_artist.json()["detail"]


def test_hub_add_by_url(tmp_path):
    root = tmp_path / "lib"
    raw = (tmp_path / "src.png")
    _png(raw, (0, 255, 0))
    blob = raw.read_bytes()

    def fake_paths(scope="global", project=None):
        return root / "global"

    def fake_dl(url, out, **kw):
        Path(out).write_bytes(blob)
        return len(blob)

    with patch.object(store_mod, "library_paths", side_effect=fake_paths), \
         patch.object(store_mod, "ClipEmbedder", FakeEmbedder), \
         patch("nolan.http_client.download_file_sync", side_effect=fake_dl):
        client = TestClient(create_hub_app(db_path=None, projects_dir=None))
        r = client.post("/api/images/add", json={"url": "https://x.org/a.png",
                                                 "source": "web", "license": "CC0"})
        assert r.status_code == 200 and r.json()["created"]
        assert len(client.get("/api/images/list?scope=global").json()["results"]) == 1
        # missing url -> 400
        assert client.post("/api/images/add", json={}).status_code == 400


def test_extract_ingest_to_library_uses_local_files(tmp_path):
    """Extract -> library ingest reuses downloaded files (no re-fetch) and dedups."""
    from nolan.webui.operations import _ingest_results_to_library
    from nolan.image_search import ImageSearchResult
    from nolan.imagelib import ImageLibrary

    root = tmp_path / "lib"
    img = _png(tmp_path / "a.png", (255, 0, 0))
    results = [ImageSearchResult(url="https://x.org/a.png", source="gutenberg",
                                 license="Public domain", title="plate 1")]
    records = [{"url": "https://x.org/a.png", "local_path": str(img)}]

    with patch.object(store_mod, "library_paths", side_effect=lambda scope="global", project=None: root / "global"), \
         patch.object(store_mod, "ClipEmbedder", FakeEmbedder):
        added = _ingest_results_to_library(results, records, "global", None, "https://page")
        assert added == 1
        lib = ImageLibrary("global", embedder=FakeEmbedder())
        assert lib.catalog.count() == 1
        a = lib.list()[0]
        assert a.query == "https://page" and a.license == "Public domain"
        # idempotent
        assert _ingest_results_to_library(results, records, "global", None, "https://page") == 0


def test_hub_promote(tmp_path):
    from nolan.imagelib import ImageLibrary
    root = tmp_path / "lib"

    def fake_paths(scope="global", project=None):
        return root / (f"project_{project}" if scope == "project" and project else "global")

    with patch.object(store_mod, "library_paths", side_effect=fake_paths), \
         patch.object(store_mod, "ClipEmbedder", FakeEmbedder):
        plib = ImageLibrary("project", project="p1", embedder=FakeEmbedder())
        a, _ = plib.add_file(_png(tmp_path / "r.png", (255, 0, 0)), title="red")

        client = TestClient(create_hub_app(db_path=None, projects_dir=None))
        r = client.post(f"/api/images/{a.id}/promote", json={"project": "p1"})
        assert r.status_code == 200 and r.json()["ok"]
        assert client.get("/api/images/list?scope=global").json()["results"][0]["title"] == "red"
        # missing project -> 400
        assert client.post(f"/api/images/{a.id}/promote", json={}).status_code == 400


def test_every_registered_adapter_is_describable_without_running_a_crawl():
    """A MENU MUST NEVER RUN A CRAWL'S PRECONDITIONS.

    `/api/visuallib/sources` built its list by calling `collection()` on every adapter. An adapter
    whose collection needs an argument therefore 500'd the whole route and rendered the Sources tab
    EMPTY for every source — including one with 69,117 indexed rows. `describe()` answers from the
    registry (and `source_registry` for identity/rights), so one unwalkable source costs its own row
    and nothing else.

    Asserted as a PROPERTY of the mechanism, not against whichever adapters happen to be registered
    today — a roster-shaped test would pass or fail on someone else's in-flight source."""
    from nolan.imagelib.harvest import SOURCES, SourceAdapter

    for name, adapter in SOURCES.items():
        d = adapter.describe()
        assert d["title"], f"{name}: no menu title"
        assert d["rights"], f"{name}: a source must state its rights"
        assert not d["error"], f"{name} raised while being described: {d['error']}"

    # an adapter that CANNOT be walked whole is described anyway, from the shared registry
    def _explodes(*a, **kw):
        raise ValueError("this source requires a --query")

    guarded = SourceAdapter(id="artvee", collection=_explodes, items=iter,
                            enumeration="search-ranked", requires_query=True)
    d = guarded.describe()
    assert d["requires"] and not d["error"]
    assert d["title"] and d["rights"], "identity and rights come from source_registry, not the crawl"

    # and one that raises UNEXPECTEDLY degrades to its own row rather than the whole menu
    boom = SourceAdapter(id="artvee", collection=_explodes, items=iter, enumeration="bulk-listing")
    d = boom.describe()
    assert d["error"] and d["title"], "an unexpected failure must not erase the source"


def test_source_coverage_never_mixes_measured_and_unmeasured_collections(tmp_path):
    """"Unknown must read as unknown, never as full" has to survive AGGREGATION.

    `Collection.coverage` is honest per collection, but the Sources row summed EVERY collection's
    rows over only the denominators that existed — two different populations in one ratio. Live:
    artvee read 69,117/65,720 = 105% because 3 of its 480 collections publish no upstream count,
    and PDIA read a flat 100% while 576 of its 577 collections, holding 9,523 of its 11,197 rows,
    had no denominator at all. A source that is 40% measured must not render as fully indexed."""
    from nolan.imagelib.catalog import Collection
    root = tmp_path / "lib"

    def fake_paths(scope="global", project=None):
        return root / "global"

    with patch.object(store_mod, "library_paths", side_effect=fake_paths), \
         patch.object(store_mod, "ClipEmbedder", FakeEmbedder):
        lib = ImageLibrary(scope="global")
        known = lib.catalog.upsert_collection(Collection(
            slug="known", source="artic", title="measured", rights="CC0", upstream_count=100))
        blind = lib.catalog.upsert_collection(Collection(
            slug="blind", source="artic", title="no denominator", rights="CC0"))
        from nolan.imagelib.catalog import Asset
        for col, n, tag in ((known, 40, "k"), (blind, 60, "b")):
            for i in range(n):
                lib.catalog.add(Asset(content_hash=f"{tag}{i}", path="", title=f"{tag}{i}",
                                      source="artic", source_ref=f"artic:{tag}{i}",
                                      collection_id=col.id, held=0, license="CC0"))

        client = TestClient(create_hub_app(db_path=None, projects_dir=None))
        row = next(s for s in client.get("/api/visuallib/sources").json()["sources"]
                   if s["id"] == "artic")

    assert row["indexed"] == 100, "the row count is every row, unchanged"
    assert row["upstream"] == 100, "the denominator covers only the measured collection"
    assert row["rows_measured"] == 40, "so the numerator must too — 40/100, not 100/100"
    assert row["collections_unmeasured"] == 1 and row["rows_unmeasured"] == 60, (
        "what the ratio excludes has to be reported, or 40% reads as the whole story")
