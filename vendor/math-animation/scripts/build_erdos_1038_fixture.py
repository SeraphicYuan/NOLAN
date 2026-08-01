"""Build a compact ERDŐS 1038 potential-landscape acceptance fixture."""

from __future__ import annotations

from math import sqrt
from pathlib import Path

from math_animation.bundle import write_json_atomic
from math_animation.contracts import (
    ActionCue,
    AxesVisualObject,
    BeatSpec,
    CameraPose,
    CreateAction,
    FormulaSpec,
    FunctionGraphVisualObject,
    IntervalVisualObject,
    MathClaim,
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
LOWER_LIMIT = 1.834430475762661
UPPER_WIDTH = 2 * sqrt(2)


def word(utterance: str, index: int) -> WordAnchor:
    return WordAnchor(utterance_id=utterance, word_index=index, edge="start")


def build() -> ProjectSpec:
    narration = generate_synthetic_narration(
        [
            (
                "landscape",
                "Treat the polynomial as a landscape and zero as the waterline "
                "the submerged footprint is where its size is below one",
            ),
            (
                "extremes",
                "The narrow width approaches one point eight three four but no "
                "finite polynomial attains it while endpoint roots attain two root two",
            ),
        ],
        ROOT / "examples" / "assets" / "synthetic_erdos_1038.wav",
        word_seconds=0.3,
        word_gap_seconds=0.065,
        utterance_gap_seconds=0.65,
        trailing_silence_seconds=0.65,
    )

    landscape_scene = SceneProgram(
        scene_kind="3d",
        initial_camera=CameraPose(
            phi_degrees=66,
            theta_degrees=-58,
            zoom=0.72,
        ),
        objects=[
            TextVisualObject(
                id="landscape.title",
                text="ERDŐS 1038 — the potential landscape",
                position=(0.0, 3.25, 0.0),
                fixed_in_frame=True,
                font_size=38,
                weight="bold",
                max_width=11.2,
            ),
            ParametricSurfaceVisualObject(
                id="landscape.surface",
                u_range=(-1.75, 1.75),
                v_range=(-2.2, 2.2),
                x="u",
                y="v",
                z="0.55*((u**2-1)**2-1)",
                resolution=(30, 12),
                role="changing",
                fill_opacity=0.52,
                stroke_width=0.3,
                maximum_absolute_coordinate=4.0,
            ),
            ParametricSurfaceVisualObject(
                id="landscape.zero",
                u_range=(-2.0, 2.0),
                v_range=(-2.35, 2.35),
                x="u",
                y="v",
                z="0",
                resolution=(8, 8),
                role="fixed",
                fill_opacity=0.2,
                stroke_width=0.2,
                maximum_absolute_coordinate=3.0,
            ),
            ParametricCurveVisualObject(
                id="landscape.left-boundary",
                parameter_range=(-2.2, 2.2, 0.04),
                x="-sqrt(2)",
                y="t",
                z="0",
                role="positive",
                stroke_width=7,
            ),
            ParametricCurveVisualObject(
                id="landscape.right-boundary",
                parameter_range=(-2.2, 2.2, 0.04),
                x="sqrt(2)",
                y="t",
                z="0",
                role="positive",
                stroke_width=7,
            ),
            MathTexVisualObject(
                id="landscape.formula",
                formula_id="formula.waterline",
                latex_parts=["|f_2(x)|-1", "=", "0"],
                part_roles=["changing", "foreground", "fixed"],
                position=(0.0, -3.25, 0.0),
                fixed_in_frame=True,
                font_size=41,
                max_width=7.0,
            ),
        ],
        cues=[
            ActionCue(
                id="landscape-title",
                start_at=word("landscape", 0),
                actions=[
                    CreateAction(target="landscape.title", run_time=0.45)
                ],
            ),
            ActionCue(
                id="landscape-sheet",
                start_at=word("landscape", 2),
                actions=[
                    CreateAction(target="landscape.surface", run_time=1.0)
                ],
            ),
            ActionCue(
                id="landscape-waterline",
                start_at=word("landscape", 7),
                actions=[
                    CreateAction(target="landscape.zero", run_time=0.75)
                ],
            ),
            ActionCue(
                id="landscape-boundaries",
                start_at=word("landscape", 12),
                mode="parallel",
                actions=[
                    CreateAction(
                        target="landscape.left-boundary",
                        run_time=0.75,
                    ),
                    CreateAction(
                        target="landscape.right-boundary",
                        run_time=0.75,
                    ),
                    CreateAction(target="landscape.formula", run_time=0.75),
                ],
            ),
        ],
    )

    extremes_scene = SceneProgram(
        objects=[
            TextVisualObject(
                id="extremes.title",
                text="Two different kinds of extreme",
                position=(0.0, 3.15, 0.0),
                font_size=41,
                weight="bold",
                max_width=11.0,
            ),
            AxesVisualObject(
                id="extremes.axes",
                x_range=(-1.8, 1.8, 0.5),
                y_range=(-1.1, 2.0, 0.5),
                x_length=7.0,
                y_length=3.4,
                position=(-2.6, 0.55, 0.0),
            ),
            FunctionGraphVisualObject(
                id="extremes.curve",
                axes="extremes.axes",
                expression="(x**2-1)**2-1",
                x_range=(-1.7, 1.7),
                role="changing",
                stroke_width=6,
            ),
            ScalarFieldFootprintVisualObject(
                id="extremes.footprint",
                expression="(x**2-1)**2-1",
                x_range=(-1.7, 1.7),
                y_range=(-0.16, 0.16),
                threshold=0.0,
                resolution=(85, 5),
                position=(-2.6, -1.55, 0.0),
                role="positive",
                fill_opacity=0.58,
                minimum_selected_fraction=0.7,
                maximum_selected_fraction=0.9,
            ),
            IntervalVisualObject(
                id="extremes.lower",
                start=-LOWER_LIMIT / 2,
                end=LOWER_LIMIT / 2,
                left_closed=False,
                right_closed=False,
                expected_width=LOWER_LIMIT,
                label="infimum 1.834430… — approached",
                position=(2.55, 0.65, 0.0),
                role="changing",
            ),
            IntervalVisualObject(
                id="extremes.upper",
                start=-sqrt(2),
                end=sqrt(2),
                left_closed=False,
                right_closed=False,
                expected_width=UPPER_WIDTH,
                label="maximum 2√2 — attained",
                position=(2.55, -1.35, 0.0),
                role="positive",
            ),
            MathTexVisualObject(
                id="extremes.width",
                formula_id="formula.upper-width",
                latex_parts=[
                    "(-\\sqrt2,\\sqrt2)",
                    "\\Longrightarrow",
                    "\\text{width}=2\\sqrt2",
                ],
                part_roles=["fixed", "foreground", "positive"],
                position=(2.7, 2.25, 0.0),
                font_size=34,
                max_width=5.0,
            ),
        ],
        cues=[
            ActionCue(
                id="extremes-title",
                start_at=word("extremes", 0),
                actions=[CreateAction(target="extremes.title", run_time=0.45)],
            ),
            ActionCue(
                id="extremes-curve",
                start_at=word("extremes", 2),
                mode="parallel",
                actions=[
                    CreateAction(target="extremes.axes", run_time=0.7),
                    CreateAction(target="extremes.curve", run_time=0.7),
                    CreateAction(
                        target="extremes.footprint",
                        animation="fade_in",
                        run_time=0.7,
                    ),
                ],
            ),
            ActionCue(
                id="extremes-lower",
                start_at=word("extremes", 6),
                actions=[
                    CreateAction(target="extremes.lower", run_time=0.7)
                ],
            ),
            ActionCue(
                id="extremes-upper",
                start_at=word("extremes", 14),
                mode="parallel",
                actions=[
                    CreateAction(target="extremes.upper", run_time=0.7),
                    CreateAction(target="extremes.width", run_time=0.7),
                ],
            ),
        ],
    )

    return ProjectSpec(
        project_id="erdos-1038-potential-landscape",
        title="ERDŐS 1038: the potential landscape",
        request=RequestSpec(
            content=(
                "Explain the polynomial footprint and distinguish its "
                "unattained lower limit from its attained upper width."
            ),
            audience="mathematically mature general audience",
            script_policy="locked",
            target_duration_seconds=16.5,
        ),
        narration=narration,
        math_ledger=MathLedger(
            claims=[
                MathClaim(
                    id="claim.lower-limit",
                    statement=(
                        "The width infimum is 1.834430475762661… and is not "
                        "attained by a finite polynomial."
                    ),
                    verification="verified",
                    evidence=["Math-To-Manim ERDŐS 1038 reference explainer"],
                ),
                MathClaim(
                    id="claim.upper-width",
                    statement=(
                        "For (x²−1)^m the subunit interval has width 2√2."
                    ),
                    verification="verified",
                    evidence=[
                        "|(x²−1)^m|<1 iff |x²−1|<1 iff |x|<√2"
                    ],
                ),
            ],
            formulas=[
                FormulaSpec(
                    id="formula.endpoint-family",
                    latex_parts=["f_m(x)", "=", "(x^2-1)^m"],
                    plain_language="Equal root piles at minus and plus one.",
                ),
                FormulaSpec(
                    id="formula.waterline",
                    latex_parts=["|f_2(x)|-1", "=", "0"],
                    plain_language=(
                        "The waterline marks where the polynomial has size one."
                    ),
                ),
                FormulaSpec(
                    id="formula.upper-width",
                    latex_parts=[
                        "(-\\sqrt2,\\sqrt2)",
                        "\\Longrightarrow",
                        "\\text{width}=2\\sqrt2",
                    ],
                    plain_language="The endpoint family attains width two root two.",
                ),
            ],
        ),
        style=StyleTemplateRef(
            template_id="erdos-copper-night",
            raw={
                "colors": {
                    "background": "#0c1015",
                    "foreground": "#f1ede4",
                    "muted": "#7f8a94",
                },
                "semantic_colors": {
                    "changing": "#d97855",
                    "fixed": "#5a8dbf",
                    "positive": "#66b985",
                },
                "typography": {
                    "font": "Avenir Next",
                    "title_size": 49,
                    "body_size": 23,
                    "math_size": 43,
                },
            },
        ),
        beats=[
            BeatSpec(
                id="landscape",
                title="The potential landscape",
                learning_objective="Interpret the subunit set as a footprint.",
                narration_utterance_id="landscape",
                duration_seconds=7.6,
                scene_program=landscape_scene,
            ),
            BeatSpec(
                id="extremes",
                title="Approached versus attained",
                learning_objective="Distinguish an infimum from a maximum.",
                narration_utterance_id="extremes",
                duration_seconds=8.2,
                scene_program=extremes_scene,
            ),
        ],
        render=RenderSettings(
            renderer="cairo",
            quality="l",
            pixel_width=1280,
            pixel_height=720,
            frame_rate=24,
            seed=41,
        ),
    )


if __name__ == "__main__":
    destination = ROOT / "examples" / "erdos_1038_featured_project.json"
    write_json_atomic(destination, build())
    print(destination)
