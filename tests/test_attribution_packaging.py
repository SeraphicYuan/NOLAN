"""SOTA #5+#6 — attribution manifest honesty + packaging assembly."""

import asyncio
import json
from pathlib import Path

from nolan.attribution import build_attribution, collect_assets, named_asset_scenes
from nolan.packaging import build_chapters, build_package


PLAN = {"sections": {
    "Beat one": [
        {"id": "s1", "start_seconds": 0.0, "end_seconds": 5.0, "energy": 0.7,
         "matched_clip": {"video_path": "assets/broll_video/s1.mp4",
                          "external": True, "source": "pexels_video",
                          "license": "Pexels License", "source_url": "https://p/x",
                          "title": "Server aisle"}},
        {"id": "s2", "start_seconds": 5.0, "end_seconds": 9.0,
         "matched_asset": "assets/broll/s2.jpg",
         "asset_license": {"source": "pexels", "license": "Pexels License",
                           "source_url": "https://p/y", "title": "Aerial"}},
    ],
    "Beat two": [
        {"id": "s3", "start_seconds": 9.0, "end_seconds": 14.0,
         "matched_asset": "assets/broll/mystery.jpg"},          # no license!
        {"id": "s4", "start_seconds": 14.0, "end_seconds": 18.0,
         "generated_asset": "s4.png", "comfyui_prompt": "desert campus"},
        {"id": "s5", "start_seconds": 18.0, "end_seconds": 22.0,
         "visual_type": "archival-art",
         "search_query": "Prima Porta Augustus statue",
         "matched_asset": "assets/art/aug.jpg"},
    ],
}}


def test_collect_assets_keeps_unknowns_loud():
    assets = collect_assets(PLAN)
    kinds = {a["kind"] for a in assets}
    assert {"stock video", "stock image", "image", "generated image"} <= kinds
    unverified = [a for a in assets if not a.get("license")]
    # the mystery image AND the un-sidecared art still are named, not dropped
    assert {a["path"] for a in unverified} == {"assets/broll/mystery.jpg",
                                               "assets/art/aug.jpg"}


def test_build_attribution_writes_verify_section(tmp_path):
    (tmp_path / "scene_plan.json").write_text(json.dumps(PLAN), encoding="utf-8")
    manifest = build_attribution(tmp_path)
    assert manifest["counts"]["unverified"] == 2
    credits = (tmp_path / "CREDITS.md").read_text(encoding="utf-8")
    assert "VERIFY BEFORE PUBLISH" in credits
    assert "Pexels License" in credits


def test_named_asset_scenes_targets_art():
    named = named_asset_scenes(PLAN)
    assert [s["id"] for s in named] == ["s5"]


def test_build_chapters_anchor_zero():
    ch = build_chapters(PLAN)
    assert ch[0]["t"] == 0.0 and ch[0]["title"] == "Beat one"
    assert ch[1]["title"] == "Beat two"


def test_build_package_deterministic(tmp_path):
    (tmp_path / "scene_plan.json").write_text(json.dumps(PLAN), encoding="utf-8")
    (tmp_path / "script.md").write_text(
        "# Video Script\n\n## Beat one [0:00]\n\nSomewhere around May of 2027, "
        "roughly 49,000 people are going to find out where their electricity "
        "comes from.\n", encoding="utf-8")
    inv = asyncio.run(build_package(tmp_path, llm=None, skip_thumb_render=True))
    pkg = tmp_path / "package"
    assert (pkg / "chapters.txt").read_text(encoding="utf-8").startswith("00:00 Beat one")
    assert inv["items"]["subtitles"] is None          # honest gap (no srt)
    assert inv["items"]["titles"] and inv["items"]["unverified_assets"] == 2
    assert (pkg / "description.txt").exists() and (pkg / "CREDITS.md").exists()
