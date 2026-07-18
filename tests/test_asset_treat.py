"""End-to-end for the BAKED per-asset 'treat' op through quickedit_asset — the layer the fx button hits
via POST /api/hf/asset-quickedit (path resolution + callable out_ext + real ffmpeg + pool registration),
which the argv-level tests in test_ground_effect.py don't cover. A colour grade on an image yields a NEW
pool asset registered in pool.json; an image + plate becomes an .mp4."""
import shutil
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"

from nolan.hyperframes import edit as hfedit   # noqa: E402


def _comp():
    name = "_hf_treat_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "compositions" / "frames").mkdir(parents=True)   # _comp_dir only accepts a dir with this (marks a real comp)
    (dst / "assets").mkdir(parents=True)
    Image.new("RGB", (160, 90), (120, 90, 60)).save(dst / "assets" / "pic.png")
    return name, dst


def test_treat_bakes_and_registers_a_new_pool_asset():
    name, dst = _comp()
    try:
        r = hfedit.quickedit_asset(name, "assets/pic.png", "treat", {"effects": ["sepia"]}, "new")
        out = dst / r["path"]
        assert r["mode"] == "new" and out.exists() and out.suffix == ".png"    # colour-only → keeps the image ext
        assert out.name in (dst / "pool.json").read_text(encoding="utf-8")      # registered in the pool
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def test_treat_image_plus_plate_becomes_mp4():
    from nolan.effects.library import resolve_plate
    if not resolve_plate("rain"):
        import pytest
        pytest.skip("rain plate not stocked")
    name, dst = _comp()
    try:
        r = hfedit.quickedit_asset(name, "assets/pic.png", "treat", {"effects": ["noir", "rain"]}, "new")
        out = dst / r["path"]
        assert out.suffix == ".mp4" and out.exists() and out.stat().st_size > 0   # image + plate → animated video
        assert out.name in (dst / "pool.json").read_text(encoding="utf-8")
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def test_treat_preview_is_a_scratch_sample_not_pooled():
    """The fx-modal 'Preview result' bakes a low-res sample WITHOUT registering it as a pool asset."""
    name, dst = _comp()
    try:
        out = hfedit.treat_preview(name, "assets/pic.png", ["sepia"])
        assert out.exists() and out.stat().st_size > 0 and "_fxpreview" in str(out)
        pj = dst / "pool.json"                                          # not registered in the pool
        assert (not pj.exists()) or (out.name not in pj.read_text(encoding="utf-8"))
    finally:
        shutil.rmtree(dst, ignore_errors=True)
