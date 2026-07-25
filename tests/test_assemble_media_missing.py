"""A referenced asset that resolves to NOTHING must stop the DAG, not warn.

INCIDENT (diamond-v2, first pass): 11 unresolved image refs. `stage_referenced_media` printed a `⚠`
and returned; the style gate reported PASS; the render died ~20 minutes later on a wall of HTTP404.
The information was available for free, before the spend — that is the definition of a silent cap.
"""
import json
import sys
from pathlib import Path

import pytest

BRIDGE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"


def _mod():
    sys.path.insert(0, str(BRIDGE))
    try:
        import assemble_media
        return assemble_media
    finally:
        sys.path.pop(0)


def _comp(tmp_path, refs, present=()):
    fdir = tmp_path / "compositions" / "frames"
    fdir.mkdir(parents=True)
    (tmp_path / "assets").mkdir(exist_ok=True)
    for p in present:
        f = tmp_path / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x")
    scenes = [{"id": f"s{i}", "type": "statement", "data": {"ground": {"kind": "image", "src": r}}}
              for i, r in enumerate(refs)]
    (fdir / "01-a.spec.json").write_text(
        json.dumps({"frames": [{"id": "01-a", "scenes": scenes}]}), encoding="utf-8")
    return tmp_path


def test_a_missing_ref_raises_before_the_render(tmp_path):
    comp = _comp(tmp_path, ["assets/nope.jpg"])
    with pytest.raises(SystemExit, match="resolve to NOTHING"):
        _mod().stage_referenced_media(comp)


def test_the_error_names_every_missing_ref(tmp_path):
    comp = _comp(tmp_path, ["assets/a.jpg", "assets/b.mp4"])
    with pytest.raises(SystemExit) as e:
        _mod().stage_referenced_media(comp)
    assert "a.jpg" in str(e.value) and "b.mp4" in str(e.value)
    assert "HF_ALLOW_MISSING_MEDIA=1" in str(e.value)          # the escape hatch is discoverable


def test_the_knowing_exception_warns_and_continues(tmp_path, monkeypatch, capsys):
    comp = _comp(tmp_path, ["assets/nope.jpg"])
    monkeypatch.setenv("HF_ALLOW_MISSING_MEDIA", "1")
    res = _mod().stage_referenced_media(comp)
    assert res["missing"] == ["assets/nope.jpg"]
    assert "rendering anyway" in capsys.readouterr().out


def test_all_refs_present_is_silent_and_stages_nothing(tmp_path):
    comp = _comp(tmp_path, ["assets/ok.jpg"], present=["assets/ok.jpg"])
    res = _mod().stage_referenced_media(comp)
    assert res == {"staged": [], "missing": []}


def test_a_ref_stageable_from_capture_is_not_missing(tmp_path):
    """The staging path still works — only genuinely-unresolvable refs are fatal."""
    comp = _comp(tmp_path, ["assets/from_capture.jpg"],
                 present=["capture/assets/from_capture.jpg"])
    res = _mod().stage_referenced_media(comp)
    assert res["staged"] == ["assets/from_capture.jpg"] and res["missing"] == []
    assert (comp / "assets" / "from_capture.jpg").exists()
