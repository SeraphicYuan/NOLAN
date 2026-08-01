from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from math_animation.compiler import ManimCompiler
from math_animation.contracts import (
    ActionCue,
    AnimatePointCloudTimeAction,
    AnimateTrackerAction,
    AnnotationVisualObject,
    ArrowVisualObject,
    AxesVisualObject,
    BeatSpec,
    BoundsPointAssertion,
    CameraAction,
    CameraPose,
    ConnectorVisualObject,
    CreateAction,
    ExpressionBinding,
    FadeInAction,
    FadeOutAction,
    FinitePointAssertion,
    FunctionGraphVisualObject,
    GroupVisualObject,
    MathTexVisualObject,
    MoveAction,
    NarrationInput,
    PointCloudState,
    PointCloudVisualObject,
    ProjectionAssertion,
    ProjectSpec,
    RectangleVisualObject,
    RequestSpec,
    SceneProgram,
    ScalarTrackerSpec,
    SetStyleAction,
    SpreadPointAssertion,
    TextVisualObject,
    TraceVisualObject,
    TrackedPointVisualObject,
    TransformMathAction,
    TransformPointCloudAction,
    UtteranceTiming,
    WordAnchor,
    WordTiming,
)
from math_animation.style import normalize_style


def point_cloud() -> PointCloudVisualObject:
    return PointCloudVisualObject(
        id="cloud.main",
        sample_count=100,
        sample_end=99,
        bindings=[
            ExpressionBinding(name="phase", expression="i / 10 + t"),
        ],
        states=[
            PointCloudState(
                id="flat",
                x="cos(phase)",
                y="0 * i",
                z="sin(phase)",
            ),
            PointCloudState(
                id="lifted",
                x="cos(phase)",
                y="0.5 * sin(phase)",
                z="sin(phase)",
            ),
        ],
        initial_state="flat",
        projection_assertions=[
            ProjectionAssertion(
                id="assert.xz",
                source_state="lifted",
                source_axes=("x", "z"),
                target_state="flat",
                target_axes=("x", "z"),
            )
        ],
    )


def scene_program() -> SceneProgram:
    return SceneProgram(
        scene_kind="3d",
        initial_camera=CameraPose(phi_degrees=90, theta_degrees=-90),
        objects=[
            MathTexVisualObject(
                id="formula",
                latex_parts=["E", "=", "mc^2"],
                part_roles=["primary", "foreground", "changing"],
                fixed_in_frame=True,
            ),
            point_cloud(),
        ],
        cues=[
            ActionCue(
                id="reveal",
                mode="parallel",
                actions=[
                    CreateAction(target="formula", run_time=0.5),
                    CreateAction(target="cloud.main", run_time=0.5),
                ],
            ),
            ActionCue(
                id="lift",
                mode="parallel",
                actions=[
                    TransformPointCloudAction(
                        target="cloud.main",
                        state="lifted",
                        run_time=1.5,
                    ),
                    CameraAction(
                        phi_degrees=65,
                        theta_degrees=-45,
                        run_time=1.5,
                    ),
                ],
            ),
        ],
    )


def test_scene_program_rejects_unsafe_vector_expression() -> None:
    with pytest.raises(ValidationError, match="approved math functions"):
        PointCloudVisualObject(
            id="cloud",
            sample_count=10,
            sample_end=9,
            states=[
                PointCloudState(
                    id="bad",
                    x="__import__('os')",
                    y="i",
                    z="i",
                )
            ],
            initial_state="bad",
        )


def test_scene_program_rejects_use_before_create() -> None:
    with pytest.raises(ValidationError, match="used before it is created"):
        SceneProgram(
            scene_kind="3d",
            objects=[point_cloud()],
            cues=[
                ActionCue(
                    id="bad",
                    actions=[
                        TransformPointCloudAction(
                            target="cloud.main",
                            state="lifted",
                        )
                    ],
                )
            ],
        )


def test_parallel_actions_must_share_run_time() -> None:
    with pytest.raises(ValidationError, match="same run_time"):
        ActionCue(
            id="bad-clock",
            mode="parallel",
            actions=[
                CameraAction(phi_degrees=60, run_time=1.0),
                CameraAction(theta_degrees=20, run_time=2.0),
            ],
        )


