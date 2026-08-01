"""Compile or render the expanded templates and test pedagogy sensitivity."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from math_animation.bundle import write_json_atomic
from math_animation.contracts import (
    ActionCue,
    BeatSpec,
    CreateAction,
    NarrationInput,
    ProjectSpec,
    RenderSettings,
    RequestSpec,
    SceneProgram,
    StyleTemplateRef,
    TextVisualObject,
    UtteranceTiming,
)
from math_animation.expanded_planning import ExpandedPlanner
from math_animation.pedagogy import evaluate_pedagogy
from math_animation.pipeline import AuthoringPipeline
from math_animation.planning import PlanningRequest
from math_animation.synthetic import generate_synthetic_narration


ROOT = Path(__file__).resolve().parents[1]


def _risk_fixture() -> ProjectSpec:
    objects = [
        TextVisualObject(
            id=f"risk-label-{index}",
            text="A long competing annotation " * 3,
        )
        for index in range(10)
    ]
    return ProjectSpec(
        project_id="expanded-pedagogy-risk",
        title="Synthetic pedagogy sensitivity case",
        request=RequestSpec(content="Graph the function clearly."),
        narration=NarrationInput(
            utterances=[
                UtteranceTiming(
                    id="risk.words",
                    text="Graph the function clearly.",
                )
            ]
        ),
        beats=[
            BeatSpec(
                id="risk",
                title="Graph the function",
                learning_objective="Graph the curve and explain its shape.",
                narration_utterance_id="risk.words",
                duration_seconds=5,
                scene_program=SceneProgram(
                    objects=objects,
                    cues=[
                        ActionCue(
                            id="risk.show-all",
                            mode="parallel",
                            actions=[
                                CreateAction(target=item.id, run_time=0.2)
                                for item in objects
                            ],
                        )
                    ],
                ),
            )
        ],
        render=RenderSettings(
            quality="l",
            pixel_width=640,
            pixel_height=360,
            frame_rate=15,
            seed=107,
        ),
    )


def _contact_sheet(run_dir: Path, destination: Path) -> None:
    from PIL import Image, ImageDraw

    review = json.loads(
        (run_dir / "review" / "report.json").read_text(encoding="utf-8")
    )
    frames = []
    for clip in review["clips"]:
        stable_frames = [
            item
            for item in clip["frames"]
            if item.get("kind") == "stable"
        ]
        for frame in stable_frames or [clip["frames"][0]]:
            frames.append(
                (
                    clip["beat_id"],
                    frame["id"],
                    run_dir / frame["path"],
                )
            )
    cell_width, cell_height = 420, 266
    columns = 2
    rows = (len(frames) + columns - 1) // columns
    sheet = Image.new(
        "RGB",
        (cell_width * columns, cell_height * rows),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    for index, (beat_id, frame_id, path) in enumerate(frames):
        with Image.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail((cell_width, cell_height - 30))
        x = (index % columns) * cell_width
        y = (index // columns) * cell_height
        sheet.paste(image, (x, y + 30))
        draw.text(
            (x + 6, y + 6),
            f"{beat_id}: {frame_id}",
            fill="black",
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("/tmp/math-animation-expanded-pedagogy"),
    )
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()

    utterances = [
        (
            "derive.words",
            "Derive the solution step by step. Start with three x plus five "
            "equals twenty, then isolate three x, and finally obtain x equals "
            "five.",
        ),
        (
            "compare.words",
            "Compare y equals x squared versus y equals two x squared. The "
            "second parabola is vertically stretched, so it grows faster away "
            "from the origin.",
        ),
    ]
    narration = generate_synthetic_narration(
        utterances,
        ROOT / "examples" / "assets" / "synthetic_expanded_pedagogy.wav",
        word_seconds=0.19,
        word_gap_seconds=0.035,
        utterance_gap_seconds=0.45,
        trailing_silence_seconds=0.5,
    )
    script = (
        "Derive the solution step by step: $3x+5=20$, then $3x=15$, "
        "and finally $x=5$.\n\n"
        "Compare $y=x^2$ versus $y=2x^2$ and explain the difference."
    )
    planning = ExpandedPlanner().plan(
        PlanningRequest(
            project_id="expanded-pedagogy-benchmark",
            title="Expanded planning and pedagogy benchmark",
            script=script,
            audience="introductory algebra learners",
            narration=narration,
            style=StyleTemplateRef(
                template_id="expanded-pedagogy",
                raw={
                    "colors": {
                        "background": "#0b1220",
                        "foreground": "#f5f1e8",
                        "muted": "#8f9aaa",
                    },
                    "semantic_colors": {
                        "primary": "#55c2b5",
                        "changing": "#f08a66",
                        "fixed": "#72a7e8",
                    },
                    "typography": {
                        "font": "Avenir Next",
                        "title_size": 40,
                        "body_size": 23,
                        "math_size": 46,
                    },
                },
            ),
            render=RenderSettings(
                renderer="cairo",
                quality="l",
                pixel_width=640,
                pixel_height=360,
                frame_rate=15,
                seed=107,
            ),
        )
    )
    pedagogy = evaluate_pedagogy(planning.project)
    risk = evaluate_pedagogy(_risk_fixture())
    examples_dir = ROOT / "examples" / "expanded_pedagogy"
    examples_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(examples_dir / "expanded-planning.json", planning.artifact)
    write_json_atomic(examples_dir / "project.json", planning.project)
    write_json_atomic(examples_dir / "pedagogy.json", pedagogy)
    write_json_atomic(examples_dir / "synthetic-risk.pedagogy.json", risk)

    result = AuthoringPipeline(
        runs_dir=args.runs_dir,
        render_timeout_seconds=360,
    ).run(
        planning.project,
        render=args.render,
        compose=args.render,
        minimum_pedagogy_score=0.9,
        use_cache=True,
    )
    review = None
    performance = json.loads(
        (result.run_dir / "performance.json").read_text(encoding="utf-8")
    )
    if args.render:
        review = json.loads(
            (result.run_dir / "review" / "report.json").read_text(
                encoding="utf-8"
            )
        )
    templates = [
        item.selected_template for item in planning.artifact.beats
    ]
    passed = (
        templates == ["equation_sequence", "concept_comparison"]
        and pedagogy.status == "passed"
        and pedagogy.total_score >= 0.9
        and risk.status in {"needs_review", "failed"}
        and risk.total_score < 0.78
        and (review is None or review["status"] == "passed")
    )
    report = {
        "schema_version": (
            "math-animation.expanded-pedagogy-benchmark-report.v1"
        ),
        "status": "passed" if passed else "failed",
        "render_enabled": args.render,
        "run_dir": str(result.run_dir),
        "selected_templates": templates,
        "custom_python_rate": 0.0,
        "pedagogy_status": pedagogy.status,
        "pedagogy_score": pedagogy.total_score,
        "dimension_scores": {
            item.dimension: item.score for item in pedagogy.dimensions
        },
        "synthetic_risk_status": risk.status,
        "synthetic_risk_score": risk.total_score,
        "synthetic_risk_findings": [
            item.id for item in risk.findings
        ],
        "review_status": review["status"] if review else None,
        "review_warning_count": len(review["warnings"]) if review else None,
        "review_error_count": len(review["errors"]) if review else None,
        "fresh_render_count": sum(
            not bool(item.get("cache_hit"))
            for item in result.manifest.renders
        ),
        "cache_reused_count": sum(
            bool(item.get("cache_hit"))
            for item in result.manifest.renders
        ),
        "performance": performance,
        "final_video_media": (
            review.get("final_video_media") if review else None
        ),
    }
    if args.render and result.final_video is not None:
        video = ROOT / "artifacts" / "expanded_pedagogy_benchmark.mp4"
        keyframes = (
            ROOT / "artifacts" / "expanded_pedagogy_benchmark_keyframes.png"
        )
        review_artifact = (
            ROOT / "artifacts" / "expanded_pedagogy_benchmark_review.json"
        )
        shutil.copy2(result.final_video, video)
        _contact_sheet(result.run_dir, keyframes)
        write_json_atomic(review_artifact, review)
        report.update(
            {
                "video_artifact": str(video),
                "keyframes_artifact": str(keyframes),
                "review_artifact": str(review_artifact),
            }
        )
    destination = ROOT / "artifacts" / (
        "expanded_pedagogy_benchmark_report.json"
        if args.render
        else "expanded_pedagogy_benchmark_compile_report.json"
    )
    write_json_atomic(destination, report)
    print(destination)
    print(result.run_dir)
    if result.final_video:
        print(result.final_video)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
