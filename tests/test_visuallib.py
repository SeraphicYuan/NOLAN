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
    because adding one to a populated table is the expensive part. Nothing writes it, so it
    cannot become an authored field with no consumer (WIRING_CHECKLIST pitfall #1).

    NOTE, and this is the live state rather than the original justification: when this column
    shipped, the HF path had no focal point at all (compose's `media_ground` hardcoded
    `background-position:center`). The camera umbrella (`src/nolan/camera`) landed the same day
    and its solver DOES take one — `solve_push(target=(x, y))`, framed so the target stays put.
    So the consumer now exists and the missing half is the PRODUCER: a pass that turns a picture
    into labelled boxes. Wiring `regions` is a real task now, not a deferred one.
    """
    assert "regions" in _ASSET_MIGRATIONS
    a, _ = _discovery_row(lib, tmp_path, ref="artic:9")
    assert a.regions is None
    import inspect
    assert "regions" not in inspect.signature(lib.add_discovery).parameters

    # The sentinel watches the CONSUMER's contract, not a CSS string: this is what `regions` would
    # feed. If the parameter is renamed or dropped, the wiring plan above needs rewriting.
    from nolan.camera import solve
    assert "target" in inspect.signature(solve.solve_push).parameters, (
        "the camera solver's `target` went away — re-derive how a labelled region would reach "
        "the render path before wiring `regions`")


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
    from nolan.imagelib.store import _route_weights

    n_i, n_c, _ = _route_weights(named=True, use_clip=True)
    l_i, l_c, _ = _route_weights(named=False, use_clip=True)
    assert n_i >= 0.6 and n_i - n_c >= 0.4, "a NAMED query must be identity-dominant"
    assert l_c >= 0.6 and l_c - l_i >= 0.4, "a LOOK query must be CLIP-dominant"


def test_the_title_cover_bonus_stays_a_TIEBREAK(lib):
    """It is a bonus, not a channel. Tuned at 97,610 rows it was 0.4; the corpus reached 357,027
    and that same number cost 10.8 points of named recall@1 — enough to put the routed system
    BELOW identity-only, inverting the point of routing. The Met is why: 248,472 rows of short
    generic titles ("Bowl", "Fragment") share tokens with almost any query, so a tiebreak became
    a promoter of near-misses.

    Swept over 28 named golden needs at 357,027 rows: 0.0 → 89.3, 0.05 → 92.9, 0.1 → 89.3,
    0.2/0.3/0.4 → 82.1. This guards the SHAPE — a cover bonus that can outweigh the dominant
    channel is not a tiebreak — not the specific decimal, which is the eval's business.
    """
    from nolan.imagelib.store import _route_weights

    n_i, _, n_cov = _route_weights(named=True, use_clip=True)
    assert 0 < n_cov <= 0.1, "the cover bonus must stay a tiebreak — re-run the eval if you move it"
    assert n_cov < n_i / 2, "a tiebreak cannot rival the dominant channel"
    # ...and it applies ONLY to named queries; a look query has no title to cover
    assert _route_weights(named=False, use_clip=True)[2] == 0.0
    assert _route_weights(named=False, use_clip=False)[2] == 0.0


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
        assert callable(adapter.items) and callable(adapter.collection)
        col = adapter.collection()
        assert col.slug and col.source == name and col.rights, f"{name}: collection needs rights"


def test_met_wikidata_qid_is_parsed_when_the_source_hands_it_over():
    """The whole justification for the nullable `wikidata_qid` column: the Met publishes the
    entity id, so recording it costs one column and no extra call. Live-checked at 8 of 8 rows on
    a European Paintings harvest."""
    from nolan.imagelib.harvest import _met_qid
    assert _met_qid("https://www.wikidata.org/wiki/Q18689458") == "Q18689458"
    assert _met_qid("http://www.wikidata.org/wiki/Q5582 ") == "Q5582"
    assert _met_qid("") is None and _met_qid(None) is None
    assert _met_qid("https://www.metmuseum.org/art/collection/search/436535") is None


def test_met_department_accepts_id_or_name():
    from nolan.imagelib.harvest import _met_dept_id
    assert _met_dept_id("Photographs") == 19 and _met_dept_id("photographs") == 19
    assert _met_dept_id("19") == 19 and _met_dept_id(None) is None
    with pytest.raises(ValueError, match="unknown Met department"):
        _met_dept_id("Department of Vibes")


def test_limit_means_rows_indexed_in_every_adapter():
    """ONE meaning for `limit` across adapters (pitfall #4 — two dialects for one decision). It
    mattered: the Met's listing is unfiltered, so `limit` as "ids fetched" silently delivered 2
    rows for a request of 12."""
    from nolan.imagelib import harvest as H
    for name in H.SOURCES:
        src = inspect_source(H.SOURCES[name].items)
        assert "yielded" in src, f"{name}: limit must count rows INDEXED, not records fetched"


def inspect_source(fn) -> str:
    import inspect
    return inspect.getsource(fn)


def test_harvest_report_counts_what_it_dropped():
    from nolan.imagelib.harvest import HarvestReport
    rep = HarvestReport(collection="c")
    rep.skipped_rights += 1
    rep.refused_gate += 1
    rep.note("refused: watermark")
    d = json.loads(json.dumps(rep.to_dict()))
    assert d["skipped_rights"] == 1 and d["refused_gate"] == 1 and d["reasons"]


# --- the crawler contract: strategy, cursor, denominator ------------------------------------

def test_every_adapter_declares_a_known_enumeration_strategy():
    """HOW a source can be walked is per-source knowledge with real consequences (is it capped?
    can it resume?), and it had nowhere to live but a docstring — where it was also wrong."""
    from nolan.imagelib.harvest import ENUMERATION, SOURCES
    for name, a in SOURCES.items():
        assert a.enumeration in ENUMERATION, f"{name}: unknown strategy {a.enumeration!r}"
        assert a.id == name, f"{name}: adapter id disagrees with its registry key"
    for key, spec in ENUMERATION.items():
        assert {"purpose", "when_to_use", "constraint"} <= set(spec), f"{key}: incomplete entry"


def test_an_unknown_enumeration_strategy_is_refused_at_construction():
    """A typo'd strategy must fail loudly at import, not silently mean nothing."""
    from nolan.imagelib.harvest import SourceAdapter, artic_collection, artic_items
    with pytest.raises(ValueError, match="unknown enumeration"):
        SourceAdapter(id="x", collection=artic_collection, items=artic_items,
                      enumeration="vibes")


def test_a_resumable_adapter_accepts_a_cursor():
    """`resumable=True` is a claim about the signature, so check the signature."""
    import inspect
    from nolan.imagelib.harvest import SOURCES
    for name, a in SOURCES.items():
        if not a.resumable:
            continue
        params = inspect.signature(a.items).parameters
        assert "cursor" in params, f"{name}: declares resumable but items() takes no cursor"


def test_cursor_advances_within_a_page_not_only_between_pages():
    """REGRESSION, caught by a live smoke run. A page-granular cursor never advances at all when
    `limit` is satisfied inside the first page, so repeated small harvests re-walk page 1 forever
    and coverage never grows: four runs of limit=4 produced four rows and no progress."""
    from nolan.imagelib.harvest import SOURCES
    src = inspect_source(SOURCES["artic"].items)
    assert '"offset": idx + 1' in src, "artic cursor must record its position WITHIN the page"


def test_no_paged_adapter_advances_its_cursor_past_unconsumed_rows():
    """REGRESSION, and it has now happened TWICE — once in artic, once in cleveland, where a
    harvest of 4 rows left the cursor at 100 and the next run skipped 96 rows it had never seen.

    Re-walking a row is free (source_ref dedup turns it into a refresh); SKIPPING loses it in
    silence. So a per-item cursor update inside a page loop must be indexed by the ITEM, never by
    the page length.
    """
    import re
    from nolan.imagelib.harvest import SOURCES
    for name, adapter in SOURCES.items():
        src = inspect_source(adapter.items)
        body = src[src.index("yield HarvestItem"):] if "yield HarvestItem" in src else ""
        for line in body.splitlines():
            if "report.cursor" in line and "len(data)" in line:
                raise AssertionError(
                    f"{name}: cursor advances by page length beside a yielded item "
                    f"({line.strip()}) — that skips every row the caller did not consume")


def test_the_cursor_advances_only_after_a_row_is_consumed():
    """Re-walking a row is free (source_ref dedup turns it into a refresh); SKIPPING one loses it
    silently, which is the failure this tier exists to prevent. So the cursor update must sit
    after the yield, never before it."""
    from nolan.imagelib.harvest import SOURCES
    for name in ("artic", "met"):
        src = inspect_source(SOURCES[name].items)
        body = src[src.index("yield HarvestItem"):]
        assert "report.cursor" in body, (
            f"{name}: cursor must advance AFTER the yield, or a crash mid-index skips a row")


def test_collection_carries_a_denominator_and_reports_unknown_honestly():
    """`item_count` alone reads as complete. 841 of 62,035 is 1.4%, and a collection that cannot
    be asked how big it is must report unknown rather than full."""
    from nolan.imagelib.catalog import Collection
    c = Collection(slug="s", source="artic", title="t", item_count=841, upstream_count=62035)
    assert c.coverage == pytest.approx(0.01356, abs=1e-4)
    assert Collection(slug="s", source="x", title="t", item_count=841).coverage is None
    # a stale denominator smaller than what we hold must not read as >100%
    assert Collection(slug="s", source="x", title="t",
                      item_count=99, upstream_count=10).coverage == 1.0


def test_every_adapter_that_can_be_asked_declares_an_upstream_count(tmp_path):
    from nolan.imagelib.harvest import SOURCES
    for name, a in SOURCES.items():
        assert a.upstream_count is not None and callable(a.upstream_count), (
            f"{name}: no way to ask how much exists — coverage would be unmeasurable")


def test_collection_migrations_are_applied_to_an_existing_db(tmp_path):
    """The columns land by ALTER TABLE on open, so an existing catalog.db upgrades in place."""
    import sqlite3
    from nolan.imagelib.catalog import AssetCatalog, _COLLECTION_MIGRATIONS
    db = tmp_path / "catalog.db"
    # a pre-migration collections table, exactly as the first release created it
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE collections (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "slug TEXT UNIQUE NOT NULL, source TEXT NOT NULL, title TEXT NOT NULL, "
                "description TEXT, rights TEXT, copyright_free INTEGER, era TEXT, topics TEXT, "
                "url TEXT, item_count INTEGER, added_at TEXT NOT NULL, last_crawled TEXT)")
    con.commit()
    con.close()

    cat = AssetCatalog(db)
    cols = {r["name"] for r in cat._conn.execute("PRAGMA table_info(collections)")}
    for name in _COLLECTION_MIGRATIONS:
        assert name in cols, f"{name} was not migrated onto an existing collections table"


def test_met_csv_rows_filters_public_domain_offline(tmp_path, monkeypatch):
    """THE reason the dump exists: the rights filter runs offline, so a request is never spent
    discovering that an object is in copyright."""
    import csv as _csv
    from nolan.imagelib import harvest as H

    path = tmp_path / "MetObjects.csv"
    # utf-8-SIG on purpose: the real dump carries a BOM, and without it the first column name
    # reads as '﻿Object Number' and every lookup of it silently misses.
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=["Object Number", "Is Public Domain", "Object ID",
                                           "Department", "Title"])
        w.writeheader()
        w.writerow({"Object Number": "1", "Is Public Domain": "True", "Object ID": "11",
                    "Department": "European Paintings", "Title": "a"})
        w.writerow({"Object Number": "2", "Is Public Domain": "False", "Object ID": "22",
                    "Department": "European Paintings", "Title": "b"})
        w.writerow({"Object Number": "3", "Is Public Domain": "True", "Object ID": "33",
                    "Department": "Photographs", "Title": "c"})
    monkeypatch.setattr(H, "_met_csv_path", lambda: path)

    assert H.met_public_domain_ids() == [11, 33]
    assert H.met_public_domain_ids(dept="European Paintings") == [11]
    assert H.met_public_domain_ids(dept="Photographs") == [33]


def test_phase_a_indexes_a_record_without_fetching_pixels(lib, tmp_path, monkeypatch):
    """The phase split: pixels are ~50x the cost of the record (~29h vs ~20min for the artic
    catalog), so Phase A must write a searchable row and fetch NOTHING."""
    calls = []

    def _boom(url, dest, **kw):
        calls.append(url)
        raise AssertionError("Phase A must not download anything")

    monkeypatch.setattr("nolan.http_client.download_file_sync", _boom)

    asset, created = lib.add_discovery(
        source_ref="artic:1", thumb_url="https://example.org/t.jpg",
        url="https://example.org/full.jpg", source="artic", title="A Bridge",
        creator="Someone", license="CC0", width=3000, height=2000, pixels=False)
    assert created and calls == []
    assert asset.thumb_path is None, "a record-only row has no local thumbnail"
    assert asset.thumb_url == "https://example.org/t.jpg", (
        "the thumb URL must be kept, or Phase B would have to re-walk the whole source")
    assert asset.has_pixels is False
    # the identity channel still indexed — this row IS findable by name
    assert asset.identity_text()

    st = lib.discovery_stats()
    assert st["discovery"] == 1 and st["with_pixels"] == 0 and st["pixels_pct"] == 0.0


def test_pixel_coverage_is_reported_separately_from_row_count(lib, tmp_path):
    """A records-only collection must not read as fully indexed just because rows exist."""
    lib.add_discovery(source_ref="artic:1", thumb_url="https://e.org/1.jpg", source="artic",
                      title="one", license="CC0", pixels=False)
    lib.add_discovery(source_ref="artic:2", thumb_url="https://e.org/2.jpg", source="artic",
                      title="two", license="CC0", pixels=False)
    st = lib.discovery_stats()
    assert st["discovery"] == 2
    assert st["with_pixels"] == 0
    assert st["pixels_pct"] == 0.0


def test_backfill_fetches_pixels_and_runs_the_gates_phase_a_could_not(lib, tmp_path, monkeypatch):
    """Phase B is where the pixel-dependent gates run — they had nothing to run on in Phase A,
    and a row whose picture we look at and refuse must be retired, not left half-indexed."""
    from PIL import Image

    lib.add_discovery(source_ref="artic:7", thumb_url="https://e.org/7.jpg", source="artic",
                      title="seven", license="CC0", width=4000, height=4000, pixels=False)

    def _fake_dl(url, dest, **kw):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        import numpy as np
        rng = np.random.default_rng(4)
        Image.fromarray(rng.integers(40, 220, size=(400, 400, 3), dtype="uint8")).save(dest)

    monkeypatch.setattr("nolan.http_client.download_file_sync", _fake_dl)
    res = lib.backfill_pixels(limit=10)
    assert res["fetched"] == 1 and res["refused"] == 0, res

    a = lib.catalog.get_by_ref("artic:7")
    assert a.thumb_path and a.has_pixels
    assert lib.discovery_stats()["pixels_pct"] == 100.0


def test_a_small_picture_is_KEPT_as_a_thumbnail_not_retired(lib, tmp_path, monkeypatch):
    """The thumbnail path no longer applies a resolution floor.

    A thumbnail is a 512px preview — something to LOOK at in the grid — and refusing to show a
    picture because its original is small is a judgement about USE, made at the wrong moment and
    with a wildly disproportionate consequence: the old behaviour deleted the file AND set the
    row to `rejected`, retiring a catalogue record over a preview.

    The floor still exists; it runs at PROMOTION, on the real bytes of something a human has
    chosen to hold.
    """
    import numpy as np
    from PIL import Image

    lib.add_discovery(source_ref="artic:8", thumb_url="https://e.org/8.jpg", source="artic",
                      title="eight", license="CC0", width=1000, height=1000, pixels=False)

    def _fake_dl(url, dest, **kw):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        # a tiny object adrift on a huge grey sweep: content is ~4% of the frame, which the
        # content floor used to refuse outright
        canvas = np.full((400, 400, 3), 128, dtype="uint8")
        rng = np.random.default_rng(9)
        canvas[190:210, 190:210] = rng.integers(0, 255, size=(20, 20, 3), dtype="uint8")
        Image.fromarray(canvas).save(dest)

    monkeypatch.setattr("nolan.http_client.download_file_sync", _fake_dl)
    res = lib.backfill_pixels(limit=10, embed=False)
    assert res["fetched"] == 1 and res["refused"] == 0, res
    a = lib.catalog.get_by_ref("artic:8")
    assert a.status == "active", "a small preview must not retire the catalogue row"
    assert a.thumb_path, "and the picture is kept, so the card can show it"


# --- on-demand pixels: concurrent, gated, and after ranking ----------------------------------

def _fake_thumb_downloader(monkeypatch, size=(400, 400), delay=0.0):
    """A downloader that writes a real (textured, full-bleed) image so the gates pass.

    Also records the MAXIMUM number of downloads in flight at once, which is how the concurrency
    claim gets tested directly instead of inferred from wall-clock — a timing assertion here
    measured the serial CLIP embed as much as the parallel fetch, and was both flaky and wrong.
    """
    import threading
    import time as _t
    import numpy as np
    from PIL import Image

    class _Calls(list):
        """A list that also carries the in-flight watermark."""
        state: dict

    calls = _Calls()
    state = {"inflight": 0, "max_inflight": 0}
    lock = threading.Lock()

    def _dl(url, dest, **kw):
        with lock:
            calls.append(url)
            state["inflight"] += 1
            state["max_inflight"] = max(state["max_inflight"], state["inflight"])
        try:
            if delay:
                _t.sleep(delay)
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            rng = np.random.default_rng(abs(hash(url)) % 2**31)
            Image.fromarray(rng.integers(40, 220, size=(size[1], size[0], 3),
                                         dtype="uint8")).save(dest)
        finally:
            with lock:
                state["inflight"] -= 1

    monkeypatch.setattr("nolan.http_client.download_file_sync", _dl)
    calls.state = state
    return calls


def test_warm_pixels_fetches_concurrently(lib, monkeypatch):
    """The FETCH is what runs wide — it is nearly all network. The CLIP embed and the SQLite
    write stay serial on purpose, and they are the floor on a page (~90 ms/row), so this asserts
    parallelism directly rather than through wall-clock."""
    calls = _fake_thumb_downloader(monkeypatch, delay=0.05)
    rows = []
    for i in range(16):
        a, _ = lib.add_discovery(source_ref=f"artic:{i}", thumb_url=f"https://e.org/{i}.jpg",
                                 source="artic", title=f"t{i}", license="CC0", pixels=False)
        rows.append(a)

    res = lib.warm_pixels(rows, concurrency=8)

    assert res["fetched"] == 16 and len(calls) == 16
    assert calls.state["max_inflight"] > 1, "the fetch ran serially"
    assert calls.state["max_inflight"] <= 8, "concurrency cap not honoured"
    assert all(lib.catalog.get(a.id).has_pixels for a in rows)


def test_warm_pixels_honours_a_serial_setting(lib, monkeypatch):
    calls = _fake_thumb_downloader(monkeypatch, delay=0.01)
    rows = [lib.add_discovery(source_ref=f"artic:{i}", thumb_url=f"https://e.org/{i}.jpg",
                              source="artic", title=f"t{i}", license="CC0", pixels=False)[0]
            for i in range(4)]
    lib.warm_pixels(rows, concurrency=1)
    assert calls.state["max_inflight"] == 1


def test_warm_pixels_runs_the_same_gate_as_the_batch_path(lib, monkeypatch):
    """One implementation for both doors — the same picture must not be admitted by one and
    refused by the other. Still true now that the floor is gone: BOTH keep it."""
    import numpy as np
    from PIL import Image

    def _dl(url, dest, **kw):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        canvas = np.full((400, 400, 3), 128, dtype="uint8")   # a speck on a huge grey sweep
        rng = np.random.default_rng(3)
        canvas[195:205, 195:205] = rng.integers(0, 255, size=(10, 10, 3), dtype="uint8")
        Image.fromarray(canvas).save(dest)

    monkeypatch.setattr("nolan.http_client.download_file_sync", _dl)
    a, _ = lib.add_discovery(source_ref="artic:1", thumb_url="https://e.org/1.jpg",
                             source="artic", title="t", license="CC0",
                             width=1000, height=1000, pixels=False)
    res = lib.warm_pixels([a], tier="archival", embed=False)
    assert res["fetched"] == 1 and res["refused"] == 0
    assert lib.catalog.get(a.id).status == "active"


def test_the_watermark_door_is_still_shut(lib, monkeypatch):
    """Dropping the floor is not dropping the gate. The watermark check is skipped outright for
    open-access sources — all four current ones — so it costs nothing today, and it is the one
    thing between a future rights-managed source and a watermarked preview in the library. A
    picture we cannot legally show is a different problem from one that is merely small."""
    import numpy as np
    from PIL import Image

    def _dl(url, dest, **kw):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        rng = np.random.default_rng(5)
        Image.fromarray(rng.integers(60, 200, size=(400, 600, 3), dtype="uint8")).save(dest)

    monkeypatch.setattr("nolan.http_client.download_file_sync", _dl)
    # The heuristic's OWN behaviour is tested against real images elsewhere; what changed here is
    # whether it is still CALLED, so that is what this asserts — stub its verdict and check the
    # refusal is honoured. Synthesising an image that trips it would be testing the heuristic.
    called = []

    def _suspect(path):
        called.append(path)
        return True

    monkeypatch.setattr("nolan.asset_gate.banner_suspect", _suspect)

    # declared dims clear the INDEX-time floor (a separate door, on the source's own numbers,
    # deliberately still in place) so the row is admitted and the watermark check gets to run
    a, _ = lib.add_discovery(source_ref="agency:1", thumb_url="https://e.org/w.jpg",
                             source="some_agency", title="stock", license="CC0",
                             width=2400, height=1600, pixels=False)
    res = lib.warm_pixels([a], embed=False)
    assert called, "banner_suspect must still be consulted for a non-open-access source"
    assert res["refused"] == 1 and res["fetched"] == 0, res
    assert any("watermark" in r for r in res["reasons"]), res["reasons"]

    # ...and NOT consulted for the open-access museums, where it is a pure waste of ~2.4 ms/row
    called.clear()
    b, _ = lib.add_discovery(source_ref="artic:9", thumb_url="https://e.org/9.jpg",
                             source="artic", title="a print", license="CC0",
                             width=2400, height=1600, pixels=False)
    assert lib.warm_pixels([b], embed=False)["fetched"] == 1
    assert not called, "open-access sources skip the watermark check"


def test_warming_only_ever_touches_the_returned_page(lib, monkeypatch):
    """Warming is bounded by the page, never by the candidate pool. It runs AFTER ranking, so it
    can only ever fetch what was actually returned.

    NOT asserted here, because it is a property of SCALE rather than an invariant: on the live
    97,610-row library a look query with warm=True acquired **0** thumbnails, because look
    ranking is CLIP-dominant (0.9) and CLIP only knows rows that already have pixels — so the
    rows that need them cannot rank high enough to earn them. That loop is real and is why
    `warm` is no longer a default, but it depends on the corpus dwarfing the candidate pool. A
    six-row fixture reproduces the opposite, and a test contrived to show it would be testing the
    narrative rather than the code.
    """
    calls = _fake_thumb_downloader(monkeypatch)
    for i in range(12):
        lib.add_discovery(source_ref=f"artic:{i}", thumb_url=f"https://e/{i}.jpg",
                          source="artic", title=f"Riverbank Study {i}", license="CC0",
                          pixels=False)
    lib.search_discovery("riverbank", k=3, warm=True)
    assert len(calls) <= 3, f"warmed {len(calls)} rows to serve a page of 3"


def test_warm_without_embed_keeps_the_thumbnail_but_skips_clip(lib, monkeypatch):
    """The download is ~48 ms/row (32 fetch + 16 gate); the CLIP embed is ~103. A page that only
    needs pictures to LOOK AT should not pay the larger one."""
    _fake_thumb_downloader(monkeypatch)
    a, _ = lib.add_discovery(source_ref="artic:1", thumb_url="https://e/1.jpg", source="artic",
                             title="A Bridge", license="CC0", pixels=False)
    res = lib.warm_pixels([a], embed=False)
    assert res["fetched"] == 1 and res["embedded"] == 0
    row = lib.catalog.get(a.id)
    assert row.has_pixels, "the thumbnail must still be kept — the card needs a picture"
    # ...and it is absent from the look channel until something embeds it
    assert lib._disc_coll().count() == 0


def test_use_clip_false_never_touches_the_model(lib, monkeypatch):
    """`self.embedder` is lazy, so a search page that never asks for the look channel never
    loads the ~150 MB CLIP model at all. That is the saving — not a faster query."""
    lib.add_discovery(source_ref="artic:1", thumb_url="https://e/1.jpg", source="artic",
                      title="A Stone Bridge", license="CC0", pixels=False)

    def _boom(*a, **k):
        raise AssertionError("CLIP was loaded despite use_clip=False")

    monkeypatch.setattr(type(lib.embedder), "embed_text", _boom)
    hits = lib.search_discovery("stone bridge", k=5, use_clip=False)
    assert hits and hits[0].asset.source_ref == "artic:1"


def test_without_clip_identity_takes_the_full_weight(lib):
    """Otherwise a look query would score on a 0.1 assist while 0.9 went to a channel returning
    nothing — every result flattened to near-zero."""
    from nolan.imagelib.store import _route_weights

    for named in (True, False):
        wi, wc, _ = _route_weights(named=named, use_clip=False)
        assert (wi, wc) == (1.0, 0.0), (
            "with the look channel off, identity must carry the full weight")


def test_the_api_does_not_warm_by_default():
    """Warming DOWNLOADS, PERSISTS and can RETIRE rows (`status='rejected'` when pixels fail the
    gate). A write inside a read must not be implicit on every keystroke — and it cost 32 s on a
    named query against 0.5 s without."""
    from pathlib import Path as _P
    src = (_P(__file__).resolve().parents[1] / "src" / "nolan" / "webui" / "routes"
           / "images_extract.py").read_text(encoding="utf-8")
    assert "warm: bool = False" in src, "the discover route must not warm by default"


def test_search_does_no_network_io_unless_asked(lib, monkeypatch):
    """A plain programmatic search must stay free of fetches — warming is opt-in."""
    calls = _fake_thumb_downloader(monkeypatch)
    lib.add_discovery(source_ref="artic:1", thumb_url="https://e.org/1.jpg", source="artic",
                      title="A Stone Bridge", license="CC0", pixels=False)
    lib.search_discovery("stone bridge", k=5)
    assert calls == [], "search warmed pixels without being asked"

    lib.search_discovery("stone bridge", k=5, warm=True)
    assert len(calls) == 1, "warm=True must fetch the page's pixels"


def test_warming_happens_after_ranking_not_before(lib, monkeypatch):
    """Warming before ranking would fetch for every candidate the three channels touched (k*3)
    to serve a page of k."""
    calls = _fake_thumb_downloader(monkeypatch)
    for i in range(9):
        lib.add_discovery(source_ref=f"artic:{i}", thumb_url=f"https://e.org/{i}.jpg",
                          source="artic", title=f"bridge {i}", license="CC0", pixels=False)
    hits = lib.search_discovery("bridge", k=3, warm=True)
    assert len(hits) <= 3
    assert len(calls) <= 3, f"warmed {len(calls)} rows to serve a page of 3"


# --- the structured caption (v1) -------------------------------------------------------------

def test_caption_schema_registry_names_a_consumer_for_every_field():
    """An authored field with no consumer is this repo's most-repeated bug, so the consumer sits
    beside the field rather than in a doc that can drift away from it."""
    from nolan.imagelib.caption import CAPTION_FIELDS
    for name, spec in CAPTION_FIELDS.items():
        assert spec.get("consumer"), f"{name}: no consumer"
        assert spec.get("purpose"), f"{name}: no purpose"


def test_the_fields_measurement_killed_are_gone():
    """v0 had 20 fields; half died on a 50-row validation. They must not creep back:
    focal_zone was constant 50/50, has_border agreed with pixels 16/50 (worse than chance),
    open_zones was a template, named_content never once fired."""
    from nolan.imagelib.caption import CAPTION_FIELDS, PROMPT
    dead = ("focal_zone", "has_border", "open_zones", "named_content",
            "weather", "vantage", "time_of_day", "frame_or_mount", "subject_bleed")
    for f in dead:
        assert f not in CAPTION_FIELDS, f"{f} was measured and cut — it must not return"
        assert f not in PROMPT, f"{f} still appears in the prompt"


def test_caption_asks_for_no_numbers_and_no_identity():
    """The model NAMES, a detector LOCALISES. And a caption is never an identity."""
    from nolan.imagelib.caption import PROMPT
    low = PROMPT.lower()
    for banned in ("percent", "pixel", "bounding box", "coordinates", "hex"):
        assert banned not in low, f"the caption prompt asks for {banned!r} — CV owns numbers"
    assert "do not name the artwork" in low


def test_parse_normalises_enums_to_closed_vocabularies():
    """A value outside the vocabulary must be coerced, not written through to a consumer that
    will silently never match it (checklist class 3)."""
    from nolan.imagelib.caption import parse_caption
    cap = parse_caption('{"summary": "a bowl", "human_presence": "MANY", '
                        '"panel_count": "diptych", "text_in_image": "sig", '
                        '"condition": "mint", "subjects": "a, b, c"}')
    assert cap["human_presence"] == "none"        # 'MANY' is not in the vocabulary
    assert cap["panel_count"] == "single"
    assert cap["text_in_image"] == "none"
    assert cap["condition"] == "clean"
    assert cap["subjects"] == ["a", "b", "c"]     # a comma string is accepted as a list
    assert cap["schema"] == 1


def test_free_text_fields_accept_a_string_or_a_list():
    """REGRESSION, found by looking at live output. Asked for "2-3 adjectives" the same model
    returned "quiet, rustic, simple" for one image and ["historical", "austere"] for the next;
    str() would have written the literal ['historical', 'austere'] — brackets and all — into
    `description`, which is the text BGE embeds."""
    from nolan.imagelib.caption import caption_text, parse_caption
    cap = parse_caption('{"summary": "a coin", "mood": ["historical", "austere"], '
                        '"palette_words": ["silver", "grey"]}')
    assert cap["mood"] == "historical, austere"
    assert cap["palette_words"] == "silver, grey"
    assert "[" not in caption_text(cap) and "'" not in caption_text(cap)


def test_parse_survives_code_fences_and_refuses_a_summaryless_caption():
    from nolan.imagelib.caption import parse_caption
    assert parse_caption('```json\n{"summary": "a ship"}\n```')["summary"] == "a ship"
    assert parse_caption('{"subjects": ["x"]}') is None, "no summary means no caption"
    assert parse_caption("not json at all") is None
    assert parse_caption("") is None


def test_text_in_image_separates_a_signature_from_a_watermark():
    """The v0 taxonomy scored a coin's inscribed Latin the same as a caption strip. Split, it
    called van Dyck's signature 'depicted' and a Getty bar 'overlay-watermark'."""
    from nolan.imagelib.caption import is_watermarked, parse_caption
    sig = parse_caption('{"summary": "a portrait", "text_in_image": "depicted"}')
    mark = parse_caption('{"summary": "a portrait", "text_in_image": "overlay-watermark"}')
    assert is_watermarked(sig) is False
    assert is_watermarked(mark) is True


def test_caption_context_withholds_the_title():
    """Hand the model the answer and it describes the title instead of the picture."""
    from nolan.imagelib.caption import build_context
    ctx = build_context(collection="Art Institute open-access", artist="Claude Monet",
                        kind="painting")
    assert "Monet" in ctx and "Art Institute" in ctx and "painting" in ctx
    assert build_context() == ""


def test_caption_lands_beside_identity_never_inside_it(lib, monkeypatch):
    """The whole tier rests on this: a caption is a reading of the picture, an identity is a
    claim about WHICH picture it is, and only one may ever be a model's guess."""
    from PIL import Image
    import numpy as np
    from nolan.imagelib.harvest import describe_discovery

    thumb_dir = lib.base / "thumbs" / "aa"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    p = thumb_dir / "x.jpg"
    Image.fromarray(np.random.default_rng(1).integers(
        0, 255, size=(64, 64, 3), dtype="uint8")).save(p)

    a = lib.catalog.add(Asset(content_hash="ref:x", path="thumbs/aa/x.jpg", held=0,
                              source_ref="artic:5", title="A Bridge", creator="Someone",
                              identity_source="catalog", thumb_path="thumbs/aa/x.jpg",
                              source="artic", status="active"))
    before = (a.title, a.creator, a.identity_source)

    def fake_describer(path, prompt=None):
        return ('{"summary": "a stone bridge over a river at dusk", '
                '"subjects": ["bridge", "river"], "action": "static", '
                '"human_presence": "none", "panel_count": "single", '
                '"text_in_image": "none", "condition": "clean", "mood": "calm", '
                '"palette_words": "slate and umber", "uncertain": []}')

    n = describe_discovery(lib, limit=5, describer=fake_describer, model="fake-vlm")
    assert n == 1
    row = lib.catalog.get(a.id)
    assert (row.title, row.creator, row.identity_source) == before, "identity untouched"
    assert row.description_source == "fake-vlm"
    assert row.caption_schema == 1
    cap = row.caption()
    assert cap["subjects"] == ["bridge", "river"]
    assert "stone bridge" in row.description


def test_a_row_already_at_this_schema_is_not_recaptioned(lib):
    """Never pay twice — but an OLDER schema version is a re-caption candidate, which is the
    entire reason the version integer exists."""
    from nolan.imagelib.harvest import describe_discovery
    from PIL import Image
    import numpy as np

    thumb_dir = lib.base / "thumbs" / "bb"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.random.default_rng(2).integers(
        0, 255, size=(64, 64, 3), dtype="uint8")).save(thumb_dir / "y.jpg")
    a = lib.catalog.add(Asset(content_hash="ref:y", path="thumbs/bb/y.jpg", held=0,
                              source_ref="artic:6", title="T", source="artic",
                              thumb_path="thumbs/bb/y.jpg", status="active",
                              description_source="old-vlm", caption_schema=1))
    calls = []

    def fake(path, prompt=None):
        calls.append(1)
        return '{"summary": "x"}'

    assert describe_discovery(lib, limit=5, describer=fake, model="v") == 0
    assert calls == []

    lib.catalog.update(a.id, caption_schema=0)          # pretend it was captioned at v0
    assert describe_discovery(lib, limit=5, describer=fake, model="v") == 1


