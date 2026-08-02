"""Offline tests for the artvee search module (no network).

Parsing is exercised against a faithful inline fixture of the artvee
WooCommerce/WoodMart listing markup; the client's pagination/filter/sort logic
is tested with the network layer monkeypatched.
"""

import pytest

from nolan.artvee import (
    ArtveeClient, ArtveeFilter, ArtveeResult,
    parse_listing, slugify_artist, _split_year, _to_mb, _parse_dims,
    _has_next_page,
)


def _tile(*, sk, url, title, alt, artist=None, artist_slug=None, cat=None,
          sd="1319 x 1800px", hd="3761 x 5132px", sdmb="2.58 MB", hdmb="20.61 MB",
          data_id="1000"):
    """Render one product-grid-item tile the way artvee does (attrs HTML-escaped)."""
    sk_json = (f'{{&quot;sdlimagesize&quot;:&quot;{sd}&quot;,'
               f'&quot;hdlimagesize&quot;:&quot;{hd}&quot;,'
               f'&quot;hdlfilesize&quot;:&quot;{hdmb}&quot;,'
               f'&quot;sdlfilesize&quot;:&quot;{sdmb}&quot;,'
               f'&quot;sk&quot;:&quot;{sk}&quot;}}')
    brands = (f'<div class="woodmart-product-brands-links" data-df="" data-aid="68">'
              f'<a href="https://artvee.com/artist/{artist_slug}/">{artist}</a></div>'
              if artist else '')
    cats = (f'<div class="woodmart-product-cats">'
            f'<a href="https://artvee.com/c/{(cat or "").lower()}/" rel="tag">{cat}</a></div>'
            if cat else '')
    return (
        f'<div class="product-grid-item product woodmart-hover-tiled col-md-3 col-sm-4" data-loop="1">'
        f'<div class="product-element-top product-image-link pttl tbmc linko" data-yr="0" '
        f'data-cnt="99" data-id="{data_id}" data-sk="{sk_json}" data-url="{url}">'
        f'<img width="500px" height="682px" alt="{alt}" class="lazy" '
        f'src="https://mdl.artvee.com/ft/{sk}.jpg" /></div>'
        f'<div class="product-element-bottom mmbb-m scatt"><div class="pbm">'
        f'<div class="tbmc linko"><h3 class="product-title">'
        f'<a href="https://artvee.com{url}/">{title}</a></h3></div>'
        f'{brands}{cats}</div></div></div>'
    )


FIXTURE = (
    "<main>"
    + _tile(sk="406646mt", url="/dl/depiction-of-athena",
            title="Depiction of Athena (1896) ", alt="Depiction of Athena",
            artist="Anonymous", artist_slug="anonymous", cat="Mythology",
            sd="1319 x 1800px", sdmb="2.58 MB", data_id="1088340")
    + _tile(sk="73700dr", url="/dl/die-geburt-der-athena",
            title="Die Geburt der Athena (before 1842) ", alt="Die Geburt der Athena",
            artist="Moritz von Schwind", artist_slug="moritz-von-schwind", cat="Drawings",
            sd="1800 x 762px", sdmb="918.44 KB", data_id="845072")
    + _tile(sk="xyz900", url="/dl/sea-storm",
            title="Sea Storm", alt="Sea Storm",
            artist="J. M. W. Turner", artist_slug="j-m-w-turner", cat=None,
            sd="2000 x 1500px", sdmb="3.10 MB", data_id="500")
    # malformed tile: no data-sk core -> must be skipped
    + '<div class="product-grid-item product"><h3 class="product-title">'
      '<a href="https://artvee.com/dl/broken/">Broken</a></h3></div>'
    + "</main>"
)


