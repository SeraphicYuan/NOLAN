"""Bespoke mode (nolan.hyperframes.bespoke): hand a selected scene to an agent to author a fully-custom
`raw` scene. The task brief must CARRY the scene's context (narration + word timings, theme tokens, the
frame's other scenes for continuity, the raw seek-safe contract, the propose call); the composer gate
must REJECT a non-seek-safe raw scene; dispatch writes one brief per selected scene."""
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"

from nolan.hyperframes import bespoke as bsp   # noqa: E402
from nolan.hyperframes import edit as hfedit    # noqa: E402


def _comp():
    name = "_hf_bespoke_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "compositions" / "frames").mkdir(parents=True)
    (dst / "compositions" / "frames" / "01-x.spec.json").write_text(json.dumps({"frames": [{"id": "01-x", "dur": 12.0, "scenes": [
        {"id": "f01s01", "type": "statement", "start": 0, "dur": 6, "data": {"lines": ["the setup"]}},
        {"id": "f01s02", "type": "stat", "start": 6, "dur": 6, "data": {"items": [{"value": "7", "label": "questions"}]}},
    ]}]}), encoding="utf-8")
    (dst / "hyperframes.json").write_text('{"theme":"highlighter-editorial"}', encoding="utf-8")
    (dst / "audio_meta.json").write_text(json.dumps({"voices": [{"frame": "1", "words": [
        {"word": "the", "start": 0.1, "end": 0.3}, {"word": "setup", "start": 0.3, "end": 0.9},
        {"word": "seven", "start": 6.2, "end": 6.6}, {"word": "questions", "start": 6.6, "end": 7.2},
    ]}]}), encoding="utf-8")
    return name, dst


def test_bespoke_brief_carries_scene_context():
    name, dst = _comp()
    try:
        brief = bsp.bespoke_task_brief(name, "01-x", "f01s02", direction="kinetic type per question", session="nolan3")
        # narration + word timings (word-anchored reveals)
        assert "questions" in brief and '"seven"@0.2s' in brief          # frame-local timing (6.2 - 6.0 start)
        # theme tokens (the actual palette, not hardcoded)
        assert "--accent" in brief or "--text" in brief
        # continuity: the frame's OTHER scene is named
        assert "f01s01" in brief and "statement" in brief
        # composition archetype injected (the A/B/C/D lever): f01s02 is a `stat` scene -> centered-hero
        assert "the layout archetype" in brief and "centered-hero" in brief
        assert "rule-of-thirds" in brief                                  # grid guidance, not pixels
        # the hard contract + the exact submit call
        assert "transforms + opacity ONLY" in brief and "data-track-index" in brief and "83%" in brief
        assert "propose_scene_edit" in brief and "type\":\"raw\"" in brief
        assert "kinetic type per question" in brief                       # the human direction is carried
        assert "nolan3" in brief                                          # the agent's session
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def test_gate_rejects_non_seek_safe_raw():
    # a bespoke raw scene with a non-deterministic / repeating tween is REJECTED by the composer gate (reverts);
    # a clean one lands. Exercised through the same raw lander the effect flow uses.
    from nolan.hyperframes import effect as eff
    name, dst = _comp()
    try:
        bad_tl = ['tl.to("#f01s02-x",{x:Math.random()*40,yoyo:true,repeat:-1},0);']
        html = ['<div id="f01s02-x" class="clip" data-start="6" data-duration="6" data-track-index="2"></div>']
        assert eff.apply_effect(name, "01-x", "f01s02", html, bad_tl).get("applied") is False   # gated out
        assert hfedit.load_frame_spec(name, "01-x")[0]["frames"][0]["scenes"][1]["type"] == "stat"   # reverted
        good_tl = ['tl.fromTo("#f01s02-x",{opacity:0},{opacity:1,duration:0.5},6.2);']
        assert eff.apply_effect(name, "01-x", "f01s02", html, good_tl).get("applied") is True
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def test_dispatch_writes_one_brief_per_scene():
    name, dst = _comp()
    try:
        # NON-EXISTENT sessions on purpose — a real fleet name (nolan1…) would send a live tmux message
        # and INTERRUPT that agent. Here dispatch gracefully fails per scene, but a brief is still written.
        r = bsp.dispatch_bespoke(name, ["f01s01", "f01s02"], direction="", sessions=["_bsp_test_a", "_bsp_test_b"])
        assert len(r["results"]) == 2
        assert {x["scene_id"] for x in r["results"]} == {"f01s01", "f01s02"}
        assert {x["session"] for x in r["results"]} == {"_bsp_test_a", "_bsp_test_b"}   # round-robin fan-out
        for x in r["results"]:
            assert Path(x["task"]).exists() and x["frame_id"] == "01-x"              # brief written, frame resolved
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def test_frame_of_scene_resolves():
    name, dst = _comp()
    try:
        assert bsp._frame_of_scene(name, "f01s02") == "01-x"
        assert bsp._frame_of_scene(name, "nope") is None
    finally:
        shutil.rmtree(dst, ignore_errors=True)
