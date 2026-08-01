from __future__ import annotations

from pathlib import Path

from math_animation.bundle import write_json_atomic
from math_animation.cache import build_cache_report
from math_animation.compiler import ManimCompiler
from math_animation.contracts import (
    BeatSpec,
    ProjectSpec,
    RequestSpec,
    TitleCardBlock,
)
from math_animation.style import normalize_style
from tests.test_compiler import timed_project


def test_cache_report_matches_identical_compilation(tmp_path: Path) -> None:
    project = timed_project()
    style = normalize_style(project.style)
    first = tmp_path / "first"
    first.mkdir()
    first_compilation = ManimCompiler().compile(project, style, first)
    report = build_cache_report(
        project,
        style,
        first_compilation,
        first,
        tmp_path,
    )
    clip = first / first_compilation.timeline.clips[0].expected_media_path
    clip.parent.mkdir(parents=True, exist_ok=True)
    clip.write_bytes(b"synthetic cached video")
    write_json_atomic(first / "cache.json", report)

    second = tmp_path / "second"
    second.mkdir()
    second_compilation = ManimCompiler().compile(project, style, second)
    second_report = build_cache_report(
        project,
        style,
        second_compilation,
        second,
        tmp_path,
    )

    assert second_report["entries"][0]["status"] == "hit"
    assert second_report["entries"][0]["source_sha256"]


def test_cache_invalidates_only_changed_beat(tmp_path: Path) -> None:
    project = ProjectSpec(
        project_id="two-beat-cache",
        title="Two beats",
        request=RequestSpec(content="cache two beats"),
        beats=[
            BeatSpec(
                id="one",
                title="One",
                learning_objective="First.",
                duration_seconds=1.35,
                blocks=[
                    TitleCardBlock(id="one.title", title="One", run_time=1.0)
                ],
            ),
            BeatSpec(
                id="two",
                title="Two",
                learning_objective="Second.",
                duration_seconds=1.35,
                blocks=[
                    TitleCardBlock(id="two.title", title="Two", run_time=1.0)
                ],
            ),
        ],
    )
    style = normalize_style(project.style)
    first = tmp_path / "first"
    first.mkdir()
    first_compilation = ManimCompiler().compile(project, style, first)
    first_report = build_cache_report(
        project, style, first_compilation, first, tmp_path
    )
    for clip in first_compilation.timeline.clips:
        destination = first / clip.expected_media_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"cached")
    write_json_atomic(first / "cache.json", first_report)

    changed_beat = project.beats[1].model_copy(
        update={
            "blocks": [
                TitleCardBlock(
                    id="two.title",
                    title="Two, revised",
                    run_time=1.0,
                )
            ]
        }
    )
    changed = project.model_copy(
        update={"beats": [project.beats[0], changed_beat]}
    )
    second = tmp_path / "second"
    second.mkdir()
    second_compilation = ManimCompiler().compile(changed, style, second)
    report = build_cache_report(
        changed, style, second_compilation, second, tmp_path
    )

    assert [entry["status"] for entry in report["entries"]] == ["hit", "miss"]
