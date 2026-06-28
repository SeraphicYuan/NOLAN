"""Tests for the link -> assets extractors (fast, no network).

The high-def heuristics and site parsers are exercised against inline HTML
fixtures; the only network-touching helpers (fetch_html, the Met API) are not
called here.
"""

from unittest.mock import patch

import pytest

from nolan.image_search import ImageSearchResult
from nolan.extractors import extract_from_url, get_extractor, resolve_result, resolve_results
from nolan.extractors import _best_candidate, _rewrite_thumbnail, _maximize_iiif
from nolan.extractors.base import (
    is_image_url, looks_like_junk, resolve, srcset_largest,
)
from nolan.extractors.archive import ArchiveExtractor
from nolan.extractors.generic import GenericExtractor
from nolan.extractors.gutenberg import GutenbergExtractor
from nolan.extractors.iiif import IIIFExtractor
from nolan.extractors.loc import LoCExtractor, _split_dims
from nolan.extractors.wikimedia import WikimediaExtractor, original_upload_url


# ---------------------------------------------------------------- helpers
def test_is_image_url():
    assert is_image_url("https://x.com/a/b.JPG")
    assert is_image_url("https://x.com/a/b.png?v=2".split("?")[0])
    assert not is_image_url("https://x.com/page.html")
    assert not is_image_url(None)


def test_looks_like_junk():
    assert looks_like_junk("https://x.com/img/logo.png")
    assert looks_like_junk("https://x.com/assets/sprite-icons.png")
    assert not looks_like_junk("https://x.com/photos/sunset.jpg")


def test_srcset_largest():
    s = "small.jpg 200w, medium.jpg 800w, big.jpg 1600w"
    assert srcset_largest(s) == "big.jpg"
    assert srcset_largest("a.jpg 1x, b.jpg 2x") == "b.jpg"
    assert srcset_largest(None) is None


def test_resolve_relative_and_protocol():
    base = "https://site.com/dir/page.html"
    assert resolve(base, "images/x.jpg") == "https://site.com/dir/images/x.jpg"
    assert resolve(base, "//cdn.com/x.jpg") == "https://cdn.com/x.jpg"
    assert resolve(base, "data:image/png;base64,AAAA") is None
    assert resolve(base, "javascript:void(0)") is None


# ---------------------------------------------------------------- dispatch
@pytest.mark.parametrize("url,expected", [
    ("https://www.gutenberg.org/files/21790/21790-h/21790-h.htm", "gutenberg"),
    ("https://commons.wikimedia.org/wiki/File:Foo.jpg", "wikimedia"),
    ("https://en.wikipedia.org/wiki/Earth", "wikimedia"),
    ("https://www.metmuseum.org/art/collection/search/436535", "met"),
    ("https://archive.org/details/LonBruce45", "archive"),
    ("https://www.loc.gov/item/2021669449/", "loc"),
    ("https://iiif.io/api/cookbook/recipe/0009-book-1/manifest.json", "iiif"),
    ("https://example.org/iiif/2/abc/info.json", "iiif"),
    ("https://example.com/blog/post", "web"),
])
def test_dispatch(url, expected):
    assert get_extractor(url).name == expected


# ---------------------------------------------------------------- generic
def test_generic_prefers_linked_fullres_over_thumb():
    html = """
    <html><head><meta property="og:image" content="https://s.com/hero.jpg"></head>
    <body>
      <a href="images/illus-048.jpg"><img src="images/p048-t.png" width="275"></a>
      <img src="/icons/logo.png" width="32" height="32">
      <img src="/tiny.png" width="20" height="20">
      <img src="/photos/big.jpg" srcset="/photos/sm.jpg 300w, /photos/lg.jpg 1200w">
    </body></html>
    """
    results = GenericExtractor().extract("https://s.com/book/page.html", html)
    urls = [r.url for r in results]

    # og:image hero comes first
    assert urls[0] == "https://s.com/hero.jpg"
    # linked full-res chosen over the embedded thumbnail
    assert "https://s.com/book/images/illus-048.jpg" in urls
    full = next(r for r in results if r.url.endswith("illus-048.jpg"))
    assert full.thumbnail_url == "https://s.com/book/images/p048-t.png"
    # srcset largest chosen
    assert "https://s.com/photos/lg.jpg" in urls
    # icon + tiny image filtered out
    assert not any("logo.png" in u for u in urls)
    assert not any("tiny.png" in u for u in urls)


