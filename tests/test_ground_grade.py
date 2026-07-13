"""ground.grade — the GENERIC visual-treatment field (cool/warm/darken/desaturate/…) as a gated CSS filter
on any image ground. The generic answer to "cool it down"-class notes, instead of per-block tint fields."""
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"
sys.path.insert(0, str(BRIDGE))
import compose  # noqa: E402


def test_grades_registry_covers_common_treatments():
    assert {"warm", "cool", "darken", "brighten", "contrast", "desaturate"} <= set(compose.GRADES)


def test_media_ground_applies_grade_filter():
    html = "".join(compose.media_ground("s1", {"kind": "image", "src": "a.jpg", "grade": "cool"}, 0, 5)[0])
    assert f"filter:{compose.GRADES['cool']}" in html and "s1-gnd" in html


def test_media_ground_no_grade_no_filter():
    assert "filter:" not in "".join(compose.media_ground("s2", {"kind": "image", "src": "b.jpg"}, 0, 5)[0])


def test_media_ground_unknown_grade_ignored():
    # an unknown value is dropped (no filter) rather than injecting garbage CSS
    assert "filter:" not in "".join(compose.media_ground("s3", {"kind": "image", "src": "c.jpg", "grade": "zzz"}, 0, 5)[0])
