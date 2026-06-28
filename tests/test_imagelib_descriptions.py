"""Phase 1: picture-library descriptions + BGE semantic search."""

import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from nolan.imagelib.catalog import Asset, AssetCatalog
from nolan.imagelib.store import ImageLibrary


def _img(path: Path, color):
    Image.new("RGB", (320, 240), color).save(path)
    return path


def _lib(tmp_path, **kw) -> ImageLibrary:
    return ImageLibrary(scope="global", base_dir=tmp_path / "lib", **kw)


def test_description_stored_and_semantic_search(tmp_path):
    lib = _lib(tmp_path)
    specs = [
        ((200, 50, 50), "a soldier crouching in a muddy World War One trench, grim wartime mood"),
        ((50, 200, 50), "a packed modern football stadium crowd cheering under bright lights"),
        ((50, 50, 200), "an ancient Chinese silk scroll painting of mountains and rivers"),
    ]
    for i, (color, desc) in enumerate(specs):
        p = _img(tmp_path / f"s{i}.png", color)
        lib.add_file(p, source="test", description=desc, embed=False)

    # text->text semantic match should surface the right asset
    top_war = lib.search_by_description("warfare in the trenches", k=3)
    assert top_war and "trench" in (top_war[0].asset.description or "")

    top_sport = lib.search_by_description("a sports arena full of fans", k=3)
    assert top_sport and "stadium" in (top_sport[0].asset.description or "")

    top_art = lib.search_by_description("traditional east asian artwork", k=3)
    assert top_art and "silk scroll" in (top_art[0].asset.description or "")


def test_describer_hook_auto_describes(tmp_path):
    calls = {"n": 0}

    def stub(path):
        calls["n"] += 1
        return "stubbed vision description of a generic scene"

    lib = _lib(tmp_path, describer=stub)
    p = _img(tmp_path / "x.png", (10, 20, 30))
    asset, created = lib.add_file(p, source="test", embed=False)
    assert created and calls["n"] == 1
    assert asset.description == "stubbed vision description of a generic scene"
    # and it's searchable
    hits = lib.search_by_description("generic scene", k=1)
    assert hits and hits[0].asset.id == asset.id


def test_explicit_description_skips_describer(tmp_path):
    def stub(path):
        raise AssertionError("describer must not run when description is given")

    lib = _lib(tmp_path, describer=stub)
    p = _img(tmp_path / "y.png", (1, 2, 3))
    asset, _ = lib.add_file(p, description="explicit", embed=False)
    assert asset.description == "explicit"


def test_backfill_descriptions(tmp_path):
    lib = _lib(tmp_path)
    p = _img(tmp_path / "z.png", (9, 9, 9))
    asset, _ = lib.add_file(p, source="test", embed=False, describe=False)
    assert asset.description is None

    n = lib.backfill_descriptions(lambda path: "a quiet empty room")
    assert n == 1
    assert lib.catalog.get(asset.id).description == "a quiet empty room"
    assert lib.search_by_description("empty room", k=1)


def test_catalog_migration_adds_description_column(tmp_path):
    # simulate an OLD db without the description column
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, content_hash TEXT UNIQUE NOT NULL,
        path TEXT NOT NULL, url TEXT, source TEXT, source_url TEXT, license TEXT,
        title TEXT, width INTEGER, height INTEGER, bytes INTEGER, tags TEXT,
        query TEXT, status TEXT NOT NULL DEFAULT 'active', added_at TEXT NOT NULL)""")
    conn.execute("""INSERT INTO assets (content_hash, path, status, added_at)
                    VALUES ('h1','p1','active','2026-01-01')""")
    conn.commit(); conn.close()

    cat = AssetCatalog(db)  # should migrate, not crash
    cols = {r["name"] for r in cat._conn.execute("PRAGMA table_info(assets)")}
    assert "description" in cols
    # existing row still readable; new write with description works
    a = cat.get_by_hash("h1")
    assert a is not None and a.description is None
    cat.set_description(a.id, "added later")
    assert cat.get(a.id).description == "added later"


def test_hybrid_search_merges_clip_and_description(tmp_path):
    lib = _lib(tmp_path)
    p = _img(tmp_path / "h.png", (120, 60, 30))
    asset, _ = lib.add_file(
        p, source="test", description="a vintage sepia photograph of a city street",
        embed=True)
    hits = lib.search_hybrid("old photo of a town", k=3)
    assert hits and hits[0].asset.id == asset.id
    assert hits[0].score > 0