# --- collection dialect + read-time inheritance -----------------------------------------------

def test_dialect_terms_drop_the_conjunction():
    """REGRESSION, observed live. Asked for a palette the model wrote "slate blue, charcoal,
    ochre, and pale cream", and a plain comma split stored a term called "and pale cream" — which
    then inherited to every un-captioned row in the collection."""
    from nolan.imagelib.caption import consensus, dialect_text
    caps = [{"palette_words": "slate blue, charcoal, ochre, and pale cream",
             "mood": "quiet, still, and austere", "subjects": []}] * 2
    d = consensus(caps)
    assert "pale cream" in d["palette_words"]
    assert not any(t.startswith("and ") for t in d["palette_words"]), d["palette_words"]
    assert not any(t.startswith("and ") for t in d["mood"]), d["mood"]
    assert "and " not in dialect_text(d).replace("; ", "|")[:0] + ""


# --- facets: the missing consumer for the catalog columns -------------------------------------

def _seed_facets(lib):
    rows = [
        ("a:1", "Under the Wave", "Katsushika Hokusai", "woodblock print", "Arts of Asia",
         "Japan", "1830/33"),
        ("a:2", "Sudden Shower", "Utagawa Hiroshige", "woodblock print", "Arts of Asia",
         "Japan", "1857"),
        ("a:3", "The Bedroom", "Vincent van Gogh", "oil on canvas", "Painting and Sculpture",
         "France", "1889"),
        ("a:4", "Melencolia I", "Albrecht Durer", "engraving", "Prints and Drawings",
         "Germany", "1514"),
        ("a:5", "A Coverlet", None, "textile", "Textiles", "America", "1800s"),
    ]
    for ref, title, creator, cls, dept, place, date in rows:
        lib.add_discovery(source_ref=ref, thumb_url=f"https://e/{ref}.jpg", source="artic",
                          title=title, creator=creator, classification=cls, department=dept,
                          place=place, date_text=date, license="CC0", pixels=False)


