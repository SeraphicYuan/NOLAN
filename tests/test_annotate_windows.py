"""annotate_scene_plan window semantics — aligned windows are authoritative.

Regression for the re-tiling bug that stretched a beat-aligned section from
76.5s to 127.5s: annotate must keep valid start/end verbatim and only place
window-less scenes after their predecessor.
"""

from nolan.orchestrator.render import RenderOutcome, annotate_scene_plan


def _plan(scenes):
    return {"sections": {"S": [dict(s) for s in scenes]}}


def _outcomes(plan):
    return [RenderOutcome(scene_id=s["id"], visual_type="b-roll",
                          rendered_clip=f"assets/rendered/{s['id']}.mp4",
                          template=None, skipped_reason=None)
            for s in plan["sections"]["S"]]


def test_aligned_windows_preserved_verbatim():
    plan = _plan([
        {"id": "a", "start_seconds": 10.0, "end_seconds": 14.5, "duration": "99s"},
        {"id": "b", "start_seconds": 14.5, "end_seconds": 20.0, "duration": "99s"},
    ])
    total, rendered = annotate_scene_plan(plan, _outcomes(plan))
    scenes = plan["sections"]["S"]
    assert (scenes[0]["start_seconds"], scenes[0]["end_seconds"]) == (10.0, 14.5)
    assert (scenes[1]["start_seconds"], scenes[1]["end_seconds"]) == (14.5, 20.0)
    assert total == 20.0                        # last aligned end, not 198s
    assert rendered == 2


def test_unaligned_scenes_tile_sequentially():
    plan = _plan([
        {"id": "a", "duration": "4s"},
        {"id": "b", "duration": "6s"},
    ])
    total, _ = annotate_scene_plan(plan, _outcomes(plan))
    scenes = plan["sections"]["S"]
    assert (scenes[0]["start_seconds"], scenes[0]["end_seconds"]) == (0.0, 4.0)
    assert (scenes[1]["start_seconds"], scenes[1]["end_seconds"]) == (4.0, 10.0)
    assert total == 10.0


def test_mixed_gap_fill_does_not_shift_aligned_scenes():
    plan = _plan([
        {"id": "a", "start_seconds": 0.0, "end_seconds": 5.0, "duration": "5s"},
        {"id": "b", "duration": "3s"},                      # window-less
        {"id": "c", "start_seconds": 8.0, "end_seconds": 12.0, "duration": "99s"},
    ])
    total, _ = annotate_scene_plan(plan, _outcomes(plan))
    scenes = plan["sections"]["S"]
    assert (scenes[1]["start_seconds"], scenes[1]["end_seconds"]) == (5.0, 8.0)
    # the aligned scene after the gap-fill is untouched
    assert (scenes[2]["start_seconds"], scenes[2]["end_seconds"]) == (8.0, 12.0)
    assert total == 12.0
