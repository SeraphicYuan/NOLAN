"""Render one colliding and one corrected comparison to test visual review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from math_animation.bundle import write_json_atomic
from math_animation.contracts import (
    ActionCue,
    BeatSpec,
    CreateAction,
    MathTexVisualObject,
    ProjectSpec,
    RenderSettings,
    RequestSpec,
    SceneProgram,
    StyleTemplateRef,
)
from math_animation.pipeline import AuthoringPipeline


ROOT = Path(__file__).resolve().parents[1]


def _beat(beat_id: str, separation: float) -> BeatSpec:
    objects = [
        MathTexVisualObject(
            id=f"{beat_id}.left",
            latex_parts=[r"y=x^2-6x+5"],
            position=(-separation, 0.0, 0.0),
            font_size=68,
            max_width=5.0,
        ),
        MathTexVisualObject(
            id=f"{beat_id}.right",
            latex_parts=[r"y=(x-3)^2-4"],
            position=(separation, 0.0, 0.0),
            font_size=68,
            max_width=5.0,
        ),
    ]
    return BeatSpec(
        id=beat_id,
        title=beat_id,
        learning_objective="Compare two equivalent formulas.",
        duration_seconds=1.8,
        scene_program=SceneProgram(
            objects=objects,
            cues=[
                ActionCue(
                    id=f"{beat_id}.show",
                    mode="parallel",
                    actions=[
                        CreateAction(
                            target=item.id,
                            animation="write",
                            run_time=0.55,
                        )
                        for item in objects
                    ],
                )
            ],
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("/tmp/math-animation-layout-collision-smoke"),
    )
    args = parser.parse_args()
    project = ProjectSpec(
        project_id="layout-collision-smoke",
        title="Rendered layout collision smoke",
        request=RequestSpec(content="Compare equivalent quadratic forms."),
        style=StyleTemplateRef(
            template_id="collision-smoke",
            raw={
                "colors": {
                    "background": "#08111f",
                    "foreground": "#f5f0e6",
                    "muted": "#99a9b8",
                },
                "typography": {"math_size": 68},
            },
        ),
        beats=[
            _beat("colliding", 2.5),
            _beat("separated", 3.4),
        ],
        render=RenderSettings(
            quality="l",
            pixel_width=640,
            pixel_height=360,
            frame_rate=12,
            seed=157,
        ),
    )
    result = AuthoringPipeline(
        runs_dir=args.runs_dir,
        render_timeout_seconds=360,
    ).run(
        project,
        render=True,
        compose=False,
        use_cache=False,
    )
    review = json.loads(
        (result.run_dir / "review" / "report.json").read_text(encoding="utf-8")
    )
    collision_diagnostics = [
        item
        for item in review["diagnostics"]
        if item["evidence"].get("kind") == "visual_collision"
    ]
    caught_colliding = any(
        item["beat_id"] == "colliding"
        and set(item["evidence"]["object_ids"])
        == {"colliding.left", "colliding.right"}
        for item in collision_diagnostics
    )
    false_positive = any(
        item["beat_id"] == "separated"
        for item in collision_diagnostics
    )
    passed = caught_colliding and not false_positive
    report = {
        "schema_version": "math-animation.layout-collision-smoke.v1",
        "status": "passed" if passed else "failed",
        "run_dir": str(result.run_dir),
        "caught_colliding_beat": caught_colliding,
        "separated_false_positive": false_positive,
        "collision_diagnostics": collision_diagnostics,
        "review_status": review["status"],
    }
    destination = ROOT / "artifacts" / "layout_collision_smoke_report.json"
    write_json_atomic(destination, report)
    print(destination)
    print(result.run_dir)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