def test_generic_dedupes():
    html = '<a href="/a.jpg"><img src="/a.jpg"></a><img src="/a.jpg">'
    results = GenericExtractor().extract("https://s.com/", html)
    assert sum(1 for r in results if r.url == "https://s.com/a.jpg") == 1


def test_limit_applies():
    html = "".join(f'<img src="/p{i}.jpg">' for i in range(10))
    results = extract_from_url("https://s.com/", html=html, fetch=False, limit=4)
    assert len(results) == 4


# ---------------------------------------------------------------- gutenberg
def test_gutenberg_license_and_fullres():
    html = '<a href="images/illus-048.jpg"><img src="images/p048-t.png" width="275"></a>'
    results = GutenbergExtractor().extract(
        "https://www.gutenberg.org/files/21790/21790-h/21790-h.htm", html)
    assert len(results) == 1
    r = results[0]
    assert r.url.endswith("/images/illus-048.jpg")
    assert r.license == "Public domain (Project Gutenberg)"
    assert r.source == "gutenberg"


# ---------------------------------------------------------------- wikimedia
def test_wikimedia_original_upload_url():
    thumb = ("https://upload.wikimedia.org/wikipedia/commons/thumb/"
             "c/cb/Name.jpg/960px-Name.jpg")
    assert original_upload_url(thumb) == (
        "https://upload.wikimedia.org/wikipedia/commons/c/cb/Name.jpg")
    # already-original is unchanged
    orig = "https://upload.wikimedia.org/wikipedia/commons/c/cb/Name.jpg"
    assert original_upload_url(orig) == orig


def test_wikimedia_extracts_originals_from_thumbs():
    html = """
    <a href="//upload.wikimedia.org/wikipedia/commons/c/cb/Earth.jpg">Original file</a>
    <img src="//upload.wikimedia.org/wikipedia/commons/thumb/c/cb/Earth.jpg/500px-Earth.jpg">
    <img src="/static/icons/logo.png">
    """
    results = WikimediaExtractor().extract(
        "https://commons.wikimedia.org/wiki/File:Earth.jpg", html)
    urls = {r.url for r in results}
    # both the explicit original and the de-thumbed src collapse to one original
    assert urls == {"https://upload.wikimedia.org/wikipedia/commons/c/cb/Earth.jpg"}
    assert all(r.source == "wikimedia" for r in results)


# ---------------------------------------------------------------- iiif
import json

V3_MANIFEST = json.dumps({
    "@context": "http://iiif.io/api/presentation/3/context.json",
    "type": "Manifest", "label": {"en": ["Book"]},
    "items": [
        {"type": "Canvas", "label": {"en": ["p1"]}, "items": [{"type": "AnnotationPage", "items": [
            {"type": "Annotation", "body": {
                "id": "https://x.org/img1.jpg", "type": "Image",
                "service": [{"id": "https://x.org/iiif/img1", "type": "ImageService3"}]}}]}]},
        {"type": "Canvas", "items": [{"type": "AnnotationPage", "items": [
            {"type": "Annotation", "body": {"id": "https://x.org/plain.jpg", "type": "Image"}}]}]},
    ],
})

V2_MANIFEST = json.dumps({
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@type": "sc:Manifest", "label": "Old",
    "sequences": [{"canvases": [{"@type": "sc:Canvas", "images": [{"resource": {
        "@id": "https://x.org/full.jpg",
        "service": {"@id": "https://x.org/iiif/2/abc",
                    "@context": "http://iiif.io/api/image/2/context.json"}}}]}]}],
})

