"""The author gate for `ground.camera`, and the catalog that makes it discoverable.

A camera move that does not exist, or one asked of a ground with nothing to move, must fail at the
gate in ~1s — not silently do nothing in a 25-minute render. This is the same class the phantom-cue
gate covers, applied to the new field before it has a chance to become one.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge"
CATALOG = json.loads((BRIDGE / "catalog.json").read_text(encoding="utf-8"))["scene_templates"]
PY = r"D:\env\nolan\python.exe"


def _author(tmp_path, ground):
    spec = {"frames": [{"id": "f1", "dur": 10.0, "scenes": [
        {"id": "s1", "type": "statement", "start": 0.0, "dur": 10.0,
         "data": {"kicker": "K", "lines": ["one"], "operative": "one", "ground": ground}}]}]}
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    r = subprocess.run([PY, "-X", "utf8", str(BRIDGE / "author.py"), "--spec", str(p), "--validate-only"],
                       capture_output=True, text=True, encoding="utf-8", cwd=str(BRIDGE))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


@pytest.mark.skipif(not Path(PY).exists(), reason="windows python not available")
def test_a_valid_camera_passes(tmp_path):
    rc, out = _author(tmp_path, {"kind": "image", "src": "assets/x.jpg", "camera": "push-in"})
    assert rc == 0, out


@pytest.mark.skipif(not Path(PY).exists(), reason="windows python not available")
def test_an_unknown_move_is_refused_by_name(tmp_path):
    rc, out = _author(tmp_path, {"kind": "image", "src": "assets/x.jpg", "camera": "kenburns-supreme"})
    assert rc != 0 and "kenburns-supreme" in out


@pytest.mark.skipif(not Path(PY).exists(), reason="windows python not available")
def test_a_camera_on_a_ground_with_no_media_is_refused(tmp_path):
    """A paper ground has nothing to move; a video ground carries its own motion."""
    rc, out = _author(tmp_path, {"kind": "paper", "camera": "push-in"})
    assert rc != 0 and "IMAGE ground" in out


@pytest.mark.skipif(not Path(PY).exists(), reason="windows python not available")
def test_a_box_move_without_a_box_is_refused(tmp_path):
    """Without a region `push-to-detail` cannot know how tight to go — it would quietly be push-in."""
    rc, out = _author(tmp_path, {"kind": "image", "src": "assets/x.jpg", "camera": {"move": "push-to-detail"}})
    assert rc != 0 and "camera.box" in out
    rc2, _ = _author(tmp_path, {"kind": "image", "src": "assets/x.jpg",
                                "camera": {"move": "push-to-detail", "box": [0.3, 0.3, 0.2, 0.2]}})
    assert rc2 == 0


def test_the_catalog_advertises_every_registered_move():
    """An authoring agent reads the catalog, not the source. A move it cannot see does not exist."""
    from nolan.camera.registry import MOVES
    text = json.dumps(CATALOG)
    missing = [m for m in MOVES if m not in text]
    assert not missing, f"registered but undiscoverable: {missing}"


def test_camera_is_declared_wherever_ground_is():
    """`camera` lives inside the ground spec, so every block that takes a ground must show it."""
    for name, entry in CATALOG.items():
        ds = entry.get("data_schema") or {}
        if "ground" in ds and "media_ground" in str(ds.get("ground", "")):
            assert "camera" in ds, f"{name} takes a ground but never advertises `camera`"
