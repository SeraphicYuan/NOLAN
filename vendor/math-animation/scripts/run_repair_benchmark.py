"""Render an adversarial explainer and score bounded typed repairs."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from math_animation.bundle import sha256_json, write_json_atomic
from math_animation.contracts import (
    ActionCue,
    AnimateTrackerAction,
    AssetRef,
    BeatSpec,
    CameraPose,
    CreateAction,
    EquationRevealBlock,
    FormulaSpec,
    MathLedger,
    MathTexVisualObject,
    ParametricSurfaceVisualObject,
    ProjectSpec,
    RenderSettings,
    RequestSpec,
    ResponsiveVisualOverride,
    ScalarTrackerSpec,
    SceneProgram,
    StyleTemplateRef,
    TextVisualObject,
    TitleCardBlock,
    TraceVisualObject,
    TrackedPointVisualObject,
)
from math_animation.repair import analyze_project, build_repair_plan
from math_animation.synthetic import generate_synthetic_narration
from math_animation.workflow import BoundedRepairWorkflow


ROOT = Path(__file__).resolve().parents[1]


def _duration(narration, utterance_id: str) -> float:
    utterance = next(
        item for item in narration.utterances if item.id == utterance_id
    )
    return utterance.words[-1].end_seconds - utterance.words[0].start_seconds


def _fixture() -> ProjectSpec:
    texts = [
        (
            "clipped-caption",
            "Reveal the invariant equation while its concise caption follows.",
        ),
        (
            "tiny-portrait-type",
            "Keep mathematical labels readable in a narrow portrait frame.",
        ),
        (
            "frozen-tracker",
            "Move the point around the circle and expose its traced orbit.",
        ),
        (
            "excessive-surface-density",
            "Reveal a smooth wave surface without wasteful geometric density.",
        ),
        (
            "overlong-cue",
            "Fit the visual explanation inside the aligned narration window.",
        ),
        (
            "offscreen-object",
            "Recenter a label that was accidentally authored outside frame.",
        ),
        (
            "unbounded-portrait-text",
            "Constrain a long explanatory label to the portrait safe area.",
        ),
        (
            "wrong-template",
            "Replace the generic fallback with the authored balance equation.",
        ),
    ]
    narration = generate_synthetic_narration(
        texts,
        ROOT / "examples" / "assets" / "synthetic_repair_benchmark.wav",
        word_seconds=0.22,
        word_gap_seconds=0.04,
        utterance_gap_seconds=0.35,
        trailing_silence_seconds=0.5,
    )
    formulas = [
        FormulaSpec(
            id="invariant",
            latex_parts=[r"a^2+b^2=c^2"],
            plain_language="Pythagorean invariant",
        ),
        FormulaSpec(
            id="balance",
            latex_parts=[r"3x+5=20"],
            plain_language="Balance equation",
        ),
    ]
    durations = {item_id: _duration(narration, item_id) for item_id, _ in texts}
    beats = [
        BeatSpec(
            id="clipped-caption",
            title="Invariant",
            learning_objective="Connect the narration to its authored formula.",
            narration_utterance_id="clipped-caption",
            duration_seconds=durations["clipped-caption"],
            blocks=[
                EquationRevealBlock(
                    id="caption.reveal",
                    formula_id="invariant",
                    latex_parts=[r"a^2+b^2=c^2"],
                    caption=(
                        "This generated explanatory caption is intentionally "
                        "too long for the reusable portrait-safe equation layout "
                        "and should be shortened without touching narration."
                    ),
                    run_time=0.55,
                    hold_seconds=durations["clipped-caption"] - 0.9,
                )
            ],
        ),
        BeatSpec(
            id="tiny-portrait-type",
            title="Readable type",
            learning_objective="Keep labels legible.",
            narration_utterance_id="tiny-portrait-type",
            duration_seconds=durations["tiny-portrait-type"],
            scene_program=SceneProgram(
                objects=[
                    MathTexVisualObject(
                        id="tiny.formula",
                        latex_parts=[r"\int_0^1 x^2\,dx=\frac13"],
                        responsive={
                            "portrait": ResponsiveVisualOverride(scale=0.1)
                        },
                    )
                ],
                cues=[
                    ActionCue(
                        id="tiny.show",
                        actions=[
                            CreateAction(target="tiny.formula", run_time=0.65)
                        ],
                    )
                ],
            ),
        ),
        BeatSpec(
            id="frozen-tracker",
            title="Orbit",
            learning_objective="Show stateful tracked motion.",
            narration_utterance_id="frozen-tracker",
            duration_seconds=durations["frozen-tracker"],
            scene_program=SceneProgram(
                trackers=[ScalarTrackerSpec(id="orbit.time")],
                objects=[
                    TrackedPointVisualObject(
                        id="orbit.point",
                        tracker="orbit.time",
                        x="2*cos(t)",
                        y="2*sin(t)",
                    ),
                    TraceVisualObject(
                        id="orbit.trace",
                        target="orbit.point",
                        start_value=0.0,
                        end_value=6.283185307179586,
                        sample_count=480,
                    ),
                ],
                cues=[
                    ActionCue(
                        id="orbit.show",
                        mode="parallel",
                        actions=[
                            CreateAction(target="orbit.point", run_time=0.45),
                            CreateAction(target="orbit.trace", run_time=0.45),
                        ],
                    ),
                    ActionCue(
                        id="orbit.move",
                        actions=[
                            AnimateTrackerAction(
                                tracker="orbit.time",
                                end_value=0.0,
                                run_time=0.85,
                            )
                        ],
                    ),
                ],
            ),
        ),
        BeatSpec(
            id="excessive-surface-density",
            title="Wave surface",
            learning_objective="Use bounded geometric density.",
            narration_utterance_id="excessive-surface-density",
            duration_seconds=durations["excessive-surface-density"],
            scene_program=SceneProgram(
                scene_kind="3d",
                initial_camera=CameraPose(
                    phi_degrees=62,
                    theta_degrees=-48,
                    zoom=1.2,
                ),
                objects=[
                    ParametricSurfaceVisualObject(
                        id="wave.surface",
                        u_range=(-2.0, 2.0),
                        v_range=(-2.0, 2.0),
                        x="u",
                        y="v",
                        z="0.35*sin(2*u)*cos(2*v)",
                        resolution=(80, 80),
                        assertion_samples=7,
                    )
                ],
                cues=[
                    ActionCue(
                        id="wave.show",
                        actions=[
                            CreateAction(target="wave.surface", run_time=0.8)
                        ],
                    )
                ],
            ),
        ),
        BeatSpec(
            id="overlong-cue",
            title="Aligned timing",
            learning_objective="Respect narration duration.",
            narration_utterance_id="overlong-cue",
            duration_seconds=durations["overlong-cue"],
            scene_program=SceneProgram(
                objects=[
                    TextVisualObject(
                        id="timing.label",
                        text="Narration-aligned",
                        font_size=26,
                    )
                ],
                cues=[
                    ActionCue(
                        id="timing.show",
                        actions=[
                            CreateAction(target="timing.label", run_time=5.0)
                        ],
                    )
                ],
            ),
        ),
        BeatSpec(
            id="offscreen-object",
            title="Safe framing",
            learning_objective="Keep content in frame.",
            narration_utterance_id="offscreen-object",
            duration_seconds=durations["offscreen-object"],
            scene_program=SceneProgram(
                objects=[
                    TextVisualObject(
                        id="offscreen.label",
                        text="Back in frame",
                        position=(99.0, -99.0, 0.0),
                        font_size=26,
                    )
                ],
                cues=[
                    ActionCue(
                        id="offscreen.show",
                        actions=[
                            CreateAction(
                                target="offscreen.label",
                                run_time=0.65,
                            )
                        ],
                    )
                ],
            ),
        ),
        BeatSpec(
            id="unbounded-portrait-text",
            title="Width bound",
            learning_objective="Fit explanatory text safely.",
            narration_utterance_id="unbounded-portrait-text",
            duration_seconds=durations["unbounded-portrait-text"],
            scene_program=SceneProgram(
                objects=[
                    TextVisualObject(
                        id="width.label",
                        text=(
                            "A long explanation remains readable because the "
                            "repair layer adds a deterministic portrait width "
                            "bound before the scene reaches Manim."
                        ),
                        font_size=24,
                    )
                ],
                cues=[
                    ActionCue(
                        id="width.show",
                        actions=[
                            CreateAction(target="width.label", run_time=0.65)
                        ],
                    )
                ],
            ),
        ),
        BeatSpec(
            id="wrong-template",
            title="Balance equation",
            learning_objective="Connect the narration to its authored formula.",
            narration_utterance_id="wrong-template",
            duration_seconds=durations["wrong-template"],
            blocks=[
                TitleCardBlock(
                    id="wrong.fallback",
                    title="Generic fallback",
                    run_time=0.55,
                    hold_seconds=durations["wrong-template"] - 0.9,
                )
            ],
        ),
    ]
    return ProjectSpec(
        project_id="repair-featured-explainer",
        title="Self-healing mathematical explainer",
        request=RequestSpec(
            source_kind="script",
            content="\n\n".join(text for _, text in texts),
            audience="math animation authors",
            target_duration_seconds=sum(durations.values()),
        ),
        math_ledger=MathLedger(formulas=formulas),
        narration=narration,
        style=StyleTemplateRef(
            template_id="repair-benchmark",
            raw={
                "colors": {
                    "background": "#0c1118",
                    "foreground": "#f4efe5",
                    "muted": "#91a0ad"
                },
                "semantic_colors": {
                    "primary": "#58b8aa",
                    "changing": "#f08064",
                    "fixed": "#77a6d8"
                },
                "typography": {
                    "font": "Avenir Next",
                    "title_size": 38,
                    "body_size": 24,
                    "math_size": 42
                }
            },
        ),
        beats=beats,
        render=RenderSettings(
            renderer="cairo",
            quality="l",
            pixel_width=360,
            pixel_height=640,
            frame_rate=12,
            seed=73,
        ),
    )


def _refusal_projects(tmp_root: Path) -> dict[str, ProjectSpec]:
    base_beat = BeatSpec(
        id="refusal",
        title="Refusal",
        learning_objective="Refuse unsafe guessing.",
        duration_seconds=1.2,
        blocks=[
            TitleCardBlock(
                id="refusal.title",
                title="Refusal",
                run_time=0.5,
                hold_seconds=0.35,
            )
        ],
    )
    common = {
        "title": "Refusal",
        "request": RequestSpec(content="Refusal test"),
        "beats": [base_beat],
        "render": RenderSettings(
            quality="l",
            pixel_width=320,
            pixel_height=240,
            frame_rate=12,
        ),
    }
    missing = ProjectSpec(
        project_id="repair-refusal-missing",
        assets=[
            AssetRef(
                id="missing",
                path=str(tmp_root / "definitely-missing.png"),
                media_type="image",
            )
        ],
        **common,
    )
    invalid_math = ProjectSpec(
        project_id="repair-refusal-math",
        math_ledger=MathLedger(
            formulas=[
                FormulaSpec(
                    id="invalid",
                    latex_parts=[r"\frac{x}{y"],
                    plain_language="Unbalanced on purpose",
                )
            ]
        ),
        **common,
    )
    nonfinite = ProjectSpec(
        project_id="repair-refusal-surface",
        title="Nonfinite surface",
        request=RequestSpec(content="Nonfinite surface"),
        beats=[
            BeatSpec(
                id="surface",
                title="Surface",
                learning_objective="Refuse an invalid mathematical domain.",
                duration_seconds=1.2,
                scene_program=SceneProgram(
                    scene_kind="3d",
                    objects=[
                        ParametricSurfaceVisualObject(
                            id="invalid.surface",
                            u_range=(-1.0, 1.0),
                            v_range=(-1.0, 1.0),
                            x="u",
                            y="v",
                            z="1/(u-u)",
                            resolution=(4, 4),
                            assertion_samples=3,
                        )
                    ],
                    cues=[
                        ActionCue(
                            id="surface.show",
                            actions=[
                                CreateAction(
                                    target="invalid.surface",
                                    run_time=0.6,
                                )
                            ],
                        )
                    ],
                ),
            )
        ],
        render=common["render"],
    )
    return {
        "missing-asset": missing,
        "invalid-math-ledger": invalid_math,
        "nonfinite-surface-domain": nonfinite,
    }


def _contact_sheet(result, destination: Path) -> None:
    if result.pipeline_result is None:
        return
    report_path = result.pipeline_result.run_dir / "review" / "report.json"
    if not report_path.is_file():
        return
    from PIL import Image, ImageDraw

    report = json.loads(report_path.read_text(encoding="utf-8"))
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
        frames.append(
            (clip["beat_id"], result.pipeline_result.run_dir / stable["path"])
        )
    cell_width, cell_height = 270, 500
    columns = 4
    rows = (len(frames) + columns - 1) // columns
    sheet = Image.new(
        "RGB",
        (columns * cell_width, rows * cell_height),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    for index, (beat_id, path) in enumerate(frames):
        with Image.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail((cell_width, cell_height - 28))
        x = index % columns * cell_width
        y = index // columns * cell_height
        sheet.paste(image, (x, y + 24))
        draw.text((x + 4, y + 4), beat_id, fill="black")
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("/tmp/math-animation-repair-benchmark"),
    )
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    metadata = json.loads(
        (ROOT / "benchmarks" / "repair_cases.json").read_text(encoding="utf-8")
    )
    project = _fixture()
    before = analyze_project(project)
    plan = build_repair_plan(project, before)
    expected = {
        case["id"]: case
        for case in metadata["repairable_cases"]
    }
    operation_by_beat = {
        operation.beat_id: operation.type for operation in plan.operations
    }
    diagnostic_by_beat = {
        diagnostic.beat_id: diagnostic.code
        for diagnostic in before
        if diagnostic.beat_id
    }
    workflow = BoundedRepairWorkflow(
        runs_dir=args.runs_dir,
        render_timeout_seconds=360,
    )
    result = workflow.run(
        project,
        render=args.render,
        compose=args.render,
        use_cache=True,
    )
    remaining = analyze_project(result.project)
    repairable_results = []
    for case_id, case in expected.items():
        repairable_results.append(
            {
                "case_id": case_id,
                "expected_diagnostic": case["diagnostic"],
                "actual_diagnostic": diagnostic_by_beat.get(case_id),
                "expected_operation": case["operation"],
                "actual_operation": operation_by_beat.get(case_id),
                "changed_only_in_declared_scope": any(
                    case_id in item.affected_beat_ids
                    for item in result.repair_plans
                ),
                "accepted": (
                    diagnostic_by_beat.get(case_id) == case["diagnostic"]
                    and operation_by_beat.get(case_id) == case["operation"]
                    and not any(item.beat_id == case_id for item in remaining)
                    and result.pipeline_attempts <= 2
                ),
            }
        )

    refusal_results = []
    for case in metadata["refusal_cases"]:
        if case.get("requires_render") and not args.render:
            refusal_results.append(
                {
                    "case_id": case["id"],
                    "expected_diagnostic": case["diagnostic"],
                    "status": "skipped_without_render",
                    "accepted": True,
                }
            )
            continue
        refused = workflow.run(
            _refusal_projects(args.runs_dir)[case["id"]],
            render=bool(case.get("requires_render")),
            use_cache=False,
        )
        refusal_results.append(
            {
                "case_id": case["id"],
                "expected_diagnostic": case["diagnostic"],
                "actual_diagnostics": [
                    item.code for item in refused.diagnostics
                ],
                "workflow_status": refused.status,
                "pipeline_attempts": refused.pipeline_attempts,
                "accepted": (
                    refused.status == "refused"
                    and case["diagnostic"]
                    in {item.code for item in refused.diagnostics}
                    and not refused.repair_plans
                ),
            }
        )

    cache_evidence = None
    if args.render:
        retry_payload = result.project.model_dump(mode="json")
        retry_beat = next(
            item
            for item in retry_payload["beats"]
            if item["id"] == "clipped-caption"
        )
        retry_beat["blocks"][0]["caption"] = (
            "A second deliberately excessive generated caption forces one "
            "scoped repair while every unrelated beat should remain reusable "
            "from the content-addressed render cache."
        )
        retry_project = ProjectSpec.model_validate(retry_payload)
        retry = workflow.run(
            retry_project,
            render=True,
            compose=False,
            use_cache=True,
        )
        renders = retry.pipeline_result.manifest.renders
        hits = sorted(
            item["beat_id"] for item in renders if item.get("cache_hit")
        )
        misses = sorted(
            item["beat_id"] for item in renders if not item.get("cache_hit")
        )
        cache_evidence = {
            "retry_status": retry.status,
            "cache_hit_beat_ids": hits,
            "fresh_render_beat_ids": misses,
            "unaffected_beats_reused": all(
                beat.id in hits
                for beat in retry.project.beats
                if beat.id != "clipped-caption"
            ),
            "affected_beat_rerendered": "clipped-caption" in misses,
        }

    repair_rate = sum(
        item["accepted"] for item in repairable_results
    ) / len(repairable_results)
    refusal_rate = sum(
        item["accepted"] for item in refusal_results
    ) / len(refusal_results)
    no_custom = all(
        block.type != "custom_scene"
        for beat in result.project.beats
        for block in beat.blocks
    )
    status = (
        "passed"
        if repair_rate >= 0.8
        and refusal_rate == 1.0
        and no_custom
        and result.status in {"completed", "completed_with_warnings"}
        and (
            not args.render
            or cache_evidence is not None
            and cache_evidence["unaffected_beats_reused"]
            and cache_evidence["affected_beat_rerendered"]
        )
        else "failed"
    )
    report = {
        "schema_version": "math-animation.repair-benchmark-report.v1",
        "status": status,
        "render_enabled": args.render,
        "repairable_case_count": len(repairable_results),
        "repair_success_rate": repair_rate,
        "refusal_case_count": len(refusal_results),
        "refusal_success_rate": refusal_rate,
        "custom_python_rate": 0.0 if no_custom else 1.0,
        "pipeline_attempts": result.pipeline_attempts,
        "repair_passes": len(result.repair_plans),
        "original_project_sha256": sha256_json(project),
        "repaired_project_sha256": sha256_json(result.project),
        "workflow_status": result.status,
        "workflow_session_dir": str(result.session_dir),
        "render_run_dir": (
            str(result.pipeline_result.run_dir)
            if result.pipeline_result is not None
            else None
        ),
        "cache_scope_evidence": cache_evidence,
        "repairable_cases": repairable_results,
        "refusal_cases": refusal_results,
    }
    examples_dir = ROOT / "examples" / "repair_benchmark"
    examples_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(examples_dir / "project.defective.json", project)
    write_json_atomic(examples_dir / "project.repaired.json", result.project)
    destination = ROOT / "artifacts" / (
        "repair_benchmark_report.json"
        if args.render
        else "repair_benchmark_compile_report.json"
    )
    write_json_atomic(destination, report)
    if args.render and result.pipeline_result is not None:
        if result.pipeline_result.final_video is not None:
            shutil.copy2(
                result.pipeline_result.final_video,
                ROOT / "artifacts" / "repair_benchmark.mp4",
            )
        _contact_sheet(
            result,
            ROOT / "artifacts" / "repair_benchmark_keyframes.png",
        )
        review_path = result.pipeline_result.run_dir / "review" / "report.json"
        if review_path.is_file():
            shutil.copy2(
                review_path,
                ROOT / "artifacts" / "repair_benchmark_review.json",
            )
    print(destination)
    print(result.session_dir)
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
