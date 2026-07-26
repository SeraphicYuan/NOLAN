"""Visual Lib — the not-held discovery tier of the picture library. Honesty tests.

Each test below pins a claim the design makes, in the repo's house style: the rule exists only if
a test fails when it stops being true. The four that matter most:

  1. the discovery tier is OPT-IN on every read path (a not-held row has no file, so leaking one
     into a held-tier caller is a FileNotFoundError at render time);
  2. collection provenance is STICKY (the transcript library's re-caption incident, ported);
  3. the source's own id is the row's identity (a re-crawl updates, never duplicates);
  4. `regions` ships as a column and NOTHING authors or consumes it — the location field was
     deliberately deferred until its executor exists, and this test is what keeps the deferral
     honest rather than letting an inert field drift in.
"""
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from nolan.imagelib import Collection, ImageLibrary                       # noqa: E402
from nolan.imagelib.catalog import _ASSET_MIGRATIONS, Asset, AssetCatalog  # noqa: E402


@pytest.fixture()
def lib(tmp_path):
    return ImageLibrary(base_dir=tmp_path)


def _fake_thumb(path: Path, size=(64, 64)) -> Path:
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (90, 110, 130)).save(path)
    return path


def _discovery_row(lib, tmp_path, ref="artic:1", **kw):
    """Add a discovery row without the network: pre-place the thumbnail the door would fetch."""
    thumb_url = kw.pop("thumb_url", f"https://www.artic.edu/iiif/2/{ref}/full/600,/0/default.jpg")
    _fake_thumb(lib._thumb_dest(ref, thumb_url))
    return lib.add_discovery(
        source_ref=ref, thumb_url=thumb_url, source="artic",
        url=kw.pop("url", "https://www.artic.edu/iiif/2/x/full/1686,/0/default.jpg"),
        license=kw.pop("license", "CC0 (Art Institute of Chicago)"),
        width=kw.pop("width", 2000), height=kw.pop("height", 1500), embed=False, **kw)


# --- 1. the tier is opt-in ---------------------------------------------------------------

def test_discovery_rows_are_excluded_from_held_read_paths(lib, tmp_path):
    """THE regression guard. `list()` and `search_by_title()` feed callers that will open the
    file (the acquisition engine's library source, backfill_descriptions, the /images UI)."""
    # Disjoint vocabularies, so a title match can only come from the tier under test.
    lib.catalog.add(Asset(content_hash="h1", path="files/a.jpg", title="Nighthawks"))
    _discovery_row(lib, tmp_path, title="Water Lilies")

    assert [a.title for a in lib.catalog.list()] == ["Nighthawks"]
    assert [a.title for a in lib.catalog.list(held=0)] == ["Water Lilies"]
    assert len(lib.catalog.list(held=None)) == 2
    assert [h.asset.title for h in lib.search_by_title("hopper nighthawks")] == ["Nighthawks"]
    assert lib.search_by_title("monet water lilies") == []
    assert [h.asset.title for h in lib.search_by_title("monet water lilies", held=0)] \
        == ["Water Lilies"]


def test_discovery_vectors_live_in_their_own_collections():
    """Not a style choice: `search()` resolves a chroma id straight to an asset, so one shared
    collection would leak not-held rows into every existing caller."""
    from nolan.imagelib import store
    assert store._DISC_COLLECTION != store._COLLECTION
    assert store._DISC_IDENT_COLLECTION != store._DESC_COLLECTION


# --- 2. sticky provenance ----------------------------------------------------------------

def test_collection_rights_survive_a_pass_that_does_not_know_them(tmp_path):
    """Ported from the incident that cost the transcript library a public-domain label: a
    re-crawl that knows nothing about rights must not silently re-label the collection."""
    cat = AssetCatalog(tmp_path / "c.db")
    cat.upsert_collection(Collection(slug="s", source="artic", title="T",
                                     rights="CC0", copyright_free=True))
    cat.upsert_collection(Collection(slug="s", source="artic", title="T", item_count=99))
    got = cat.get_collection("s")
    assert got.rights == "CC0" and got.copyright_free is True and got.item_count == 99


# --- 3. the source id is the identity ----------------------------------------------------

def test_recrawl_refreshes_by_source_ref_instead_of_duplicating(lib, tmp_path):
    a, created = _discovery_row(lib, tmp_path, title="Old title")
    assert created
    b, created2 = _discovery_row(lib, tmp_path, title="Corrected title", creator="Monet")
    assert not created2 and b.id == a.id
    assert b.title == "Corrected title" and b.creator == "Monet"
    assert lib.catalog.count(held=0) == 1


