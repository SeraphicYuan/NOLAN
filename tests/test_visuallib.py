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


def test_backfill_retires_a_row_whose_pixels_fail_the_content_floor(lib, tmp_path, monkeypatch):
    """The D2 floor, applied at the moment the pixels first exist."""
    from PIL import Image
    import numpy as np

    lib.add_discovery(source_ref="artic:8", thumb_url="https://e.org/8.jpg", source="artic",
                      title="eight", license="CC0", width=1000, height=1000, pixels=False)

    def _fake_dl(url, dest, **kw):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        # a tiny object adrift on a huge grey sweep: content is ~4% of the frame
        canvas = np.full((400, 400, 3), 128, dtype="uint8")
        rng = np.random.default_rng(9)
        canvas[190:210, 190:210] = rng.integers(0, 255, size=(20, 20, 3), dtype="uint8")
        Image.fromarray(canvas).save(dest)

    monkeypatch.setattr("nolan.http_client.download_file_sync", _fake_dl)
    res = lib.backfill_pixels(limit=10, tier="archival")
    assert res["refused"] == 1 and res["fetched"] == 0, res
    assert any("below the archival floor" in r for r in res["reasons"]), res["reasons"]
    assert lib.catalog.get_by_ref("artic:8").status == "rejected"


def test_met_csv_absent_fails_loudly(tmp_path, monkeypatch):
    """No silent fallback to an empty id list — that would read as "this department is empty"."""
    from nolan.imagelib import harvest as H
    monkeypatch.setattr(H, "_met_csv_path", lambda: tmp_path / "nope.csv")
    with pytest.raises(FileNotFoundError, match="not downloaded yet"):
        H.met_public_domain_ids()