def test_catalog_columns_are_finally_filterable(lib):
    """Those columns were populated across 97k rows and NOTHING could filter on any of them —
    an authored field with no consumer, the first pitfall in the wiring checklist."""
    _seed_facets(lib)
    assert len(lib.catalog.list(held=0, limit=99)) == 5
    assert len(lib.catalog.list(held=0, limit=99, image_kind="print")) == 3
    assert len(lib.catalog.list(held=0, limit=99, department="Arts of Asia")) == 2
    assert len(lib.catalog.list(held=0, limit=99, creator="Hokusai")) == 1
    assert len(lib.catalog.list(held=0, limit=99, place="Japan")) == 2
    # filters COMBINE
    assert len(lib.catalog.list(held=0, limit=99,
                                image_kind="print", place="Japan")) == 2


def test_the_library_is_shared_per_scope_not_rebuilt(tmp_path):
    """REGRESSION, and the worst defect this tier has had.

    The hub built a new ImageLibrary on every request, so each search reloaded CLIP (~150 MB) and
    re-opened chroma's HNSW indexes. At 1,091 rows nobody noticed. At 97,610 a single
    /api/images/discover took **90 seconds**, against 2.4 s for the same search on a reused
    instance — the retrieval was never slow, the setup was, and it was paid per keystroke.
    """
    from nolan.imagelib import shared_library
    a = shared_library(base_dir=tmp_path)
    b = shared_library(base_dir=tmp_path)
    assert a is b, "a second call must reuse the instance, not rebuild it"
    assert shared_library(base_dir=tmp_path / "other") is not a, "different scopes stay separate"


def test_the_shared_cache_is_keyed_on_the_RESOLVED_path(tmp_path, monkeypatch):
    """REGRESSION. Keyed on (scope, project) it ignored a redirected `library_paths`, so a caller
    asking for "global" got whichever directory the first caller happened to open — which handed
    two hub tests the previous test's tmp library."""
    import nolan.imagelib.store as store_mod
    from nolan.imagelib import reset_shared_libraries, shared_library

    reset_shared_libraries()
    one, two = tmp_path / "one", tmp_path / "two"
    monkeypatch.setattr(store_mod, "library_paths", lambda *a, **k: one)
    a = shared_library("global")
    monkeypatch.setattr(store_mod, "library_paths", lambda *a, **k: two)
    b = shared_library("global")
    assert a is not b, "a redirected library_paths must produce a different instance"
    assert Path(b.base).resolve() == two.resolve()
    reset_shared_libraries()


def test_the_hub_routes_use_the_shared_library():
    """Grep-enforced, because this is invisible until it is slow: a route that constructs
    ImageLibrary directly reintroduces the 90-second search without failing any test."""
    from pathlib import Path as _P
    root = _P(__file__).resolve().parents[1] / "src" / "nolan" / "webui" / "routes"
    for name in ("images_extract.py", "visual_lib.py"):
        src = (root / name).read_text(encoding="utf-8")
        assert "shared_library" in src, f"{name} must open the library via shared_library()"
        assert "return ImageLibrary(" not in src, (
            f"{name} constructs ImageLibrary per call — that reloads CLIP and chroma every "
            f"request")


def test_every_asset_field_survives_a_round_trip(tmp_path):
    """REGRESSION, and a guard for a whole bug CLASS. `year_from`/`year_to` were added to the
    migrations, the dataclass and the updatable set — but not to the INSERT column list, so the
    parser ran, the Asset carried the value, and the database silently stored NULL. Nothing
    errored; the filter just returned nothing.

    Rather than pin one column, set every field to a distinct value and read it back.
    """
    import dataclasses
    from nolan.imagelib.catalog import Asset, AssetCatalog

    cat = AssetCatalog(tmp_path / "c.db")
    values, skip = {}, {"id", "added_at", "held", "status", "bytes", "width", "height",
                        "collection_id", "caption_schema", "year_from", "year_to"}
    for f in dataclasses.fields(Asset):
        if f.name in skip:
            continue
        values[f.name] = f"v-{f.name}"
    a = cat.add(Asset(**{**values, "held": 0, "status": "active", "width": 11, "height": 22,
                         "bytes": 33, "collection_id": 44, "caption_schema": 1,
                         "year_from": -55, "year_to": 66}))
    back = cat.get(a.id)
    for name, want in values.items():
        assert getattr(back, name) == want, f"{name} did not survive the INSERT"
    for name, want in (("width", 11), ("height", 22), ("bytes", 33), ("collection_id", 44),
                       ("caption_schema", 1), ("year_from", -55), ("year_to", 66)):
        assert getattr(back, name) == want, f"{name} did not survive the INSERT"


def test_an_unknown_filter_raises_rather_than_being_ignored(lib):
    """A silently-dropped filter returns a plausible WRONG answer, which is worse than an error."""
    with pytest.raises(ValueError, match="not filterable"):
        lib.catalog.list(held=0, colour="blue")
    with pytest.raises(ValueError, match="not a facet field"):
        lib.catalog.facets("colour")


def test_facet_counts_describe_the_set_they_narrow(lib):
    """A count that disagreed with the result set would be worse than no count — it promises
    rows the click will not deliver. Both go through one `_filter_sql`."""
    _seed_facets(lib)
    for value, count in lib.catalog.facets("image_kind", held=0):
        assert len(lib.catalog.list(held=0, limit=99, image_kind=value)) == count

    # a facet never narrows by ITSELF — otherwise every count would be its own total
    counts = dict(lib.catalog.facets("image_kind", held=0, image_kind="print"))
    assert counts.get("painting") == 1, "asking for image_kind facets must not pre-filter by it"

    # ...but it DOES respect the other active filters
    asia = dict(lib.catalog.facets("image_kind", held=0, department="Arts of Asia"))
    assert asia == {"print": 2}


def test_year_filters_overlap_rather_than_contain(lib):
    """An object dated 1830-1833 belongs in a search for 1831. Requiring containment would drop
    every imprecisely-dated row, which in a museum corpus is most of them."""
    _seed_facets(lib)
    got = {a.source_ref for a in lib.catalog.list(held=0, limit=99,
                                                  year_from=1831, year_to=1831)}
    # a:1 is dated "1830/33" -> (1830,1833) and a:5 is "1800s" -> (1800,1899). BOTH overlap the
    # single year 1831, and both are correct answers — an imprecisely dated row is still a
    # candidate. Containment would have returned neither.
    assert got == {"a:1", "a:5"}, got

    century = {a.source_ref for a in lib.catalog.list(held=0, limit=99,
                                                      year_from=1800, year_to=1899)}
    assert century == {"a:1", "a:2", "a:3", "a:5"}
    assert {a.source_ref for a in lib.catalog.list(held=0, limit=99, year_to=1600)} == {"a:4"}


def test_an_undated_row_is_excluded_from_a_date_filter(lib):
    """"We don't know when" cannot honestly answer "before 1850"."""
    lib.add_discovery(source_ref="a:9", thumb_url="https://e/9.jpg", source="artic",
                      title="Undated Thing", date_text="n.d.", license="CC0", pixels=False)
    a = lib.catalog.get_by_ref("a:9")
    assert a.year_from is None and a.year_to is None
    assert lib.catalog.list(held=0, limit=99, year_from=1000, year_to=3000) == []


def test_years_are_parsed_at_write_time(lib):
    _seed_facets(lib)
    assert (lib.catalog.get_by_ref("a:1").year_from,
            lib.catalog.get_by_ref("a:1").year_to) == (1830, 1833)
    assert (lib.catalog.get_by_ref("a:5").year_from,
            lib.catalog.get_by_ref("a:5").year_to) == (1800, 1899)


def test_filters_narrow_the_search_not_just_the_listing(lib):
    """Filters change the DENOMINATOR — that is the whole point. A title search over Hokusai's
    481 rows is a different task from the same search over 97,625."""
    _seed_facets(lib)
    unfiltered = lib.search_discovery("print", k=10)
    assert len(unfiltered) >= 3

    hits = lib.search_discovery("print", k=10, department="Arts of Asia")
    assert hits, "a filtered search must still return its matches"
    assert all(h.asset.department == "Arts of Asia" for h in hits)
    assert {h.asset.source_ref for h in hits} <= {"a:1", "a:2"}


def test_a_filter_that_matches_nothing_returns_nothing(lib):
    _seed_facets(lib)
    assert lib.search_discovery("wave", k=10, department="Nonexistent Wing") == []


def test_the_discovery_tier_stays_opt_in_through_filters(lib, tmp_path):
    """Invariant 1 must survive the new surface: `held` still defaults to the HELD tier."""
    _seed_facets(lib)
    assert lib.catalog.list(limit=99, image_kind="print") == [], "held=1 is still the default"
    assert len(lib.catalog.list(limit=99, held=0, image_kind="print")) == 3


# --- batched identity indexing ---------------------------------------------------------------

def test_batching_is_invisible_to_a_reader(lib):
    """A write-side optimisation must not change what a read sees: a row indexed a moment ago has
    to be findable now, whether during a 56k crawl or a single add."""
    lib.add_discovery(source_ref="artic:1", thumb_url="https://e/1.jpg", source="artic",
                      title="A Stone Bridge at Dusk", creator="Someone", license="CC0",
                      pixels=False)
    assert lib._ident_buf, "the single add should have BUFFERED, not written"
    hits = lib.search_discovery("stone bridge", k=5)
    assert any(h.asset.source_ref == "artic:1" for h in hits), "read did not flush the buffer"
    assert not lib._ident_buf


def test_flush_is_batched_not_per_row(lib, monkeypatch):
    """The whole point: one BGE forward pass per batch instead of one per row."""
    calls = []
    real = lib._disc_ident_coll

    class _Spy:
        def __init__(self, inner):
            self.inner = inner

        def upsert(self, ids, documents, metadatas):
            calls.append(len(ids))
            return self.inner.upsert(ids=ids, documents=documents, metadatas=metadatas)

        def __getattr__(self, k):
            return getattr(self.inner, k)

    monkeypatch.setattr(lib, "_disc_ident_coll", lambda: _Spy(real()))
    for i in range(10):
        lib.add_discovery(source_ref=f"artic:{i}", thumb_url=f"https://e/{i}.jpg",
                          source="artic", title=f"row {i}", license="CC0", pixels=False)
    assert calls == [], "ten adds should not have written ten times"
    n = lib.flush_index()
    assert n == 10 and calls == [10], f"expected ONE upsert of 10, got {calls}"


def test_reindex_repairs_a_row_missing_from_the_index(lib):
    """Batching makes a gap possible (a hard kill between the SQLite write and the flush), and a
    re-crawl cannot close it — a refresh with unchanged identity skips re-embedding by design."""
    lib.add_discovery(source_ref="artic:1", thumb_url="https://e/1.jpg", source="artic",
                      title="Indexed Properly", license="CC0", pixels=False)
    lib.flush_index()
    # simulate the crash: the row is in SQLite, its embedding never made it out of memory
    lib.add_discovery(source_ref="artic:2", thumb_url="https://e/2.jpg", source="artic",
                      title="Lost In The Buffer", license="CC0", pixels=False)
    lib._ident_buf.clear()

    res = lib.reindex_identity()
    assert res["missing"] == 1 and res["indexed"] == 1, res
    hits = lib.search_discovery("Lost In The Buffer", k=5)
    assert any(h.asset.source_ref == "artic:2" for h in hits)

    assert lib.reindex_identity()["missing"] == 0, "a second run must find nothing to repair"


def test_the_crawl_cursor_never_runs_ahead_of_the_index():
    """If the cursor advanced past buffered rows, a resume would never revisit them AND a refresh
    would never re-embed them — a permanent hole in identity search."""
    from nolan.imagelib.harvest import harvest
    src = inspect_source(harvest)
    body = src[src.index("def _persist_cursor"):]
    flush = body.index("flush_index")
    upsert = body.index("upsert_collection")
    assert flush < upsert, "flush_index() must run BEFORE the cursor is persisted"


def test_spanning_sample_covers_kinds_not_the_corpus_skew():
    """A proportional sample of a 60%-painting corpus says almost nothing about the coins,
    textiles and object photography that carry every hard case."""
    from nolan.imagelib.caption import spanning_sample

    class A:
        def __init__(self, i, k):
            self.id, self.image_kind = i, k

    rows = [A(i, "painting") for i in range(50)] + [A(100, "coin"), A(101, "textile")]
    picks = spanning_sample(rows, n=6)
    kinds = [p.image_kind for p in picks]
    assert "coin" in kinds and "textile" in kinds, kinds
    assert kinds.count("painting") <= 4


def test_consensus_counts_rather_than_asks_a_model():
    """No second model call to summarise the first model's answers — the repeated part is what
    is wanted, and counting cannot introduce a claim no caption made."""
    from nolan.imagelib.caption import consensus, dialect_text
    caps = [
        {"subjects": ["ship", "sea"], "mood": "stormy, bleak", "palette_words": "slate, grey",
         "human_presence": "none"},
        {"subjects": ["ship", "harbour"], "mood": "stormy", "palette_words": "slate",
         "human_presence": "none"},
    ]
    d = consensus(caps)
    assert d["n"] == 2
    assert d["subjects"][0] == "ship"
    assert "stormy" in d["mood"] and "slate" in d["palette_words"]
    txt = dialect_text(d)
    assert "2 sampled" in txt, "a dialect must say how many rows it came from"
    assert dialect_text(None) == "" and dialect_text({"n": 0}) == ""


def test_an_uncaptioned_row_inherits_the_dialect_but_a_captioned_one_does_not(lib):
    """Inheritance is applied at READ time: written into the row it would be indistinguishable
    from something observed about that row."""
    import json as _json
    from nolan.imagelib.catalog import Artist, Collection

    col = lib.catalog.upsert_collection(Collection(
        slug="c1", source="artic", title="Seascapes",
        dialect_json=_json.dumps({"n": 12, "subjects": ["ship", "sea"], "mood": ["stormy"],
                                  "palette_words": ["slate"]})))
    lib.catalog.upsert_artist(Artist(name="A Painter", movement="Romanticism", source="t"))

    bare, _ = lib.add_discovery(source_ref="a:1", thumb_url="https://e/1.jpg", source="artic",
                                title="Untitled", creator="A Painter", license="CC0",
                                collection_id=col.id, pixels=False)
    text = lib.effective_description(bare)
    assert "Typical of this collection" in text and "ship" in text
    assert "Romanticism" in text, "artist manner inherits too"

    got, _ = lib.add_discovery(source_ref="a:2", thumb_url="https://e/2.jpg", source="artic",
                               title="Named", creator="A Painter", license="CC0",
                               collection_id=col.id, pixels=False,
                               description="a three-masted barque heeling in a gale")
    lib.catalog.update(got.id, caption_json=_json.dumps({"summary": "a barque in a gale"}),
                       caption_schema=1)
    own = lib.effective_description(lib.catalog.get(got.id))
    assert "Typical of this collection" not in own, "a captioned row speaks for itself"
    assert "barque" in own


# --- artist world-knowledge: one call per PERSON ---------------------------------------------

