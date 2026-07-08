"""Render story v2 — Chapter hosts motion comps and video steps.

Pins the spec→chapter-step conversion (prop mapping, media path resolution,
hostability boundaries) and premium's new scene precedence (rendered_clip >
scored still > vector clip match).
"""

import pytest

from nolan.motion.executor import chapter_step_for_spec
from nolan.premium_render import PremiumIneligible, _scene_step


# --- chapter_step_for_spec ---------------------------------------------------------

def test_stat_over_maps_image_to_background(tmp_path):
    img = tmp_path / "crowd.jpg"
    img.write_bytes(b"x")
    block, props = chapter_step_for_spec(
        {"effect": "stat-over", "backend": "remotion", "target": "StatOver",
         "content": {"image": "crowd.jpg", "value": 800, "suffix": "B",
                     "caption": "AI infrastructure"}},
        tmp_path)
    assert block == "StatOver"
    assert props["background"] == str(img)          # absolute for stage.mjs
    assert props["value"] == 800 and props["suffix"] == "B"


def test_split_screen_maps_left_right(tmp_path):
    for n in ("a.jpg", "b.jpg"):
        (tmp_path / n).write_bytes(b"x")
    block, props = chapter_step_for_spec(
        {"effect": "split-screen", "backend": "remotion", "target": "SplitScreen",
         "content": {"left": "a.jpg", "right": "b.jpg",
                     "left_label": "then", "right_label": "now"}},
        tmp_path)
    assert block == "SplitScreen"
    assert props["background"].endswith("a.jpg") and props["foreground"].endswith("b.jpg")
    assert props["leftLabel"] == "then"


def test_photo_montage_pro_gets_distinct_key(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")   # the media gate verifies existence
    block, props = chapter_step_for_spec(
        {"effect": "photo-montage-pro", "backend": "remotion", "target": "PhotoMontage",
         "content": {"cards": [{"src": "a.jpg", "x": 0.3, "y": 0.4}]}},
        tmp_path)
    assert block == "PhotoMontagePro"               # never shadows the block rebuild
    assert props["cards"][0]["src"].endswith("a.jpg")


def test_block_backend_routes_through_adapters(tmp_path):
    block, props = chapter_step_for_spec(
        {"effect": "counter", "backend": "block", "target": "StatCount",
         "content": {"value": 42, "label": "answers"}},
        tmp_path)
    assert block == "StatCount"


def test_unhostable_returns_none(tmp_path):
    assert chapter_step_for_spec(
        {"effect": "still-motion", "backend": "remotion", "target": "StillMotion",
         "content": {"image": "a.jpg"}}, tmp_path) is None
    assert chapter_step_for_spec(
        {"effect": "line-chart", "backend": "python", "target": "LineChartRenderer",
         "content": {"points": [["a", 1]]}}, tmp_path) is None


def test_invalid_spec_is_loud(tmp_path):
    with pytest.raises(ValueError):
        chapter_step_for_spec({"effect": "no-such-effect", "content": {}}, tmp_path)


# --- premium scene precedence -------------------------------------------------------

def _mp4(tmp_path, name="clip.mp4"):
    p = tmp_path / name
    p.write_bytes(b"x")
    return p


def test_motion_spec_becomes_hosted_step(tmp_path):
    img = tmp_path / "crowd.jpg"
    img.write_bytes(b"x")
    scene = {"id": "s1", "visual_type": "b-roll",
             "motion_spec": {"effect": "stat-over", "backend": "remotion",
                             "target": "StatOver",
                             "content": {"image": str(img), "value": 12}}}
    block, props = _scene_step(scene, tmp_path, 30, 4.0)
    assert block == "StatOver" and props["value"] == 12


def test_invalid_motion_spec_fails_eligibility(tmp_path):
    scene = {"id": "s1", "visual_type": "b-roll",
             "motion_spec": {"effect": "no-such-effect", "content": {}}}
    with pytest.raises(PremiumIneligible):
        _scene_step(scene, tmp_path, 30, 4.0)


def test_rendered_clip_becomes_video_step(tmp_path):
    clip = _mp4(tmp_path)
    scene = {"id": "s1", "visual_type": "b-roll", "rendered_clip": str(clip)}
    block, props = _scene_step(scene, tmp_path, 30, 4.0)
    assert block == "Video" and props["src"] == str(clip)


def test_scored_still_outranks_vector_clip_match(tmp_path):
    clip = _mp4(tmp_path)
    still = tmp_path / "still.jpg"
    still.write_bytes(b"x")
    scene = {"id": "s1", "visual_type": "b-roll",
             "matched_asset": str(still),
             "matched_clip": {"video_path": str(clip), "clip_start": 3.5}}
    block, _ = _scene_step(scene, tmp_path, 30, 4.0)
    assert block == "ArtworkStage"                  # still wins
    scene.pop("matched_asset")
    block, props = _scene_step(scene, tmp_path, 30, 4.0)
    assert block == "Video"
    assert props["startFromFrames"] == 105          # 3.5s * 30fps


def test_video_scene_is_premium_eligible_now(tmp_path):
    clip = _mp4(tmp_path)
    scene = {"id": "s1", "visual_type": "b-roll",
             "matched_clip": {"video_path": str(clip), "clip_start": 0}}
    block, _ = _scene_step(scene, tmp_path, 30, 4.0)
    assert block == "Video"


def test_auto_shots_yield_to_motion_spec(tmp_path):
    from nolan.premium_render import _expand_shots
    for n in ("a.jpg", "b.jpg", "crowd.jpg"):
        (tmp_path / n).write_bytes(b"x")
    scene = {"id": "s1", "visual_type": "archival-art",
             "shots": [{"src": str(tmp_path / "a.jpg")},
                       {"src": str(tmp_path / "b.jpg")}],
             "shots_auto": True,
             "motion_spec": {"effect": "stat-over", "backend": "remotion",
                             "target": "StatOver",
                             "content": {"image": str(tmp_path / "crowd.jpg"),
                                         "value": 7}}}
    units = _expand_shots(scene, tmp_path, 30, 240, ordinal=0)
    assert len(units) == 1 and units[0][0] == "StatOver"   # motion won
    # human shots (auto flag cleared) outrank the motion spec again
    scene["shots_auto"] = False
    units = _expand_shots(scene, tmp_path, 30, 240, ordinal=0)
    assert len(units) == 2 and units[0][0] == "ArtworkStage"
