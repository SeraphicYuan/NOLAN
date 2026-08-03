"""Asset provenance: a derivation is a RECORDED FACT, not something parsed out of a filename.

Two live bugs, one cause. `fit_ground_to_scene` recovered a clip's original with
`re.sub(r"_fit\\d+s(?:_\\d+)?$", "", stem)` and then looked for it in `assets/` — so when only the
derivative had been staged there (the original sitting in `capture/assets/videos/`), the fit silently
no-op'd: `ground auto-fit skipped (asset not found: assets/a19_04.mp4)`. And at publish time,
the-diamond-illusion-v3 had 91 assets on screen with 24 absent from `pool.json` entirely and no
derivation chain at all — we could not say where a quarter of the shipped frames came from.

Also pinned here: the report must read the RAW pool rows. Its first version read `asset_pool_meta`
(a narrow projection for the edit UI) and reported 65 of 91 assets as NO-LICENCE while `pool.json`
held a Pexels licence and a source URL for every one — exactly the all-false-positives check that
WIRING_CHECKLIST #11 says takes its one true positive with it.
"""
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"

from nolan.hyperframes import edit as hfedit             # noqa: E402
from nolan.hyperframes import provenance as P            # noqa: E402


@pytest.fixture()
def comp():
    name = "_hf_provenance_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    fdir = dst / "compositions" / "frames"
    fdir.mkdir(parents=True)
    (fdir / "01-beat.spec.json").write_text(json.dumps({"frames": [{"id": "01-beat", "dur": 12.0, "scenes": [
        {"id": "s1", "type": "statement", "start": 0, "dur": 6,
         "data": {"lines": ["a"], "ground": {"kind": "image", "src": "assets/shot.jpg"}}},
        {"id": "s2", "type": "statement", "start": 6, "dur": 6,
         "data": {"lines": ["b"], "ground": {"kind": "image", "src": "assets/ghost.jpg"}}},
    ]}]}), encoding="utf-8")
    (dst / "hyperframes.json").write_text('{"theme":"highlighter-editorial"}', encoding="utf-8")
    (dst / "assets").mkdir()
    from PIL import Image
    Image.new("RGB", (64, 48), (10, 60, 120)).save(dst / "assets" / "shot.jpg")
    Image.new("RGB", (64, 48), (120, 60, 10)).save(dst / "assets" / "ghost.jpg")
    (dst / "pool.json").write_text(json.dumps([
        {"id": "a1", "file": "shot.jpg", "media_type": "image", "source": "pexels",
         "license": "Pexels License (free for commercial use)",
         "source_url": "https://www.pexels.com/photo/x-1/", "photographer": "A. Person"},
    ]), encoding="utf-8")     # ghost.jpg is on screen and NOT in the pool — the UNKNOWN case
    try:
        yield name
    finally:
        shutil.rmtree(dst, ignore_errors=True)


# --- the raw-row reader (the near-miss that made the report useless) --------------------------------

def test_pool_entries_carries_what_the_ui_projection_drops(comp):
    raw = hfedit.pool_entries(comp)["shot.jpg"]
    assert raw["license"].startswith("Pexels") and raw["source_url"]
    proj = hfedit.asset_pool_meta(comp)["shot.jpg"]
    assert "license" not in proj, "asset_pool_meta is a UI view; provenance must not read it"


def test_licensed_assets_are_not_reported_as_missing_a_licence(comp):
    rep = P.audit(comp)
    row = next(r for r in rep["rows"] if r["file"] == "shot.jpg")
    assert row["status"] == "OK", "reading the projection reported 65 of 91 real licences as missing"
    assert row["license"].startswith("Pexels")


# --- the report -------------------------------------------------------------------------------------

def test_an_unrecorded_on_screen_asset_is_UNKNOWN_not_silently_omitted(comp):
    rep = P.audit(comp)
    row = next(r for r in rep["rows"] if r["file"] == "ghost.jpg")
    assert row["status"] == "UNKNOWN" and row["in_pool"] is False
    assert rep["summary"]["on_screen"] == 2 and rep["summary"]["in_pool"] == 1


def _repool(comp, entry):
    pool = json.loads((hfedit._comp_dir(comp) / "pool.json").read_text(encoding="utf-8"))
    pool = [e for e in pool if e.get("file") != entry["file"]] + [entry]
    (hfedit._comp_dir(comp) / "pool.json").write_text(json.dumps(pool), encoding="utf-8")


def test_unknown_and_unchecked_are_separate_buckets(comp):
    """One means 'we never recorded this', the other 'we looked and could not confirm'. Collapsing
    them lets the first hide inside the second."""
    _repool(comp, {"id": "a2", "file": "ghost.jpg", "media_type": "image",
                   "source": "transcript_lib (youtube)", "license": "CC BY 4.0", "source_url": "u"})
    rep = P.audit(comp)
    assert next(r for r in rep["rows"] if r["file"] == "ghost.jpg")["status"] == "UNCHECKED"
    assert "UNKNOWN" not in rep["summary"]["by_status"]


def test_a_url_is_not_a_licence(comp):
    """The report announced `{"OK": 22}` — 100% clean — on a comp with two ddgs-scraped stills whose
    licence cell was empty, because the test was `not (license or source_url)`. In the one artifact
    whose job is licence traceability, that is confidently wrong rather than merely silent."""
    _repool(comp, {"id": "a3", "file": "ghost.jpg", "media_type": "image", "source": "ddgs",
                   "license": "", "source_url": "https://example.test/found-it"})
    row = next(r for r in P.audit(comp)["rows"] if r["file"] == "ghost.jpg")
    assert row["status"] == "NO-LICENCE", "a link tells you where to look, not what you may use"