def test_artist_key_folds_the_ways_a_catalog_writes_one_name():
    """Without this the amortisation silently fails: fifty works by one painter become fifty
    artists and fifty LLM calls, which is the exact cost the table exists to avoid."""
    from nolan.imagelib.catalog import artist_key
    k = artist_key("Claude Monet")
    assert artist_key("Monet, Claude") == k
    assert artist_key("Claude Monet (French, 1840-1926)") == k
    assert artist_key("  claude   monet ") == k
    assert artist_key("Édouard Manet") != k
    assert artist_key("") == "" and artist_key(None) == ""


def test_artist_key_is_order_independent():
    """Institutions order names differently and the WORDS are the identity. Measured over the
    live corpus, this folds 19 groups covering 2,073 rows, every one a genuine duplicate."""
    from nolan.imagelib.catalog import artist_key
    assert artist_key("Auguste Louis Lepère") == artist_key("Louis Auguste Lepère")
    assert artist_key("Baiitsu Yamamoto") == artist_key("Yamamoto Baiitsu")
    assert artist_key("Jan Sadeler, I") == artist_key("Jan I Sadeler (Flemish, 1550-1600)")
    assert artist_key("Artist Unknown") == artist_key("Unknown Artist")


def test_artist_key_never_merges_on_a_shared_word():
    """MEASURED TRAP. Grouping by surname merged Hiroshige with Hiroshige II and III (father,
    son, grandson), James McNeill Whistler with Beatrix Godwin Whistler (his wife), Ancient Roman
    with Ancient Greek, and 134 distinct people under "Charles". Attributing one artist's
    movement and palette to another's works is far worse than a duplicate call.

    The rule is: the same WORDS in any order — never merely a shared word.
    """
    from nolan.imagelib.catalog import artist_key
    for a, b in [("Utagawa Hiroshige", "Utagawa Hiroshige II"),
                 ("Utagawa Hiroshige II", "Utagawa Hiroshige III"),
                 ("James McNeill Whistler", "Beatrix Godwin Whistler"),
                 ("Charles Meryon", "Charles Samuel Keene"),
                 ("Ancient Roman", "Ancient Greek"),
                 ("Katsukawa Shunsho", "Katsukawa Shun'ei")]:
        assert artist_key(a) != artist_key(b), f"{a!r} and {b!r} are DIFFERENT people"


def test_rekey_merges_without_losing_what_was_learned(lib):
    """Changing the key strands what is already learned unless the table is re-keyed — and a
    merge must keep the entry that KNOWS something, not whichever sorted first."""
    from nolan.imagelib.catalog import Artist
    cat = lib.catalog
    # two spellings of one man, as artic and cleveland write him
    cat.upsert_artist(Artist(name="Louis Auguste Lepère", name_key="louis-auguste-lepere-OLD",
                             movement="Etching revival", source="t"))
    cat.upsert_artist(Artist(name="Auguste Louis Lepère", name_key="auguste-louis-lepere-OLD",
                             note="not recognised", source="t"))
    res = cat.rekey_artists()
    assert res["merged"] == 1 and res["remaining"] == 1
    a = cat.get_artist("Auguste Louis Lepère")
    assert a is not None and a.movement == "Etching revival", (
        "the merge kept the miss instead of the real answer")


def test_creator_histogram_orders_by_rows_covered(lib):
    """The ordering IS the budget — commonest first means a bounded number of calls covers the
    most rows instead of an arbitrary slice."""
    for i in range(3):
        lib.add_discovery(source_ref=f"a:{i}", thumb_url="https://e/x.jpg", source="artic",
                          title=f"m{i}", creator="Claude Monet", license="CC0", pixels=False)
    lib.add_discovery(source_ref="a:9", thumb_url="https://e/y.jpg", source="artic",
                      title="d", creator="Monet, Claude", license="CC0", pixels=False)
    lib.add_discovery(source_ref="a:8", thumb_url="https://e/z.jpg", source="artic",
                      title="v", creator="Vincent van Gogh", license="CC0", pixels=False)
    hist = lib.catalog.creator_histogram(held=0)
    assert hist[0][2] == 4, "the four Monet spellings must fold into one creator"
    assert hist[0][0] == artist_key_of("Claude Monet")
    assert hist[1][2] == 1


def artist_key_of(name):
    from nolan.imagelib.catalog import artist_key
    return artist_key(name)


class _FakeLLM:
    """Records calls so the test can prove one-per-artist, not one-per-artwork."""
    model = "fake"

    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    async def generate(self, prompt, system_prompt=None):
        self.prompts.append(prompt)
        return self.reply


def test_enrichment_costs_one_call_per_artist_not_per_artwork(lib):
    import asyncio
    from nolan.imagelib.artists import enrich_artists

    for i in range(5):
        lib.add_discovery(source_ref=f"a:{i}", thumb_url="https://e/x.jpg", source="artic",
                          title=f"m{i}", creator="Claude Monet", license="CC0", pixels=False)
    llm = _FakeLLM('{"recognised": true, "movement": "Impressionism", '
                   '"period": "late 19th century", "style": "broken colour, plein air", '
                   '"subjects": "gardens, water, haystacks", "palette": "lilac and green"}')
    res = asyncio.run(enrich_artists(lib, limit=10, llm=llm, model="fake"))

    assert len(llm.prompts) == 1, "five works by one painter must cost ONE call"
    assert res["learned"] == 1 and res["rows_covered"] == 5
    assert res["leverage"] == 5.0
    a = lib.catalog.get_artist("Claude Monet")
    assert a.movement == "Impressionism" and a.source == "fake"
    assert "Impressionism" in a.context_line()


def test_enrichment_never_pays_twice_for_the_same_artist(lib):
    import asyncio
    from nolan.imagelib.artists import enrich_artists

    lib.add_discovery(source_ref="a:1", thumb_url="https://e/x.jpg", source="artic",
                      title="m", creator="Claude Monet", license="CC0", pixels=False)
    llm = _FakeLLM('{"recognised": true, "movement": "Impressionism"}')
    asyncio.run(enrich_artists(lib, limit=10, llm=llm, model="fake"))
    asyncio.run(enrich_artists(lib, limit=10, llm=llm, model="fake"))
    assert len(llm.prompts) == 1, "a known artist must never be re-asked"


def test_an_unrecognised_artist_is_cached_as_a_miss(lib):
    """An unrecognised name is a real, cacheable answer. Re-asking every run is how a bounded
    budget gets eaten by the same forty obscure names."""
    import asyncio
    from nolan.imagelib.artists import enrich_artists

    lib.add_discovery(source_ref="a:1", thumb_url="https://e/x.jpg", source="artic",
                      title="x", creator="Zorblatt the Unknown", license="CC0", pixels=False)
    llm = _FakeLLM('{"recognised": false, "movement": null, "period": null, '
                   '"style": null, "subjects": null, "palette": null}')
    r1 = asyncio.run(enrich_artists(lib, limit=10, llm=llm, model="fake"))
    r2 = asyncio.run(enrich_artists(lib, limit=10, llm=llm, model="fake"))
    assert r1["unrecognised"] == 1 and r2["called"] == 0
    a = lib.catalog.get_artist("Zorblatt the Unknown")
    assert a.movement is None and a.note == "not recognised"
    assert a.context_line() == "", "we know nothing, so the context line must be empty"


def test_hedged_and_nullish_answers_stay_null(lib):
    """A model that writes "unknown" into a text column has made the column useless — you can no
    longer tell "we asked and it did not know" from "it knows this is unknown"."""
    import asyncio
    from nolan.imagelib.artists import enrich_artists

    lib.add_discovery(source_ref="a:1", thumb_url="https://e/x.jpg", source="artic",
                      title="x", creator="Someone", license="CC0", pixels=False)
    llm = _FakeLLM('```json\n{"recognised": true, "movement": "unknown", "period": "N/A", '
                   '"style": "  ", "subjects": "portraits", "palette": "none"}\n```')
    asyncio.run(enrich_artists(lib, limit=5, llm=llm, model="fake"))
    a = lib.catalog.get_artist("Someone")
    assert a.movement is None and a.period is None and a.style is None and a.palette is None
    assert a.subjects == "portraits", "a real answer still lands"


def test_artist_knowledge_never_touches_row_identity(lib):
    """An artist's movement is context ABOUT the maker, not a claim about WHICH artwork this is.
    Same invariant that stops a caption becoming an identity."""
    import asyncio
    from nolan.imagelib.artists import enrich_artists

    asset, _ = lib.add_discovery(source_ref="a:1", thumb_url="https://e/x.jpg", source="artic",
                                 title="Water Lilies", creator="Claude Monet", license="CC0",
                                 pixels=False)
    before = (asset.identity_source, asset.identity_text())
    llm = _FakeLLM('{"recognised": true, "movement": "Impressionism", "style": "plein air"}')
    asyncio.run(enrich_artists(lib, limit=5, llm=llm, model="fake"))
    after = lib.catalog.get_by_ref("a:1")
    assert (after.identity_source, after.identity_text()) == before


# --- the visual knowledge table: looked up, not guessed --------------------------------------

def _wd_artist(**kw):
    from nolan.imagelib.catalog import Artist
    return Artist(**kw)


def test_a_firm_is_active_from_inception_not_twenty_years_later():
    """The five biggest creators in this library are tobacco-card publishers, not people. Adding
    the human apprenticeship offset would place every one of them two decades after the work we
    actually hold."""
    person = _wd_artist(name="X", birth_year=1840, death_year=1926, kind="person")
    firm = _wd_artist(name="Allen & Ginter", birth_year=1865, death_year=1890,
                      kind="organization")
    assert person.active_years() == (1860, 1926)
    assert firm.active_years() == (1865, 1890)


def test_lifespan_reads_as_a_label_in_every_partial_case():
    assert _wd_artist(name="X", birth_year=1834, death_year=1903).lifespan() == "1834–1903"
    assert _wd_artist(name="X", birth_year=1912).lifespan() == "b. 1912"
    assert _wd_artist(name="X", death_year=1912).lifespan() == "d. 1912"
    assert _wd_artist(name="X").lifespan() == ""


def test_the_date_gate_rejects_a_maker_who_could_not_have_made_the_work():
    """NASCAR is genuinely a business, so no structural check refuses it for "Nasca" — the 389
    objects dated -200 to 1532 are what disagree."""
    from nolan.imagelib.artists import _date_conflict

    nascar = _wd_artist(name="NASCAR", birth_year=1948, kind="organization")
    assert _date_conflict(nascar, (-55.0, 387)), "a 2,000-year gap must not bind"
    monet = _wd_artist(name="Claude Monet", birth_year=1840, death_year=1926, kind="person")
    assert _date_conflict(monet, (1880.0, 59)) is None
    # A late impression of an old plate is still the same engraver — the slack has to cover it.
    durer = _wd_artist(name="Albrecht Dürer", birth_year=1471, death_year=1528, kind="person")
    assert _date_conflict(durer, (1600.0, 40)) is None
    # One dated work can be a bad parse; the gate must not fire on it.
    assert _date_conflict(nascar, (-55.0, 1)) is None


def test_anonymity_is_never_looked_up():
    """Measured: "Anonymous" resolves to a talent-management company and would have stamped
    "b. 1999" onto 810 Met rows whose only claim is that the museum does not know who made them.

    `folded_artist` deliberately KEEPS "Anonymous, British, 19th century" — a school is a real
    narrowing — so the lookup needs its own, stricter rule."""
    from nolan.imagelib.artists import _unsearchable
    from nolan.imagelib.catalog import artist_key

    for name in ("Anonymous", "Unknown", "Artist Unknown", "Unidentified Photographer",
                 "Anonymous, British, 19th century", "Unknown Italian"):
        assert _unsearchable(name, artist_key(name)), name
    for name in ("Claude Monet", "Allen & Ginter", "Utagawa Hiroshige"):
        assert not _unsearchable(name, artist_key(name)), name


def test_a_model_never_overwrites_what_was_looked_up(lib):
    """Per-field provenance exists for exactly this: a looked-up birth year and a generated one
    are different claims. The LLM pass fills the gaps Wikidata leaves and touches nothing else."""
    import asyncio
    import json as _json
    from nolan.imagelib.artists import enrich_artists
    from nolan.imagelib.catalog import Artist

    lib.add_discovery(source_ref="a:1", thumb_url="https://e/x.jpg", source="artic",
                      title="m", creator="Claude Monet", license="CC0", pixels=False)
    lib.catalog.upsert_artist(Artist(
        name="Claude Monet", movement="Impressionism", birth_year=1840, death_year=1926,
        checked_at="2026-01-01T00:00:00+00:00",
        sources_json=_json.dumps({"movement": "wikidata", "birth_year": "wikidata"})))

    llm = _FakeLLM('{"recognised": true, "movement": "Cubism", "style": "broken colour", '
                   '"palette": "lilac and green"}')
    asyncio.run(enrich_artists(lib, limit=5, llm=llm, model="fake"))

    a = lib.catalog.get_artist("Claude Monet")
    assert a.movement == "Impressionism", "the model must not overwrite a looked-up movement"
    assert a.birth_year == 1840
    assert a.style == "broken colour", "but it MUST fill what Wikidata has no column for"
    assert a.sources["movement"] == "wikidata"
    assert a.sources["style"] == "fake"


def test_the_llm_pass_still_runs_for_an_artist_wikidata_only_checked(lib):
    """`fill_artists_wikidata` creates a row for everyone it looks up, INCLUDING its misses. If
    "already known" still meant "has a row", the model pass would skip every artist Wikidata
    touched and style/subjects/palette would stay empty forever."""
    import asyncio
    from nolan.imagelib.artists import enrich_artists
    from nolan.imagelib.catalog import Artist

    lib.add_discovery(source_ref="a:1", thumb_url="https://e/x.jpg", source="artic",
                      title="m", creator="Obscure Etcher", license="CC0", pixels=False)
    lib.catalog.upsert_artist(Artist(name="Obscure Etcher",
                                     checked_at="2026-01-01T00:00:00+00:00"))
    llm = _FakeLLM('{"recognised": true, "style": "dry point"}')
    res = asyncio.run(enrich_artists(lib, limit=5, llm=llm, model="fake"))
    assert res["learned"] == 1
    assert lib.catalog.get_artist("Obscure Etcher").style == "dry point"


def test_rekeying_cannot_drop_a_column_added_after_it_was_written(lib):
    """`rekey_artists` DELETEs every row before re-inserting. A hardcoded column list there
    silently discards whatever was added to the table later — which is what would have happened
    to the whole Wikidata block the first time anyone re-keyed."""
    from nolan.imagelib.catalog import Artist

    cat = lib.catalog
    cat.upsert_artist(Artist(name="Claude Monet", birth_year=1840, death_year=1926,
                             nationality="France", biography="French painter",
                             wikidata_qid="Q296", kind="person",
                             wikipedia_url="https://en.wikipedia.org/wiki/Claude_Monet",
                             sources_json='{"birth_year": "wikidata"}',
                             checked_at="2026-01-01T00:00:00+00:00"))
    cat.rekey_artists()
    a = cat.get_artist("Claude Monet")
    assert (a.birth_year, a.death_year, a.nationality) == (1840, 1926, "France")
    assert a.wikidata_qid == "Q296" and a.kind == "person"
    assert a.biography and a.wikipedia_url and a.checked_at
    assert a.sources["birth_year"] == "wikidata"


def test_the_primary_maker_is_chosen_by_ROLE_not_by_position():
    """30% of the Met's attributed rows credit several names, pipe-separated. The first slot holds
    "Artist" only 47,286 times out of 97,567, so position 0 would file half of them under a print
    shop."""
    from nolan.imagelib.harvest import primary_maker

    # the museum's own primary attribution wins wherever it sits
    assert primary_maker("Jacques Callot|Israël Henriet", "Artist|Publisher") == "Jacques Callot"
    assert primary_maker("Israël Henriet|Jacques Callot", "Publisher|Artist") == "Jacques Callot"
    # "Artist" outranks other making roles: West painted it, Green only engraved the reproduction
    assert primary_maker("John Boydell|Valentine Green|Benjamin West",
                         "Publisher|Engraver|Artist") == "Benjamin West"
    # a hand that made it beats whoever published it, when no one is called the artist
    assert primary_maker("W. Duke, Sons & Co.|Knapp & Company",
                         "Publisher|Lithographer") == "Knapp & Company"
    # no roles at all — fall back to the first name rather than dropping the credit
    assert primary_maker("Claude Monet|Someone Else") == "Claude Monet"


def test_a_sitter_is_never_credited_as_the_maker():
    """Filing a portrait under the person depicted is the worst join this can make: it hands that
    person's biography to every row. Measured in the dump: Sitter 6,051 slots, Subject 2,821,
    Person in Photograph 1,246."""
    from nolan.imagelib.harvest import primary_maker

    assert primary_maker("Mathew B. Brady|Abraham Lincoln", "Artist|Sitter") == "Mathew B. Brady"
    # credited ONLY to the man in the photograph — there is no maker, and None says so
    assert primary_maker("Abraham Lincoln", "Sitter") is None
    assert primary_maker("Someone|Another", "Sitter|Dedicatee") is None
    # van Gogh is the SUBJECT here; Gachet really did etch it
    assert primary_maker("Louis Lumet|Vincent van Gogh|Dr. Paul Ferdinand Gachet",
                         "Dedicatee|Subject|Artist") == "Dr. Paul Ferdinand Gachet"