class TestHelpers:
    def test_split_year_plain(self):
        assert _split_year("Depiction of Athena (1896) ") == ("Depiction of Athena", 1896)

    def test_split_year_qualified(self):
        assert _split_year("X (before 1842)") == ("X", 1842)
        assert _split_year("Y (ca. 1832)") == ("Y", 1832)
        assert _split_year("Z (c. 1500-1510)") == ("Z", 1500)

    def test_split_year_non_date_paren_preserved(self):
        assert _split_year("Still Life (recto)") == ("Still Life (recto)", None)
        assert _split_year("Portrait (No. 12)") == ("Portrait (No. 12)", None)

    def test_split_year_none(self):
        assert _split_year("Untitled") == ("Untitled", None)

    def test_to_mb(self):
        assert _to_mb("20.61 MB") == pytest.approx(20.61)
        assert _to_mb("918.44 KB") == pytest.approx(918.44 / 1024)
        assert _to_mb(None) is None
        assert _to_mb("weird") is None

    def test_parse_dims(self):
        assert _parse_dims("1319 x 1800px") == (1319, 1800)
        assert _parse_dims("6,495 x 2,751px") == (6495, 2751)
        assert _parse_dims(None) == (None, None)

    def test_slugify(self):
        assert slugify_artist("William Etty") == "william-etty"
        assert slugify_artist("Narcisse-Virgile Diaz de La Peña") == \
            "narcisse-virgile-diaz-de-la-pena"


class TestParseListing:
    def test_parses_all_valid_tiles(self):
        items = parse_listing(FIXTURE)
        assert len(items) == 3          # malformed tile skipped
        assert [r.sk for r in items] == ["406646mt", "73700dr", "xyz900"]

    def test_full_metadata_first(self):
        r = parse_listing(FIXTURE)[0]
        assert r.title == "Depiction of Athena"
        assert r.year == 1896
        assert r.artist == "Anonymous"
        assert r.artist_slug == "anonymous"
        assert r.category == "Mythology"
        assert r.artvee_id == "1088340"
        assert (r.sd_width, r.sd_height) == (1319, 1800)
        assert (r.hd_width, r.hd_height) == (3761, 5132)
        assert r.sd_filesize_mb == pytest.approx(2.58)
        assert r.orientation == "portrait"
        assert r.thumbnail_url == "https://mdl.artvee.com/ft/406646mt.jpg"
        assert r.detail_url == "https://artvee.com/dl/depiction-of-athena/"

    def test_qualified_year_and_landscape(self):
        r = parse_listing(FIXTURE)[1]
        assert r.year == 1842
        assert r.title == "Die Geburt der Athena"
        assert r.orientation == "landscape"

    def test_missing_category_ok(self):
        r = parse_listing(FIXTURE)[2]
        assert r.category is None
        assert r.artist == "J. M. W. Turner"
        assert r.year is None

    def test_dedupes_repeated_sk(self):
        assert len(parse_listing(FIXTURE + FIXTURE)) == 3

    def test_has_next_page(self):
        assert _has_next_page('<a class="next page-numbers" href="x">Next</a>')
        assert not _has_next_page(FIXTURE)


class TestArtveeFilter:
    def _r(self, **kw):
        base = dict(sk="s", detail_url="u", title="t")
        base.update(kw)
        return ArtveeResult(**base)

    def test_artist_substring(self):
        r = self._r(artist="William Etty")
        assert ArtveeFilter(artist="etty").matches(r)
        assert not ArtveeFilter(artist="turner").matches(r)

    def test_year_range(self):
        assert ArtveeFilter(year_min=1800, year_max=1900).matches(self._r(year=1850))
        assert not ArtveeFilter(year_max=1900).matches(self._r(year=1950))
        # require_year drops undated works
        assert not ArtveeFilter(year_min=1800).matches(self._r(year=None))

    def test_orientation_and_resolution(self):
        r = self._r(sd_width=2000, sd_height=1500)   # landscape, 3.0 MP
        assert ArtveeFilter(orientation="landscape").matches(r)
        assert not ArtveeFilter(orientation="portrait").matches(r)
        assert ArtveeFilter(min_width=1500).matches(r)
        assert not ArtveeFilter(min_width=2500).matches(r)
        assert ArtveeFilter(min_megapixels=2.5).matches(r)
        assert not ArtveeFilter(min_megapixels=4.0).matches(r)

    def test_category_anyof(self):
        r = self._r(category="Mythology")
        assert ArtveeFilter(categories=["mythology", "marine"]).matches(r)
        assert not ArtveeFilter(categories=["landscape"]).matches(r)

    def test_exclude_anonymous(self):
        assert not ArtveeFilter(exclude_anonymous=True).matches(self._r(artist="Anonymous"))
        assert not ArtveeFilter(exclude_anonymous=True).matches(self._r(artist=None))
        assert ArtveeFilter(exclude_anonymous=True).matches(self._r(artist="Turner"))