def test_a_missing_licence_outranks_an_unchecked_origin(comp):
    """Precedence is deliberate: 'you may not be allowed to use this' is more actionable than
    'nobody has eyeballed the pixels yet'."""
    _repool(comp, {"id": "a4", "file": "ghost.jpg", "media_type": "image", "source": "ddgs",
                   "license": "", "source_url": ""})
    assert next(r for r in P.audit(comp)["rows"] if r["file"] == "ghost.jpg")["status"] == "NO-LICENCE"


def test_scraped_detection_covers_the_sources_the_pool_actually_records(comp):
    """This imported `acquire.judge.is_scraped`, which answers a narrower question for the acquisition
    cull and returns False for `ddgs`, `youtube` AND `archive.org` as they appear in pool.json — so
    the UNCHECKED bucket was dead code and every scraped asset fell through to OK."""
    for src in ("ddgs", "transcript_lib (youtube)", "archive.org", "youtube"):
        assert P.is_scraped(src), f"{src!r} must count as scraped"
    for src in ("pexels", "library", "krea2 (generated)"):
        assert not P.is_scraped(src)


def test_the_report_renders_and_names_what_needs_attention(comp):
    out = P.write_report(comp)
    text = out.read_text(encoding="utf-8")
    assert "Asset provenance" in text and "ghost.jpg" in text
    assert "Needs attention" in text and "UNKNOWN" in text
    assert "Pexels" in text, "the full inventory carries the licence, not just the problems"


def test_it_reports_and_does_not_gate():
    """A hard gate would block every publish on day one (24 of 91 unknown) and be disabled in a week."""
    import inspect
    src = inspect.getsource(P)
    assert "raise" not in src.replace("raises", ""), "the provenance pass must not block a publish"


# --- derivation is recorded, not parsed --------------------------------------------------------------

def test_a_derivation_records_its_parent(comp):
    res = hfedit.quickedit_asset(comp, "assets/shot.jpg", "crop",
                                 {"x": 0, "y": 0, "w": 32, "h": 24}, mode="new", name="shot_crop")
    row = hfedit.pool_entries(comp)[res["name"]]
    assert row["derived_from"] == "shot.jpg" and row["op"] == "crop"
    assert hfedit.pool_original(comp, res["name"]) == "shot.jpg"


def test_a_chain_of_derivations_walks_back_to_the_true_original(comp):
    one = hfedit.quickedit_asset(comp, "assets/shot.jpg", "crop",
                                 {"x": 0, "y": 0, "w": 48, "h": 32}, mode="new", name="shot_a")
    two = hfedit.quickedit_asset(comp, f"assets/{one['name']}", "crop",
                                 {"x": 0, "y": 0, "w": 24, "h": 16}, mode="new", name="shot_b")
    assert hfedit.pool_original(comp, two["name"]) == "shot.jpg", \
        "a filename could never express two hops"


def test_pool_original_is_none_for_a_non_derivative(comp):
    assert hfedit.pool_original(comp, "shot.jpg") is None, "None, not a guess"


def test_a_corrupt_cycle_terminates(comp):
    pool = json.loads((hfedit._comp_dir(comp) / "pool.json").read_text(encoding="utf-8"))
    pool += [{"file": "loop_a.jpg", "derived_from": "loop_b.jpg", "media_type": "image"},
             {"file": "loop_b.jpg", "derived_from": "loop_a.jpg", "media_type": "image"}]
    (hfedit._comp_dir(comp) / "pool.json").write_text(json.dumps(pool), encoding="utf-8")
    assert hfedit.pool_original(comp, "loop_a.jpg") is not None      # terminates rather than hanging


# --- the stage/store fallback (the other half of the auto-fit no-op) ----------------------------------

def test_an_original_that_lives_only_in_the_store_still_resolves(comp):
    """`assets/` is the STAGE (rebuilt from the store, holds only what specs reference); the original
    can legitimately exist only in `capture/assets/**`. Requiring the literal path is what made the
    fit silently do nothing."""
    root = hfedit._comp_dir(comp)
    store = root / "capture" / "assets" / "videos"
    store.mkdir(parents=True)
    (store / "stored_only.mp4").write_bytes(b"V" * 4096)
    got = hfedit._resolve_asset_path(comp, "assets/stored_only.mp4")
    assert got.exists() and got.parent.name == "videos"


def test_a_genuinely_missing_asset_still_raises(comp):
    with pytest.raises(FileNotFoundError):
        hfedit._resolve_asset_path(comp, "assets/nope.jpg")


def test_fit_asks_the_index_before_parsing_a_name():
    """Over the AST, not the text: the function's comment quotes the old `re.sub` to explain what it
    replaced, and a substring check matched that prose instead of the code."""
    import ast
    import inspect
    import textwrap
    tree = ast.parse(textwrap.dedent(inspect.getsource(hfedit.fit_ground_to_scene)))
    calls = [(n.lineno, n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", ""))
             for n in ast.walk(tree) if isinstance(n, ast.Call)]
    idx_line = next((ln for ln, nm in calls if nm == "pool_original"), None)
    sub_line = next((ln for ln, nm in calls if nm == "sub"), None)
    assert idx_line is not None, "the fit must ask the pool index for the original"
    assert sub_line is None or idx_line < sub_line, \
        "the index is consulted FIRST; the filename regex is only the legacy fallback"
