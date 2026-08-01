from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from math_animation.bundle import sha256_json
from math_animation.contracts import (
    ActionCue,
    AnimateTrackerAction,
    AssetRef,
    BeatSpec,
    CreateAction,
    EquationRevealBlock,
    FormulaSpec,
    MathLedger,
    ProjectSpec,
    RenderSettings,
    RequestSpec,
    ResponsiveVisualOverride,
    ScalarTrackerSpec,
    SceneProgram,
    TextVisualObject,
    TitleCardBlock,
    TraceVisualObject,
    TrackedPointVisualObject,
)
from math_animation.repair import (
    analyze_project,
    apply_repair_plan,
    build_repair_plan,
)

# Only the two control-plane tests below need LangGraph (the optional
# `.[workflow]` extra). The four typed-repair PLANNER tests must keep running in
# an env without it — skipping the whole module to satisfy two imports would
# silently drop two thirds of this file's coverage in NOLAN's pipeline env.
requires_langgraph = pytest.mark.skipif(
    importlib.util.find_spec("langgraph") is None,
    reason="needs the optional [workflow] extra (pip install -e '.[workflow]')",
)


def _project(beat: BeatSpec, *, project_id: str = "repair") -> ProjectSpec:
    return ProjectSpec(
        project_id=project_id,
        title="Repair",
        request=RequestSpec(content="Repair fixture"),
        beats=[beat],
        render=RenderSettings(
            quality="l",
            pixel_width=360,
            pixel_height=640,
            frame_rate=12,
        ),
    )


def test_long_generated_caption_is_shortened_with_scoped_diff() -> None:
    beat = BeatSpec(
        id="caption",
        title="Caption",
        learning_objective="Test caption fitting.",
        duration_seconds=2.0,
        blocks=[
            EquationRevealBlock(
                id="reveal",
                latex_parts=["x=1"],
                caption="This generated caption is intentionally much too long "
                "for a reusable portrait layout and should be shortened safely.",
                run_time=0.5,
                hold_seconds=1.15,
            )
        ],
    )
    project = _project(beat)
    diagnostics = analyze_project(project)
    assert {item.code for item in diagnostics} == {"text_overflow"}
    plan = build_repair_plan(project, diagnostics)
    assert plan.affected_beat_ids == ["caption"]
    assert [item.type for item in plan.operations] == [
        "shorten_generated_caption"
    ]
    repaired = apply_repair_plan(project, plan)
    assert len(repaired.beats[0].blocks[0].caption or "") <= 72
    assert sha256_json(repaired) != sha256_json(project)


def test_portrait_font_position_and_density_repairs_are_typed() -> None:
    point = TrackedPointVisualObject(
        id="point",
        tracker="time",
        x="cos(t)",
        y="sin(t)",
        responsive={
            "portrait": ResponsiveVisualOverride(
                position=(99.0, 99.0, 0.0),
                scale=0.1,
            )
        },
    )
    title = TextVisualObject(
        id="title",
        text="A very long generated explanatory sentence without a width bound "
        "that cannot safely fit a narrow portrait output.",
        responsive={"portrait": ResponsiveVisualOverride(scale=0.1)},
    )
    trace = TraceVisualObject(
        id="trace",
        target="point",
        end_value=2.0,
        sample_count=3000,
    )
    project = _project(
        BeatSpec(
            id="scene",
            title="Scene",
            learning_objective="Test responsive repair.",
            duration_seconds=3.0,
            scene_program=SceneProgram(
                trackers=[ScalarTrackerSpec(id="time")],
                objects=[title, point, trace],
                cues=[
                    ActionCue(
                        id="show",
                        actions=[
                            CreateAction(target="title", run_time=0.3),
                            CreateAction(target="point", run_time=0.3),
                            CreateAction(target="trace", run_time=0.3),
                        ],
                    ),
                    ActionCue(
                        id="move",
                        actions=[
                            AnimateTrackerAction(
                                tracker="time",
                                end_value=0.0,
                                run_time=0.5,
                            )
                        ],
                    ),
                ],
            ),
        )
    )
    diagnostics = analyze_project(project)
    assert {
        "illegible_type",
        "text_overflow",
        "excessive_density",
        "frozen_motion",
    }.issubset({item.code for item in diagnostics})
    plan = build_repair_plan(project, diagnostics)
    assert {
        "set_responsive_scale",
        "set_max_width",
        "reposition_object",
        "reduce_density",
        "set_tracker_end_value",
    }.issubset({item.type for item in plan.operations})
    repaired = apply_repair_plan(project, plan)
    assert analyze_project(repaired) == []