class TestAdvancedSearch:
    def test_filter_and_sort(self, monkeypatch):
        cli = ArtveeClient()
        monkeypatch.setattr(cli, "search", lambda *a, **k: parse_listing(FIXTURE))
        # keep landscape only, sort by year ascending
        out = cli.advanced_search(
            "athena", filters=ArtveeFilter(orientation="landscape"),
            sort_by="year", descending=False, max_results=10)
        assert [r.sk for r in out] == ["73700dr", "xyz900"]  # 1842 dated first, undated last
        # sort by pixels descending
        out2 = cli.advanced_search("athena", sort_by="pixels", descending=True)
        assert out2[0].sk == "xyz900"   # 2000x1500 = 3.0 MP is largest

    def test_requires_query_or_artist(self):
        with pytest.raises(ValueError):
            ArtveeClient().advanced_search(None)


class TestArtveeProvider:
    """The image_search adapter maps ArtveeResult -> ImageSearchResult (lazily)."""

    def _prov(self, monkeypatch, *, resolve_sdl=True, n=2):
        import nolan.artvee as artvee_mod
        from nolan.image_search import ArtveeProvider

        class FakeClient:
            def search(self, query, max_results=10):
                return parse_listing(FIXTURE)[:n]

            def resolve_download(self, r):
                return (f"https://mdl.artvee.com/sdl/{r.sk}sdl.jpg?sig=abc"
                        if resolve_sdl else None)

        monkeypatch.setattr(artvee_mod, "ArtveeClient", FakeClient)
        return ArtveeProvider()

    def test_search_is_lazy_and_maps_fields(self, monkeypatch):
        prov = self._prov(monkeypatch)
        assert prov.is_available()
        res = prov.search("athena", max_results=2)
        assert len(res) == 2
        r0 = res[0]
        assert r0.source == "artvee"
        # search does NOT resolve — url is the cheap preview; resolve() upgrades it
        assert r0.url == "https://artvee.com/mcnt/upl/406646mt.jpg"
        assert r0.source_url == "https://artvee.com/dl/depiction-of-athena/"
        assert r0.thumbnail_url == "https://mdl.artvee.com/ft/406646mt.jpg"
        assert r0.title == "Depiction of Athena"
        assert r0.photographer == "Anonymous"
        assert (r0.width, r0.height) == (1319, 1800)   # real SDL dims for the gate/sort
        assert "Public Domain" in r0.license

    def test_resolve_upgrades_to_sdl(self, monkeypatch):
        prov = self._prov(monkeypatch)
        r = prov.search("athena")[0]
        out = prov.resolve(r)
        assert out.url == "https://mdl.artvee.com/sdl/406646mtsdl.jpg?sig=abc"

    def test_resolve_miss_keeps_preview(self, monkeypatch):
        prov = self._prov(monkeypatch, resolve_sdl=False)
        r = prov.search("athena")[0]
        assert prov.resolve(r).url == "https://artvee.com/mcnt/upl/406646mt.jpg"

    def test_client_resolve_asset_noop_for_museums(self):
        from nolan.image_search import ImageSearchClient, ImageSearchResult
        c = ImageSearchClient()
        r = ImageSearchResult(url="https://images.metmuseum.org/x.jpg", source="met")
        assert c.resolve_asset(r) is r     # museum provider has no resolve override

    def test_registered_in_client(self):
        from nolan.image_search import ImageSearchClient
        c = ImageSearchClient()
        assert "artvee" in c.providers
        assert "artvee" in c.get_available_providers()