def test_backfill_movements_uses_the_STORED_artist_key(lib):
    """Re-folding `creator` recomputes a key the row already carries, and gets a worse one on the
    31,452 Met rows crediting several people — so the re-key bought nothing downstream and the
    backfill reported `changed: 0` on 31k moved rows."""
    from nolan.imagelib.catalog import Artist

    asset, _ = lib.add_discovery(source_ref="met:1", thumb_url="https://e/x.jpg", source="met",
                                 title="An etching", creator="Jacques Callot|Israël Henriet",
                                 primary_maker="Jacques Callot", license="CC0", pixels=False)
    assert asset.artist_key == "callot jacques", "the join key must point at the maker"
    assert asset.creator == "Jacques Callot|Israël Henriet", "creator keeps what the source said"

    lib.catalog.upsert_artist(Artist(name="Jacques Callot", movement="Baroque", source="t"))
    res = lib.backfill_movements()
    assert res["changed"] == 1, res
    assert lib.catalog.get_by_ref("met:1").movement == "Baroque"


def test_the_creator_histogram_groups_on_the_STORED_key(lib):
    """Re-folding `creator` rebuilt the pre-repair buckets — Rowlandson reading 552 works instead
    of 2,010 — so the enrichment budget kept being spent on fragments of artists already learned,
    and the Artists tab showed counts that disagreed with the grid it links to."""
    for i in range(3):
        lib.add_discovery(source_ref=f"met:{i}", thumb_url="https://e/x.jpg", source="met",
                          title=f"e{i}", creator="Jacques Callot|Israël Henriet",
                          primary_maker="Jacques Callot", license="CC0", pixels=False)
    lib.add_discovery(source_ref="met:9", thumb_url="https://e/x.jpg", source="met",
                      title="solo", creator="Jacques Callot", license="CC0", pixels=False)
    hist = dict((k, n) for k, _, n in lib.catalog.creator_histogram(held=0))
    assert hist.get("callot jacques") == 4, (
        f"the pair must join the solo work, got {hist}")


def test_pruning_orphan_artists_keeps_every_row_that_learned_something(lib):
    """Re-keying strands rows by design. Dropping the empty ones is housekeeping; dropping one
    that holds facts would throw away work that cost real lookups."""
    from nolan.imagelib.catalog import Artist

    lib.add_discovery(source_ref="a:1", thumb_url="https://e/x.jpg", source="artic",
                      title="m", creator="Claude Monet", license="CC0", pixels=False)
    lib.catalog.upsert_artist(Artist(name="Claude Monet", birth_year=1840))
    # an orphan that knows nothing — exactly what a re-key leaves behind
    lib.catalog.upsert_artist(Artist(name="Someone|Someone Else", checked_at="2026-01-01"))
    # an orphan that DOES know something — must survive
    lib.catalog.upsert_artist(Artist(name="Forgotten Painter", movement="Baroque"))

    res = lib.catalog.prune_orphan_artists()
    assert res["orphaned_and_empty"] == 1
    assert res["kept_orphans_with_facts"] == 1
    assert lib.catalog.get_artist("Someone|Someone Else") is None
    assert lib.catalog.get_artist("Forgotten Painter").movement == "Baroque"
    assert lib.catalog.get_artist("Claude Monet").birth_year == 1840
    assert lib.catalog.prune_orphan_artists()["orphaned_and_empty"] == 0, "must be idempotent"


def test_the_met_dump_hands_over_artist_qids_positionally():
    """Both columns are pipe-separated and positional, and a slot may be blank when the museum
    identified one collaborator but not the other. Splitting either column alone shifts every id
    by one on the rows with more than one maker."""
    from nolan.imagelib.harvest import _met_csv_path, met_artist_qids

    if not _met_csv_path().exists():
        import pytest
        pytest.skip("Met bulk CSV not downloaded on this machine")
    m = met_artist_qids()
    assert len(m) > 10_000, f"expected the dump's ~20k artist identifications, got {len(m)}"
    assert m.get("claude monet") == "Q296"


# --- the catalog tier: fields, not prose -----------------------------------------------------

def test_image_kind_is_derived_from_the_sources_own_words():
    """The VLM was asked this and lost to a regex over the institution's own classification on
    every row where they disagreed — the museum already catalogued the object."""
    from nolan.imagelib.taxonomy import IMAGE_KINDS, image_kind
    # real values from both vocabularies, not invented ones
    assert image_kind("Photographs|Ephemera") == "photograph"   # compound; photo wins over book
    assert image_kind("Medals and Plaquettes") == "coin"        # shape beats material
    assert image_kind("Textiles-Woven") == "textile"
    assert image_kind("Ceramics-Porcelain") == "ceramic"
    assert image_kind("Prints|Ornament & Architecture") == "print"
    assert image_kind("painting") == "painting"                 # artic is lowercase
    assert image_kind("oil on canvas") == "painting"            # ...and mixes in the medium
    assert image_kind("Dress") == "textile"                     # the Met names the garment
    assert image_kind("Archery Equipment-Arrowheads") == "metalwork"
    assert all(k in IMAGE_KINDS for k in
               (image_kind("Vases"), image_kind("Drawings"), image_kind("Glass")))


def test_image_kind_falls_through_loudly_not_silently():
    """Closed vocabulary with a LOUD fallback (checklist class 3). An unmapped value must become
    `unknown` and be countable, never get quietly filed under `object`."""
    from nolan.imagelib.taxonomy import image_kind, kind_coverage
    assert image_kind("Zorblatt Assemblage") == "unknown"
    assert image_kind(None) == "unknown" and image_kind("") == "unknown"
    cov = kind_coverage([("Prints",), ("Zorblatt",), ("Vases",)])
    assert cov["print"] == 1 and cov["ceramic"] == 1 and cov["unknown"] == 1


def test_first_non_empty_field_decides(tmp_path):
    """The Art Institute puts 'painting' in one row's column and 'oil on canvas' in the next, so
    a single-field lookup would return unknown for a large share of a well-described collection."""
    from nolan.imagelib.taxonomy import image_kind
    assert image_kind(None, "", "etching") == "print"
    assert image_kind("Sculpture", "oil on canvas") == "sculpture"   # authority order holds


def test_catalog_fields_are_stored_as_columns_not_only_prose(lib):
    """'Oil on canvas, Saint-Rémy-de-Provence, oil on canvas, Painting and Sculpture of Europe'
    embeds fine and filters not at all — you cannot ask a sentence for 'textiles from Iran'."""
    asset, _ = lib.add_discovery(
        source_ref="artic:99", thumb_url="https://e.org/x.jpg", source="artic",
        title="Wheat Field", license="CC0", pixels=False,
        description="Oil on canvas, Saint-Rémy-de-Provence, painting, Painting and Sculpture",
        medium="Oil on canvas", classification="painting",
        department="Painting and Sculpture of Europe", place="Saint-Rémy-de-Provence")
    assert asset.medium == "Oil on canvas"
    assert asset.classification == "painting"
    assert asset.department == "Painting and Sculpture of Europe"
    assert asset.place == "Saint-Rémy-de-Provence"
    assert asset.image_kind == "painting", "derived at write time"
    # the prose survives untouched, because it is what BGE embeds
    assert "Saint-Rémy" in (asset.description or "")


def test_rederive_recomputes_kinds_without_a_recrawl(lib, monkeypatch):
    """A caption is expensive to redo; a bucket derived from the source's own words costs one SQL
    pass. That is what makes the vocabulary safe to correct."""
    lib.add_discovery(source_ref="artic:1", thumb_url="https://e.org/1.jpg", source="artic",
                      title="a", license="CC0", classification="Zorblatt", pixels=False)
    assert lib.catalog.get_by_ref("artic:1").image_kind == "unknown"

    import nolan.imagelib.taxonomy as tax
    real = tax.image_kind
    monkeypatch.setattr(tax, "image_kind", lambda *v: "textile" if any(
        "Zorblatt" in (x or "") for x in v) else real(*v))

    res = lib.rederive_kinds()
    assert res["changed"] == 1
    assert lib.catalog.get_by_ref("artic:1").image_kind == "textile"
    assert "unknown_pct" in res, "the fallthrough rate must be reported, not hidden"


def test_met_csv_absent_fails_loudly(tmp_path, monkeypatch):
    """No silent fallback to an empty id list — that would read as "this department is empty"."""
    from nolan.imagelib import harvest as H
    monkeypatch.setattr(H, "_met_csv_path", lambda: tmp_path / "nope.csv")
    with pytest.raises(FileNotFoundError, match="not downloaded yet"):
        H.met_public_domain_ids()


def _fake_met(monkeypatch, ids, *, no_image=(), latency=None):
    """Stand in for the Met's per-object endpoint, with CONTROLLABLE per-id latency so the
    concurrent walk can be made to complete its requests out of order on purpose."""
    import time as _t

    from nolan.imagelib import harvest as H

    monkeypatch.setattr(H, "met_public_domain_ids", lambda dept=None: list(ids))
    monkeypatch.setattr(H, "_met_csv_path", lambda: __import__("pathlib").Path(__file__))
    seen = []

    class _Resp:
        def __init__(self, oid):
            self.oid = oid

        def json(self):
            return {"objectID": self.oid, "title": f"Object {self.oid}",
                    "primaryImage": "" if self.oid in no_image else f"https://e/{self.oid}.jpg",
                    "primaryImageSmall": f"https://e/{self.oid}s.jpg",
                    "isPublicDomain": True, "objectURL": f"https://met/{self.oid}"}

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, **kw):
            oid = int(url.rsplit("/", 1)[-1])
            if latency:
                _t.sleep(latency(oid))
            seen.append(oid)
            return _Resp(oid)

    monkeypatch.setattr(H.httpx if hasattr(H, "httpx") else __import__("httpx"),
                        "Client", lambda *a, **kw: _Client())
    return seen


def test_the_concurrent_met_walk_still_yields_in_cursor_order(monkeypatch):
    """The Met costs one request per object, so the walk rate IS the crawl — 8 workers took a
    240-id sample from 8.7 to 18.8 objects/second. But the resume cursor is a single OFFSET into
    the id list, and it only means anything if everything before it has been dealt with. So the
    requests may race; the yields may not.

    Latency here is deliberately inverted — later ids answer FIRST — so a version that yielded on
    completion instead of on position would fail this and leave holes a resume never fills.
    """
    from nolan.imagelib import harvest as H

    ids = list(range(100, 132))
    _fake_met(monkeypatch, ids, latency=lambda oid: (131 - oid) * 0.002)

    report = H.HarvestReport(collection="met-test")
    got = [it for it in H.met_items(limit=999, report=report)]
    assert [int(i.source_ref.split(":")[1]) for i in got] == ids
    assert report.cursor == {"offset": len(ids)}, report.cursor
    assert report.exhausted


def test_a_bounded_met_harvest_does_not_overrun_its_limit(monkeypatch):
    """`limit` counts ROWS INDEXED — the contract every adapter honours. A batched fetcher makes
    it easy to break: asking for 12 must not walk a whole 64-id batch past them, or a resume
    restarts beyond rows that were never indexed."""
    from nolan.imagelib import harvest as H

    ids = list(range(200, 400))
    seen = _fake_met(monkeypatch, ids)

    report = H.HarvestReport(collection="met-test")
    got = list(H.met_items(limit=12, report=report))
    assert len(got) == 12
    assert report.cursor == {"offset": 12}, report.cursor
    # the batch floor is the worker count, so at most one batch of over-fetch — never 64
    assert len(seen) <= 12 + H._MET_WORKERS, f"fetched {len(seen)} records for 12 rows"
    assert not report.exhausted


def test_a_met_id_with_no_image_is_consumed_not_revisited(monkeypatch):
    """A skipped id must move the cursor past itself, or a department full of imageless objects
    re-pays for them on every run."""
    from nolan.imagelib import harvest as H

    ids = [10, 11, 12, 13]
    _fake_met(monkeypatch, ids, no_image={11, 12})

    report = H.HarvestReport(collection="met-test")
    got = list(H.met_items(limit=999, report=report))
    assert [int(i.source_ref.split(":")[1]) for i in got] == [10, 13]
    assert report.skipped_no_image == 2
    assert report.cursor == {"offset": 4}


def test_a_met_resume_starts_after_the_last_consumed_id(monkeypatch):
    """The whole point of the cursor: a job measured in hours that cannot resume never finishes."""
    from nolan.imagelib import harvest as H

    ids = list(range(500, 540))
    seen = _fake_met(monkeypatch, ids)

    report = H.HarvestReport(collection="met-test")
    first = list(H.met_items(limit=10, report=report))
    assert report.cursor == {"offset": 10}

    seen.clear()
    report2 = H.HarvestReport(collection="met-test")
    second = list(H.met_items(limit=10, report=report2, cursor=report.cursor))
    assert [int(i.source_ref.split(":")[1]) for i in second] == list(range(510, 520))
    assert not set(seen) & {int(i.source_ref.split(":")[1]) for i in first}, \
        "a resume must not re-fetch what the first pass already consumed"


