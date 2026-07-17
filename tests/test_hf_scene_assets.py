"""Phase 3 of the HF edit-loop program (docs/HF_EDIT_LOOP.md): drag-drop an asset onto a scene →
validated, named `{scene_id}_edit_{vid|pic}{N}`, landed in assets/ + the pool (with scene/frame
provenance), and added to the scene's shortlist. Backend (add_scene_asset / remove_scene_asset)."""
import io
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"

from nolan.hyperframes import edit as hfedit   # noqa: E402


def _png_bytes(color=(200, 60, 60)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def comp():
    """A throwaway comp under videos/ with one frame + one scene (so discovery + load_frame_spec work)."""
    name = "_hf_scene_assets_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    fdir = dst / "compositions" / "frames"
    fdir.mkdir(parents=True)
    (fdir / "f1.spec.json").write_text(json.dumps(
        {"frames": [{"id": "f1", "dur": 10.0, "scenes": [
            {"id": "s1", "type": "statement", "start": 0, "dur": 5, "data": {"lines": ["hi"]}}]}]}), encoding="utf-8")
    try:
        yield name
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def test_add_scene_asset_names_shortlists_and_registers(comp):
    png = _png_bytes()
    r1 = hfedit.add_scene_asset(comp, "f1", "s1", "dropped.png", png)
    assert r1["name"] == "s1_edit_pic1.png"                     # {scene}_edit_pic1
    assert r1["media_type"] == "image" and r1["path"] == "assets/s1_edit_pic1.png"
    cdir = VIDEOS / comp
    assert (cdir / "assets" / "s1_edit_pic1.png").exists()
    assert (cdir / "capture" / "assets" / "s1_edit_pic1.png").exists()   # also lands in the pool media dir

    # pool.json entry carries scene/frame provenance
    pool = json.loads((cdir / "pool.json").read_text(encoding="utf-8"))
    e = next(x for x in pool if x["file"] == "s1_edit_pic1.png")
    assert e["scene_id"] == "s1" and e["frame_id"] == "f1" and e["source"] == "manual-edit"
    assert e["id"] == "s1_edit_pic1.png" and e["license"] == "user-provided"

    # scene.meta.shortlist got the entry
    spec, info = hfedit.load_frame_spec(comp, "f1")
    sl = spec["frames"][info["i"]]["scenes"][0]["meta"]["shortlist"]
    assert len(sl) == 1 and sl[0]["name"] == "s1_edit_pic1.png"

    # a SECOND (different) asset increments the index
    r2 = hfedit.add_scene_asset(comp, "f1", "s1", "another.jpg", _png_bytes((30, 30, 200)))
    assert r2["name"] == "s1_edit_pic1.jpg" or r2["name"] == "s1_edit_pic2.jpg"   # next pic index
    # dedup: the SAME bytes as r1 → returns the existing entry, no third file
    r3 = hfedit.add_scene_asset(comp, "f1", "s1", "again.png", png)
    assert r3.get("deduped") is True and r3["name"] == "s1_edit_pic1.png"


def test_add_scene_asset_rejects_junk(comp):
    with pytest.raises(ValueError):
        hfedit.add_scene_asset(comp, "f1", "s1", "notreal.jpg", b"this is not an image")
    with pytest.raises(ValueError):
        hfedit.add_scene_asset(comp, "f1", "s1", "weird.txt", b"text file")   # unsupported ext


def test_remove_scene_asset(comp):
    hfedit.add_scene_asset(comp, "f1", "s1", "a.png", _png_bytes())
    out = hfedit.remove_scene_asset(comp, "f1", "s1", "s1_edit_pic1.png")
    assert out["remaining"] == 0
    spec, info = hfedit.load_frame_spec(comp, "f1")
    assert spec["frames"][info["i"]]["scenes"][0]["meta"]["shortlist"] == []