class TestArtSourceWiring:
    """Honesty: art sources are real, gate-trusted, and artvee is the high tier."""

    def test_art_sources_are_real_providers(self):
        from nolan.image_search import ImageSearchClient
        from nolan.art_sourcing import ART_SOURCES
        providers = ImageSearchClient().providers
        missing = [s for s in ART_SOURCES if s not in providers]
        assert not missing, f"ART_SOURCES not registered as providers: {missing}"

    def test_every_art_source_is_trusted_archival(self):
        # Couples ART_SOURCES <-> asset_gate.OPEN_ACCESS_SOURCES: an art source
        # must pass the archival gate on its NAME alone (license may be None),
        # else it only passes by an incidental license string (the artvee bug).
        from nolan.asset_gate import check_candidate
        from nolan.image_search import ImageSearchResult
        from nolan.art_sourcing import ART_SOURCES
        for s in ART_SOURCES:
            r = ImageSearchResult(url=f"https://example.org/{s}.jpg", source=s,
                                  license=None, width=1500, height=2000)
            v = check_candidate(r, tier="archival")
            assert v.ok, f"art source {s!r} not trusted by archival gate: {v.reasons}"

    def test_artvee_is_primary_high_tier(self):
        from nolan.art_sourcing import (ART_SOURCES, ART_SOURCES_PRIMARY,
                                        ART_SOURCES_FALLBACK)
        assert ART_SOURCES_PRIMARY == ["artvee"]
        assert ART_SOURCES[0] == "artvee"                 # uniformly-open art tier remains strict
        assert "artvee" not in ART_SOURCES_FALLBACK
        assert set(ART_SOURCES) == set(ART_SOURCES_PRIMARY) | set(ART_SOURCES_FALLBACK)

    def test_artvee_first_class_in_gate(self):
        from nolan.asset_gate import OPEN_ACCESS_SOURCES
        assert "artvee" in OPEN_ACCESS_SOURCES


class TestExactTitleTiering:
    """exact_title_pass queries the high tier (artvee) first; museums only fall back."""

    def _scene(self):
        from types import SimpleNamespace
        return SimpleNamespace(id="s1", search_query="Pallas Athena Fighting",
                               matched_asset=None)

    def _fake_client(self, *, artvee_hits):
        from nolan.image_search import ImageSearchResult
        queried = []

        class FakeClient:
            def search_assets(self, query, media_type=None, sources=None, max_results=8):
                queried.append(list(sources or []))
                if "artvee" in (sources or []):
                    if not artvee_hits:
                        return []
                    return [ImageSearchResult(
                        url="https://mdl.artvee.com/sdl/x.jpg?sig=1",
                        title="Pallas Athena Fighting Centaurs", source="artvee",
                        width=1500, height=2000, license="Public Domain (Artvee)")]
                return [ImageSearchResult(
                    url="https://images.metmuseum.org/y.jpg",
                    title="Pallas Athena Fighting", source="met",
                    width=1500, height=2000, license=None)]

            def resolve_asset(self, r):
                return r

            def download_image(self, r, path, prefer_large=True):
                from pathlib import Path
                Path(path).write_bytes(b"x" * 2048)
                return Path(path)

        return FakeClient(), queried

    def test_artvee_hit_short_circuits_museums(self, monkeypatch, tmp_path):
        import nolan.asset_gate as gate
        from nolan.asset_gate import GateVerdict
        import nolan.art_sourcing as art
        monkeypatch.setattr(gate, "check_file", lambda *a, **k: GateVerdict(ok=True))
        client, queried = self._fake_client(artvee_hits=True)
        scene = self._scene()
        kind = art.exact_title_pass(
            scene, client=client, ingest_lib=None, out_dir=tmp_path,
            project_root=tmp_path, img_sources=art.ART_SOURCES)
        assert kind == "exact:artvee"
        assert scene.matched_asset == "s1.jpg"
        # museums were never queried — only the artvee (primary) tier
        assert queried and all("artvee" in q and "met" not in q for q in queried)

    def test_falls_back_to_museums_when_artvee_empty(self, monkeypatch, tmp_path):
        import nolan.asset_gate as gate
        from nolan.asset_gate import GateVerdict
        import nolan.art_sourcing as art
        monkeypatch.setattr(gate, "check_file", lambda *a, **k: GateVerdict(ok=True))
        client, queried = self._fake_client(artvee_hits=False)
        scene = self._scene()
        kind = art.exact_title_pass(
            scene, client=client, ingest_lib=None, out_dir=tmp_path,
            project_root=tmp_path, img_sources=art.ART_SOURCES)
        assert kind == "exact:met"
        # both tiers queried, artvee first then the museum fallback
        assert any("artvee" in q for q in queried)
        assert any("met" in q for q in queried)