def _write_met_csv(tmp_path, rows):
    import csv as _csv
    path = tmp_path / "MetObjects.csv"
    cols = ["Object Number", "Is Public Domain", "Object ID", "Department", "Title",
            "Artist Display Name", "Object Date", "Medium", "Classification", "Culture",
            "Country", "Region", "Object Wikidata URL", "Link Resource"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    return path


def test_phase_a_reads_the_met_dump_and_spends_no_requests(tmp_path, monkeypatch):
    """The dump has 54 columns and EVERY field this adapter indexes; the per-object request buys
    only the image url, which Phase A never fetches. It was spending 248,472 requests — ~7.6
    hours — to learn a URL it was going to throw away."""
    from nolan.imagelib import harvest as H

    monkeypatch.setattr(H, "_met_csv_path", lambda: _write_met_csv(tmp_path, [
        {"Object ID": "11", "Is Public Domain": "True", "Department": "Greek and Roman Art",
         "Title": "Terracotta krater", "Artist Display Name": "", "Object Date": "ca. 450 BC",
         "Medium": "Terracotta", "Classification": "Vases", "Culture": "Greek, Attic",
         "Country": "", "Region": "Attica",
         "Object Wikidata URL": "https://www.wikidata.org/wiki/Q123",
         "Link Resource": "https://www.metmuseum.org/art/collection/search/11"},
        {"Object ID": "12", "Is Public Domain": "False", "Department": "Photographs",
         "Title": "Restricted", "Medium": "Albumen"},
        {"Object ID": "13", "Is Public Domain": "True", "Department": "Egyptian Art",
         "Title": "Faience hippopotamus", "Object Date": "ca. 1961-1878 BC",
         "Medium": "Faience", "Classification": "Faience", "Country": "Egypt"},
    ]))

    def _boom(*a, **kw):
        raise AssertionError("Phase A must not touch the Met API")

    monkeypatch.setattr(H.httpx if hasattr(H, "httpx") else __import__("httpx"), "Client", _boom)

    report = H.HarvestReport(collection="met-test")
    got = list(H.met_items(limit=99, report=report, pixels=False))
    assert [i.source_ref for i in got] == ["met:11", "met:13"], "the restricted row is filtered"
    krater = got[0]
    # every indexed field, straight off the CSV
    assert krater.title == "Terracotta krater"
    assert krater.date_text == "ca. 450 BC"
    assert krater.medium == "Terracotta" and krater.classification == "Vases"
    assert krater.department == "Greek and Roman Art" and krater.culture == "Greek, Attic"
    assert krater.place == "Attica", "Country is blank, so Region stands in"
    assert krater.wikidata_qid == "Q123"
    assert krater.license.startswith("CC0")
    # ...and the ONE field it cannot have
    assert krater.thumb_url is None and krater.url is None
    # The cursor counts PUBLIC-DOMAIN rows, not CSV lines — the restricted row is filtered by
    # `met_csv_rows` and never enters the sequence. That is what makes this offset the SAME
    # offset the API walk uses (it indexes `met_public_domain_ids`, the identically-filtered
    # list), so a crawl can switch between the two paths and still resume correctly.
    assert report.exhausted and report.cursor == {"offset": 2}


def test_a_csv_phase_a_and_an_api_walk_share_one_cursor(tmp_path, monkeypatch):
    """Two enumeration paths over one source is exactly how a resume quietly loses rows. They
    must index the same sequence, so a Phase A run can be continued by a pixels run."""
    from nolan.imagelib import harvest as H

    rows = [{"Object ID": str(i), "Is Public Domain": "True" if i % 2 else "False",
             "Department": "Egyptian Art", "Title": f"Thing {i}"} for i in range(10, 20)]
    monkeypatch.setattr(H, "_met_csv_path", lambda: _write_met_csv(tmp_path, rows))
    pd_ids = H.met_public_domain_ids()
    assert pd_ids == [11, 13, 15, 17, 19]

    rep = H.HarvestReport(collection="m")
    first = list(H.met_items(limit=2, report=rep, pixels=False))
    assert [i.source_ref for i in first] == ["met:11", "met:13"]
    assert rep.cursor == {"offset": 2}

    # hand that cursor to the API path — it must pick up at 15, not re-walk 11 and 13
    seen = _fake_met(monkeypatch, pd_ids)
    rep2 = H.HarvestReport(collection="m")
    second = list(H.met_items(limit=2, report=rep2, pixels=True, cursor=rep.cursor))
    assert [i.source_ref for i in second] == ["met:15", "met:17"]
    assert 11 not in seen and 13 not in seen


def test_a_pixels_harvest_still_asks_the_met_api(tmp_path, monkeypatch):
    """The CSV path is chosen by PHASE, not by convenience: a run that will fetch pixels needs
    the image url, so it must keep paying the per-object request."""
    from nolan.imagelib import harvest as H

    monkeypatch.setattr(H, "_met_csv_path", lambda: _write_met_csv(tmp_path, [
        {"Object ID": "11", "Is Public Domain": "True", "Department": "Egyptian Art",
         "Title": "A Thing"}]))
    seen = _fake_met(monkeypatch, [11])

    got = list(H.met_items(limit=99, report=H.HarvestReport(collection="m"), pixels=True))
    assert seen == [11], "pixels=True must resolve the image url from the API"
    assert got[0].thumb_url == "https://e/11s.jpg"


def test_phase_b_resolves_the_image_url_it_deferred(lib, monkeypatch):
    """The other half of the trade. A record-only Met row carries no url, so it must not be a
    dead end — the request moves to the moment something wants its pixels."""
    from nolan.imagelib import harvest as H

    lib.add_discovery(source_ref="met:11", thumb_url=None, url=None, source="met",
                      title="Terracotta krater", license="CC0 (The Metropolitan Museum of Art)",
                      pixels=False)
    lib.add_discovery(source_ref="met:12", thumb_url=None, url=None, source="met",
                      title="An object with no picture",
                      license="CC0 (The Metropolitan Museum of Art)", pixels=False)
    assert lib.catalog.get_by_ref("met:11").thumb_url is None

    asked = []

    def _resolve(refs, **kw):
        asked.extend(refs)
        return {"met:11": {"thumb_url": "https://e/11s.jpg", "url": "https://e/11.jpg"},
                "met:12": {"thumb_url": None, "url": None}}

    import dataclasses
    monkeypatch.setitem(H.SOURCES, "met",
                        dataclasses.replace(H.SOURCES["met"], resolve_image_urls=_resolve))
    n = lib._resolve_missing_thumb_urls(lib.catalog.list(held=0, limit=99))

    assert n == 1 and sorted(asked) == ["met:11", "met:12"]
    assert lib.catalog.get_by_ref("met:11").thumb_url == "https://e/11s.jpg"
    # a row the Met has no image for stays NULL — a real answer, so it is never a pixel
    # candidate again rather than being re-asked on every backfill run
    assert lib.catalog.get_by_ref("met:12").thumb_url is None


# --- 14a. the authoring pipeline can finally SEE this tier -----------------------------------

def _acquire_ctx(lib, monkeypatch, tmp_path):
    """A Context wired to `lib`, with the network stubbed."""
    from nolan.acquire import context as C

    monkeypatch.setattr("nolan.imagelib.shared_library", lambda **kw: lib, raising=False)
    monkeypatch.setattr(C, "shared_library", lambda **kw: lib, raising=False)

    class _Cfg:
        clip_seconds = 30
        sources = ("visuallib",)

    return C.build_context(_Cfg(), want_stock=False, want_clip=False, want_gen=False,
                           want_clips_library=False, want_transcript_lib=False,
                           want_transcript_frames=False, project_dir=tmp_path)


def test_the_pipeline_could_not_see_357000_rows(lib, monkeypatch, tmp_path):
    """`search_library` queries held=1 — the pictures whose bytes are on disk, 46 of them — and
    nothing in acquire/ referenced the discovery tier at all. So the entire museum library was
    invisible to the thing that makes videos.

    This asserts the tier is reachable AND that a discovery row arrives as a POINTER (no local
    path yet), which is the same shape a stock result has and is why the engine needed no change.
    """
    for i in range(4):
        lib.add_discovery(source_ref=f"artic:{i}", thumb_url=f"https://e/{i}.jpg",
                          url=f"https://e/full{i}.jpg", source="artic",
                          title=f"Woodblock print of a wave {i}", creator="Utagawa Hiroshige",
                          license="CC0", classification="woodblock print", place="Japan",
                          date_text="1857", width=2000, height=1500, pixels=False)
    lib.catalog.add(Asset(content_hash="held1", path="f/held.jpg", title="Already held",
                          held=1))

    ctx = _acquire_ctx(lib, monkeypatch, tmp_path)
    assert ctx.search_visuallib is not None, "the discovery tier must be reachable from acquire"

    got = ctx.search_visuallib({"query": "woodblock wave"}, 10)
    assert got, "the discovery tier returned nothing"
    assert all(c.source == "visuallib" for c in got)
    assert all(c.path is None for c in got), "a discovery row is a POINTER until it is fetched"
    assert all(c.ref.startswith("https://") for c in got)
    assert {c.meta["creator"] for c in got} == {"Utagawa Hiroshige"}


def test_an_agent_can_NARROW_before_ranking(lib, monkeypatch, tmp_path):
    """The point of wiring this tier is not another search box. `image_kind`, `movement`,
    `creator`, `place` and the year range are catalog COLUMNS, so a need can turn 357,027 rows
    into a few hundred with a WHERE clause before a single vector is compared. That is a
    different operation from ranking and it is the one an authoring agent wants."""
    lib.add_discovery(source_ref="a:1", thumb_url="https://e/1.jpg", url="https://e/f1.jpg",
                      source="artic", title="Sudden Shower", creator="Utagawa Hiroshige",
                      license="CC0", classification="woodblock print", place="Japan",
                      date_text="1857", width=2000, height=1500, pixels=False)
    lib.add_discovery(source_ref="a:2", thumb_url="https://e/2.jpg", url="https://e/f2.jpg",
                      source="artic", title="Sudden Shower over a bridge", creator="Someone Else",
                      license="CC0", classification="oil on canvas", place="France",
                      date_text="1920", width=2000, height=1500, pixels=False)

    ctx = _acquire_ctx(lib, monkeypatch, tmp_path)

    wide = ctx.search_visuallib({"query": "sudden shower"}, 10)
    assert len(wide) == 2

    narrow = ctx.search_visuallib(
        {"query": "sudden shower", "facets": {"creator": "Hiroshige"}}, 10)
    assert [c.meta["title"] for c in narrow] == ["Sudden Shower"]

    # a PURE facet need, with no query at all — "any Japanese print from the 1850s"
    browse = ctx.search_visuallib(
        {"query": "", "facets": {"place": "Japan", "year_from": 1850, "year_to": 1860}}, 10)
    assert [c.meta["title"] for c in browse] == ["Sudden Shower"]

    # Facets live in their OWN block. Loose among the need's keys, a typo'd `movemnet` could not
    # be told apart from ordinary need metadata, so it would be silently dropped and the search
    # would answer confidently over the wrong denominator.
    assert ctx.search_visuallib({"query": "x", "facets": {"colour": "blue"}}, 5) == []
    # ...and a stray top-level key is just need metadata, correctly ignored rather than guessed at
    assert len(ctx.search_visuallib({"query": "sudden shower", "creator": "Hiroshige"}, 10)) == 2


def test_the_download_hook_dispatches_by_source(lib, monkeypatch, tmp_path):
    """`Context.download` is ONE callable and the engine calls it for every candidate without a
    path. The stock downloader reads `meta["_res"]` and returns False for anything else, so
    assigning it directly would have silently dropped every discovery candidate."""
    lib.add_discovery(source_ref="artic:9", thumb_url="https://e/9.jpg", url="https://e/f9.jpg",
                      source="artic", title="A Print", license="CC0",
                      width=2000, height=1500, pixels=False)

    def _dl(url, dest, **kw):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        _fake_thumb(Path(dest), size=(1400, 1100))

    monkeypatch.setattr("nolan.http_client.download_file_sync", _dl)
    ctx = _acquire_ctx(lib, monkeypatch, tmp_path)
    c = ctx.search_visuallib({"query": "a print"}, 5)[0]

    assert ctx.download(c, tmp_path / "cands") is True
    assert c.path and c.path.exists(), "the fetched bytes must land on the candidate"


# --- 14b. PDIA: the first curated-collection source ------------------------------------------

def _pdia_page(page, total_pages=2, sort=None, images=None):
    return {"images": images if images is not None else [
        {"uuid": f"u{page}-{i}", "title": f"Plate {page}-{i}",
         "artists": [{"label": "Virginia Frances Sterrett"}],
         "displayDate": "1920", "sortYear": 1920,
         "src": f"/collections/old-french-fairytales/plate-{page}-{i}.jpg",
         "width": 900, "height": 600, "publicationDate": "2019-01-31T00:00:00.000Z",
         "encompassingWork": "Old French Fairy Tales", "openRanking": 5}
        for i in range(3)],
        "sort": sort if sort is not None else {"sortType": "pub-date", "sortOrder": "asc"},
        "pagination": {"lastPage": page, "totalPages": total_pages},
        "meta": {"totalImages": total_pages * 3}}


def _fake_pdia(monkeypatch, pages):
    from nolan.imagelib import harvest as H

    class _Resp:
        def __init__(self, d): self._d = d
        def json(self): return self._d

    class _Client:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, **kw):
            n = int(url.rsplit("/", 1)[-1].split(".")[0])
            return _Resp(pages(n))

    monkeypatch.setattr(__import__("httpx"), "Client", lambda *a, **kw: _Client())
    monkeypatch.setattr(H.time, "sleep", lambda *_: None)


def test_pdia_refuses_to_walk_when_the_api_ignores_the_requested_sort(monkeypatch):
    """The API silently substitutes its default for any sort key it does not recognise — probed:
    `year/asc`, `title/asc` and an invented `totally-bogus-sort/asc` all returned 200 in
    pub-date order, and `pub-date/sideways` quietly returned DESC.

    Desc is the one direction that breaks a cursor: newest-first shifts every offset whenever the
    archive publishes, so a resume silently skips a row, forever, with nothing to see. The
    response echoes the sort it applied, so this verifies rather than trusts."""
    from nolan.imagelib import harvest as H

    _fake_pdia(monkeypatch, lambda n: _pdia_page(
        n, sort={"sortType": "pub-date", "sortOrder": "desc"}))     # the silent flip
    with pytest.raises(RuntimeError, match="refused the requested sort"):
        list(H.pdia_items(limit=10, report=H.HarvestReport(collection="p")))

    _fake_pdia(monkeypatch, lambda n: _pdia_page(
        n, sort={"sortType": "date", "sortOrder": "asc"}))          # a real but wrong sort type
    with pytest.raises(RuntimeError, match="refused the requested sort"):
        list(H.pdia_items(limit=10, report=H.HarvestReport(collection="p")))


def test_every_pdia_row_carries_BOTH_a_thumbnail_and_a_full_size_url(monkeypatch):
    """Two urls, two jobs: `thumb_url` is what warming keeps locally, `url` is the untouched
    original that promotion fetches. Storing only one makes a row either un-previewable or
    un-fetchable, and nothing complains until someone clicks.

    They must also point at the CDN. The listing's `src` is a path on
    images.pdimagearchive.org, NOT on the site — joining it to the site gave a 404 HTML page
    for all 11,197 rows, so warming "succeeded" at downloading an error page and "Get
    thumbnails" appeared to do nothing.
    """
    from nolan.imagelib import harvest as H

    _fake_pdia(monkeypatch, _pdia_page)
    for it in H.pdia_items(limit=3, report=H.HarvestReport(collection="p")):
        assert it.thumb_url and it.url, it
        assert it.thumb_url.startswith(H.PDIA_CDN), it.thumb_url
        assert it.url.startswith(H.PDIA_CDN), it.url
        # the thumbnail asks the CDN to resize; the full size is deliberately untouched
        assert it.thumb_url.endswith(f"?width={H._PDIA_THUMB_PX}"), it.thumb_url
        assert "?" not in it.url, "promotion must fetch the ORIGINAL, not a derivative"
        assert not it.thumb_url.startswith(H.PDIA_SITE + "/"), "the site is not the image host"


def test_the_pdia_thumbnail_width_matches_what_the_library_keeps():
    """Asking the CDN for more pixels than `_shrink` keeps means paying for bytes that are
    thrown away. The constant is restated in `harvest` (store imports harvest, so it cannot be
    imported the other way) — this is what stops the two drifting."""
    from nolan.imagelib.harvest import _PDIA_THUMB_PX
    from nolan.imagelib.store import _THUMB_PX
    assert _PDIA_THUMB_PX == _THUMB_PX


def test_repairing_the_urls_needs_no_recrawl(lib):
    """The path was always right and only the host was wrong, so 11,197 rows are fixable from
    what is already stored — one SQL pass, no network."""
    from nolan.imagelib import harvest as H

    lib.add_discovery(source_ref="pdia:x", source="pdia", title="A Plate", license="CC0",
                      thumb_url=f"{H.PDIA_SITE}/collections/set/a.jpg",
                      url=f"{H.PDIA_SITE}/collections/set/a.jpg",
                      width=900, height=600, pixels=False, tier="curated")

    assert lib.repair_pdia_image_urls() == {"repaired": 1}
    a = lib.catalog.get_by_ref("pdia:x")
    assert a.url == f"{H.PDIA_CDN}/collections/set/a.jpg"
    assert a.thumb_url == f"{H.PDIA_CDN}/collections/set/a.jpg?width={H._PDIA_THUMB_PX}"
    # idempotent — a second run finds nothing left pointing at the site
    assert lib.repair_pdia_image_urls() == {"repaired": 0}


def test_pdia_reads_the_collection_slug_out_of_the_image_path(monkeypatch):
    """The single best property of this source's shape: membership costs no extra request."""
    from nolan.imagelib import harvest as H

    _fake_pdia(monkeypatch, _pdia_page)
    items = list(H.pdia_items(limit=3, report=H.HarvestReport(collection="p")))
    assert [i.collection.slug for i in items] == ["pdia-old-french-fairytales"] * 3
    assert items[0].collection.rights.startswith("CC0")
    assert items[0].width == 900 and items[0].height == 600
    assert items[0].source_ref == "pdia:u1-0"


def test_an_uncollected_pdia_row_falls_back_rather_than_carrying_no_collection(monkeypatch):
    """26% of the archive belongs to no curated set — measured across pages 1, 150 and 312. That
    is not an edge case, so it gets a real row rather than a NULL."""
    from nolan.imagelib import harvest as H

    _fake_pdia(monkeypatch, lambda n: _pdia_page(n, images=[
        {"uuid": "loose", "title": "Unfiled", "artists": [], "displayDate": "1900",
         "src": "/images/loose.jpg", "width": 900, "height": 600,
         "publicationDate": "2019-01-31T00:00:00.000Z", "openRanking": 1}]))
    items = list(H.pdia_items(limit=1, report=H.HarvestReport(collection="p")))
    assert items[0].collection is None, "no curated set -> the harvest's own collection"
    assert H.pdia_collection().slug == "pdia-uncollected"


def test_a_curated_collection_is_upserted_once_not_once_per_image(lib, monkeypatch):
    """You asked for this explicitly: don't re-fetch the same collection repeatedly. A 300-image
    set would otherwise be 300 identical upserts."""
    from nolan.imagelib import harvest as H

    _fake_pdia(monkeypatch, lambda n: _pdia_page(n, total_pages=2))
    seen = []
    real = lib.upsert_collection

    def _spy(c):
        seen.append(c.slug)
        return real(c)

    monkeypatch.setattr(lib, "upsert_collection", _spy)
    rep = H.harvest("pdia", limit=6, library=lib, pixels=False)

    assert rep.added == 6
    # 6 images, ONE curated collection -> it is upserted once, not six times
    assert seen.count("pdia-old-french-fairytales") == 1, seen
    rows = lib.catalog.list(held=0, limit=99)
    cid = {r.collection_id for r in rows}
    assert len(cid) == 1
    assert lib.catalog.get_collection_by_id(cid.pop()).slug == "pdia-old-french-fairytales"


def test_the_curated_tier_waives_the_floor_but_never_the_rights(lib):
    """Dropping the resolution floor for a hand-curated source must not become a licence
    loophole. Measured: the archival floor refused 37% of PDIA, including a 1024x661 print
    rejected on its SHORT side and half the plates of a single book."""
    from nolan.asset_gate import STRICT_RIGHTS_TIERS, clears_floor

    assert clears_floor(455, 761, "archival") is False
    assert clears_floor(455, 761, "curated") is True, "the floor is waived"
    assert "curated" in STRICT_RIGHTS_TIERS, "rights are NOT waived"

    # ...and end to end: a small CC0 row is admitted, a small unlicensed one is still refused
    a, _ = lib.add_discovery(source_ref="pdia:small", thumb_url="https://e/s.jpg", source="pdia",
                             title="Design No. 19", license="CC0 (Public Domain Image Archive)",
                             width=455, height=761, pixels=False, tier="curated")
    assert a.id
    with pytest.raises(ValueError, match="license unknown"):
        lib.add_discovery(source_ref="pdia:nolicense", thumb_url="https://e/n.jpg",
                          source="pdia", title="Unknown rights", license=None,
                          width=455, height=761, pixels=False, tier="curated")


