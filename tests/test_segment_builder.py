"""Tests for the build-from-segment pipeline (fast, mocked — no LLM/render/services)."""
import asyncio
import json
from pathlib import Path

import pytest

from nolan.scenes import Scene, ScenePlan
from nolan.segment import (
    AssetResolver, ResolverConfig, assign_timing, parse_srt, from_script,
    SegmentBuilder, BuildConfig, suggest_spans, FOOTAGE_TYPES,
)


# ---------------------------------------------------------------- fakes
class FakeLLM:
    """Returns canned JSON depending on the prompt/guide content."""
    def __init__(self, scenes=None):
        self._scenes = scenes or [
            {"id": "s1", "visual_type": "b-roll", "narration_excerpt": "city skyline at dusk",
             "visual_description": "aerial city skyline"},
            {"id": "s2", "visual_type": "statistic", "narration_excerpt": "up 300 percent",
             "visual_description": "a +300% counter, green"},
        ]

    async def generate(self, prompt, system_prompt=None):
        sp = system_prompt or ""
        if "self-contained" in sp:        # suggest_spans
            return '[{"start": 10, "end": 70, "title": "Part", "reason": "complete point"}]'
        if "render spec" in sp:           # nolan.motion compile_spec
            return ('{"effect":"counter","content":{"value":300,"prefix":"+","suffix":"%",'
                    '"label":"x"},"style":{"tone":"success"},"position":"center"}')
        if '"category"' in prompt:        # PASS2 (beats injected as JSON) -> scenes
            return json.dumps(self._scenes)
        return json.dumps([{"id": "beat_1", "narration": "n", "category": "b-roll"}])  # PASS1 beats


# ---------------------------------------------------------------- unit: resolver
def test_resolver_routes_motion_search_and_escalation():
    cfg = ResolverConfig(search_threshold=0.5, enable_generation=True)

    # 1) a scene with a motion_spec -> motion
    s_motion = Scene(id="a", visual_type="statistic", motion_spec={"effect": "counter", "backend": "python"})
    # 2) b-roll with a strong search match -> search
    s_hit = Scene(id="b", visual_type="b-roll", visual_description="skyline")
    # 3) b-roll with a weak match -> escalate to generation
    s_miss = Scene(id="c", visual_type="b-roll", visual_description="abstract idea")

    def search_fn(scene):
        if scene.id == "b":
            return {"video_path": "x.mp4", "clip_start": 1, "clip_end": 5, "similarity_score": 0.8}
        return {"video_path": "x.mp4", "clip_start": 1, "clip_end": 5, "similarity_score": 0.2}

    r = AssetResolver(cfg, search_fn=search_fn)
    assert r.resolve(s_motion).startswith("motion:")
    assert r.resolve(s_hit).startswith("search")
    assert s_hit.matched_clip is not None
    assert r.resolve(s_miss).startswith("generated")
    assert s_miss.comfyui_prompt  # escalation set a gen prompt


def test_resolver_no_generation_yields_none():
    r = AssetResolver(ResolverConfig(enable_generation=False, enable_search=False))
    s = Scene(id="x", visual_type="b-roll", visual_description="y")
    assert r.resolve(s).startswith("none")


def test_resolver_external_before_generation():  # P2
    cfg = ResolverConfig(enable_search=False, enable_external=True, enable_generation=True)
    r = AssetResolver(cfg, external_fn=lambda s: "ext.jpg")
    s = Scene(id="x", visual_type="b-roll", visual_description="y")
    assert r.resolve(s).startswith("external")
    assert s.matched_asset == "ext.jpg"


def test_builder_tts_hook_used_when_no_vo(tmp_path):  # P3
    called = {}

    def tts(text, out):
        Path(out).write_bytes(b"a")
        called["text"] = text
        return out

    b = SegmentBuilder(FakeLLM(), BuildConfig(out_dir=tmp_path), tts_fn=tts)
    seg = from_script("hello world", tmp_path)  # no vo_path
    vo = b._resolve_vo(seg)
    assert Path(vo).exists() and called.get("text")