def test_scene_program_compiles_persistent_3d_actions(tmp_path: Path) -> None:
    project = ProjectSpec(
        project_id="scene-program",
        title="Scene program",
        request=RequestSpec(content="show a lifted point cloud"),
        beats=[
            BeatSpec(
                id="lift",
                title="Lift",
                learning_objective="Show depth.",
                duration_seconds=3.0,
                scene_program=scene_program(),
            )
        ],
    )
    result = ManimCompiler().compile(
        project,
        normalize_style(project.style),
        tmp_path,
    )
    source = result.source_files[0].read_text(encoding="utf-8")

    assert "class LiftScene(ThreeDScene)" in source
    assert "np.linspace(0.0, 99.0, 100" in source
    assert "self.add_fixed_in_frame_mobjects(obj_0)" in source
    assert "added_anims=[Transform(obj_1" in source
    assert "self.move_camera(" in source
    assert "np.allclose(" in source
    assert "projection assertion assert.xz failed" in source
    assert len(result.visual_ir_files) == 1
    assert result.visual_ir_files[0].is_file()


def test_scene_program_cue_uses_nolan_word_anchor(tmp_path: Path) -> None:
    program = SceneProgram(
        objects=[
            MathTexVisualObject(id="formula", latex_parts=["x", "=", "1"])
        ],
        cues=[
            ActionCue(
                id="word-synced",
                start_at=WordAnchor(
                    utterance_id="u1",
                    word_index=1,
                    edge="start",
                ),
                actions=[CreateAction(target="formula", run_time=0.5)],
            )
        ],
    )
    project = ProjectSpec(
        project_id="word-synced-scene",
        title="Word synced scene",
        request=RequestSpec(content="sync the equation"),
        narration=NarrationInput(
            provider="nolan",
            utterances=[
                UtteranceTiming(
                    id="u1",
                    text="Now reveal",
                    words=[
                        WordTiming(
                            word="Now",
                            start_seconds=2.0,
                            end_seconds=2.4,
                        ),
                        WordTiming(
                            word="reveal",
                            start_seconds=3.0,
                            end_seconds=3.5,
                        ),
                    ],
                )
            ],
        ),
        beats=[
            BeatSpec(
                id="equation",
                title="Equation",
                learning_objective="Use Nolan timing.",
                narration_utterance_id="u1",
                duration_seconds=2.0,
                scene_program=program,
            )
        ],
    )
    result = ManimCompiler().compile(
        project,
        normalize_style(project.style),
        tmp_path,
    )
    source = result.source_files[0].read_text(encoding="utf-8")

    assert "self.wait(1.0)" in source


def test_scene_program_compiles_dynamic_cloud_reentry_and_fit(
    tmp_path: Path,
) -> None:
    cloud = point_cloud().model_copy(
        update={
            "projection_assertions": [
                ProjectionAssertion(
                    id="assert.xz",
                    source_state="lifted",
                    source_axes=("x", "z"),
                    target_state="flat",
                    target_axes=("x", "z"),
                    time_values=[0.0, 2.0, 4.0],
                )
            ]
        }
    )
    program = SceneProgram(
        scene_kind="3d",
        objects=[
            MathTexVisualObject(
                id="formula",
                latex_parts=["x", "=", "1"],
                max_width=8.0,
            ),
            cloud,
        ],
        cues=[
            ActionCue(
                id="create",
                mode="parallel",
                actions=[
                    CreateAction(target="formula", run_time=0.5),
                    CreateAction(target="cloud.main", run_time=0.5),
                ],
            ),
            ActionCue(
                id="evolve",
                actions=[
                    AnimatePointCloudTimeAction(
                        target="cloud.main",
                        state="flat",
                        end_time=4.0,
                        run_time=1.0,
                    )
                ],
            ),
            ActionCue(
                id="leave",
                actions=[FadeOutAction(target="cloud.main", run_time=0.5)],
            ),
            ActionCue(
                id="return",
                actions=[FadeInAction(target="cloud.main", run_time=0.5)],
            ),
        ],
    )
    project = ProjectSpec(
        project_id="dynamic-scene",
        title="Dynamic scene",
        request=RequestSpec(content="stress dynamic point clouds"),
        beats=[
            BeatSpec(
                id="dynamic",
                title="Dynamic",
                learning_objective="Exercise reusable dynamic primitives.",
                duration_seconds=2.5,
                scene_program=program,
            )
        ],
    )
    result = ManimCompiler().compile(
        project,
        normalize_style(project.style),
        tmp_path,
    )
    source = result.source_files[0].read_text(encoding="utf-8")

    assert "ValueTracker(0.0)" in source
    assert "def obj_1_points_0(t):" in source
    assert "add_updater(obj_1_updater_" in source
    assert ".animate(rate_func=linear).set_value(4.0)" in source
    assert "clear_updaters()" in source
    assert "FadeOut(obj_1)" in source
    assert "FadeIn(obj_1)" in source
    assert source.count("np.allclose(") == 3
    assert "scale_to_fit_width(8.0)" in source


