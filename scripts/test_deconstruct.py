"""Test: video deconstruction package (Tier 2) — mock LLM, no vision, no agent.

Verifies:
  1. Beats: mock-LLM segmentation with gap/overlap repair; fallback split.
  2. Operators: mock-LLM classification, invalid-op band fallback, garbage → fallback.
  3. build_extract E2E on a generated video + fake segments: beats carry
     operator/energy/pace/transition/treatment, draft plan is scene_plan-shaped,
     evidence frames written, montage collapse works.
  4. Synthesis task brief content; store lifecycle; hub routes registered.

Usage:
    D:/env/nolan/python.exe -X utf8 scripts/test_deconstruct.py
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.nolan.deconstruct import (DeconstructionStore, build_extract,
                                   deconstruction_synthesis_task)
from src.nolan.deconstruct.beats import segment_beats
from src.nolan.deconstruct.operators import classify_operators
from src.nolan.indexer import VideoIndex
from src.nolan.models.video import InferredContext


class MockLLM:
    def __init__(self, reply):
        self.reply = reply

    async def generate(self, prompt, system_prompt=None):
        return self.reply


def test_beats():
    shots = [{"shot_index": i, "timestamp_start": i * 2.0, "timestamp_end": (i + 1) * 2.0,
              "camera_motion": "static"} for i in range(10)]
    said = [f"line {i}" for i in range(10)]
    mock = MockLLM(json.dumps({"beats": [
        {"title": "Cold open", "function": "hook", "first_shot": 0, "last_shot": 2},
        {"title": "Deep dive", "function": "evidence", "first_shot": 5, "last_shot": 8},
        {"title": "Close", "function": "close", "first_shot": 8, "last_shot": 9}]}))
    res = asyncio.run(segment_beats(shots, said, 20.0, llm=mock))
    assert res["source"] == "llm"
    cover = [i for b in res["beats"] for i in range(b["first_shot"], b["last_shot"] + 1)]
    assert cover == list(range(10)), cover      # gap-free full cover after repair
    res = asyncio.run(segment_beats(shots, said, 20.0, llm=None))
    assert res["source"] == "fallback" and res["beats"][0]["function"] == "hook"
    print("beats OK — llm parse + gap/overlap repair + fallback")


def test_operators():
    def beats():
        return [{"title": "A", "function": "hook", "t0": 0, "t1": 6, "said": "x",
                 "shown": "y", "band": "literal", "asset_types": "painting"},
                {"title": "B", "function": "close", "t0": 6, "t1": 20, "said": "x",
                 "shown": "y", "band": "tonal/abstract", "asset_types": "photo"}]
    bs = beats()
    mock = MockLLM(json.dumps({"classifications": [
        {"beat": 0, "operator": "knowledge", "why": "named artwork", "confidence": "high"},
        {"beat": 1, "operator": "NOT-AN-OP", "why": "bad", "confidence": "high"}]}))
    r = asyncio.run(classify_operators(bs, llm=mock))
    assert r["source"] == "llm"
    assert bs[0]["operator"] == "knowledge" and bs[0]["operator_confidence"] == "high"
    assert bs[1]["operator"] == "tonal" and bs[1]["operator_confidence"] == "low"
    bs = beats()
    r = asyncio.run(classify_operators(bs, llm=MockLLM("garbage")))
    assert r["source"] == "fallback" and bs[0]["operator"] == "literal"
    print("operators OK — llm + invalid-op fallback + garbage fallback")


def test_extract_e2e(td: Path):
    from scripts.test_visual_facts import make_test_video
    vp = td / "test.mp4"
    make_test_video(vp)
    idx = VideoIndex(td / "t.db")
    vid = idx.add_video(path=str(vp), duration=9.0, checksum="c", fingerprint="fp-dec")
    idx.add_segments_bulk(vid, [
        {"timestamp_start": 0.0, "timestamp_end": 3.0,
         "frame_description": "a red painting of a battle",
         "transcript": "The war began with a betrayal.",
         "combined_summary": "Narration over a red battle painting",
         "inferred_context": InferredContext(objects=["painting"]), "sample_reason": "first_frame"},
        {"timestamp_start": 3.0, "timestamp_end": 6.0,
         "frame_description": "green landscape panning",
         "transcript": "Years passed while the kingdom waited.",
         "combined_summary": "Slow pan over green fields",
         "inferred_context": InferredContext(location="countryside"),
         "sample_reason": "scene_change (adaptive)"},
        {"timestamp_start": 6.0, "timestamp_end": 9.0,
         "frame_description": "a blue seascape", "transcript": "And then he came home.",
         "combined_summary": "Calm blue sea at dusk",
         "inferred_context": InferredContext(story_context="homecoming"),
         "sample_reason": "scene_change (adaptive)"},
    ])

    store = DeconstructionStore(td / "video_deconstructions")
    slug = store.create(str(vp), title="Test Video")
    extract, plan = asyncio.run(build_extract(
        str(vp), idx, llm=None, embed=None, frames_dir=store.frames_dir(slug)))
    store.write_extract(slug, extract)
    store.write_plan(slug, plan)
    store.task_path(slug).write_text(
        deconstruction_synthesis_task(slug, "Test Video", str(vp)), encoding="utf-8")

    assert extract["shot_count"] == 3 and extract["beats"]
    for b in extract["beats"]:
        for k in ("operator", "energy", "pace_dir", "transition", "motion_speed",
                  "cuts_per_min", "function", "said"):
            assert k in b, f"beat missing {k}"
    scenes = [s for sec in plan["sections"].values() for s in sec]
    assert scenes and all(s["visual_type"] in
                          ("b-roll", "generated-image", "text-overlay", "graphic")
                          for s in scenes)
    assert all(s["id"].startswith("scene_") and "narration_excerpt" in s for s in scenes)
    assert list(store.frames_dir(slug).glob("beat_*.jpg")), "no evidence frames"

    task = store.read_text(slug, "task")
    for needle in ("extract.json", "breakdown.md", "recovered_plan.json",
                   "ComfyUI prompt", "operator", "frames/beat_NN.jpg"):
        assert needle in task, f"task brief missing {needle!r}"

    meta = store.get(slug)
    assert meta["has_extract"] and meta["has_plan"] and not meta["has_breakdown"]
    assert store.list() and store.list()[0]["slug"] == slug
    assert store.delete(slug) and not store.exists(slug)
    print("extract e2e OK — beats+tempo+operators, plan schema, frames, task brief, store")


def test_montage_collapse():
    from src.nolan.deconstruct.extract import _draft_plan
    shots = [{"shot_index": i, "timestamp_start": float(i), "timestamp_end": i + 1.0,
              "asset_type": "photo", "rep_timestamp": i + 0.5} for i in range(12)]
    beats = [{"title": "Montage", "function": "evidence", "first_shot": 0, "last_shot": 11,
              "t0": 0.0, "t1": 12.0, "said": "many things", "energy": 0.7,
              "transition": "cut", "motion_speed": "fast", "operator": "tonal",
              "dominant_treatment": "as-is"}]
    plan = _draft_plan("v.mp4", beats, shots, ["x"] * 12)
    scenes = plan["sections"]["Montage"]
    assert len(scenes) == 1 and "montage of 12 shots" in scenes[0]["visual_description"]
    print("montage collapse OK — >8-shot beat becomes one scene")


def test_hub_routes(td: Path):
    VideoIndex(td / "lib.db")
    from src.nolan.hub import create_hub_app
    app = create_hub_app(db_path=td / "lib.db")
    routes = {getattr(r, "path", "") for r in app.routes}
    for p in ("/deconstruct", "/api/deconstruct", "/api/deconstruct/run",
              "/api/deconstruct/{slug}", "/api/deconstruct/{slug}/artifact/{name}",
              "/api/deconstruct/{slug}/frame/{fname}"):
        assert p in routes, f"missing route {p}"
    from src.nolan.webui import operations
    import inspect
    assert inspect.iscoroutinefunction(operations.deconstruct_video)
    params = set(inspect.signature(operations.deconstruct_video).parameters)
    for p in ("config", "store_root", "db_path", "video_path", "session",
              "provider", "enable_vision", "use_llm", "profile"):
        assert p in params, f"missing param {p}"
    print("hub OK — routes + operation signature")


def main():
    test_beats()
    test_operators()
    test_montage_collapse()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        test_extract_e2e(Path(td))
        test_hub_routes(Path(td))
    print("\nOK - deconstruction verified.")


if __name__ == "__main__":
    main()