def test_discovery_requires_a_stable_source_ref(lib):
    with pytest.raises(ValueError, match="source_ref"):
        lib.add_discovery(source_ref="", thumb_url="https://x/y.jpg", source="artic")


def test_identity_is_catalog_derived(lib, tmp_path):
    """A description may be model-written; an identity may not. The two provenances are separate
    columns because only one of them is allowed to be a guess."""
    a, _ = _discovery_row(lib, tmp_path, title="Water Lilies", creator="Claude Monet",
                          date_text="1906", institution="Art Institute of Chicago",
                          description="Oil on canvas, France")
    assert a.identity_source == "catalog" and a.description_source == "catalog"
    assert "Water Lilies" in a.identity_text() and "Claude Monet" in a.identity_text()


def test_catalog_prose_does_not_count_as_captioned(lib, tmp_path):
    """Coverage honesty: every harvested row carries catalog prose, so counting it would report
    an entirely un-captioned collection as complete."""
    _discovery_row(lib, tmp_path, ref="artic:7", description="Oil on canvas, France")
    assert lib.discovery_stats()["described_pct"] == 0.0
    lib.catalog.update(lib.catalog.list(held=0)[0].id, description_source="gemma-4-26b")
    assert lib.discovery_stats()["described_pct"] == 100.0


def test_a_model_caption_survives_a_recrawl(lib, tmp_path):
    _discovery_row(lib, tmp_path, ref="artic:8", description="Oil on canvas")
    aid = lib.catalog.list(held=0)[0].id
    lib.catalog.set_description(aid, "a pond of lilies at dusk")
    lib.catalog.update(aid, description_source="gemma-4-26b")
    _discovery_row(lib, tmp_path, ref="artic:8", description="Oil on canvas")   # re-crawl
    got = lib.catalog.get(aid)
    assert got.description == "a pond of lilies at dusk" and got.description_source == "gemma-4-26b"


# --- 4. the deferred field stays inert ---------------------------------------------------

def test_regions_column_exists_and_nothing_populates_it(lib, tmp_path):
    """`regions` (labelled subject/face/text/watermark boxes) ships as a nullable column ONLY
    because adding one to a populated table is the expensive part. Its executor — a focal point
    in compose's media_ground, which today hardcodes `background-position:center` and
    `transform-origin:50% 50%` — does not exist, so nothing may write the field. An authored
    field with no consumer is this repo's most-repeated bug (WIRING_CHECKLIST pitfall #1)."""
    assert "regions" in _ASSET_MIGRATIONS
    a, _ = _discovery_row(lib, tmp_path, ref="artic:9")
    assert a.regions is None
    import inspect
    assert "regions" not in inspect.signature(lib.add_discovery).parameters
    ground = (REPO / "render-service/_lab_hyperframes/bridge/compose.py").read_text(
        encoding="utf-8", errors="replace")
    assert "transform-origin:50% 50%" in ground, (
        "media_ground gained a focal point — if the executor now exists, wire `regions` to it "
        "(authored field + consumer + PLAN_FIELD_CONSUMERS entry) and rewrite this test")


# --- the acquisition doors ---------------------------------------------------------------

def test_harvest_door_refuses_a_blocklisted_host(lib):
    """No network: the host blocklist rejects before any fetch."""
    with pytest.raises(ValueError, match="stock-preview domain"):
        lib.add_discovery(source_ref="x:1", thumb_url="https://c8.alamy.com/comp/R93/vase.jpg",
                          source="ddgs", license="CC0", width=3000, height=2000)


def test_harvest_door_refuses_below_the_archival_floor(lib):
    with pytest.raises(ValueError, match="resolution floor"):
        lib.add_discovery(source_ref="x:2", thumb_url="https://www.artic.edu/iiif/2/a/x.jpg",
                          source="artic", license="CC0", width=320, height=240)


def test_harvest_door_refuses_unknown_rights(lib):
    """Archival tier: a named work whose rights are unknown is exactly the Alamy failure mode."""
    with pytest.raises(ValueError, match="license unknown"):
        lib.add_discovery(source_ref="x:3", thumb_url="https://example.org/a.jpg",
                          source="somewhere", license=None, width=3000, height=2000)


