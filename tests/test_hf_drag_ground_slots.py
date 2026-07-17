"""Drag-drop "use as ground" slots on the /hyperframes edit page. The JS `groundSlot()` derives the target
field from the block's catalog `data_schema` (not a hardcoded map), so this guards BOTH halves of that
contract: (a) the data_schema advertises the background field the JS keys on, and (b) compose CONSUMES it as
an image (not a phantom field). Incident: dropping a background onto a `lower_third` said "no ground slot"
because the old hardcoded map knew only 5 blocks — 7 blocks with a `backdrop`/`background` field were missed."""
import json
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"
sys.path.insert(0, str(BRIDGE))
import compose  # noqa: E402

CATALOG = json.loads((BRIDGE / "catalog.json").read_text(encoding="utf-8"))["scene_templates"]


def _fields(block):
    return set(CATALOG[block]["data_schema"].keys())


def test_catalog_advertises_the_fields_the_js_keys_on():
    # image-drop targets groundSlot() picks, in priority order — lock the field names in
    assert "backdrop" in _fields("lower_third")           # the incident block
    for b in ("collage", "gallery", "carousel", "social_card"):
        assert "backdrop" in _fields(b)
    assert "ground" in _fields("statement") and "ground" in _fields("stat")
    assert "image" in _fields("newshead")
    assert "source" in _fields("document")
    assert "right" in _fields("comparison")
    # blocks with NO image-background slot → groundSlot returns null, the 'use' button is disabled
    for b in ("geo", "timeline", "diagram", "chart", "code", "raw"):
        assert not ({"ground", "image", "source", "right", "backdrop"} & _fields(b)), f"{b} unexpectedly has a bg slot"


def _lt(backdrop):
    sc = {"id": "s1", "type": "lower_third", "start": 0.0, "dur": 5.0,
          "data": {"name": "X", "role": "Y", "style": "block", "position": "bl", "backdrop": backdrop}}
    return "".join(compose.lower_third("s1", sc)[0])


def test_lower_third_consumes_backdrop_image_not_phantom():
    html = _lt("assets/videos/f01s06_edit_pic1.jpg")       # what the fix's patch writes: data.backdrop = <image>
    assert "background-image:url('assets/videos/f01s06_edit_pic1.jpg')" in html   # rendered, full-bleed
    assert "inset:0" in html


def test_lower_third_backdrop_colour_still_works():
    html = _lt("#0a0b0c")
    assert "background:#0a0b0c" in html and "background-image" not in html


def test_collage_consumes_backdrop_image():
    sc = {"id": "s1", "type": "collage", "start": 0.0, "dur": 5.0,
          "data": {"subjects": [{"src": "a.png"}], "backdrop": "assets/videos/x_edit_pic1.jpg"}}
    html = "".join(compose.collage("s1", sc)[0])
    assert "background-image:url('assets/videos/x_edit_pic1.jpg')" in html