def test_common_geometry_layout_and_math_actions_compile(tmp_path: Path) -> None:
    program = SceneProgram(
        objects=[
            AxesVisualObject(id="axes", position=(-2.0, 0.0, 0.0)),
            FunctionGraphVisualObject(
                id="graph",
                axes="axes",
                expression="0.25*x**2",
                role="primary",
            ),
            RectangleVisualObject(
                id="box",
                width=2.0,
                height=1.0,
                position=(3.0, 0.0, 0.0),
                fill_role="fixed",
                fill_opacity=0.2,
            ),
            ArrowVisualObject(
                id="arrow",
                start=(1.0, 0.0, 0.0),
                end=(2.0, 0.0, 0.0),
            ),
            AnnotationVisualObject(
                id="note",
                text="local area",
                point=(3.0, 0.0, 0.0),
                label_position=(3.0, 1.5, 0.0),
            ),
            GroupVisualObject(
                id="diagram",
                members=["box", "arrow", "note"],
            ),
            MathTexVisualObject(
                id="equation",
                latex_parts=["3x+5", "=", "20"],
                fixed_in_frame=True,
                max_width=8.0,
            ),
        ],
        cues=[
            ActionCue(
                id="reveal",
                mode="parallel",
                actions=[
                    CreateAction(target="axes", run_time=0.5),
                    CreateAction(target="graph", run_time=0.5),
                    CreateAction(target="diagram", run_time=0.5),
                    CreateAction(target="equation", run_time=0.5),
                ],
            ),
            ActionCue(
                id="change",
                mode="parallel",
                actions=[
                    MoveAction(
                        target="diagram",
                        position=(2.5, -0.5, 0.0),
                        run_time=0.8,
                    ),
                    SetStyleAction(
                        target="graph",
                        role="changing",
                        opacity=0.7,
                        run_time=0.8,
                    ),
                    TransformMathAction(
                        target="equation",
                        latex_parts=["3x", "=", "15"],
                        part_roles=["primary", "foreground", "changing"],
                        run_time=0.8,
                    ),
                ],
            ),
        ],
    )
    project = ProjectSpec(
        project_id="common-grammar",
        title="Common grammar",
        request=RequestSpec(content="exercise common geometry"),
        beats=[
            BeatSpec(
                id="grammar",
                title="Grammar",
                learning_objective="Compile common persistent geometry.",
                duration_seconds=1.3,
                scene_program=program,
            )
        ],
    )
    result = ManimCompiler().compile(
        project,
        normalize_style(project.style),
        tmp_path,
    )
    source = result.source_files[0].read_text(encoding="utf-8")

    assert "Axes(" in source
    assert ".plot(lambda x:" in source
    assert "Rectangle(" in source
    assert "VGroup(obj_2, obj_3, obj_4)" in source
    assert "TransformMatchingTex(obj_6" in source
    assert ".animate.set_color(" in source
    assert "_assert_screen_safe(obj_6" in source


