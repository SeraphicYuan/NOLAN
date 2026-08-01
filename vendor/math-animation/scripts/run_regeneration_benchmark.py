"""Render failures, regenerate typed beats, and verify the second attempt."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from math_animation.bundle import write_json_atomic
from math_animation.contracts import (
    ActionCue,
    BeatSpec,
    CreateAction,
    DotVisualObject,
    EquationRevealBlock,
    FormulaSpec,
    MathLedger,
    MoveAction,
    ProjectSpec,
    RenderSettings,
    RequestSpec,
    SceneProgram,
    StyleTemplateRef,
    TextVisualObject,
)
from math_animation.planning import PlanningBeatContext, VisualDecision
from math_animation.pipeline import AuthoringPipeline
from math_animation.regeneration import generate_regeneration_artifacts
from math_animation.repair import (
    Diagnostic,
    apply_repair_plan,
    build_repair_plan,
)
from math_animation.synthetic import generate_synthetic_narration
from math_animation.workflow import BoundedRepairWorkflow


ROOT = Path(__file__).resolve().parents[1]


class BenchmarkRegenerationProvider:
    provider_id = "synthetic-grounded-regenerator-v1"

    def __init__(self):
        self.calls: list[dict[str, object]] = []

    def decide(self, context: PlanningBeatContext) -> VisualDecision:
        decision = VisualDecision(
            template="equation_reveal",
            rationale=(
                "The rendered representation failed visual review; use the "
                "authored ledger formula through a deterministic equation block."
            ),
            confidence=0.99,
        )
        self.calls.append(
            {
                "context": context.model_dump(mode="json"),
                "decision": decision.model_dump(mode="json"),
            }
        )
        return decision

    def write_audit(self, destination: Path) -> None:
        write_json_atomic(
            destination,
            {
                "schema_version": "math-animation.synthetic-model-calls.v1",
                "provider_id": self.provider_id,
                "calls": self.calls,
            },
        )


def _fixture() -> ProjectSpec:
    utterances = [
        ("control.words", "Keep this control equation unchanged."),
        ("balance.words", "Show the authored balance equation clearly."),
        ("identity.words", "Show the authored trigonometric identity clearly."),
    ]
    narration = generate_synthetic_narration(
        utterances,
        ROOT / "examples" / "assets" / "synthetic_regeneration_benchmark.wav",
        word_seconds=0.25,
        word_gap_seconds=0.04,
        utterance_gap_seconds=0.4,
        trailing_silence_seconds=0.5,
    )
    durations = {
        utterance.id: (
            utterance.words[-1].end_seconds
            - utterance.words[0].start_seconds
        )
        for utterance in narration.utterances
    }
    return ProjectSpec(
        project_id="typed-regeneration-benchmark",
        title="Typed regeneration benchmark",
        request=RequestSpec(
            source_kind="script",
            content="\n\n".join(text for _, text in utterances),
            audience="math animation authors",
        ),
        math_ledger=MathLedger(
            formulas=[
                FormulaSpec(
                    id="control",
                    latex_parts=[r"x=x"],
                    plain_language="Control equation",
                ),
                FormulaSpec(
                    id="balance",
                    latex_parts=[r"3x+5=20"],
                    plain_language="Balance equation",
                ),
                FormulaSpec(
                    id="identity",
                    latex_parts=[r"\sin^2\theta+\cos^2\theta=1"],
                    plain_language="Trigonometric identity",
                ),
            ]
        ),
        narration=narration,
        style=StyleTemplateRef(
            template_id="regeneration-benchmark",
            raw={
                "colors": {
                    "background": "#0c1118",
                    "foreground": "#f4efe5",
                    "muted": "#91a0ad",
                },
                "semantic_colors": {
                    "primary": "#58b8aa",
                    "changing": "#f08064",
                    "fixed": "#77a6d8",
                },
                "typography": {
                    "font": "Avenir Next",
                    "title_size": 38,
                    "body_size": 24,
                    "math_size": 44,
                },
            },
        ),
        beats=[
            BeatSpec(
                id="control",
                title="Control equation",
                learning_objective="Keep an accepted beat unchanged.",
                narration_utterance_id="control.words",
                duration_seconds=durations["control.words"],
                blocks=[
                    EquationRevealBlock(
                        id="control.reveal",
                        formula_id="control",
                        latex_parts=[r"x=x"],
                        caption="Unchanged control",
                        run_time=0.55,
                        hold_seconds=durations["control.words"] - 0.9,
                    )
                ],
            ),
            BeatSpec(
                id="blank-balance",
                title="Balance equation",
                learning_objective="Show the authored balance equation.",
                narration_utterance_id="balance.words",
                duration_seconds=durations["balance.words"],
                scene_program=SceneProgram(
                    objects=[
                        DotVisualObject(
                            id="blank.dot",
                            radius=0.001,
                            role="foreground",
                        )
                    ],
                    cues=[
                        ActionCue(
                            id="blank.show",
                            actions=[
                                CreateAction(
                                    target="blank.dot",
                                    run_time=0.55,
                                )
                            ],
                        )
                    ],
                ),
            ),
            BeatSpec(
                id="frozen-identity",
                title="Trigonometric identity",
                learning_objective="Show the authored trigonometric identity.",
                narration_utterance_id="identity.words",
                duration_seconds=durations["identity.words"],
                scene_program=SceneProgram(
                    objects=[
                        TextVisualObject(
                            id="frozen.label",
                            text="Identity",
                            font_size=30,
                        )
                    ],
                    cues=[
                        ActionCue(
                            id="frozen.show",
                            actions=[
                                CreateAction(
                                    target="frozen.label",
                                    run_time=0.45,
                                )
                            ],
                        ),
                        ActionCue(
                            id="frozen.move",
                            actions=[
                                MoveAction(
                                    target="frozen.label",
                                    position=(0.0, 0.0, 0.0),
                                    run_time=0.8,
                                )
                            ],
                        ),
                    ],
                ),
            ),
        ],
        render=RenderSettings(
            quality="l",
            pixel_width=640,
            pixel_height=360,
            frame_rate=15,
            seed=83,
        ),
    )


def _contact_sheet(run_dir: Path, destination: Path) -> None:
    from PIL import Image, ImageDraw

    report = json.loads(
        (run_dir / "review" / "report.json").read_text(encoding="utf-8")
    )
    frames = []
    for clip in report["clips"]:
        stable = next(
            (
                frame
                for frame in clip["frames"]
                if frame.get("kind") == "stable"
            ),
            clip["frames"][0],
        )
        frames.append((clip["beat_id"], run_dir / stable["path"]))
    cell_width, cell_height = 360, 230
    sheet = Image.new(
        "RGB",
        (cell_width * len(frames), cell_height),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    for index, (beat_id, path) in enumerate(frames):
        with Image.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail((cell_width, cell_height - 24))
        x = index * cell_width
        sheet.paste(image, (x, 24))
        draw.text((x + 4, 4), beat_id, fill="black")
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("/tmp/math-animation-regeneration-benchmark"),
    )
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    metadata = json.loads(
        (ROOT / "benchmarks" / "regeneration_cases.json").read_text(
            encoding="utf-8"
        )
    )
    project = _fixture()
    provider = BenchmarkRegenerationProvider()
    if not args.render:
        diagnostics = [
            Diagnostic(
                id=f"diag-{case['id']}",
                code=case["injected_failure"],
                severity="warning",
                stage="review",
                message=f"Synthetic {case['injected_failure']} diagnostic.",
                beat_id=case["id"],
                suggested_repairs=["regenerate_beat"],
            )
            for case in metadata["cases"]
        ]
        plan = build_repair_plan(
            project,
            diagnostics,
            enable_regeneration=True,
        )
        regenerations = generate_regeneration_artifacts(
            project,
            plan,
            diagnostics,
            provider,
        )
        regenerated_project = apply_repair_plan(
            project,
            plan,
            regenerations=regenerations,
        )
        pipeline = AuthoringPipeline(runs_dir=args.runs_dir).run(
            regenerated_project
        )
        final_templates = {
            beat.id: (
                beat.blocks[0].type if beat.blocks else "scene_program"
            )
            for beat in regenerated_project.beats
        }
        cases = [
            {
                **case,
                "final_template": final_templates[case["id"]],
                "accepted": (
                    final_templates[case["id"]]
                    == case["expected_template"]
                ),
            }
            for case in metadata["cases"]
        ]
        report = {
            "schema_version": (
                "math-animation.regeneration-benchmark-report.v1"
            ),
            "status": (
                "passed"
                if all(case["accepted"] for case in cases)
                else "failed"
            ),
            "render_enabled": False,
            "provider_call_count": len(provider.calls),
            "custom_python_rate": 0.0,
            "compile_run_dir": str(pipeline.run_dir),
            "cases": cases,
        }
        examples_dir = ROOT / "examples" / "regeneration_benchmark"
        examples_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(
            examples_dir / "project.defective.json",
            project,
        )
        write_json_atomic(
            examples_dir / "project.regenerated.json",
            regenerated_project,
        )
        destination = (
            ROOT / "artifacts" / "regeneration_benchmark_compile_report.json"
        )
        write_json_atomic(destination, report)
        print(destination)
        print(pipeline.run_dir)
        return 0 if report["status"] == "passed" else 1
    workflow = BoundedRepairWorkflow(
        runs_dir=args.runs_dir,
        render_timeout_seconds=360,
        regeneration_provider=provider,
    )
    started = time.perf_counter()
    result = workflow.run(
        project,
        render=args.render,
        compose=args.render,
        use_cache=True,
    )
    elapsed = time.perf_counter() - started
    plans = [
        operation
        for plan in result.repair_plans
        for operation in plan.operations
        if operation.type == "regenerate_beat"
    ]
    regenerated = {
        operation.beat_id: operation for operation in plans
    }
    final_templates = {
        beat.id: (
            beat.blocks[0].type if beat.blocks else "scene_program"
        )
        for beat in result.project.beats
    }
    first_review_codes: dict[str, set[str]] = {}
    for path in sorted((result.session_dir / "diagnostics").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for diagnostic in payload["diagnostics"]:
            if diagnostic["stage"] != "review" or not diagnostic["beat_id"]:
                continue
            first_review_codes.setdefault(
                diagnostic["beat_id"],
                set(),
            ).add(diagnostic["code"])
    cases = []
    for case in metadata["cases"]:
        cases.append(
            {
                **case,
                "observed_diagnostics": sorted(
                    first_review_codes.get(case["id"], set())
                ),
                "regeneration_planned": case["id"] in regenerated,
                "final_template": final_templates[case["id"]],
                "accepted": (
                    case["injected_failure"]
                    in first_review_codes.get(case["id"], set())
                    and case["id"] in regenerated
                    and final_templates[case["id"]]
                    == case["expected_template"]
                ),
            }
        )
    renders = (
        result.pipeline_result.manifest.renders
        if result.pipeline_result is not None
        else []
    )
    cache_hits = sorted(
        item["beat_id"] for item in renders if item.get("cache_hit")
    )
    fresh = sorted(
        item["beat_id"] for item in renders if not item.get("cache_hit")
    )
    final_review = (
        json.loads(
            (
                result.pipeline_result.run_dir / "review" / "report.json"
            ).read_text(encoding="utf-8")
        )
        if args.render and result.pipeline_result is not None
        else None
    )
    status = (
        "passed"
        if all(case["accepted"] for case in cases)
        and result.status == "completed"
        and result.pipeline_attempts == (2 if args.render else 1)
        and len(provider.calls) == len(cases)
        and (
            not args.render
            or (
                cache_hits == [metadata["unaffected_control"]]
                and sorted(fresh) == sorted(case["id"] for case in cases)
                and final_review["status"] == "passed"
            )
        )
        else "failed"
    )
    report = {
        "schema_version": "math-animation.regeneration-benchmark-report.v1",
        "status": status,
        "render_enabled": args.render,
        "workflow_status": result.status,
        "pipeline_attempts": result.pipeline_attempts,
        "regeneration_provider": provider.provider_id,
        "provider_call_count": len(provider.calls),
        "custom_python_rate": 0.0,
        "elapsed_seconds": elapsed,
        "cache_hit_beat_ids_on_final_attempt": cache_hits,
        "fresh_render_beat_ids_on_final_attempt": fresh,
        "final_review_status": (
            final_review["status"] if final_review is not None else None
        ),
        "final_review_warning_count": (
            len(final_review["warnings"]) if final_review is not None else None
        ),
        "final_review_error_count": (
            len(final_review["errors"]) if final_review is not None else None
        ),
        "workflow_session_dir": str(result.session_dir),
        "final_run_dir": (
            str(result.pipeline_result.run_dir)
            if result.pipeline_result is not None
            else None
        ),
        "cases": cases,
    }
    examples_dir = ROOT / "examples" / "regeneration_benchmark"
    examples_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(examples_dir / "project.defective.json", project)
    write_json_atomic(examples_dir / "project.regenerated.json", result.project)
    destination = ROOT / "artifacts" / (
        "regeneration_benchmark_report.json"
        if args.render
        else "regeneration_benchmark_compile_report.json"
    )
    write_json_atomic(destination, report)
    if args.render and result.pipeline_result is not None:
        if result.pipeline_result.final_video is not None:
            shutil.copy2(
                result.pipeline_result.final_video,
                ROOT / "artifacts" / "regeneration_benchmark.mp4",
            )
        review_path = result.pipeline_result.run_dir / "review" / "report.json"
        shutil.copy2(
            review_path,
            ROOT / "artifacts" / "regeneration_benchmark_review.json",
        )
        prior_reviews = [
            path / "review" / "report.json"
            for path in sorted(
                (args.runs_dir / "pipeline-runs").glob(
                    "*-typed-regeneration-benchmark*"
                )
            )
            if path != result.pipeline_result.run_dir
            and (path / "review" / "report.json").is_file()
        ]
        if prior_reviews:
            shutil.copy2(
                prior_reviews[0],
                ROOT
                / "artifacts"
                / "regeneration_benchmark_first_review.json",
            )
        _contact_sheet(
            result.pipeline_result.run_dir,
            ROOT / "artifacts" / "regeneration_benchmark_keyframes.png",
        )
    print(destination)
    print(result.session_dir)
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