INFO_JSON = json.dumps({
    "@context": "http://iiif.io/api/image/2/context.json",
    "@id": "https://x.org/iiif/2/abc", "width": 5000, "height": 4000,
})


def test_iiif_v3_manifest():
    r = extract_from_url("https://x.org/manifest.json", html=V3_MANIFEST, fetch=False)
    urls = [x.url for x in r]
    # service-backed canvas -> built at max; serviceless canvas -> direct id
    assert "https://x.org/iiif/img1/full/max/0/default.jpg" in urls
    assert "https://x.org/plain.jpg" in urls
    assert all(x.source == "iiif" for x in r)


def test_iiif_v2_manifest_uses_full_size():
    r = extract_from_url("https://x.org/manifest.json", html=V2_MANIFEST, fetch=False)
    # v2 image service -> 'full' (not 'max')
    assert r[0].url == "https://x.org/iiif/2/abc/full/full/0/default.jpg"


def test_iiif_info_json():
    r = extract_from_url("https://x.org/iiif/2/abc/info.json", html=INFO_JSON, fetch=False)
    assert len(r) == 1
    assert r[0].url == "https://x.org/iiif/2/abc/full/full/0/default.jpg"
    assert (r[0].width, r[0].height) == (5000, 4000)


def test_iiif_ignores_non_iiif_json():
    # JSON that isn't IIIF -> nothing (extractor matched URL but content isn't a manifest)
    assert IIIFExtractor().extract("https://x.org/manifest.json", '{"foo": 1}') == []


# ---------------------------------------------------------------- loc
def test_loc_split_dims():
    clean, h, w = _split_dims("https://tile.loc.gov/x/full/pct:100/0/default.jpg#h=2721&w=1789")
    assert clean.endswith("default.jpg") and (h, w) == (2721, 1789)
    assert _split_dims("https://x/a.jpg") == ("https://x/a.jpg", None, None)


# ---------------------------------------------------------------- archive
def test_archive_identifier():
    ex = ArchiveExtractor()
    assert ex._identifier("https://archive.org/details/LonBruce45") == "LonBruce45"
    assert ex._identifier("https://archive.org/download/foo/bar.jpg") == "foo"
    assert ex.matches("https://archive.org/details/x")
    assert not ex.matches("https://archive.org/about")


# ---------------------------------------------------------------- resolve
def test_best_candidate_prefers_largest():
    orig = ImageSearchResult(url="thumb.jpg")
    found = [
        ImageSearchResult(url="a.jpg", width=100, height=100),
        ImageSearchResult(url="b.jpg", width=2000, height=3000),
        ImageSearchResult(url="c.jpg"),  # no dims
    ]
    assert _best_candidate(found, orig).url == "b.jpg"


def test_best_candidate_skips_same_url():
    orig = ImageSearchResult(url="same.jpg")
    assert _best_candidate([ImageSearchResult(url="same.jpg")], orig) is None


def test_maximize_iiif():
    assert _maximize_iiif("http://h/iiif/2/x/full/730,/0/default.jpg") == \
        "http://h/iiif/2/x/full/max/0/default.jpg"
    assert _maximize_iiif("http://h/iiif/2/x/full/!400,400/0/default.jpg") == \
        "http://h/iiif/2/x/full/max/0/default.jpg"
    # already max/full or non-IIIF -> unchanged
    assert _maximize_iiif("http://h/iiif/2/x/full/max/0/default.jpg").endswith("/full/max/0/default.jpg")
    assert _maximize_iiif("https://example.com/photo.jpg") == "https://example.com/photo.jpg"


def test_resolve_maximizes_sized_iiif_from_page():
    r = ImageSearchResult(url="https://thumbs/clip/150x150/abc", source_url="https://cali/item")
    sized = [ImageSearchResult(url="http://arch/iiif/2/c:1/full/730,/0/default.jpg",
                               width=730, height=571)]
    with patch("nolan.extractors.extract_from_url", return_value=sized):
        out = resolve_result(r)
    assert out.url == "http://arch/iiif/2/c:1/full/max/0/default.jpg"
    assert out.width is None and out.height is None  # dims were for the 730 rendition


