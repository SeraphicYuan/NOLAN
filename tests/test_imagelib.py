"""Tests for the picture library (catalog + store + semantic search).

A color-based FakeEmbedder stands in for CLIP so the full
catalog -> ChromaDB -> search path is exercised without downloading the model:
a red image embeds near the text "red", a blue image near "blue".
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from nolan.imagelib import Asset, AssetCatalog, ImageLibrary, library_paths


# ----------------------------------------------------------------- fakes/helpers
class FakeEmbedder:
    """Embeds by dominant color (images) / keyword (text) into a 3-vec."""

    _WORDS = {"red": [1.0, 0.0, 0.0], "green": [0.0, 1.0, 0.0], "blue": [0.0, 0.0, 1.0]}

    def embed_image(self, path):
        from PIL import Image
        with Image.open(path) as im:
            r, g, b = im.convert("RGB").resize((1, 1)).getpixel((0, 0))
        m = max(r, g, b) or 1
        return [r / m, g / m, b / m]

    def embed_text(self, text):
        for word, vec in self._WORDS.items():
            if word in text.lower():
                return vec
        return [0.33, 0.33, 0.33]


def _solid_png(path: Path, color):
    from PIL import Image
    Image.new("RGB", (8, 8), color).save(path)
    return path


@pytest.fixture
def lib(tmp_path):
    return ImageLibrary(base_dir=tmp_path / "lib", embedder=FakeEmbedder())


# ----------------------------------------------------------------- catalog
def test_catalog_add_dedup_and_count(tmp_path):
    cat = AssetCatalog(tmp_path / "c.db")
    a = cat.add(Asset(content_hash="h1", path="x.jpg", license="CC0"))
    assert a.id is not None and a.added_at
    again = cat.add(Asset(content_hash="h1", path="x.jpg"))  # same hash
    assert again.id == a.id  # dedup -> same row
    assert cat.count() == 1


def test_catalog_list_filters(tmp_path):
    cat = AssetCatalog(tmp_path / "c.db")
    cat.add(Asset(content_hash="h1", path="1", source="met", license="CC0"))
    cat.add(Asset(content_hash="h2", path="2", source="dpla", license="In Copyright"))
    assert len(cat.list(source="met")) == 1
    assert len(cat.list(license_contains="CC0")) == 1
    cat.add(Asset(content_hash="h3", path="3", status="rejected"))
    assert cat.count("active") == 2 and cat.count() == 3


def test_catalog_set_status_hides_from_active(tmp_path):
    cat = AssetCatalog(tmp_path / "c.db")
    a = cat.add(Asset(content_hash="h1", path="1"))
    cat.set_status(a.id, "rejected")
    assert cat.list(status="active") == []


# ----------------------------------------------------------------- scope paths
def test_library_paths():
    assert library_paths("global") == Path("_library/images")
    assert library_paths("project", "venezuela") == Path("projects/venezuela/imagelib")
    with pytest.raises(ValueError):
        library_paths("project")


# ----------------------------------------------------------------- store
def test_add_file_copies_dedups_probes_dims(lib, tmp_path):
    src = _solid_png(tmp_path / "red.png", (255, 0, 0))
    asset, created = lib.add_file(src, source="test", license="CC0")
    assert created and asset.id
    assert asset.width == 8 and asset.height == 8  # probed via PIL
    assert (lib.base / asset.path).exists()        # copied into library
    # re-adding identical bytes dedups
    asset2, created2 = lib.add_file(src, source="test")
    assert not created2 and asset2.id == asset.id


def test_semantic_search_matches_color(lib, tmp_path):
    lib.add_file(_solid_png(tmp_path / "r.png", (255, 0, 0)), title="red one")
    lib.add_file(_solid_png(tmp_path / "b.png", (0, 0, 255)), title="blue one")
    hits = lib.search("red", k=2)
    assert hits, "expected a hit"
    assert hits[0].asset.title == "red one"   # red image ranks first for "red"
    assert hits[0].score > hits[-1].score or len(hits) == 1


def test_reject_removes_from_search(lib, tmp_path):
    a, _ = lib.add_file(_solid_png(tmp_path / "r.png", (255, 0, 0)), title="red")
    lib.set_status(a.id, "rejected")
    assert lib.search("red", k=5) == []


def test_search_license_filter(lib, tmp_path):
    lib.add_file(_solid_png(tmp_path / "r1.png", (255, 0, 0)), title="cc", license="CC0")
    lib.add_file(_solid_png(tmp_path / "r2.png", (250, 5, 5)), title="incopy",
                 license="In Copyright")
    hits = lib.search("red", k=5, license_contains="CC0")
    assert hits and all("cc0" in (h.asset.license or "").lower() for h in hits)


def test_add_url_downloads_then_ingests(lib, tmp_path):
    img_bytes = (tmp_path / "src.png")
    _solid_png(img_bytes, (0, 255, 0))
    raw = img_bytes.read_bytes()

    def fake_dl(url, out, **kw):
        Path(out).write_bytes(raw)
        return len(raw)

    with patch("nolan.http_client.download_file_sync", side_effect=fake_dl):
        asset, created = lib.add_url("https://x.org/pic.png", source="web", license="CC0")
    assert created and asset.source == "web"
    assert lib.search("green", k=3)[0].asset.id == asset.id


def test_stats(lib, tmp_path):
    lib.add_file(_solid_png(tmp_path / "r.png", (255, 0, 0)))
    s = lib.stats()
    assert s["active"] == 1 and s["total"] == 1


# ----------------------------------------------------------------- thread safety
# Regression: match-broll creates the library in one thread but searches from a
# ThreadPoolExecutor — SQLite must not raise "created in a thread..." there.
def test_catalog_usable_from_other_thread(tmp_path):
    import threading
    cat = AssetCatalog(tmp_path / "c.db")
    cat.add(Asset(content_hash="h1", path="x"))
    out = {}

    def worker():
        out["count"] = cat.count()
        out["got"] = cat.get_by_hash("h1") is not None

    t = threading.Thread(target=worker)
    t.start(); t.join()
    assert out == {"count": 1, "got": True}


def test_library_search_from_other_thread(lib, tmp_path):
    import threading
    lib.add_file(_solid_png(tmp_path / "r.png", (255, 0, 0)), title="red")
    out = {}

    def worker():
        out["hits"] = len(lib.search("red", k=3))

    t = threading.Thread(target=worker)
    t.start(); t.join()
    assert out["hits"] == 1


# ----------------------------------------------------------------- promote
def test_promote_to_global(tmp_path):
    import nolan.imagelib.store as sm
    from nolan.imagelib import ImageLibrary, promote_to_global

    root = tmp_path / "libs"

    def fp(scope="global", project=None):
        return root / (f"project_{project}" if scope == "project" and project else "global")

    fe = FakeEmbedder()
    with patch.object(sm, "library_paths", side_effect=fp):
        plib = ImageLibrary("project", project="p1", embedder=fe)
        a, _ = plib.add_file(_solid_png(tmp_path / "r.png", (255, 0, 0)),
                             title="red", license="CC0", source="met")

        g_asset, created = promote_to_global("p1", a.id, embedder=fe)
        assert created and g_asset.title == "red" and g_asset.license == "CC0"

        glob = ImageLibrary("global", embedder=fe)
        assert glob.catalog.count() == 1
        assert glob.search("red", k=3)[0].asset.id == g_asset.id  # embedded in global

        # idempotent (dedup by content hash)
        _, created2 = promote_to_global("p1", a.id, embedder=fe)
        assert not created2

        with pytest.raises(ValueError):
            promote_to_global("p1", 999, embedder=fe)
