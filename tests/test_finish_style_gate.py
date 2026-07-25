"""The PRE-RENDER style-contract gate, and the dials it scores against.

The lint used to run only at finish step 9, soft, AFTER the render — so a draft that missed evidence
coverage / motion footage / block variety shipped anyway and the 'revise' half of draft→lint→revise never
happened. It also linted at the preset defaults while the author had been briefed to `dense`, so brief and
gate disagreed. Both are load-bearing: test the gate raises, the escape hatch works, and the dials persist.
"""
import json

import pytest

from nolan.hyperframes.finish import _style_gate, style_dials


def _comp(tmp, scenes, dials=None):
    (tmp / "compositions" / "frames").mkdir(parents=True)
    (tmp / "compositions" / "frames" / "01-a.spec.json").write_text(
        json.dumps({"frames": [{"id": "01-a", "scenes": scenes}]}), encoding="utf-8")
    if dials is not None:
        (tmp / "hyperframes.json").write_text(json.dumps({"style_dials": dials}), encoding="utf-8")
    return tmp


def _narrow(n=20):
    """A 'three templates in a trench coat' draft — the diamond v1 disease."""
    return [{"id": f"s{i}", "type": ("statement" if i % 3 else "stat"), "start": i * 8.0, "dur": 8.0,
             "data": {"lines": ["a claim"]}} for i in range(n)]


def test_style_dials_read_from_hyperframes_json(tmp_path):
    _comp(tmp_path, _narrow(3), dials={"asset_density": "dense", "video_share": "heavy"})
    assert style_dials(tmp_path) == {"asset_density": "dense", "video_share": "heavy"}


def test_style_dials_absent_or_broken_is_empty(tmp_path):
    _comp(tmp_path, _narrow(3))
    assert style_dials(tmp_path) == {}
    (tmp_path / "hyperframes.json").write_text("{not json", encoding="utf-8")
    assert style_dials(tmp_path) == {}


def test_gate_raises_before_the_render_spend(tmp_path):
    _comp(tmp_path, _narrow(), dials={"asset_density": "dense", "video_share": "heavy"})
    with pytest.raises(RuntimeError, match="STYLE-CONTRACT GATE"):
        _style_gate(tmp_path)


def test_gate_names_the_failing_dimensions_and_the_dials_in_play(tmp_path):
    _comp(tmp_path, _narrow(), dials={"asset_density": "dense"})
    with pytest.raises(RuntimeError) as e:
        _style_gate(tmp_path)
    msg = str(e.value)
    assert "Evidence coverage" in msg and "Palette coverage" in msg   # what failed, in human labels
    assert "asset_density" in msg                                     # …and what it was scored against
    assert "HF_ALLOW_STYLE=1" in msg                                  # …and the knowing exception


def test_knowing_exception_ships_it(tmp_path, monkeypatch):
    _comp(tmp_path, _narrow(), dials={"asset_density": "dense"})
    monkeypatch.setenv("HF_ALLOW_STYLE", "1")
    _style_gate(tmp_path)                                             # no raise


def test_gate_never_blocks_a_render_on_its_own_failure(tmp_path):
    """A composition with no specs (or an unreadable one) must pass through, not hard-fail the DAG."""
    (tmp_path / "compositions" / "frames").mkdir(parents=True)
    _style_gate(tmp_path)                                             # no specs → no raise
