"""Nolan-neutral author-stage handoff artifact."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from math_animation.bundle import write_json_atomic
from math_animation.contracts import ProjectSpec, TimelineArtifact
from math_animation.style import StyleTokens


def write_nolan_handoff(
    project: ProjectSpec,
    style: StyleTokens,
    timeline: TimelineArtifact,
    run_dir: Path,
) -> Path:
    """Write the complete data Nolan needs without exposing Manim internals."""

    payload: dict[str, Any] = {
        "schema_version": "math-animation.nolan-handoff.v1",
        "project_id": project.project_id,
        "duration_seconds": timeline.duration_seconds,
        "frame_rate": timeline.frame_rate,
        "canvas": {
            "width": timeline.pixel_width,
            "height": timeline.pixel_height,
            "transparent": project.render.transparent,
        },
        "narration": {
            "provider": project.narration.provider,
            "audio_path": project.narration.audio_path,
            "utterances": [
                utterance.model_dump(mode="json")
                for utterance in project.narration.utterances
            ],
        },
        "style": {
            "template_id": project.style.template_id,
            "version": project.style.version,
            "provider": project.style.provider,
            "normalized": style.model_dump(mode="json"),
            "raw": project.style.raw,
        },
        "clips": [
            {
                "id": clip.beat_id,
                "kind": "manim",
                "start_seconds": clip.start_seconds,
                "end_seconds": clip.end_seconds,
                "duration_seconds": clip.duration_seconds,
                "media_path": clip.expected_media_path,
                "alpha": clip.alpha,
                "source_contract": f"visual_ir/{clip.beat_id}.scene.json",
            }
            for clip in timeline.clips
        ],
        "assets": [asset.model_dump(mode="json") for asset in project.assets],
    }
    destination = run_dir / "nolan_handoff.json"
    write_json_atomic(destination, payload)
    return destination
