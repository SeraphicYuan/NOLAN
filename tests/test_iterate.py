"""Tests for scene-level iteration (nolan.iterate) — fast, mocked, no real render."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from nolan import iterate
from nolan.iterate import (
    detect_pipeline, invalidate_scene, revise_scene, apply_edit,
    rerender_scenes, find_scene, load_plan_raw, editable_fields,
)


# ---------------------------------------------------------------- fakes / helpers
class FakeLLM:
    def __init__(self, revise_reply="{}"):
        self.revise_reply = revise_reply

    async def generate(self, prompt, system_prompt=None):
        if "render spec" in (system_prompt or ""):     # nolan.motion compile_spec guide
            return ('{"effect":"counter","content":{"value":300,"prefix":"+","suffix":"%",'
                    '"label":"x"},"style":{"tone":"success"},"position":"center"}')
        return self.revise_reply                        # the revise patch


def _seg_scene(sid, **kw):
    base = {"id": sid, "visual_type": "b-roll", "narration_excerpt": "n",
            "search_query": "city", "rendered_clip": f"clips/{sid}.mp4"}
    base.update(kw)
    return base


def _write_plan(dirpath: Path, scenes, *, segment=True, with_layout=False):
    dirpath.mkdir(parents=True, exist_ok=True)
    plan = {"sections": {"segment": scenes}}
    p = dirpath / "scene_plan.json"
    p.write_text(json.dumps(plan), encoding="utf-8")
    if segment:
        (dirpath / "segment_meta.json").write_text(json.dumps({"duration": 30}), encoding="utf-8")
    else:
        (dirpath / ".orchestrator").mkdir(exist_ok=True)
    return p


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- detection
def test_detect_segment_by_meta(tmp_path):
    p = _write_plan(tmp_path / "seg", [_seg_scene("s1")], segment=True)
    assert detect_pipeline(p) == "segment"


def test_detect_orchestrator_by_dir(tmp_path):
    p = _write_plan(tmp_path / "orch", [_seg_scene("s1")], segment=False)
    assert detect_pipeline(p) == "orchestrator"


def test_detect_orchestrator_by_layout_spec(tmp_path):
    # No marker files at all -> fall back to layout_spec presence.
    d = tmp_path / "bare"
    d.mkdir()
    scene = {"id": "s1", "visual_type": "graphic", "layout_spec": {"template": "quote", "params": {}}}
    (d / "scene_plan.json").write_text(json.dumps({"sections": {"a": [scene]}}), encoding="utf-8")
    assert detect_pipeline(d / "scene_plan.json") == "orchestrator"


# ---------------------------------------------------------------- invalidation
def test_invalidate_clears_field_and_deletes_clip(tmp_path):
    d = tmp_path / "seg"
    p = _write_plan(d, [_seg_scene("s1")], segment=True)
    clip = d / "clips" / "s1.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"x" * 500)

    data = load_plan_raw(p)
    scene = find_scene(data, "s1")
    invalidate_scene(p, scene, "segment")
    assert scene["rendered_clip"] is None
    assert not clip.exists()


# ---------------------------------------------------------------- revise
def test_revise_whitelists_and_compiles_motion(tmp_path, monkeypatch):
    # Agent asks to set a motion effect + sneaks a non-editable field (`id`).
    reply = json.dumps({"motion_brief": "a +300% counter, green, center",
                        "visual_type": "statistic", "id": "HACKED"})
    llm = FakeLLM(revise_reply=reply)

    async def fake_compile(brief, client, repair=True):
        return ({"effect": "counter", "backend": "python", "content": {"value": 300}}, [])
    monkeypatch.setattr("nolan.motion.compile_spec", fake_compile)

    scene = _seg_scene("s1")
    patch = run(revise_scene(scene, "make it a counter", llm, "segment"))
    assert patch["visual_type"] == "statistic"
    assert patch["motion_spec"]["effect"] == "counter"   # brief -> compiled spec
    assert "motion_brief" not in patch
    assert "id" not in patch                              # non-editable filtered out


def test_revise_motion_brief_dropped_on_validation_error(monkeypatch):
    llm = FakeLLM(revise_reply=json.dumps({"motion_brief": "bad"}))

    async def fake_compile(brief, client, repair=True):
        return ({}, ["unknown effect"])
    monkeypatch.setattr("nolan.motion.compile_spec", fake_compile)

    patch = run(revise_scene({"id": "s1"}, "x", llm, "segment"))
    assert "motion_spec" not in patch                    # not applied when invalid


def test_apply_edit_direct_patch_marks_dirty(tmp_path):
    d = tmp_path / "seg"
    p = _write_plan(d, [_seg_scene("s1")], segment=True)
    resolved = run(apply_edit(p, "s1", patch={"search_query": "stocks crash", "id": "NO"}))
    assert resolved == {"search_query": "stocks crash"}   # id filtered
    data = load_plan_raw(p)
    scene = find_scene(data, "s1")
    assert scene["search_query"] == "stocks crash"
    assert scene["rendered_clip"] is None                 # dirtied for rerender


def test_apply_edit_note_requires_client(tmp_path):
    d = tmp_path / "seg"
    p = _write_plan(d, [_seg_scene("s1")], segment=True)
    with pytest.raises(ValueError):
        run(apply_edit(p, "s1", note="change it", client=None))


def test_editable_fields_differ_by_pipeline():
    assert "layout_spec" in editable_fields("orchestrator")
    assert "layout_spec" not in editable_fields("segment")


# ---------------------------------------------------------------- rerender: segment
def test_rerender_segment_renders_only_selected(tmp_path, monkeypatch):
    d = tmp_path / "seg"
    p = _write_plan(d, [_seg_scene("s1"), _seg_scene("s2")], segment=True)
    (d / "segment_meta.json").write_text(json.dumps({"duration": 10}), encoding="utf-8")
    for sid in ("s1", "s2"):
        clip = d / "clips" / f"{sid}.mp4"
        clip.parent.mkdir(parents=True, exist_ok=True)
        clip.write_bytes(b"x" * 500)

    rendered = []
    monkeypatch.setattr("nolan.segment.builder.SegmentBuilder._reresolve_unresolved",
                        lambda self, scenes, seg: 0)
    monkeypatch.setattr("nolan.segment.builder.SegmentBuilder._render",
                        lambda self, scenes, seg: rendered.extend(s.id for s in scenes))
    monkeypatch.setattr("nolan.segment.builder.SegmentBuilder._resolve_vo",
                        lambda self, seg: d / "vo.wav")
    monkeypatch.setattr("nolan.segment.builder.SegmentBuilder._assemble",
                        lambda self, plan_path, vo, out: out)

    final = rerender_scenes(p, ["s1"], llm_client=FakeLLM())
    assert final == d / "final.mp4"
    assert rendered == ["s1"]                                 # ONLY s1 was rendered
    assert not (d / "clips" / "s1.mp4").exists()              # s1 invalidated
    assert (d / "clips" / "s2.mp4").exists()                  # s2's clip untouched
    # s2 still points at its clip in the persisted plan
    assert find_scene(load_plan_raw(p), "s2")["rendered_clip"] == "clips/s2.mp4"


# ---------------------------------------------------------------- rerender: orchestrator
def test_rerender_orchestrator_renders_only_selected_and_keeps_layout(tmp_path, monkeypatch):
    d = tmp_path / "orch"
    s1 = {"id": "s1", "visual_type": "graphic", "duration": "5s",
          "layout_spec": {"template": "quote", "params": {"text": "hi"}},
          "rendered_clip": "assets/rendered/s1.mp4"}
    s2 = {"id": "s2", "visual_type": "graphic", "duration": "5s",
          "layout_spec": {"template": "list", "params": {"items": ["a"]}},
          "rendered_clip": "assets/rendered/s2.mp4"}
    p = _write_plan(d, [s1, s2], segment=False)
    for sid in ("s1", "s2"):
        clip = d / "assets" / "rendered" / f"{sid}.mp4"
        clip.parent.mkdir(parents=True, exist_ok=True)
        clip.write_bytes(b"x" * 500)

    rendered = []

    def fake_render_scene(scene, project_path, output_dir):
        rendered.append(scene["id"])
        return SimpleNamespace(scene_id=scene["id"],
                               rendered_clip=f"assets/rendered/{scene['id']}.mp4")
    monkeypatch.setattr("nolan.orchestrator.render.render_scene", fake_render_scene)
    monkeypatch.setattr("nolan.orchestrator.render.generate_silent_audio",
                        lambda dur, out: Path(out))
    called = {}
    monkeypatch.setattr("nolan.orchestrator.render.call_assemble",
                        lambda **kw: called.update(kw))

    final = rerender_scenes(p, ["s2"])
    assert rendered == ["s2"]                       # only the selected scene re-rendered
    assert final == d / "output" / "final.mp4"
    data = load_plan_raw(p)
    # layout_spec preserved on both scenes (raw-dict round-trip, not Scene dataclass)
    assert find_scene(data, "s1")["layout_spec"]["template"] == "quote"
    assert find_scene(data, "s2")["layout_spec"]["template"] == "list"
    assert not (d / "assets" / "rendered" / "s2.mp4").exists()  # s2 was invalidated
    assert (d / "assets" / "rendered" / "s1.mp4").exists()      # s1 untouched


# ---------------------------------------------------------------- re-resolve
def test_apply_patch_clears_match_on_query_change():
    from nolan.iterate.revise import apply_patch
    scene = {"id": "s1", "search_query": "old", "matched_clip": {"video_path": "x"},
             "resolved_source": "search(0.8)", "rendered_clip": "clips/s1.mp4"}
    apply_patch(scene, {"search_query": "wall street 1929"})
    assert scene["search_query"] == "wall street 1929"
    assert scene["matched_clip"] is None        # stale pick dropped -> forces re-resolve
    assert scene["resolved_source"] is None
    assert scene["rendered_clip"] is None

    # A non-trigger edit (e.g. comfyui_prompt) must NOT drop an existing match.
    scene2 = {"id": "s2", "comfyui_prompt": "a", "matched_clip": {"video_path": "y"},
              "resolved_source": "search", "rendered_clip": "c"}
    apply_patch(scene2, {"comfyui_prompt": "b"})
    assert scene2["matched_clip"] == {"video_path": "y"}


def test_segment_reresolves_only_cleared_scenes(tmp_path):
    from nolan.scenes import Scene
    from nolan.segment import SegmentBuilder, BuildConfig, ResolverConfig
    from nolan.segment.inputs import SegmentInput

    edited = Scene(id="e", visual_type="b-roll", visual_description="a bank vault",
                   resolved_source=None)                              # cleared by an edit
    done = Scene(id="d", visual_type="b-roll", visual_description="city",
                 resolved_source="search(0.8)", matched_clip={"video_path": "keep.mp4"})

    def search_fn(scene):
        return {"video_path": "new.mp4", "clip_start": 1, "clip_end": 5, "similarity_score": 0.9}

    cfg = BuildConfig(out_dir=tmp_path, resolver=ResolverConfig(search_threshold=0.5))
    builder = SegmentBuilder(FakeLLM(), cfg, search_fn=search_fn)
    n = builder._reresolve_unresolved([edited, done], SegmentInput(sections=[], duration=10))
    assert n == 1
    assert edited.matched_clip["video_path"] == "new.mp4"            # re-searched
    assert done.matched_clip == {"video_path": "keep.mp4"}          # untouched


def test_orchestrator_reresolve_noop_without_index():
    from nolan.iterate.engine import _reresolve_broll_dicts
    stale = [{"id": "s1", "visual_type": "b-roll", "search_query": "x"}]
    assert _reresolve_broll_dicts(stale, None, None) == 0           # no client/config -> skip
    assert stale[0].get("matched_clip") is None