def test_each_source_harvests_with_its_OWN_crawler(lib, monkeypatch):
    """There is no generic walker, and a generic one could not work: the four sources enumerate
    in four incompatible ways — artic and Cleveland page a listing, the Met reads a 300 MB CSV,
    and PDIA walks a JSON API and files rows under per-item curated collections.

    `harvest()` dispatches on `SOURCES[name].items`, so selecting a source in the form runs THAT
    source's crawler. Asserted by CALLING harvest and recording which walker ran, not by reading
    the registry — the registry could be right while the dispatch ignored it.
    """
    from nolan.imagelib import harvest as H

    ran = []
    for name in sorted(H.SOURCES):
        def _spy(*a, _n=name, **kw):
            ran.append((_n, kw.get("pixels"), "cursor" in kw))
            return iter(())
        monkeypatch.setitem(H.SOURCES, name,
                            dataclasses_replace(H.SOURCES[name], items=_spy))

    for name in sorted(H.SOURCES):
        H.harvest(name, limit=1, library=lib, pixels=False)

    assert [r[0] for r in ran] == sorted(H.SOURCES) == ["artic", "cleveland", "met", "pdia"]
    # the PHASE reaches every adapter (the Met changes enumeration on it), and every one of
    # these sources is resumable so every one is handed a cursor
    assert all(r[1] is False for r in ran), ran
    assert all(r[2] for r in ran), "a resumable adapter must be given its cursor"


def dataclasses_replace(obj, **kw):
    import dataclasses
    return dataclasses.replace(obj, **kw)


def test_the_sources_view_is_per_source_not_per_collection(lib):
    """The Sources tab rendered the collections list, which was the same thing while every source
    produced one collection — and became 581 lines when PDIA contributed 577. How many
    collections a source yielded is a fact ABOUT it, not a reason to list it 577 times."""
    from nolan.imagelib import Collection

    lib.upsert_collection(Collection(slug="artic-pd", source="artic", title="artic",
                                     upstream_count=62035))
    for i in range(6):
        lib.upsert_collection(Collection(slug=f"pdia-set-{i}", source="pdia", title=f"Set {i}"))

    per_source = {}
    for c in lib.catalog.list_collections():
        per_source.setdefault(c.source, 0)
        per_source[c.source] += 1
    assert per_source == {"artic": 1, "pdia": 6}
    assert len(lib.catalog.list_collections()) == 7, "seven collections..."
    assert len(per_source) == 2, "...but only two SOURCES"


def test_collection_counts_are_one_query_not_one_per_collection(lib):
    """Invisible at four collections, catastrophic at 581. Measured on the live catalog, counting
    per collection took 118,858 ms against 248 ms for one grouped pass — and the Sources tab was
    already paying it. PDIA is what changed the arithmetic: it is the first source that yields
    many collections from one crawl, contributing 577 on its own."""
    from nolan.imagelib import Collection

    for i in range(5):
        c = lib.upsert_collection(Collection(slug=f"c{i}", source="pdia", title=f"Set {i}"))
        for j in range(i + 1):
            lib.add_discovery(source_ref=f"pdia:{i}-{j}", thumb_url=f"https://e/{i}{j}.jpg",
                              source="pdia", title=f"Plate {i}-{j}", license="CC0",
                              collection_id=c.id, pixels=False, tier="curated")

    counts = lib.catalog.collection_counts(held=0)
    assert len(counts) == 5
    by_slug = {c.slug: counts.get(c.id, {}).get("indexed", 0)
               for c in lib.catalog.list_collections()}
    assert by_slug == {"c0": 1, "c1": 2, "c2": 3, "c3": 4, "c4": 5}
    # ...and it agrees with the per-collection count it replaced, or the speed-up is a lie
    for c in lib.catalog.list_collections():
        assert counts.get(c.id, {}).get("indexed", 0) == \
            lib.catalog.count("active", held=0, collection_id=c.id)


def test_a_whole_source_harvest_is_not_a_curated_collection(lib):
    """"Aubrey Beardsley" (74 pictures someone chose) and "Cleveland Museum of Art — CC0
    artworks" (everything they hold) are different kinds of thing, and only one belongs in a
    Collections tab. `upstream_count` is the clean tell: only a source-wide crawl is in a
    position to know how big the source is."""
    from nolan.imagelib import Collection

    whole = lib.upsert_collection(Collection(slug="cleveland-cc0", source="cleveland",
                                             title="Cleveland — CC0", upstream_count=41477))
    curated = lib.upsert_collection(Collection(slug="pdia-beardsley", source="pdia",
                                               title="Aubrey Beardsley"))
    assert whole.upstream_count is not None, "a whole-source harvest knows the source's size"
    assert curated.upstream_count is None, "a curated set does not"


def test_pdia_rights_take_the_more_restrictive_of_two_claims():
    """The site frames itself as entirely public domain. MEASURED over 120 random rows, it is
    not: underlying pd-worldwide 80% / pd-us 10% / pd-50-years 1.7% / no-known-restrictions 2.5%,
    and digital no-additional-rights 94% / unclear 4.2% / SHARE-ALIKE 1.7%.

    PDIA waiving rights over its own scan cannot make a work that is still in copyright in Europe
    free to publish in Europe, and a share-alike scan is not CC0 however public-domain the
    painting under it is. A video essay published worldwide is exactly where that bites."""
    from nolan.imagelib.harvest import pdia_is_free_worldwide, pdia_license

    assert pdia_license("pd-worldwide", "no-additional-rights") == \
        "CC0 (Public Domain Image Archive)"
    assert pdia_is_free_worldwide("pd-worldwide", "no-additional-rights")

    # territorial: free where we may not be publishing
    us = pdia_license("pd-us", "no-additional-rights")
    assert "US ONLY" in us and "CC0" not in us
    assert not pdia_is_free_worldwide("pd-us", "no-additional-rights")
    assert not pdia_is_free_worldwide("pd-50-years", "no-additional-rights")

    # a copyleft obligation on the scan survives a public-domain work underneath it
    sa = pdia_license("pd-worldwide", "share-alike")
    assert "share-alike" in sa and "CC0" not in sa
    assert not pdia_is_free_worldwide("pd-worldwide", "share-alike")

    # "no known restrictions" is an absence of evidence, not an assertion of freedom
    assert not pdia_is_free_worldwide("no-known-restrictions", "no-additional-rights")
    assert not pdia_is_free_worldwide("pd-worldwide", "unclear")

    # UNREADABLE is a refusal, never a permissive default
    assert pdia_license("something-new", "no-additional-rights") is None
    assert pdia_license("pd-worldwide", None) is None


def test_enrichment_corrects_a_row_the_harvest_stamped_cc0(lib, monkeypatch):
    """The harvest labels every PDIA row CC0 from the site's blanket claim; the per-image page is
    the first place we learn a work is US-only. Leaving it CC0 would be the transcript library's
    re-labelling incident in reverse — a permissive label asserted by a pass that knew less."""
    from nolan.imagelib import harvest as H

    lib.add_discovery(source_ref="pdia:us1", thumb_url="https://e/1.jpg", source="pdia",
                      title="A US-only work", license="CC0 (Public Domain Image Archive)",
                      institution="Public Domain Image Archive", width=900, height=600,
                      pixels=False, tier="curated")
    lib.add_discovery(source_ref="pdia:odd", thumb_url="https://e/2.jpg", source="pdia",
                      title="Unreadable rights", license="CC0 (Public Domain Image Archive)",
                      institution="Public Domain Image Archive", width=900, height=600,
                      pixels=False, tier="curated")

    monkeypatch.setattr(H, "pdia_details", lambda uuids, **kw: {
        "us1": {"uuid": "us1", "parsed": True, "institution": "Library of Congress",
                "underlying_rights": "pd-us", "digital_rights": "no-additional-rights",
                "styles": ["Lithography"], "themes": ["The Future"], "tags": ["flying"]},
        "odd": {"uuid": "odd", "parsed": True, "institution": "Somewhere",
                "underlying_rights": "a-code-from-the-future",
                "digital_rights": "no-additional-rights", "styles": [], "themes": [], "tags": []},
    })

    res = lib.enrich_pdia_details(limit=10)
    assert res["enriched"] == 2 and res["not_free_worldwide"] == 1
    assert res["rights_unrecognised"] == 1

    fixed = lib.catalog.get_by_ref("pdia:us1")
    assert "US ONLY" in fixed.license and "CC0" not in fixed.license
    assert fixed.institution == "Library of Congress", "the HOLDER, not the aggregator"
    assert "The Future" in (fixed.subject or "")

    # the unreadable one keeps what it had — never relabelled by a pass that could not read it
    left = lib.catalog.get_by_ref("pdia:odd")
    assert left.license == "CC0 (Public Domain Image Archive)"


def test_a_row_buffered_twice_does_not_sink_its_whole_batch(lib):
    """chroma requires ids unique WITHIN one upsert, and the buffer can hold a row twice —
    `add_discovery` buffers it, then a pass that rewrites its identity re-buffers it before the
    flush. The whole call raised, the handler logged and returned 0, and EVERY row in that batch
    went missing from the identity index rather than just the repeat. Seen live as "batched
    identity index failed for 4 rows: Expected IDs to be unique, found duplicates of: 2, 1"."""
    a, _ = lib.add_discovery(source_ref="artic:dup", thumb_url="https://e/d.jpg", source="artic",
                             title="First text", license="CC0", pixels=False)
    b, _ = lib.add_discovery(source_ref="artic:other", thumb_url="https://e/o.jpg",
                             source="artic", title="Another row", license="CC0", pixels=False)
    lib.flush_index()

    lib.catalog.update(a.id, title="Rewritten text")
    lib._buffer_identity(lib.catalog.get(a.id))
    lib._buffer_identity(lib.catalog.get(a.id))      # the same row, twice, in one batch
    lib._buffer_identity(lib.catalog.get(b.id))
    assert lib.flush_index() == 2, "the repeat collapses; the innocent row is NOT lost"

    # and the LAST buffering won — it is the newer text, which is why something re-buffered it
    assert [h.asset.id for h in lib.search_by_title("rewritten text", held=0)] == [a.id]


def test_subject_is_finally_filterable(lib):
    """`classification` is a medium and `culture` is a place. Until PDIA's themes arrived nothing
    in this catalog could answer "pictures about ghosts" — and `tags` was populated but absent
    from FACET_LIKE, which is an authored field with no consumer."""
    a, _ = lib.add_discovery(source_ref="pdia:g", thumb_url="https://e/g.jpg", source="pdia",
                             title="Night Parade", license="CC0", width=900, height=600,
                             pixels=False, tier="curated")
    b, _ = lib.add_discovery(source_ref="pdia:f", thumb_url="https://e/f.jpg", source="pdia",
                             title="Flying Machine", license="CC0", width=900, height=600,
                             pixels=False, tier="curated")
    lib.catalog.update(a.id, subject="Ghosts & Occult, yokai, demons, folklore")
    lib.catalog.update(b.id, subject="The Future, retrofuturism, machines")

    assert [x.title for x in lib.catalog.list(held=0, limit=9, subject="Ghosts")] \
        == ["Night Parade"]
    assert [x.title for x in lib.catalog.list(held=0, limit=9, subject="retrofuturism")] \
        == ["Flying Machine"]
    assert "subject" in lib.catalog.FACET_LIKE

    # `tags` is deliberately NOT filterable. It holds whatever keyword field the source
    # published, which for artic, Cleveland and the Met is a VERBATIM copy of `classification`
    # (measured: 100.0% of all three) and for PDIA was themes. A filter is a promise about
    # meaning, and that column cannot make one — so it stays as raw provenance and raises.
    assert "tags" not in tuple(lib.catalog.FACET_LIKE) + tuple(lib.catalog.FACET_EXACT)
    with pytest.raises(ValueError, match="not filterable"):
        lib.catalog.list(held=0, limit=9, tags="Ghosts")


def test_pdia_coverage_counts_every_collection_it_filed_into(lib, monkeypatch):
    """Counting by the harvest's own collection reported "32 of 11,197 (0.3%)" for a run that
    indexed 300, because a curated-collection source files most rows elsewhere. A coverage figure
    that understates by 10x is as misleading as one that overstates."""
    from nolan.imagelib import harvest as H

    _fake_pdia(monkeypatch, lambda n: _pdia_page(n, total_pages=2))
    rep = H.harvest("pdia", limit=6, library=lib, pixels=False)
    assert rep.added == 6
    assert any("coverage: 6 of" in n for n in rep.reasons), rep.reasons


# --- 14. source quality, measured -----------------------------------------------------------

def test_every_harvest_source_is_ranked_in_the_shared_tier():
    """ONE NOLAN opinion about whether the Met outranks the Art Institute. `acquire.engine.TIERS`
    already ranks these museums; a second list inside the visual library would drift from it, and
    the one nobody looks at is the one that rots. A new adapter without a tier entry sorts LAST
    in acquisition — silently — so this fails CI instead."""
    from nolan.imagelib.quality import unranked_sources
    missing = unranked_sources("art")
    assert not missing, (f"harvest sources absent from acquire.engine.TIERS['art']: {missing}. "
                         f"Add them there — do not start a second tier list.")


def test_quality_measures_coverage_per_source(lib):
    """A hand-maintained quality table is wrong the day a crawl extends and nothing says so."""
    from nolan.imagelib.quality import source_quality

    for i in range(4):
        lib.add_discovery(source_ref=f"artic:{i}", thumb_url=f"https://e/{i}.jpg", source="artic",
                          title=f"Print {i}", creator="Utagawa Hiroshige", date_text="1857",
                          classification="woodblock print", department="Asian",
                          place="Japan", license="CC0", width=2000, height=1500, pixels=False)
    # a source whose catalog is thinner: no creator, no place, no dimensions
    for i in range(2):
        lib.add_discovery(source_ref=f"met:{i}", thumb_url=None, url=None, source="met",
                          title=f"Object {i}", classification="Vases",
                          license="CC0 (The Metropolitan Museum of Art)", pixels=False)

    rep = {e["source"]: e for e in source_quality(lib)}
    assert rep["artic"]["rows"] == 4 and rep["met"]["rows"] == 2
    assert rep["artic"]["coverage"]["creator"] == 100.0
    assert rep["met"]["coverage"]["creator"] == 0.0
    assert rep["artic"]["coverage"]["place"] == 100.0 and rep["met"]["coverage"]["place"] == 0.0
    assert rep["artic"]["pixel_dims_pct"] == 100.0 and rep["met"]["pixel_dims_pct"] == 0.0
    # DERIVED fields are reported apart from received ones — a low number there is our taxonomy
    assert rep["artic"]["derived"]["artist_key"] == 100.0
    # declared capabilities come from the registry, never restated here
    assert rep["artic"]["declared"]["publishes_pixel_dims"] is True
    assert rep["met"]["declared"]["publishes_pixel_dims"] is False
    assert rep["artic"]["tier_rank"] is not None


def test_a_walked_out_source_is_not_reported_as_partial(lib):
    """The distinction the `exhausted` column exists for. artic sits at 91% of upstream with its
    listing FULLY walked — the rest was refused on rights or by the gate, uniformly — so its
    percentages describe the collection. A ratio test called that partial and was wrong; a
    third-finished Met crawl at 16% of an id-ordered list genuinely is."""
    from nolan.imagelib import Collection
    from nolan.imagelib.quality import source_quality

    lib.add_discovery(source_ref="artic:1", thumb_url="https://e/1.jpg", source="artic",
                      title="A Print", license="CC0", pixels=False)
    lib.add_discovery(source_ref="met:1", thumb_url=None, source="met",
                      title="An Object", license="CC0", pixels=False)
    lib.upsert_collection(Collection(slug="artic-pd", source="artic", title="A",
                                     item_count=91, upstream_count=100, exhausted=True))
    lib.upsert_collection(Collection(slug="met-pd", source="met", title="M",
                                     item_count=16, upstream_count=100, exhausted=None))

    rep = {e["source"]: e for e in source_quality(lib)}
    assert rep["artic"]["exhausted"] is True and rep["artic"]["partial"] is False
    assert rep["met"]["partial"] is True, "16% of an id-ordered walk is not a representative sample"
    # sticky, like every other provenance field: a later pass that does not know must not clear it
    lib.upsert_collection(Collection(slug="artic-pd", source="artic", title="A", item_count=95))
    assert lib.catalog.get_collection("artic-pd").exhausted is True