def test_overlong_scene_timing_is_scaled_to_available_duration() -> None:
    project = _project(
        BeatSpec(
            id="timing",
            title="Timing",
            learning_objective="Test timing repair.",
            duration_seconds=1.0,
            scene_program=SceneProgram(
                objects=[TextVisualObject(id="title", text="Timing")],
                cues=[
                    ActionCue(
                        id="show",
                        actions=[
                            CreateAction(target="title", run_time=2.0)
                        ],
                    )
                ],
            ),
        )
    )
    diagnostics = analyze_project(project)
    assert [item.code for item in diagnostics] == ["timing_drift"]
    repaired = apply_repair_plan(
        project,
        build_repair_plan(project, diagnostics),
    )
    assert analyze_project(repaired) == []


def test_wrong_title_fallback_swaps_to_ledger_locked_equation() -> None:
    project = _project(
        BeatSpec(
            id="template",
            title="Balance",
            learning_objective="Connect the narration to its authored formula.",
            duration_seconds=2.0,
            blocks=[
                TitleCardBlock(
                    id="fallback",
                    title="Balance",
                    run_time=0.5,
                    hold_seconds=1.15,
                )
            ],
        )
    ).model_copy(
        update={
            "math_ledger": MathLedger(
                formulas=[
                    FormulaSpec(
                        id="balance",
                        latex_parts=["3x+5=20"],
                        plain_language="Balance equation",
                    )
                ]
            )
        }
    )
    diagnostics = analyze_project(project)
    assert [item.code for item in diagnostics] == ["template_mismatch"]
    repaired = apply_repair_plan(
        project,
        build_repair_plan(project, diagnostics),
    )
    block = repaired.beats[0].blocks[0]
    assert block.type == "equation_reveal"
    assert block.formula_id == "balance"


@requires_langgraph
def test_langgraph_workflow_repairs_then_compiles(tmp_path: Path) -> None:
    project = _project(
        BeatSpec(
            id="caption",
            title="This generated title is intentionally far too long for the "
            "portrait title-card template and must be shortened before compile.",
            learning_objective="Test the graph.",
            duration_seconds=2.0,
            blocks=[
                TitleCardBlock(
                    id="title",
                    title="This generated title is intentionally far too long "
                    "for the portrait title-card template and must be shortened.",
                    run_time=0.5,
                    hold_seconds=1.15,
                )
            ],
        ),
        project_id="graph-repair",
    )
    from math_animation.workflow import BoundedRepairWorkflow

    result = BoundedRepairWorkflow(runs_dir=tmp_path).run(project)
    assert result.status == "completed"
    assert result.pipeline_attempts == 1
    assert len(result.repair_plans) == 1
    assert result.repair_plans[0].affected_beat_ids == ["caption"]
    assert (result.session_dir / "repairs" / "01.diff.json").is_file()


@requires_langgraph
def test_missing_input_is_refused_without_pipeline_attempt(tmp_path: Path) -> None:
    project = _project(
        BeatSpec(
            id="missing",
            title="Missing",
            learning_objective="Test refusal.",
            duration_seconds=1.0,
            blocks=[
                TitleCardBlock(
                    id="title",
                    title="Missing",
                    run_time=0.4,
                    hold_seconds=0.25,
                )
            ],
        ),
        project_id="refusal",
    ).model_copy(
        update={
            "assets": [
                AssetRef(
                    id="missing",
                    path=str(tmp_path / "does-not-exist.png"),
                    media_type="image",
                )
            ]
        }
    )
    from math_animation.workflow import BoundedRepairWorkflow

    result = BoundedRepairWorkflow(runs_dir=tmp_path).run(project)
    assert result.status == "refused"
    assert result.pipeline_attempts == 0
    assert [item.code for item in result.diagnostics] == ["missing_input"]
