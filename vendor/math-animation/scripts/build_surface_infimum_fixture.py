"""Build a narrated surface, sublevel-set, and infimum acceptance fixture."""

from __future__ import annotations

from pathlib import Path

from math_animation.bundle import write_json_atomic
from math_animation.contracts import (
    ActionCue,
    AxesVisualObject,
    BeatSpec,
    CameraAction,
    CameraPose,
    CreateAction,
    FormulaSpec,
    FunctionGraphVisualObject,
    IntervalVisualObject,
    MathLedger,
    MathTexVisualObject,
    ParametricCurveVisualObject,
    ParametricSurfaceVisualObject,
    ProjectSpec,
    RenderSettings,
    RequestSpec,
    ScalarFieldFootprintVisualObject,
    SceneProgram,
    StyleTemplateRef,
    TextVisualObject,
    WordAnchor,
)
from math_animation.synthetic import generate_synthetic_narration


ROOT = Path(__file__).resolve().parents[1]


def word(utterance: str, index: int) -> WordAnchor:
    return WordAnchor(utterance_id=utterance, word_index=index, edge="start")


def build() -> ProjectSpec:
    narration = generate_synthetic_narration(
        [
            (
                "surface",
                "The bowl crosses the zero plane on a unit circle and its "
                "nonpositive footprint is the disk inside",
            ),
            (
                "infimum",
                "One over x approaches zero forever but never reaches zero "
                "so the infimum is not attained",
            ),
        ],
        ROOT / "examples" / "assets" / "synthetic_surface_infimum.wav",
        word_seconds=0.31,
        word_gap_seconds=0.07,
        utterance_gap_seconds=0.6,
        trailing_silence_seconds=0.6,
    )

    surface_scene = SceneProgram(
        scene_kind="3d",
        initial_camera=CameraPose(
            phi_degrees=64,
            theta_degrees=-52,
            zoom=0.72,
        ),
        objects=[
            TextVisualObject(
                id="surface.title",
                text="A zero level set cuts a surface",
                position=(0.0, 3.25, 0.0),
                fixed_in_frame=True,
                font_size=38,
                weight="bold",
                max_width=10.5,
            ),
            ParametricSurfaceVisualObject(
                id="surface.bowl",
                u_range=(-1.7, 1.7),
                v_range=(-1.7, 1.7),
                x="u",
                y="v",
                z="0.6*(u**2 + v**2 - 1)",
                resolution=(22, 22),
                role="changing",
                fill_opacity=0.48,
                stroke_width=0.35,
                maximum_absolute_coordinate=4.0,
            ),
            ParametricSurfaceVisualObject(
                id="surface.zero-plane",
                u_range=(-2.2, 2.2),
                v_range=(-2.2, 2.2),
                x="u",
                y="v",
                z="0",
                resolution=(8, 8),
                role="fixed",
                fill_opacity=0.22,
                stroke_width=0.25,
                maximum_absolute_coordinate=3.0,
            ),
            ParametricCurveVisualObject(
                id="surface.intersection",
                parameter_range=(0.0, 6.283185307179586, 0.035),
                x="cos(t)",
                y="sin(t)",
                z="0",
                role="positive",
                stroke_width=7,
            ),
            MathTexVisualObject(
                id="surface.formula",
                formula_id="formula.level-set",
                latex_parts=["x^2+y^2-1", "=", "0"],
                part_roles=["changing", "foreground", "fixed"],
                position=(0.0, -3.25, 0.0),
                fixed_in_frame=True,
                font_size=42,
                max_width=7.0,
            ),
        ],
        cues=[
            ActionCue(
                id="surface-title",
                start_at=word("surface", 0),
                actions=[CreateAction(target="surface.title", run_time=0.45)],
            ),
            ActionCue(
                id="surface-bowl",
                start_at=word("surface", 2),
                actions=[CreateAction(target="surface.bowl", run_time=1.1)],
            ),
            ActionCue(
                id="surface-plane",
                start_at=word("surface", 5),
                actions=[
                    CreateAction(target="surface.zero-plane", run_time=0.85)
                ],
            ),
            ActionCue(
                id="surface-intersection",
                start_at=word("surface", 8),
                mode="parallel",
                actions=[
                    CreateAction(target="surface.intersection", run_time=0.8),
                    CreateAction(target="surface.formula", run_time=0.8),
                    CameraAction(
                        theta_degrees=-28,
                        zoom=0.92,
                        run_time=0.8,
                    ),
                ],
            ),
        ],
    )

    infimum_scene = SceneProgram(
        objects=[
            TextVisualObject(
                id="infimum.title",
                text="Approached is not the same as attained",
                position=(0.0, 3.15, 0.0),
                font_size=40,
                weight="bold",
                max_width=11.0,
            ),
            AxesVisualObject(
                id="infimum.axes",
                x_range=(1.0, 10.0, 1.0),
                y_range=(0.0, 1.1, 0.2),
                x_length=7.2,
                y_length=3.5,
                position=(-1.3, 0.4, 0.0),
            ),
            FunctionGraphVisualObject(
                id="infimum.curve",
                axes="infimum.axes",
                expression="1/x",
                x_range=(1.0, 10.0),
                role="changing",
                stroke_width=6,
            ),
            IntervalVisualObject(
                id="infimum.range",
                start=0.0,
                end=1.0,
                left_closed=False,
                right_closed=True,
                expected_width=1.0,
                label="range: (0, 1]",
                position=(3.6, -1.85, 0.0),
                role="positive",
            ),
            MathTexVisualObject(
                id="infimum.formula",
                formula_id="formula.infimum",
                latex_parts=[
                    "\\inf_{x\\ge 1}\\frac{1}{x}",
                    "=",
                    "0",
                    "\\quad(\\text{not attained})",
                ],
                part_roles=[
                    "changing",
                    "foreground",
                    "fixed",
                    "muted",
                ],
                position=(3.65, 0.35, 0.0),
                font_size=37,
                max_width=5.0,
            ),
            ScalarFieldFootprintVisualObject(
                id="surface.footprint",
                expression="x**2 + y**2 - 1",
                x_range=(-1.5, 1.5),
                y_range=(-1.5, 1.5),
                threshold=0.0,
                resolution=(25, 25),
                position=(-4.8, -2.15, 0.0),
                role="positive",
                fill_opacity=0.3,
                minimum_selected_fraction=0.25,
                maximum_selected_fraction=0.5,
            ),
        ],
        cues=[
            ActionCue(
                id="infimum-title",
                start_at=word("infimum", 0),
                actions=[CreateAction(target="infimum.title", run_time=0.45)],
            ),
            ActionCue(
                id="infimum-graph",
                start_at=word("infimum", 2),
                mode="parallel",
                actions=[
                    CreateAction(target="infimum.axes", run_time=0.7),
                    CreateAction(target="infimum.curve", run_time=0.7),
                ],
            ),
            ActionCue(
                id="infimum-range",
                start_at=word("infimum", 5),
                mode="parallel",
                actions=[
                    CreateAction(target="infimum.range", run_time=0.7),
                    CreateAction(target="infimum.formula", run_time=0.7),
                ],
            ),
            ActionCue(
                id="sublevel-footprint",
                start_at=word("infimum", 11),
                actions=[
                    CreateAction(
                        target="surface.footprint",
                        animation="fade_in",
                        run_time=0.55,
                    )
                ],
            ),
        ],
    )

    return ProjectSpec(
        project_id="surface-level-set-infimum",
        title="Surfaces, sublevel sets, and unattained infima",
        request=RequestSpec(
            content=(
                "Show a surface meeting the zero plane, its sublevel footprint, "
                "and contrast a minimum with an unattained infimum."
            ),
            audience="multivariable calculus students",
            script_policy="locked",
            target_duration_seconds=13.7,
        ),
        narration=narration,
        math_ledger=MathLedger(
            formulas=[
                FormulaSpec(
                    id="formula.level-set",
                    latex_parts=["x^2+y^2-1", "=", "0"],
                    plain_language="The zero level set is the unit circle.",
                ),
                FormulaSpec(
                    id="formula.infimum",
                    latex_parts=[
                        "\\inf_{x\\ge 1}\\frac{1}{x}",
                        "=",
                        "0",
                        "\\quad(\\text{not attained})",
                    ],
                    plain_language="The values approach zero without equaling it.",
                ),
            ]
        ),
        style=StyleTemplateRef(
            template_id="surface-night",
            raw={
                "colors": {
                    "background": "#0b1016",
                    "foreground": "#f4f0e8",
                    "muted": "#82909c",
                },
                "semantic_colors": {
                    "changing": "#e46f51",
                    "fixed": "#5e91c9",
                    "positive": "#62bc83",
                },
                "typography": {
                    "font": "Avenir Next",
                    "title_size": 50,
                    "body_size": 25,
                    "math_size": 46,
                },
            },
        ),
        beats=[
            BeatSpec(
                id="surface",
                title="The zero plane",
                learning_objective="Relate a level set to a surface intersection.",
                narration_utterance_id="surface",
                duration_seconds=6.9,
                scene_program=surface_scene,
            ),
            BeatSpec(
                id="infimum",
                title="Approach without attainment",
                learning_objective="Distinguish a minimum from an infimum.",
                narration_utterance_id="infimum",
                duration_seconds=6.2,
                scene_program=infimum_scene,
            ),
        ],
        render=RenderSettings(
            renderer="cairo",
            quality="l",
            pixel_width=1280,
            pixel_height=720,
            frame_rate=24,
            seed=37,
        ),
    )


if __name__ == "__main__":
    destination = ROOT / "examples" / "surface_infimum_featured_project.json"
    write_json_atomic(destination, build())
    print(destination)
