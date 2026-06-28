"""Tests for render-clips' unified-core path (P3): _unified_render_clip."""

from pathlib import Path
from unittest.mock import patch

from nolan.cli_legacy import _unified_render_clip
from nolan.scenes import Scene


def test_renders_existing_motion_spec(tmp_path):
    s = Scene(id="g1", visual_type="text-overlay", motion_spec={"effect": "x", "backend": "python"})
    with patch("nolan.render_dispatch.render_one", return_value="motion") as ro:
        rel = _unified_render_clip(s, tmp_path / "clips", 4.0, tmp_path, llm=None)
    assert rel == "clips/g1.mp4" and ro.called


def test_lazily_authors_then_renders(tmp_path):
    s = Scene(id="g2", visual_type="text-overlay", visual_description="count to 300")

    async def fake_compile(brief, llm, **k):
        return {"effect": "counter", "backend": "python", "target": "CounterRenderer"}, []

    with patch("nolan.motion.compile_spec", side_effect=fake_compile), \
         patch("nolan.render_dispatch.render_one", return_value="motion"):
        rel = _unified_render_clip(s, tmp_path / "clips", 4.0, tmp_path, llm=object())
    assert rel == "clips/g2.mp4"
    assert s.motion_spec and s.motion_spec["effect"] == "counter"   # authored on demand


def test_returns_none_when_core_cannot_render(tmp_path):
    s = Scene(id="g3", visual_type="text-overlay", visual_description="something")

    async def fake_compile(brief, llm, **k):
        return {}, ["no effect"]   # nothing authored

    with patch("nolan.motion.compile_spec", side_effect=fake_compile), \
         patch("nolan.render_dispatch.render_one", return_value=None) as ro:
        rel = _unified_render_clip(s, tmp_path / "clips", 4.0, tmp_path, llm=object())
    assert rel is None and ro.called   # caller falls back to legacy/render-service


def test_render_error_returns_none(tmp_path):
    s = Scene(id="g4", visual_type="text-overlay", motion_spec={"effect": "x", "backend": "python"})
    with patch("nolan.render_dispatch.render_one", side_effect=RuntimeError("boom")):
        assert _unified_render_clip(s, tmp_path / "clips", 4.0, tmp_path, llm=None) is None
