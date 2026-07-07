"""Provenance & quality gate — the Alamy-incident net.

Pins: stock-preview domains rejected at candidate level (any tier), archival
tier requires known-open licensing, resolution floors, the watermark-banner
heuristic on real pixels, vision hook behavior, ingest-door refusal, and the
DOORS manifest (every acquisition point provably calls the gate — docs claim,
tests enforce).
"""

from pathlib import Path

import pytest

from nolan.asset_gate import (
    ASSET_GATE_DOORS, banner_suspect, blocked_host, check_candidate,
    check_file, scan_files,
)
from nolan.image_search import ImageSearchResult

REPO = Path(__file__).resolve().parents[1]


# --- candidate gate ----------------------------------------------------------

def _r(**kw):
    kw.setdefault("url", "https://example.org/img.jpg")
    return ImageSearchResult(**kw)


def test_alamy_preview_rejected_any_tier():
    # The literal incident URL shape (c8.alamy.com preview CDN).
    r = _r(url="https://c8.alamy.com/comp/R93YRK/vase.jpg", source="ddgs")
    for tier in ("stock", "archival"):
        v = check_candidate(r, tier=tier)
        assert not v.ok and "alamy.com" in v.reasons[0]


def test_blocklist_covers_major_agencies():
    for u in ("https://www.shutterstock.com/image-photo/x",
              "https://media.gettyimages.com/id/1/photo.jpg",
              "https://thumbs.dreamstime.com/z/x.jpg",
              "https://t3.ftcdn.net/jpg/01/x.jpg"):
        assert blocked_host(u)


def test_source_url_and_thumbnail_also_checked():
    r = _r(url="https://cdn.example.org/ok.jpg",
           source_url="https://www.alamy.com/the-vase-image123.html")
    assert not check_candidate(r, tier="stock").ok


def test_archival_requires_known_open_license():
    unknown = _r(source="ddgs", license=None,
                 width=2000, height=1500)
    assert not check_candidate(unknown, tier="archival").ok
    met = _r(source="met", license=None, width=2000, height=1500)
    assert check_candidate(met, tier="archival").ok
    cc = _r(source="ddgs", license="CC BY-SA 4.0", width=2000, height=1500)
    assert check_candidate(cc, tier="archival").ok


def test_stock_unknown_license_flags_but_passes():
    r = _r(source="ddgs", license=None, width=2000, height=1500)
    v = check_candidate(r, tier="stock")
    assert v.ok and "license-unknown" in v.flags


def test_metadata_resolution_floor():
    small = _r(source="pexels", width=320, height=240)
    assert not check_candidate(small, tier="stock").ok
    big = _r(source="pexels", width=1920, height=1080)
    assert check_candidate(big, tier="stock").ok


# --- file gate ---------------------------------------------------------------

