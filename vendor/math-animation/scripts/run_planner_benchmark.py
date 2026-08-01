"""Score the constrained planner on diverse prompts it does not special-case."""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

from math_animation.bundle import write_json_atomic
from math_animation.contracts import RenderSettings, StyleTemplateRef
from math_animation.math_validation import validate_math
from math_animation.pipeline import AuthoringPipeline
from math_animation.planning import (
    ConstrainedPlanner,
    PlanningRequest,
)
from math_animation.synthetic import generate_synthetic_narration


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=ROOT / "benchmarks" / "unseen_prompts.json",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("/tmp/math-animation-planner-benchmark"),
    )
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.benchmark.read_text(encoding="utf-8"))
    cases = payload["cases"]
    narration = generate_synthetic_narration(
        [(case["id"], case["script"]) for case in cases],
        ROOT / "examples" / "assets" / "synthetic_planner_benchmark.wav",
        word_seconds=0.18,
        word_gap_seconds=0.045,
        utterance_gap_seconds=0.45,
        trailing_silence_seconds=0.5,
    )
    script = "\n\n".join(case["script"] for case in cases)
    planning = ConstrainedPlanner().plan(
        PlanningRequest(
            project_id="unseen-planner-benchmark",
            title="Constrained planner unseen-prompt benchmark",
            script=script,
            audience="mixed mathematical learners",
            narration=narration,
            style=StyleTemplateRef(
                template_id="planner-benchmark",
                raw={
                    "colors": {
                        "background": "#0d1218",
                        "foreground": "#f3efe6",
                        "muted": "#87919a",
                    },
                    "semantic_colors": {
                        "primary": "#5aa9a1",
                        "changing": "#e2765b",
                        "fixed": "#6e9ccc",
                    },
                    "typography": {
                        "font": "Avenir Next",
                        "title_size": 42,
                        "body_size": 23,
                        "math_size": 42,
                    },
                },
            ),
            render=RenderSettings(
                renderer="cairo",
                quality="l",
                pixel_width=640,
                pixel_height=360,
                frame_rate=15,
                seed=61,
            ),
        )
    )
    examples_dir = ROOT / "examples" / "planner_benchmark"
    examples_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(examples_dir / "planning.json", planning.artifact)
    write_json_atomic(examples_dir / "project.json", planning.project)

    expected_by_beat = {
        f"beat-{index:03d}": case
        for index, case in enumerate(cases, start=1)
    }
    selections = []
    for planned_beat in planning.artifact.beats:
        case = expected_by_beat[planned_beat.beat_id]
        selections.append(
            {
                "case_id": case["id"],
                "domain": case["domain"],
                "expected_template": case["expected_template"],
                "selected_template": planned_beat.selected_template,
                "selection_correct": (
                    planned_beat.selected_template
                    == case["expected_template"]
                ),
                "confidence": planned_beat.confidence,
                "unsupported_intents": planned_beat.unsupported_intents,
                "custom_python_requested": planned_beat.custom_python_requested,
            }
        )

    pipeline = AuthoringPipeline(
        runs_dir=args.runs_dir,
        render_timeout_seconds=360,
    )
    result = pipeline.run(
        planning.project,
        render=args.render,
        compose=args.render,
        use_cache=True,
    )
    rendered = {
        entry["beat_id"]
        for entry in result.manifest.renders
        if entry.get("exit_code") == 0
    }
    cache_reused_count = sum(
        bool(entry.get("cache_hit")) for entry in result.manifest.renders
    )
    cache_sources = sorted(
        {
            str(entry["reused_from"])
            for entry in result.manifest.renders
            if entry.get("cache_hit") and entry.get("reused_from")
        }
    )
    for index, selection in enumerate(selections, start=1):
        selection["compiled"] = True
        selection["rendered"] = (
            f"beat-{index:03d}" in rendered if args.render else None
        )
        selection["accepted"] = (
            selection["selection_correct"]
            and not selection["custom_python_requested"]
            and (
                selection["rendered"] is True
                if args.render
                else selection["compiled"]
            )
        )

    math_report = validate_math(planning.project)
    total = len(selections)
    correct = sum(item["selection_correct"] for item in selections)
    accepted = sum(item["accepted"] for item in selections)
    custom = sum(item["custom_python_requested"] for item in selections)
    report = {
        "schema_version": "math-animation.planner-benchmark-report.v1",
        "status": "passed" if accepted / total >= 0.8 else "failed",
        "case_count": total,
        "selection_accuracy": correct / total,
        "acceptance_rate": accepted / total,
        "custom_python_rate": custom / total,
        "math_validation_status": math_report.status,
        "render_enabled": args.render,
        "render_run_dir": str(result.run_dir),
        "fresh_render_count": (
            len(result.manifest.renders) - cache_reused_count
            if args.render
            else 0
        ),
        "cache_reused_count": cache_reused_count,
        "cache_reuse_sources": cache_sources,
        "template_counts": dict(
            sorted(Counter(item["selected_template"] for item in selections).items())
        ),
        "cases": selections,
    }
    if args.render and result.final_video is not None:
        from PIL import Image, ImageDraw

        video_artifact = ROOT / "artifacts" / "planner_benchmark.mp4"
        shutil.copy2(result.final_video, video_artifact)
        review = json.loads(
            (result.run_dir / "review" / "report.json").read_text(
                encoding="utf-8"
            )
        )
        stable_frames = []
        for clip in review["clips"]:
            frame = next(
                item
                for item in clip["frames"]
                if item.get("kind") == "stable"
            )
            stable_frames.append(
                (
                    clip["beat_id"],
                    result.run_dir / frame["path"],
                )
            )
        cell_width, cell_height = 320, 204
        columns = 4
        rows = (len(stable_frames) + columns - 1) // columns
        sheet = Image.new(
            "RGB",
            (columns * cell_width, rows * cell_height),
            "white",
        )
        draw = ImageDraw.Draw(sheet)
        for index, (beat_id, path) in enumerate(stable_frames):
            with Image.open(path) as source:
                frame = source.convert("RGB")
                frame.thumbnail((cell_width, cell_height - 24))
            x = (index % columns) * cell_width
            y = (index // columns) * cell_height
            sheet.paste(frame, (x, y + 24))
            case = expected_by_beat[beat_id]
            draw.text(
                (x + 5, y + 5),
                f"{case['domain']}: {case['expected_template']}",
                fill="black",
            )
        keyframes_artifact = (
            ROOT / "artifacts" / "planner_benchmark_keyframes.png"
        )
        sheet.save(keyframes_artifact)
        report["video_artifact"] = str(video_artifact)
        report["keyframes_artifact"] = str(keyframes_artifact)
    destination = ROOT / "artifacts" / (
        "planner_benchmark_report.json"
        if args.render
        else "planner_benchmark_compile_report.json"
    )
    write_json_atomic(destination, report)
    print(destination)
    if result.final_video is not None:
        print(result.final_video)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
