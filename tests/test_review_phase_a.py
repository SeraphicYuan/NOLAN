"""Regression tests for the Phase-A confirmed-bug fixes (code review 2026-06)."""

from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

import nolan.imagelib.store as store_mod
from nolan.hub import create_hub_app


# 1. clip_matcher empty-query must return a 3-tuple (was bare [])
def test_clip_matcher_empty_query_returns_triple():
    import asyncio
    from nolan.clip_matcher import ClipMatcher
    from nolan.scenes import Scene

    cm = ClipMatcher(vector_search=None, llm_client=None, config=None)
    scene = Scene(id="x", visual_type="b-roll")  # no query fields -> empty query
    cands, raw, mx = asyncio.run(cm.find_candidates(scene, project_id=None))
    assert cands == [] and raw == 0 and mx is None


# 2. orchestrator "counter" maps to the renderer, not the Effect
def test_orchestrator_counter_is_renderer():
    from nolan.orchestrator.render import _build_renderer_registry
    from nolan.renderer.scenes.counter import CounterRenderer
    assert _build_renderer_registry()["counter"] is CounterRenderer


# 3. _parse_json_object uses re (no NameError) on prose-wrapped JSON
def test_parse_json_object_handles_prose():
    from nolan.webui.operations import _parse_json_object
    assert _parse_json_object('here is the result: {"a": 1, "b": "x"} thanks') == {"a": 1, "b": "x"}
    assert _parse_json_object('{"k": 2}') == {"k": 2}


# 4. renderer alpha: transparent -> true RGBA alpha; opaque -> blend toward bg
def test_alpha_color_modes():
    from nolan.renderer.base import BaseRenderer
    r = BaseRenderer.__new__(BaseRenderer)
    r.bg_color = (26, 26, 26)
    r._transparent = True
    rr, gg, bb, aa = r._alpha_color((255, 0, 0), 0.5)
    assert (rr, gg, bb) == (255, 0, 0) and abs(aa - 128) <= 1   # ~half alpha
    assert r._alpha_color((255, 255, 255), 1.0) == (255, 255, 255, 255)
    assert r._alpha_color((10, 20, 30), 0.0)[3] == 0            # fully transparent
    r._transparent = False
    # opaque: blends toward bg (not transparent), 3-tuple
    out = r._alpha_color((255, 255, 255), 0.0)
    assert out == (26, 26, 26)


# 5. scenes_serve_asset rejects path traversal but serves contained files
def test_scenes_asset_path_traversal_blocked(tmp_path):
    proj = tmp_path / "projects" / "demo"
    (proj / "assets").mkdir(parents=True)
    (proj / "scene_plan.json").write_text('{"sections": {}}')  # marker -> discoverable
    (proj / "assets" / "ok.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "projects" / "secret.txt").write_text("top secret")

    client = TestClient(create_hub_app(db_path=None, projects_dir=tmp_path / "projects"))

    # contained file serves
    assert client.get("/scenes/assets/demo/ok.png").status_code == 200
    # traversal escape is rejected (not 200)
    resp = client.get("/scenes/assets/demo/..%2f..%2fsecret.txt")
    assert resp.status_code != 200
    assert "top secret" not in resp.text
