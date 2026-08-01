from pathlib import Path

import pytest
from pydantic import ValidationError

from math_animation.compiler import ManimCompiler
from math_animation.contracts import (
    ActionCue,
    BeatSpec,
    CreateAction,
    IntervalVisualObject,
    ParametricSurfaceVisualObject,
    ProjectSpec,
    RenderSettings,
    RequestSpec,
    ResponsiveVisualOverride,
    SceneProgram,
    TextVisualObject,
)
from math_animation.style import normalize_style


def _compile(project: ProjectSpec, tmp_path: Path) -> str:
    result = ManimCompiler().compile(
        project,
        normalize_style(project.style),
        tmp_path,
    )
    return result.source_files[0].read_text(encoding="utf-8")


def test_surface_emits_sampled_numeric_guards(tmp_path: Path) -> None:
    surface = ParametricSurfaceVisualObject(
        id="surface",
        u_range=(-1.0, 1.0),
        v_range=(-2.0, 2.0),
        x="u",
        y="v",
        z="u**2-v**2",
        maximum_absolute_coordinate=5.0,
    )
    project = ProjectSpec(
        project_id="surface-check",
        title="Surface",
        request=RequestSpec(content="surface"),
        beats=[
            BeatSpec(
                id="surface",
                title="Surface",
                learning_objective="test",
                duration_seconds=1.0,
                scene_program=SceneProgram(
                    scene_kind="3d",
                    objects=[surface],
                    cues=[
                        ActionCue(
                            id="show",
                            actions=[
                                CreateAction(target="surface", run_time=0.5)
                            ],
                        )
                    ],
                ),
            )
        ],
    )
    source = _compile(project, tmp_path)
    assert "Surface(lambda u, v:" in source
    assert "surface surface contains non-finite samples" in source
    assert "surface surface exceeds coordinate bound" in source


def test_interval_width_mismatch_fails_before_render() -> None:
    with pytest.raises(ValidationError, match="interval width"):
        IntervalVisualObject(
            id="bad",
            start=-1,
            end=1,
            expected_width=3,
        )


def test_portrait_camera_and_authored_override_compile(tmp_path: Path) -> None:
    title = TextVisualObject(
        id="title",
        text="Responsive",
        position=(5.0, 2.0, 0.0),
        responsive={
            "portrait": ResponsiveVisualOverride(
                position=(0.0, 2.0, 0.0),
                scale=0.6,
            )
        },
    )
    project = ProjectSpec(
        project_id="portrait",
        title="Portrait",
        request=RequestSpec(content="portrait"),
        beats=[
            BeatSpec(
                id="portrait",
                title="Portrait",
                learning_objective="test",
                duration_seconds=1.0,
                scene_program=SceneProgram(
                    objects=[title],
                    cues=[
                        ActionCue(
                            id="show",
                            actions=[CreateAction(target="title", run_time=0.5)],
                        )
                    ],
                ),
            )
        ],
        render=RenderSettings(pixel_width=540, pixel_height=960),
    )
    source = _compile(project, tmp_path)
    assert "config.frame_width = 4.5" in source
    assert "move_to(np.array([0.0, 2.0, 0.0]" in source
    assert "obj_0.scale(0.6)" in source