def test_point_cloud_numeric_assertions_compile(tmp_path: Path) -> None:
    cloud = point_cloud().model_copy(
        update={
            "numeric_assertions": [
                FinitePointAssertion(
                    id="finite",
                    state="lifted",
                    time_values=[0.0, 2.0],
                ),
                BoundsPointAssertion(
                    id="bounded",
                    state="lifted",
                    axis="x",
                    minimum=-2.0,
                    maximum=2.0,
                ),
                SpreadPointAssertion(
                    id="spread",
                    state="lifted",
                    axis="z",
                    minimum_span=1.0,
                ),
            ]
        }
    )
    program = SceneProgram(
        scene_kind="3d",
        objects=[cloud],
        cues=[
            ActionCue(
                id="create",
                actions=[CreateAction(target="cloud.main", run_time=0.5)],
            )
        ],
    )
    project = ProjectSpec(
        project_id="numeric-assertions",
        title="Numeric assertions",
        request=RequestSpec(content="validate coordinates"),
        beats=[
            BeatSpec(
                id="assertions",
                title="Assertions",
                learning_objective="Reject invalid point geometry.",
                duration_seconds=0.5,
                scene_program=program,
            )
        ],
    )
    result = ManimCompiler().compile(
        project,
        normalize_style(project.style),
        tmp_path,
    )
    source = result.source_files[0].read_text(encoding="utf-8")

    assert source.count("np.isfinite") == 2
    assert "np.min(" in source and "np.max(" in source
    assert "np.ptp(" in source


def test_text_rejects_accidental_literal_newline() -> None:
    with pytest.raises(ValidationError, match="literal backslash-n"):
        TextVisualObject(id="bad-text", text=r"first\nsecond")


def test_dependency_driven_points_connectors_and_trace_compile(
    tmp_path: Path,
) -> None:
    program = SceneProgram(
        trackers=[ScalarTrackerSpec(id="clock", initial_value=0.0)],
        objects=[
            TrackedPointVisualObject(
                id="origin",
                tracker="clock",
                x="0",
                y="0",
                assertion_time_values=[0.0, 6.28],
                maximum_absolute_coordinate=2.0,
            ),
            TrackedPointVisualObject(
                id="endpoint",
                tracker="clock",
                x="cos(t)",
                y="sin(t)",
                assertion_time_values=[0.0, 6.28],
                maximum_absolute_coordinate=2.0,
            ),
            ConnectorVisualObject(
                id="vector",
                start_object="origin",
                end_object="endpoint",
            ),
            TraceVisualObject(
                id="trace",
                target="endpoint",
                start_value=0.0,
                end_value=6.28,
            ),
        ],
        cues=[
            ActionCue(
                id="reveal",
                mode="parallel",
                actions=[
                    CreateAction(target="origin", run_time=0.5),
                    CreateAction(target="endpoint", run_time=0.5),
                    CreateAction(target="vector", run_time=0.5),
                ],
            ),
            ActionCue(
                id="turn",
                mode="parallel",
                actions=[
                    CreateAction(
                        target="trace",
                        animation="create",
                        run_time=1.5,
                    ),
                    AnimateTrackerAction(
                        tracker="clock",
                        end_value=6.28,
                        run_time=1.5,
                    )
                ],
            ),
        ],
    )
    project = ProjectSpec(
        project_id="tracked-chain",
        title="Tracked chain",
        request=RequestSpec(content="animate a connected vector"),
        beats=[
            BeatSpec(
                id="chain",
                title="Chain",
                learning_objective="Compile dependent motion.",
                duration_seconds=2.0,
                scene_program=program,
            )
        ],
    )
    result = ManimCompiler().compile(
        project,
        normalize_style(project.style),
        tmp_path,
    )
    source = result.source_files[0].read_text(encoding="utf-8")

    assert "tracker_0 = ValueTracker(0.0)" in source
    assert "put_start_and_end_on(" in source
    assert "ParametricFunction(obj_1_position" in source
    assert "tracker_0.animate(rate_func=linear).set_value(6.28)" in source
    assert "tracked point endpoint is non-finite" in source