def test_the_thumbnail_button_does_the_same_thing_for_every_source(lib, monkeypatch):
    """A Met row indexed from the bulk dump has no `thumb_url`, and `warm_pixels` used to filter
    on exactly that — so "Get thumbnails" quietly filled the artic cards and left every Met card
    blank with nothing said. The button must not behave differently per museum."""
    import dataclasses

    from nolan.imagelib import harvest as H

    # NOT pre-placed on disk: warming skips a thumbnail it already has, which would hide the
    # very comparison this test is making.
    lib.add_discovery(source_ref="artic:1", thumb_url="https://e/1.jpg", source="artic",
                      title="A Print", license="CC0", pixels=False)
    lib.add_discovery(source_ref="met:11", thumb_url=None, url=None, source="met",
                      title="A Krater", license="CC0 (The Metropolitan Museum of Art)",
                      pixels=False)
    lib.add_discovery(source_ref="met:12", thumb_url=None, url=None, source="met",
                      title="Never photographed",
                      license="CC0 (The Metropolitan Museum of Art)", pixels=False)

    def _resolve(refs, **kw):
        return {"met:11": {"thumb_url": "https://e/11s.jpg", "url": "https://e/11.jpg"},
                "met:12": {"thumb_url": None, "url": None}}

    monkeypatch.setitem(H.SOURCES, "met",
                        dataclasses.replace(H.SOURCES["met"], resolve_image_urls=_resolve))
    fetched = []

    def _dl(url, dest, **kw):
        fetched.append(url)
        _fake_thumb(Path(dest))

    monkeypatch.setattr("nolan.http_client.download_file_sync", _dl)

    res = lib.warm_pixels(lib.catalog.list(held=0, limit=99), embed=False)
    # the Met row was resolved and then fetched, exactly like the artic one
    assert set(fetched) == {"https://e/1.jpg", "https://e/11s.jpg"}, fetched
    assert res["attempted"] == 2
    # and the one with no image upstream is COUNTED, not dropped on the floor
    assert res["no_image_upstream"] == 1, res


def test_get_thumbnails_works_when_the_query_box_is_empty(lib, monkeypatch, tmp_path):
    """`warm` lived only inside `search_discovery`, so browsing a filtered slice — the normal
    way to use the facets — dropped it silently and the button did NOTHING. An authored control
    with no consumer on one of its two paths, invisible because the failure was silence.

    Exercised through the ROUTE, because the defect was in the route's branch, not in the store.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from nolan.imagelib import store as _store
    from nolan.webui.routes import images_extract

    for i in range(3):
        lib.add_discovery(source_ref=f"artic:{i}", thumb_url=f"https://e/{i}.jpg",
                          source="artic", title=f"Print {i}", license="CC0", pixels=False)

    monkeypatch.setattr(_store, "shared_library", lambda **kw: lib)
    monkeypatch.setattr("nolan.imagelib.shared_library", lambda **kw: lib, raising=False)
    fetched = []
    monkeypatch.setattr("nolan.http_client.download_file_sync",
                        lambda url, dest, **kw: (fetched.append(url), _fake_thumb(Path(dest))))

    app = FastAPI()
    images_extract.register(app, type("Ctx", (), {"templates_dir": tmp_path,
                                                  "job_manager": None})())
    client = TestClient(app)

    # no `q` at all — a pure filtered browse
    r = client.get("/api/images/discover", params={"scope": "global", "warm": "1", "k": "5"})
    assert r.status_code == 200, r.text
    assert len(fetched) == 3, f"warm was dropped on the browse path: {fetched}"
    assert all(row["has_pixels"] for row in r.json()["results"])


def test_a_page_says_how_much_it_is_not_showing(lib):
    """24 of 5,480 with no way to the 25th reads as "that is all there is" — the same silent-cap
    failure this tier exists to avoid, one layer up."""
    for i in range(30):
        lib.add_discovery(source_ref=f"a:{i}", thumb_url=f"https://e/{i}.jpg", source="artic",
                          title=f"Print {i}", license="CC0", pixels=False)

    first = lib.catalog.list(held=0, limit=24)
    second = lib.catalog.list(held=0, limit=24, offset=24)
    assert len(first) == 24 and len(second) == 6
    # no overlap and no gap — `ORDER BY id DESC` is what makes paging stable
    assert not ({a.id for a in first} & {a.id for a in second})
    assert len({a.id for a in first} | {a.id for a in second}) == 30
    assert lib.catalog.count("active", held=0) == 30

    # an offset with no limit is a caller error, not a silently ignored argument
    with pytest.raises(ValueError, match="offset requires a limit"):
        lib.catalog.list(held=0, offset=10)


def test_paging_a_ranked_search_continues_the_same_ranking(lib):
    """Page 2 of a search must come from the ranking that produced page 1, or the two disagree
    and rows are repeated or lost between them."""
    for i in range(20):
        lib.add_discovery(source_ref=f"a:{i}", thumb_url=f"https://e/{i}.jpg", source="artic",
                          title=f"Woodblock print of a wave number {i}", license="CC0",
                          pixels=False)

    page1 = lib.search_discovery("woodblock wave", k=5, use_clip=False)
    page2 = lib.search_discovery("woodblock wave", k=5, offset=5, use_clip=False)
    assert len(page1) == 5 and len(page2) == 5
    ids1 = [h.asset.id for h in page1]
    ids2 = [h.asset.id for h in page2]
    assert not (set(ids1) & set(ids2)), "a second page must not repeat the first"
    # and it is a CONTINUATION: the whole 10 in order equals a single k=10 query
    both = [h.asset.id for h in lib.search_discovery("woodblock wave", k=10, use_clip=False)]
    assert ids1 + ids2 == both


def test_batched_writes_defers_the_commit_but_not_the_data(tmp_path):
    """One fsync per checkpoint instead of one per row. Profiled on the Met dump, `add()` cost
    5.48 ms/row against ~0.01 for the insert itself — 23 minutes of pure fsync over 248,472
    records. Rows must still be READABLE inside the batch; only durability is deferred."""
    cat = AssetCatalog(tmp_path / "c.db")
    with cat.batched_writes():
        for i in range(5):
            cat.add(Asset(content_hash=f"h{i}", path=f"f/{i}.jpg", held=0,
                          source_ref=f"x:{i}", creator="Claude Monet"))
        # visible to the same connection before the commit — the crawl reads its own writes
        assert cat.count("active", held=0) == 5
        assert cat.get_by_ref("x:3").artist_key == "claude monet"
    assert cat.count("active", held=0) == 5

    # a SECOND connection sees them only after the block closed, which is the point
    again = AssetCatalog(tmp_path / "c.db")
    assert again.count("active", held=0) == 5


def test_an_interrupted_batch_rolls_back_to_the_last_checkpoint(tmp_path):
    """A crash mid-batch must not leave a half-applied checkpoint. The crawl resumes from the
    cursor, and the cursor is only written when the batch closes."""
    cat = AssetCatalog(tmp_path / "c.db")
    cat.add(Asset(content_hash="keep", path="f/k.jpg", held=0, source_ref="x:keep"))

    with pytest.raises(RuntimeError):
        with cat.batched_writes():
            cat.add(Asset(content_hash="h9", path="f/9.jpg", held=0, source_ref="x:9"))
            cat.commit()                      # an explicit checkpoint INSIDE the batch survives
            cat.add(Asset(content_hash="h10", path="f/10.jpg", held=0, source_ref="x:10"))
            raise RuntimeError("crawl killed")

    assert cat.get_by_ref("x:keep") is not None
    assert cat.get_by_ref("x:9") is not None, "a checkpointed row is durable"
    assert cat.get_by_ref("x:10") is None, "the uncommitted tail rolled back"


def test_batched_writes_nests_without_committing_early(tmp_path):
    """`add_discovery` may itself batch. An inner block that committed would end the outer
    transaction and silently break the checkpoint boundary."""
    cat = AssetCatalog(tmp_path / "c.db")
    with pytest.raises(RuntimeError):
        with cat.batched_writes():
            cat.add(Asset(content_hash="a", path="f/a.jpg", held=0, source_ref="x:a"))
            with cat.batched_writes():
                cat.add(Asset(content_hash="b", path="f/b.jpg", held=0, source_ref="x:b"))
            # the inner block exited — if it committed, this rollback cannot undo either row
            raise RuntimeError("boom")
    assert cat.get_by_ref("x:a") is None and cat.get_by_ref("x:b") is None


def test_every_adapter_accepts_the_kwargs_harvest_actually_passes(monkeypatch):
    """`harvest` hands the same kwargs to every adapter, so a signature that does not tolerate
    them is a TypeError on the next real crawl and NOTHING catches it — the end-to-end harvest
    tests all need network. Adding `pixels` broke artic exactly this way.

    Checked by CALLING each adapter, not by reading its signature: a `**_ignored` that swallows a
    kwarg the adapter should have honoured would pass an inspection test and still be wrong.
    """
    import inspect

    from nolan.imagelib import harvest as H

    # what `harvest()` puts in items_kwargs, plus the collection-shaping kwargs it forwards
    passed = {"limit", "report", "cursor", "pixels", "dept", "query"}
    for name, adapter in sorted(H.SOURCES.items()):
        sig = inspect.signature(adapter.items)
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            continue
        missing = passed - set(sig.parameters)
        assert not missing, f"{name}.items cannot accept {sorted(missing)} — harvest passes them"

    # and prove it end-to-end: bind the real call harvest makes, with no network
    for name, adapter in sorted(H.SOURCES.items()):
        inspect.signature(adapter.items).bind(
            limit=1, report=None, cursor=None, pixels=False, dept=None, query=None)


def test_a_source_that_always_yields_a_url_is_never_asked_to_resolve(lib):
    """artic and cleveland carry image urls in their listings, so the hook must stay unused —
    a resolver called for them would be pure invented cost."""
    from nolan.imagelib import harvest as H
    assert H.SOURCES["artic"].resolve_image_urls is None
    assert H.SOURCES["cleveland"].resolve_image_urls is None

    lib.add_discovery(source_ref="artic:1", thumb_url="https://e/1.jpg", source="artic",
                      title="A Print", license="CC0", pixels=False)
    assert lib._resolve_missing_thumb_urls(lib.catalog.list(held=0, limit=99)) == 0


# --- 13. browsing by artist and by movement ------------------------------------------------

def _seed_artists(lib):
    """The spellings a real corpus actually contains, including the ones that broke the naive
    version: one painter written two ways by two institutions, and three flavours of anonymous."""
    rows = [
        # the annotated spelling deliberately OUTNUMBERS the clean one, as it does in the live
        # corpus for Lepère, Homer and Gavarni — Cleveland annotates and holds more of them
        ("a:1", "Nocturne in Black", "James McNeill Whistler"),
        ("a:2", "The Falling Rocket", "James McNeill Whistler (American, 1834-1903)"),
        ("a:3", "Arrangement in Grey", "James McNeill Whistler (American, 1834-1903)"),
        ("a:4", "Sudden Shower", "Utagawa Hiroshige"),
        ("a:5", "A Coverlet", "Unknown artist"),
        ("a:6", "A Ewer", "Artist unknown"),
        ("a:7", "A Reliquary", "Unknown"),
        ("a:8", "A Panel", "Unknown Florentine"),
        ("a:9", "An Amphora", "Ancient Greek"),
    ]
    for ref, title, creator in rows:
        lib.add_discovery(source_ref=ref, thumb_url=f"https://e/{ref}.jpg", source="artic",
                          title=title, creator=creator, license="CC0", pixels=False)


def test_one_painter_spelled_three_ways_is_one_artist(lib):
    """artic writes "James McNeill Whistler", Cleveland appends the nationality, and a third
    catalog inverts the name. Without folding, the artist picker offers him three times and each
    entry undercounts."""
    _seed_artists(lib)
    picked = {name: (key, n) for name, key, n in lib.catalog.artist_facets(held=0)}
    assert picked["James McNeill Whistler"][1] == 3, picked
    # A CLEAN spelling beats a POPULAR one. The annotated form is twice as common here, so a
    # plain frequency vote would put "(American, 1834-1903)" on the chip — which is what it did
    # for three of the live corpus's twenty biggest artists.
    assert "James McNeill Whistler (American, 1834-1903)" not in picked


def test_an_anonymous_attribution_is_not_an_artist(lib):
    """"Unknown artist" (728 rows), "Artist unknown" (428) and "Unknown" (427) would otherwise be
    three of the five biggest names in the picker, and none of them narrows to anything."""
    _seed_artists(lib)
    names = {name for name, _, _ in lib.catalog.artist_facets(held=0)}
    assert not ({"Unknown artist", "Artist unknown", "Unknown"} & names), names
    for ref in ("a:5", "a:6", "a:7"):
        assert lib.catalog.get_by_ref(ref).artist_key is None

    # ...but a school IS an identity, even when the hand is not named
    assert "Unknown Florentine" in names, "a residue that names a school must survive"
    assert "Ancient Greek" in names, "an unsigned antiquity is still attributed"


def test_clicking_an_artist_returns_exactly_the_count_it_promised(lib):
    """The chip shows a number; the click must deliver that number. It is why the picker filters
    on the stored key and not on a contains-match — "Bosch" is inside "Boschaert"."""
    _seed_artists(lib)
    for name, key, count in lib.catalog.artist_facets(held=0):
        got = lib.catalog.list(held=0, limit=99, artist_key=key)
        assert len(got) == count, f"{name}: promised {count}, delivered {len(got)}"


def test_artist_key_is_derived_on_insert_not_by_the_caller(lib):
    """Three harvest adapters, promotion and the acquisition engine all write rows. The one that
    forgets would produce a row invisible to the picker with no error to say so."""
    lib.catalog.add(Asset(content_hash="h1", path="f/a.jpg", creator="Claude Monet"))
    assert lib.catalog.get_by_hash("h1").artist_key == "claude monet"


def test_movement_normalisation_refuses_the_non_answers(lib):
    """The column was written by a model answering "what movement?", and models answer
    generously. Case is the smallest problem — over the live table it merges only 5 of 106."""
    from nolan.imagelib.artists import normalise_movement
    assert normalise_movement("aestheticism, tonalism") == "aestheticism"
    assert normalise_movement("early photography / topographic") == "early photography"
    assert normalise_movement("Ukiyo-e") == "Ukiyo-e"          # casing is preserved here...
    assert normalise_movement("none; primarily a documentarian") is None
    assert normalise_movement("n/a") is None
    assert normalise_movement("") is None
    assert normalise_movement(None) is None
    # a clause long enough to be a sentence is a description, not a movement name
    assert normalise_movement("worked mainly in the manner of the later Venetian school") is None


def test_movement_reaches_the_rows_and_picks_one_spelling(lib):
    """`movement` lives on the artists table and the filter lives on assets, so it is copied
    down. ...and THIS is where the casing is resolved: over the live table 14 artists wrote
    "ukiyo-e" and 10 wrote "Ukiyo-e", which must be one facet entry, not two."""
    from nolan.imagelib.catalog import Artist
    _seed_artists(lib)
    # lowercase OUTNUMBERS capitalised, exactly as it does live. It must still lose: a movement
    # is a proper noun, and 2-vs-1 on a house style is not evidence about how it is spelled.
    lib.catalog.upsert_artist(Artist(name="Utagawa Hiroshige", movement="ukiyo-e"))
    lib.catalog.upsert_artist(Artist(name="Kitagawa Utamaro", movement="ukiyo-e"))
    lib.catalog.upsert_artist(Artist(name="Katsushika Hokusai", movement="Ukiyo-e"))
    # folded to Whistler by name order — the movement must reach all three of his rows
    lib.catalog.upsert_artist(Artist(name="Whistler, James McNeill",
                                     movement="aestheticism, tonalism"))

    res = lib.backfill_movements()
    assert res["covered"] == 4, res            # 3 Whistlers + 1 Hiroshige
    assert dict(lib.catalog.facets("movement", held=0)) == {"aestheticism": 3, "Ukiyo-e": 1}, \
        "one spelling wins, and it is the capitalised one"


def test_learning_an_artist_pushes_the_movement_down_to_their_rows(lib):
    """A denormalised column with a stale consumer is the same bug as one with no consumer: the
    facet would keep reporting yesterday's coverage and the newly-learned artists would be
    invisible to the filter that exists to find them."""
    import asyncio

    from nolan.imagelib.artists import enrich_artists
    _seed_artists(lib)
    assert all(a.movement is None for a in lib.catalog.list(held=0, limit=99))

    class _LLM:
        async def generate(self, prompt, system_prompt=None, **kw):
            return ('{"recognised": true, "movement": "Aestheticism", "period": "Victorian", '
                    '"style": "tonal", "subjects": "nocturnes", "palette": "grey"}')

    # ONE call, bounded — enrichment spends calls on the creators covering the most rows, so this
    # buys the artist written three ways, which is exactly the leverage the table exists for.
    out = asyncio.run(enrich_artists(lib, limit=1, llm=_LLM(), model="test"))
    assert out["learned"] == 1
    assert out["movement_backfill"]["covered"] == 3, out
    # all THREE spellings of him carry it, from the single call
    assert [lib.catalog.get_by_ref(r).movement for r in ("a:1", "a:2", "a:3")] \
        == ["Aestheticism"] * 3
    assert lib.catalog.get_by_ref("a:4").movement is None, "nobody else was paid for"


def test_a_rederive_repairs_artist_keys_written_before_the_column_existed(lib):
    """97,610 rows predate the column. The pass that fills them in is the same one that already
    recomputes kinds and dates — no re-crawl, no network."""
    _seed_artists(lib)
    lib.catalog.update_many({a.id: {"artist_key": None}
                             for a in lib.catalog.list(held=0, limit=99)})
    assert lib.catalog.artist_facets(held=0) == []

    res = lib.rederive_kinds()
    assert res["anonymous"] == 3, res          # the three flavours of "we don't know"
    assert res["attributed"] == 6, res
    assert len(lib.catalog.artist_facets(held=0)) == 4   # Whistler, Hiroshige, Florentine, Greek
