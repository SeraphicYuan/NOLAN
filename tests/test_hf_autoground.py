"""#3 — auto-ground pairing for long ungrounded data scenes."""
import json
from pathlib import Path
from nolan.hyperframes import autoground as AG


def _comp(tmp: Path, scenes, pool_files, captions):
    (tmp / "compositions" / "frames").mkdir(parents=True)
    (tmp / "assets").mkdir()
    for f in pool_files:
        (tmp / "assets" / f).write_bytes(b"x")               # a real file so _pool_images accepts it
    (tmp / "pool.json").write_text(json.dumps(
        [{"file": f, "caption": captions[f], "usable": True} for f in pool_files]), encoding="utf-8")
    (tmp / "compositions" / "frames" / "01-a.spec.json").write_text(
        json.dumps({"frames": [{"id": "01-a", "dur": 40, "scenes": scenes}]}), encoding="utf-8")
    return tmp


def test_needs_ground_only_long_ungrounded_dataviz():
    assert AG._needs_ground({"type": "chart", "dur": 12, "data": {}}, 8.0)
    assert not AG._needs_ground({"type": "chart", "dur": 4, "data": {}}, 8.0)          # too short
    assert not AG._needs_ground({"type": "statement", "dur": 12, "data": {}}, 8.0)     # not data-viz
    assert not AG._needs_ground({"type": "chart", "dur": 12,
                                 "data": {"ground": {"kind": "image", "src": "x"}}}, 8.0)  # already grounded


def test_autoground_dry_run_keyword_match_and_clean_fallback(tmp_path):
    scenes = [{"id": "s1", "type": "chart", "start": 0, "dur": 12,
               "data": {"kicker": "US ELECTRICITY", "title": "Power grid"}},          # → keyword match
              {"id": "s2", "type": "chart", "start": 12, "dur": 12,
               "data": {"kicker": "ABSTRACT SPEND", "title": "Nothing lexical here"}},  # → left clean
              {"id": "s3", "type": "statement", "start": 24, "dur": 16, "data": {"lines": ["x"]}}]  # skipped
    comp = _comp(tmp_path, scenes, ["pwr.jpg", "misc.jpg"],
                 {"pwr.jpg": "high voltage power lines and electricity pylons", "misc.jpg": "a quiet street"})
    rep = AG.ground_data_scenes(comp, apply=False, use_llm=False)
    assert rep["scanned"] == 2                                # only the 2 long ungrounded charts
    assert any(g["scene"] == "s1" and g["src"] == "pwr.jpg" for g in rep["grounded"])  # lexical match grounded
    assert any(c["scene"] == "s2" for c in rep["left_clean"])   # no fit → CLEAN, never a forced/wrong ground
    assert not any(g["scene"] == "s2" for g in rep["grounded"])
