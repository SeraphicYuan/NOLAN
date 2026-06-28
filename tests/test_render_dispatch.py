"""Tests for the shared per-scene render router (P1b). Routing only — no real render."""

from types import SimpleNamespace
from unittest.mock import patch

import nolan.render_dispatch as rd


def _obj(**kw):
    base = dict(motion_spec=None, matched_clip=None, layout_spec=None,
                comfyui_prompt=None, resolved_source=None, visual_type="", id="s1")
    base.update(kw)
    return SimpleNamespace(**base)


def test_motion_routes_first(tmp_path):
    for scene in (_obj(motion_spec={"effect": "x"}), {"motion_spec": {"effect": "x"}, "id": "s1"}):
        with patch("nolan.motion.render") as m:
            kind = rd.render_one(scene, tmp_path / "o.mp4", duration=3.0)
        assert kind == "motion" and m.called


def test_broll_routes(tmp_path):
    scene = {"matched_clip": {"clip_start": 1, "clip_end": 5, "video_path": "v.mp4"}, "id": "s1"}
    with patch("nolan.ffmpeg_utils.extract_subclip") as ex:
        kind = rd.render_one(scene, tmp_path / "o.mp4", duration=4.0, fade=0.4)
    assert kind == "broll"
    args, kw = ex.call_args
    assert args[0] == "v.mp4" and args[1] == 1.0 and args[2] == 4.0   # src, start, scene-duration
    assert kw["fade"] == 0.4


def test_broll_uses_resolve_src(tmp_path):
    scene = {"matched_clip": {"clip_start": 0, "clip_end": 2}, "id": "s1"}
    with patch("nolan.ffmpeg_utils.extract_subclip") as ex:
        rd.render_one(scene, tmp_path / "o.mp4", duration=2.0,
                      source_video="S.mp4", resolve_src=lambda s: "/abs/" + str(s))
    assert ex.call_args[0][0] == "/abs/S.mp4"


def test_layout_routes(tmp_path):
    scene = {"layout_spec": {"template": "counter", "params": {}}, "id": "s1"}
    with patch("nolan.orchestrator.render.render_layout", return_value=tmp_path / "o.mp4") as rl:
        kind = rd.render_one(scene, tmp_path / "o.mp4", duration=5.0)
    assert kind == "layout" and rl.called


def test_layout_unrenderable_returns_none(tmp_path):
    scene = {"layout_spec": {"template": "custom"}, "id": "s1"}
    with patch("nolan.orchestrator.render.render_layout", return_value=None):
        assert rd.render_one(scene, tmp_path / "o.mp4", duration=5.0) is None


def test_generated_with_gen_fn(tmp_path):
    scene = {"comfyui_prompt": "a cat", "resolved_source": "generated", "id": "s1"}
    calls = []
    kind = rd.render_one(scene, tmp_path / "o.mp4", duration=5.0,
                         gen_fn=lambda s, o: calls.append(o))
    assert kind == "generated" and calls


def test_generated_without_gen_fn_falls_back_to_card(tmp_path):
    scene = {"comfyui_prompt": "a cat", "visual_type": "generated-image",
             "narration_excerpt": "hello", "id": "s1"}
    with patch("nolan.render_dispatch.render_card") as card:
        kind = rd.render_one(scene, tmp_path / "o.mp4", duration=5.0)
    assert kind == "card" and card.called   # was a black frame before P1b


def test_gen_fn_failure_falls_back_to_card(tmp_path):
    scene = {"comfyui_prompt": "x", "resolved_source": "generated", "id": "s1"}
    def boom(s, o): raise RuntimeError("comfyui down")
    with patch("nolan.render_dispatch.render_card") as card:
        kind = rd.render_one(scene, tmp_path / "o.mp4", duration=5.0, gen_fn=boom)
    assert kind == "card" and card.called


def test_no_asset_returns_none(tmp_path):
    assert rd.render_one({"id": "s1", "visual_type": "b-roll"}, tmp_path / "o.mp4", duration=5.0) is None


def test_priority_motion_over_everything(tmp_path):
    scene = {"motion_spec": {"effect": "x"}, "matched_clip": {"clip_start": 0, "clip_end": 1},
             "layout_spec": {"template": "counter"}, "id": "s1"}
    with patch("nolan.motion.render") as m, patch("nolan.ffmpeg_utils.extract_subclip") as ex:
        kind = rd.render_one(scene, tmp_path / "o.mp4", duration=2.0)
    assert kind == "motion" and m.called and not ex.called