# ---------------------------------------------------------------- unit: timing
def test_assign_timing_tiles_duration_in_proportion():
    scenes = [Scene(id="1", narration_excerpt="one two three four"),
              Scene(id="2", narration_excerpt="five six")]
    assign_timing(scenes, 60.0)
    assert scenes[0].start_seconds == 0.0
    assert scenes[-1].end_seconds == 60.0
    # contiguous
    assert scenes[1].start_seconds == scenes[0].end_seconds
    # first (4 words) gets ~2x the second (2 words)
    assert scenes[0].end_seconds > 30.0


# ---------------------------------------------------------------- unit: srt + inputs
def test_parse_srt_and_from_script(tmp_path):
    srt = tmp_path / "x.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:03,500\nHello world\n\n"
                   "2\n00:00:03,500 --> 00:00:06,000\nSecond line\n", encoding="utf-8")
    lines = parse_srt(srt)
    assert len(lines) == 2 and lines[0][0] == "Hello world" and abs(lines[0][2] - 3.5) < 1e-6

    seg = from_script("Para one here.\n\nPara two there.", tmp_path)
    assert len(seg.sections) == 2 and seg.duration > 0 and seg.vo_path is None


# ---------------------------------------------------------------- unit: suggest (P2)
def test_suggest_spans_parses_llm():
    spans = asyncio.run(suggest_spans([("a", 0, 5), ("b", 5, 10)], FakeLLM()))
    assert spans and spans[0]["start"] == 10 and spans[0]["end"] == 70


# ---------------------------------------------------------------- integration: builder modes (mocked render+assemble)
def _patch_render_and_assemble(monkeypatch, out_dir):
    import nolan.segment.builder as B

    def fake_render(scene, ctx):
        ctx.clips_dir.mkdir(parents=True, exist_ok=True)
        p = ctx.clips_dir / f"{scene.id}.mp4"
        p.write_bytes(b"x")
        scene.rendered_clip = f"{ctx.clips_dir.name}/{p.name}"
        return scene.rendered_clip

    monkeypatch.setattr(B, "render_scene_clip", fake_render)
    monkeypatch.setattr(SegmentBuilder, "_assemble",
                        lambda self, plan, vo, out: [Path(out).write_bytes(b"v"), Path(out)][1])
    monkeypatch.setattr(SegmentBuilder, "_resolve_vo",
                        lambda self, seg: [(out_dir / "vo.wav").write_bytes(b"a"), out_dir / "vo.wav"][1])


def test_builder_auto_mode(monkeypatch, tmp_path):
    _patch_render_and_assemble(monkeypatch, tmp_path)
    seg = from_script("A skyline. \n\nA +300% stat.", tmp_path)
    builder = SegmentBuilder(FakeLLM(), BuildConfig(out_dir=tmp_path, mode="auto"))
    res = asyncio.run(builder.build(seg))
    assert not res.stopped_for_review
    assert res.final_path and Path(res.final_path).exists()
    assert (tmp_path / "scene_plan.json").exists()
    assert (tmp_path / "manifest.json").exists()
    # every scene got a source recorded
    assert all(s.get("source") for s in res.manifest["scenes"])


def test_builder_review_then_resume(monkeypatch, tmp_path):
    _patch_render_and_assemble(monkeypatch, tmp_path)
    seg = from_script("A skyline.\n\nA +300% stat.", tmp_path)
    builder = SegmentBuilder(FakeLLM(), BuildConfig(out_dir=tmp_path, mode="review"))
    res = asyncio.run(builder.build(seg))
    assert res.stopped_for_review and res.final_path is None
    assert (tmp_path / "scene_plan.json").exists()
    # resume from the (possibly edited) plan
    res2 = builder.build_from_plan(tmp_path / "scene_plan.json")
    assert res2.final_path and Path(res2.final_path).exists()
