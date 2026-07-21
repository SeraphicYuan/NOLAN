"""Tests for the sync dry-run (nolan.hyperframes.sync.place_scenes write=False + report_windows).

Locks POST_MORTEM #4: the anchor→window preview must compute per-scene windows + SHORT/LONG
verdicts WITHOUT mutating the specs, so an author can re-space anchors in seconds.
"""
import json
from pathlib import Path

from nolan.hyperframes import sync


def _comp(tmp_path, words, scenes, frame_dur):
    comp = tmp_path / "comp"
    (comp / "compositions" / "frames").mkdir(parents=True)
    (comp / "audio_meta.json").write_text(json.dumps(
        {"voices": [{"frame": 1, "duration_s": frame_dur, "words": words}]}), encoding="utf-8")
    sf = comp / "compositions" / "frames" / "01.spec.json"
    sf.write_text(json.dumps({"frames": [{"id": "01", "dur": frame_dur, "scenes": scenes}]}),
                  encoding="utf-8")
    return comp, sf


def _words(n, dt=1.0):
    return [{"word": f"w{i}", "start": round(i * dt, 2), "end": round(i * dt + dt * 0.9, 2)}
            for i in range(n)]


def test_dry_run_does_not_write_but_real_run_does(tmp_path):
    scenes = [{"id": "s1", "type": "statement", "start": 0, "dur": 5, "data": {"anchor": "w0 w1"}},
              {"id": "s2", "type": "statement", "start": 5, "dur": 5, "data": {"anchor": "w10 w11"}}]
    comp, sf = _comp(tmp_path, _words(20), scenes, 20.0)
    before = sf.read_text()

    rep = sync.place_scenes(comp, write=False)
    assert sf.read_text() == before                      # DRY-RUN: spec untouched
    assert len(rep["windows"]) == 2
    assert {w["scene"] for w in rep["windows"]} == {"s1", "s2"}
    assert all("start" in w and "dur" in w and "verdict" in w for w in rep["windows"])

    sync.place_scenes(comp, write=True)
    assert sf.read_text() != before                      # real run commits the retimed windows


def test_report_flags_long_hold_ungrounded(tmp_path):
    # two ungrounded statements spanning ~10s each in a 20s frame -> both LONG-HOLD
    scenes = [{"id": "s1", "type": "statement", "start": 0, "dur": 5, "data": {"anchor": "w0 w1"}},
              {"id": "s2", "type": "statement", "start": 5, "dur": 5, "data": {"anchor": "w10 w11"}}]
    comp, _ = _comp(tmp_path, _words(20), scenes, 20.0)
    rep = sync.place_scenes(comp, write=False)
    verdicts = [w["verdict"] for w in rep["windows"]]
    assert any("LONG-HOLD" in v for v in verdicts)
    assert any(p["issue"].startswith("LONG-HOLD") for p in rep["problems"])


def test_short_window_is_relieved(tmp_path):
    # anchors 1s apart -> s1 would get a ~1s window (< readable floor); the reliever (#1) borrows from s2's
    # slack so no unreadable flash survives.
    scenes = [{"id": "s1", "type": "statement", "start": 0, "dur": 2, "data": {"anchor": "w0"}},
              {"id": "s2", "type": "statement", "start": 2, "dur": 2, "data": {"anchor": "w1"}}]
    comp, _ = _comp(tmp_path, _words(8), scenes, 8.0)
    rep = sync.place_scenes(comp, write=False)
    assert rep.get("relieved", 0) >= 1                        # the squeezed scene was grown to its minimum
    assert not any("SHORT" in w["verdict"] for w in rep["windows"])   # no illegible flash left


def test_overpacked_frame_reports_residual(tmp_path):
    # 3 newshead (5s floor each = 15s) in an 8s frame can't all be satisfied -> reliever does its best,
    # residual stays flagged (an authoring over-pack the reliever surfaces rather than hides).
    scenes = [{"id": f"s{k}", "type": "newshead", "start": k * 2.5, "dur": 2.5, "data": {"anchor": f"w{k}"}}
              for k in range(3)]
    comp, _ = _comp(tmp_path, _words(12), scenes, 8.0)
    rep = sync.place_scenes(comp, write=False)
    assert rep.get("overpacked")                              # residual reported, not silently squeezed


def test_unresolved_anchor_is_flagged(tmp_path):
    # s2's anchor is never spoken -> frame falls back to proportional, scene marked UNRESOLVED
    scenes = [{"id": "s1", "type": "statement", "start": 0, "dur": 5, "data": {"anchor": "w0 w1"}},
              {"id": "s2", "type": "statement", "start": 5, "dur": 5,
               "data": {"anchor": "nowhere in the transcript at all"}}]
    comp, _ = _comp(tmp_path, _words(20), scenes, 20.0)
    rep = sync.place_scenes(comp, write=False)
    assert any(not w["resolved"] for w in rep["windows"])