def test_rewrite_contentdm_thumbnail():
    thumb = "http://cdm17228.contentdm.oclc.org/utils/getthumbnail/collection/imc/id/22577"
    assert _rewrite_thumbnail(thumb) == (
        "http://cdm17228.contentdm.oclc.org/digital/iiif/imc/22577/full/max/0/default.jpg")
    assert _rewrite_thumbnail("https://example.com/photo.jpg") is None
    assert _rewrite_thumbnail(None) is None


def test_resolve_via_url_rewrite_no_page_fetch():
    r = ImageSearchResult(url="http://x.contentdm.oclc.org/utils/getthumbnail/collection/c/id/9",
                          source="dpla")  # note: no source_url — rewrite must still work
    with patch("nolan.extractors._verify_image", return_value=True), \
         patch("nolan.extractors.extract_from_url") as ext:
        out = resolve_result(r)
    ext.assert_not_called()  # rewrite short-circuits before any page fetch
    assert out.url.endswith("/digital/iiif/c/9/full/max/0/default.jpg")
    assert out.thumbnail_url.endswith("getthumbnail/collection/c/id/9")
    assert out.source == "dpla+resolved"


def test_resolve_rewrite_falls_back_when_unverified():
    r = ImageSearchResult(url="http://x.contentdm.oclc.org/utils/getthumbnail/collection/c/id/9",
                          source_url="https://provider.org/item")
    full = [ImageSearchResult(url="https://provider.org/big.jpg", width=1500, height=1500)]
    with patch("nolan.extractors._verify_image", return_value=False), \
         patch("nolan.extractors.extract_from_url", return_value=full):
        out = resolve_result(r)
    assert out.url == "https://provider.org/big.jpg"  # fell through to page extraction


def test_resolve_upgrades_thumbnail_to_fullres():
    r = ImageSearchResult(url="https://dpla/thumb.jpg",
                          source_url="https://provider.org/item/1", source="dpla")
    full = [ImageSearchResult(url="https://provider.org/full.jpg", width=2400, height=1800)]
    with patch("nolan.extractors.extract_from_url", return_value=full):
        out = resolve_result(r)
    assert out.url == "https://provider.org/full.jpg"
    assert out.thumbnail_url == "https://dpla/thumb.jpg"  # old image demoted
    assert (out.width, out.height) == (2400, 1800)
    assert out.source == "dpla+resolved"


def test_resolve_no_source_url_unchanged():
    r = ImageSearchResult(url="x.jpg", source="dpla")  # no source_url
    assert resolve_result(r).url == "x.jpg"


def test_resolve_no_candidates_unchanged():
    r = ImageSearchResult(url="x.jpg", source_url="https://p/item")
    with patch("nolan.extractors.extract_from_url", return_value=[]):
        assert resolve_result(r).url == "x.jpg"


def test_resolve_extractor_error_unchanged():
    r = ImageSearchResult(url="x.jpg", source_url="https://p/item")
    with patch("nolan.extractors.extract_from_url", side_effect=Exception("boom")):
        out = resolve_result(r)
    assert out.url == "x.jpg" and out.source is None


def test_resolve_results_batch():
    rs = [ImageSearchResult(url=f"t{i}.jpg", source_url=f"https://p/{i}") for i in range(3)]
    full = [ImageSearchResult(url="big.jpg", width=2000, height=2000)]
    with patch("nolan.extractors.extract_from_url", return_value=full):
        out = resolve_results(rs)
    assert all(r.url == "big.jpg" for r in out)


# ---------------------------------------------------------------- registry api
def test_extract_from_url_with_prefetched_html():
    html = '<a href="/x.jpg"><img src="/t.png"></a>'
    results = extract_from_url("https://example.com/g", html=html, fetch=False)
    assert results[0].url == "https://example.com/x.jpg"
    assert results[0].source == "web"
