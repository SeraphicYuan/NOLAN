"""Artvee's artist-as-collection contract with the Visual Lab discovery tier."""

import html as _html
from pathlib import Path

from nolan.artvee import (
    ArtveeArtistProfile, parse_artist_index, parse_artist_profile, parse_listing,
)
from nolan.imagelib.taxonomy import image_kind


PROFILE_HTML = """
<h1 class="entry-title">Alphonse Mucha</h1>
<div class="abdate">Czech, 1860-1939</div>
<div class="term-description blrclass"><p>First paragraph.</p><p>Second &amp; final.</p></div>
<div>203 items</div>
<img class="imspanc" src="https://mdl.artvee.com/artpic/Alphonse-Mucha-1.jpg" />
"""


def _tile(sk="26697po", data_id="900", title="Lance parfum (1896)",
          category="Posters"):
    payload = _html.escape(
        '{"sdlimagesize":"1287 x 1800px","hdlimagesize":"4000 x 5600px",'
        '"sdlfilesize":"2 MB","hdlfilesize":"20 MB","sk":"%s"}' % sk,
        quote=True)
    return f"""
    <div class="product-grid-item product">
      <div class="product-element-top" data-id="{data_id}" data-sk="{payload}"
           data-url="/dl/lance-parfum"></div>
      <h3 class="product-title"><a href="https://artvee.com/dl/lance-parfum/">{title}</a></h3>
      <div class="woodmart-product-brands-links">
        <a href="https://artvee.com/artist/alphonse-mucha/">Alphonse Mucha</a>
      </div>
      <div class="woodmart-product-cats">
        <a href="https://artvee.com/c/posters/">{category}</a>
      </div>
    </div>
    """


def test_artist_profile_is_collection_metadata_not_a_caption():
    p = parse_artist_profile(PROFILE_HTML, "alphonse-mucha")
    assert p.name == "Alphonse Mucha"
    assert (p.nationality, p.birth_year, p.death_year) == ("Czech", 1860, 1939)
    assert p.biography == "First paragraph. Second & final."
    assert p.item_count == 203


def test_complete_artist_index_cards_have_stable_slug_and_count():
    body = """
    <a href="https://artvee.com/artist/alphonse-mucha/">
      <h3 class="category-title"><span>Alphonse Mucha</span>
      <mark class="count">Czech, 203 Items</mark></h3></a>
    <a href="https://artvee.com/artist/paul-klee/">
      <h3><span>Paul Klee</span><mark>Swiss, 1,234 Items</mark></h3></a>
    """
    rows = parse_artist_index(body)
    assert [(r.slug, r.name, r.nationality, r.item_count) for r in rows] == [
        ("alphonse-mucha", "Alphonse Mucha", "Czech", 203),
        ("paul-klee", "Paul Klee", "Swiss", 1234),
    ]


def test_listing_keeps_exact_date_and_durable_basic_download():
    row = parse_listing("<main>" + _tile() + "</main>")[0]
    assert row.title == "Lance parfum"
    assert row.date_text == "1896"
    assert row.category == "Posters"
    assert row.standard_download_url == "https://mdl.artvee.com/sdl/26697posdl.jpg"
    assert "/hdl/" not in row.standard_download_url
    assert image_kind(row.category) == "poster"


def test_artvee_harvest_rows_match_visual_lab_fields(monkeypatch):
    import nolan.artvee as artvee
    from nolan.imagelib.harvest import HarvestReport, artvee_items

    profile = ArtveeArtistProfile(
        slug="alphonse-mucha", name="Alphonse Mucha", nationality="Czech",
        birth_year=1860, death_year=1939, biography="Artist biography.", item_count=203,
        url="https://artvee.com/artist/alphonse-mucha/")

    class FakeClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def artist_profile(self, _artist): return profile
        def _get(self, _url, params=None):
            assert params == {"orderby": "title_asc", "per_page": 70}
            return "<main>" + _tile() + "</main>"

    monkeypatch.setattr(artvee, "ArtveeClient", FakeClient)
    report = HarvestReport(collection="pilot")
    rows = list(artvee_items(limit=5, artist="alphonse-mucha", report=report))
    assert len(rows) == 1 and report.exhausted
    row = rows[0]
    assert row.source_ref == "artvee:900"
    assert row.title == "Lance parfum"
    assert row.creator == "Alphonse Mucha"
    assert row.date_text == "1896"
    assert row.classification == "Posters"
    assert row.description is None                 # catalog fields are not a model caption
    assert row.url.endswith("/sdl/26697posdl.jpg") # basic download, not premium
    assert row.artist_record.biography == "Artist biography."
    assert row.artist_record.nationality == "Czech"


def test_artvee_fast_thumbnail_mode_is_parallel_raw_and_no_clip(monkeypatch, tmp_path):
    import nolan.http_client as http
    import nolan.imagelib.store as store
    from nolan.imagelib.harvest import SOURCES
    from nolan.imagelib.store import ImageLibrary

    adapter = SOURCES["artvee"]
    assert adapter.fast_thumbnails and 2 <= adapter.thumbnail_concurrency <= 8

    lib = ImageLibrary(base_dir=tmp_path / "lib")
    monkeypatch.setattr(
        http, "download_file_sync",
        lambda _url, dest, headers=None: Path(dest).write_bytes(b"not-decoded-image-bytes"))
    monkeypatch.setattr(store, "_shrink", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("raw thumbnail mode must not invoke PIL/shrink")))
    got = lib._fetch_thumb("artvee:1", "https://mdl.artvee.com/ft/1po.jpg", raw=True)
    assert got.read_bytes() == b"not-decoded-image-bytes"