def _banner_image(path: Path) -> Path:
    """The Alamy shape: a near-black strip across the bottom carrying bright glyph pixels,
    discontinuous with a mid-grey image body."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (400, 300), (128, 128, 128))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 275, 400, 300], fill=(8, 8, 8))
    for x in range(10, 380, 16):            # sparse: dense glyphs lift the band's own mean out
        d.rectangle([x, 283, x + 3, 292], fill=(240, 240, 240))   # of the "dark strip" range
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path


def test_banner_check_still_fires_for_a_non_institutional_source(lib):
    """BOTH DIRECTIONS (checklist #11). This one must still be refused."""
    from nolan.asset_gate import banner_suspect
    ref = "ddgs:1"
    url = "https://example.org/x.jpg"
    assert banner_suspect(_banner_image(lib._thumb_dest(ref, url)))
    with pytest.raises(ValueError, match="watermark banner strip"):
        lib.add_discovery(source_ref=ref, thumb_url=url, source="ddgs", license="CC0",
                          width=3000, height=2000, embed=False)


def test_banner_check_is_skipped_for_an_open_access_institution(lib):
    """...and this one must NOT be. Measured: 4 of 4 refusals on Art Institute CC0 images were
    false positives — museum object photography on a plain mount (see add_discovery)."""
    from nolan.asset_gate import OPEN_ACCESS_SOURCES, banner_suspect
    assert "artic" in OPEN_ACCESS_SOURCES
    ref = "artic:1"
    url = "https://www.artic.edu/iiif/2/x/full/600,/0/default.jpg"
    assert banner_suspect(_banner_image(lib._thumb_dest(ref, url)))   # same pixels…
    a, created = lib.add_discovery(source_ref=ref, thumb_url=url, source="artic",
                                   license="CC0 (Art Institute of Chicago)",
                                   width=3000, height=2000, embed=False)   # …accepted here
    assert created and a.source_ref == ref


def test_both_doors_are_in_the_gate_manifest():
    from nolan.asset_gate import ASSET_GATE_DOORS
    assert "imagelib.add_discovery" in ASSET_GATE_DOORS
    assert "imagelib.promote_to_held" in ASSET_GATE_DOORS


def test_promotion_needs_a_full_image_url(lib, tmp_path):
    a, _ = _discovery_row(lib, tmp_path, ref="artic:10", url=None)
    with pytest.raises(ValueError, match="no full-image url"):
        lib.promote_to_held(a.id)


def test_promoting_a_held_row_is_a_noop(lib):
    a = lib.catalog.add(Asset(content_hash="h9", path="files/x.jpg", title="held"))
    got, promoted = lib.promote_to_held(a.id)
    assert got.id == a.id and promoted is False


# --- retrieval routing -------------------------------------------------------------------

def test_routing_keeps_one_channel_dominant(lib):
    """The measured lesson (scripts/eval_visuallib_recall.py): blending the identity and CLIP
    channels near-equally scored WORSE than either pure channel on its own kind of query — the
    wrong channel demotes the right answer. look@1 went 31.6 → 73.7 and named@1 84.2 → 94.7 when
    the routing switched to dominant-plus-assist. This fails if someone re-flattens the weights."""
    import inspect
    src = inspect.getsource(lib.search_discovery)
    m = re.search(r"wi, wc, wcov = \(([\d.]+), ([\d.]+), ([\d.]+)\) if named "
                  r"else \(([\d.]+), ([\d.]+), ([\d.]+)\)", src)
    assert m, "the routing weights moved — re-run the eval and update this test"
    n_i, n_c, _n_cov, l_i, l_c, _l_cov = (float(x) for x in m.groups())
    assert n_i >= 0.6 and n_i - n_c >= 0.4, "a NAMED query must be identity-dominant"
    assert l_c >= 0.6 and l_c - l_i >= 0.4, "a LOOK query must be CLIP-dominant"


def test_exact_titles_are_a_bonus_not_a_hard_prefix(lib):
    """Unconditionally prepending lexical matches cost 10 points of named recall@1: "first by
    title cover" is not "most likely" — a short wrong title can cover perfectly."""
    import inspect
    src = inspect.getsource(lib.search_discovery)
    assert "wcov * cover.get" in src
    assert "exact +" not in src


# --- the harvester -----------------------------------------------------------------------

def test_every_adapter_yields_a_namespaced_source_ref():
    """A not-held row keyed on a CDN url cannot survive that url rotating, so an adapter without
    a stable id is unshippable."""
    from nolan.imagelib.harvest import SOURCES
    for name, adapter in SOURCES.items():
        assert callable(adapter["items"]) and callable(adapter["collection"])
        col = adapter["collection"]()
        assert col.slug and col.source == name and col.rights, f"{name}: collection needs rights"


def test_harvest_report_counts_what_it_dropped():
    from nolan.imagelib.harvest import HarvestReport
    rep = HarvestReport(collection="c")
    rep.skipped_rights += 1
    rep.refused_gate += 1
    rep.note("refused: watermark")
    d = json.loads(json.dumps(rep.to_dict()))
    assert d["skipped_rights"] == 1 and d["refused_gate"] == 1 and d["reasons"]