def _img(tmp_path, name, w, h, painter=None):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), (120, 110, 100))
    d = ImageDraw.Draw(im)
    # non-uniform body so the banner band is the only suspicious region
    for i in range(0, w, 40):
        d.rectangle([i, h // 4, i + 20, 3 * h // 4], fill=(90 + i % 80, 80, 70))
    if painter:
        painter(im, d)
    p = tmp_path / name
    im.save(p)
    return p


def _alamy_banner(im, d):
    w, h = im.size
    band = int(h * 0.06)
    d.rectangle([0, h - band, w, h], fill=(5, 5, 5))
    d.text((int(w * 0.05), h - band + 2), "alamy  www.alamy.com  Image ID: R93YRK",
           fill=(240, 240, 235))


def test_banner_heuristic_catches_alamy_style_strip(tmp_path):
    bad = _img(tmp_path, "bad.jpg", 1600, 1200, _alamy_banner)
    assert banner_suspect(bad)
    v = check_file(bad, tier="archival")
    assert not v.ok and "banner" in v.reasons[0]


def test_clean_image_passes(tmp_path):
    good = _img(tmp_path, "good.jpg", 1600, 1200)
    assert not banner_suspect(good)
    assert check_file(good, tier="archival").ok


def test_museum_photo_on_black_background_not_flagged(tmp_path):
    # The Douris-kylix false positive: dark museum background runs to the
    # frame edge with a few glints — continuous, not a banner strip.
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (1600, 1200), (10, 8, 9))
    d = ImageDraw.Draw(im)
    d.ellipse([300, 250, 1300, 950], fill=(180, 120, 60))   # the vase
    for x in range(60, 1600, 320):                           # glints at the edge
        d.rectangle([x, 1160, x + 6, 1170], fill=(190, 190, 185))
    p = tmp_path / "museum.jpg"
    im.save(p)
    assert not banner_suspect(p)
    assert check_file(p, tier="archival").ok


def test_file_resolution_floor(tmp_path):
    tiny = _img(tmp_path, "tiny.jpg", 400, 300)
    v = check_file(tiny, tier="archival")
    assert not v.ok and "resolution floor" in v.reasons[0]


def test_vision_hook_verdicts(tmp_path):
    good = _img(tmp_path, "good2.jpg", 1600, 1200)
    assert not check_file(good, tier="stock", vision=lambda p: True).ok
    assert check_file(good, tier="stock", vision=lambda p: False).ok
    v = check_file(good, tier="stock", vision=lambda p: None)
    assert v.ok and "watermark-vision-unavailable" in v.flags


def test_scan_files_reports_suspects_only(tmp_path):
    bad = _img(tmp_path, "b.jpg", 1600, 1200, _alamy_banner)
    good = _img(tmp_path, "g.jpg", 1600, 1200)
    out = scan_files([bad, good, tmp_path / "missing.jpg"])
    assert [Path(s["path"]).name for s in out] == ["b.jpg"]


# --- ingest door -------------------------------------------------------------

def test_imagelib_ingest_refuses_blocked_domain(tmp_path):
    from nolan.imagelib import ImageLibrary
    lib = ImageLibrary("project", project="gate-test",
                       base_dir=tmp_path / "lib")
    with pytest.raises(ValueError, match="stock-preview domain"):
        lib.add_url("https://c8.alamy.com/comp/XYZ/img.jpg")


# --- doors manifest: every acquisition point provably calls the gate ---------

def _func_body(text: str, func_sig: str) -> str:
    """The body of the named def (to the next same-indent def) — crude but
    stable for grep-level enforcement."""
    i = text.find(func_sig)
    assert i >= 0, f"function {func_sig!r} not found"
    indent = text.rfind("\n", 0, i)
    col = i - indent - 1
    j = i
    while True:
        j = text.find("\ndef " if col == 0 else "\n" + " " * col + "def ", j + 1)
        if j == -1:
            return text[i:]
        if j > i:
            return text[i:j]


@pytest.mark.parametrize("door", sorted(ASSET_GATE_DOORS))
def test_door_calls_the_gate(door):
    spec = ASSET_GATE_DOORS[door]
    src = (REPO / spec["file"]).read_text(encoding="utf-8", errors="replace")
    scope = _func_body(src, spec["func"]) if spec["func"] else src
    for call in spec["calls"]:
        assert call in scope, (
            f"door {door}: {spec['file']}::{spec['func']} no longer calls "
            f"{call}() — the acquisition gate is unwired")


def test_doors_manifest_paths_exist():
    for door, spec in ASSET_GATE_DOORS.items():
        assert (REPO / spec["file"]).exists(), f"{door}: {spec['file']} missing"


def test_clean_title_strips_filename_artifacts():
    """aeneid citation rendered '…fol 52r - wm removed.jpg' ON SCREEN —
    provider titles are often filenames; the label must show the human part."""
    from nolan.asset_gate import clean_title
    assert clean_title("Vergilius Vaticanus (Vat. lat. 3225), fol 52r - wm removed.jpg") \
        == "Vergilius Vaticanus (Vat. lat. 3225), fol 52r"
    assert clean_title("Statue-Augustus.JPG") == "Statue-Augustus"
    assert clean_title("mosaic_of_virgil_cropped") == "mosaic of virgil"
    assert clean_title("Dido Building Carthage") == "Dido Building Carthage"
    assert clean_title(None) == ""
