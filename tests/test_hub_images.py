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
