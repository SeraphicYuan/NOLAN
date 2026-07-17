"""Quick-edit framework (crop first) + neutral pool-add for the /hyperframes edit page. Crop is fast enough
to run inline; in-place keeps a reversible `.orig` backup; a new-asset crop registers in the pool."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from nolan.hyperframes import edit as hfedit
from nolan.hyperframes import quickedit as qe

REPO = Path(__file__).resolve().parents[1]
VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"


def _ffmpeg_or_skip():
    try:
        ff = hfedit._ffmpeg() if hasattr(hfedit, "_ffmpeg") else __import__("nolan.hf_qa", fromlist=["_ffmpeg"])._ffmpeg()
    except Exception:
        pytest.skip("ffmpeg unavailable")
    return ff


def _dims(ff, p):
    o = subprocess.run([ff, "-i", str(p)], capture_output=True, text=True)
    ls = [l for l in (o.stdout + o.stderr).splitlines() if "Video:" in l]
    m = re.search(r"(\d{2,5})x(\d{2,5})", ls[0]) if ls else None
    return m.group(0) if m else "?"


@pytest.fixture()
def comp():
    ff = _ffmpeg_or_skip()
    name = "_hf_quickedit_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "compositions" / "frames").mkdir(parents=True)
    (dst / "assets").mkdir(parents=True)
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "testsrc=s=320x240:d=1", "-frames:v", "1",
                    str(dst / "assets" / "seed.png")], capture_output=True)
    try:
        yield name, ff, dst
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def test_crop_to_new_pool_asset(comp):
    name, ff, dst = comp
    r = hfedit.quickedit_asset(name, "assets/seed.png", "crop", {"x": 10, "y": 20, "w": 100, "h": 80}, mode="new")
    assert _dims(ff, dst / r["path"]) == "100x80" and r["mode"] == "new"
    import json
    pool = json.loads((dst / "pool.json").read_text(encoding="utf-8"))
    assert any(e.get("file") == r["name"] for e in pool)         # the new crop is a pool asset


def test_crop_in_place_is_reversible(comp):
    name, ff, dst = comp
    hfedit.quickedit_asset(name, "assets/seed.png", "crop", {"x": 0, "y": 0, "w": 50, "h": 50}, mode="inplace")
    assert _dims(ff, dst / "assets" / "seed.png") == "50x50"
    assert (dst / "assets" / "seed.orig.png").exists()           # original stashed
    hfedit.revert_asset(name, "assets/seed.png")
    assert _dims(ff, dst / "assets" / "seed.png") == "320x240"    # restored
    assert not (dst / "assets" / "seed.orig.png").exists()        # backup consumed


def test_add_pool_asset_is_neutral(comp):
    name, ff, dst = comp
    data = (dst / "assets" / "seed.png").read_bytes()
    r = hfedit.add_pool_asset(name, "My Nice Clip.png", data)
    # neutral, sanitized name (NOT scene-scoped like `f01s01_edit_pic1`); content-deduped against seed.png
    assert "_edit_" not in r["name"] and r["media_type"] == "image"


def test_bad_op_and_media_raise(comp):
    name, ff, dst = comp
    with pytest.raises(ValueError):
        qe.apply_quick_edit(dst / "assets" / "seed.png", "nope", {}, dst / "x.png")
    with pytest.raises(ValueError):
        qe.apply_quick_edit(dst / "assets" / "seed.png", "crop", {"x": 0, "y": 0, "w": 0, "h": 10}, dst / "x.png")
    with pytest.raises(ValueError):                                # trim is video-only
        qe.apply_quick_edit(dst / "assets" / "seed.png", "trim", {"start": 0, "end": 1}, dst / "x.png")


def _dur(ff, p):
    from nolan.hf_qa import probe
    return float(probe(p).duration or 0)


def test_trim_and_fit_ops(comp):
    name, ff, dst = comp
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "testsrc=s=320x240:d=4:r=30", "-f", "lavfi",
                    "-i", "sine=f=440:d=4", "-c:v", "libx264", "-c:a", "aac", "-t", "4",
                    str(dst / "assets" / "clip.mp4")], capture_output=True)
    if _dur(ff, dst / "assets" / "clip.mp4") < 1:
        pytest.skip("ffmpeg could not build the test clip")
    # TRIM [1,3] → ~2s
    t = hfedit.quickedit_asset(name, "assets/clip.mp4", "trim", {"start": 1, "end": 3}, mode="new")
    assert abs(_dur(ff, dst / t["path"]) - 2.0) < 0.25
    # FIT to 2.5s → ~2.5s (retime)
    f = hfedit.quickedit_asset(name, "assets/clip.mp4", "fit", {"target": 2.5, "src_dur": 4.0}, mode="new")
    assert abs(_dur(ff, dst / f["path"]) - 2.5) < 0.25


def test_registry_exposes_ui_and_background(comp):
    ops = hfedit.quick_edit_ops()
    assert ops["trim"]["media"] == ["video"] and ops["trim"]["ui"] == "trim"
    assert ops["fit"]["ui"] == "auto"
    assert ops["remove_bg"]["background"] is True and ops["remove_bg"]["media"] == ["image"]
