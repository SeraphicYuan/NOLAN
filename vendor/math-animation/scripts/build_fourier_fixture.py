"""Build the dependency-driven Fourier epicycle acceptance film."""

from __future__ import annotations

from pathlib import Path

from math_animation.bundle import write_json_atomic
from math_animation.contracts import (
    ActionCue,
    AnimateTrackerAction,
    BeatSpec,
    ConnectorVisualObject,
    CreateAction,
    FormulaSpec,
    MathLedger,
    MathTexVisualObject,
    OrbitCircleVisualObject,
    ProjectSpec,
    RenderSettings,
    RequestSpec,
    ScalarTrackerSpec,
    SceneProgram,
    StyleTemplateRef,
    TextVisualObject,
    TraceVisualObject,
    TrackedPointVisualObject,
    WordAnchor,
)
from math_animation.synthetic import generate_synthetic_narration


ROOT = Path(__file__).resolve().parents[1]


def word(index: int) -> WordAnchor:
    return WordAnchor(utterance_id="f1", word_index=index)


def build() -> ProjectSpec:
    narration = generate_synthetic_narration(
        [
            (
                "f1",
                "Start with one rotating vector then attach faster smaller vectors and watch their shared endpoint draw a richer curve",
            )
        ],
        ROOT / "examples" / "assets" / "synthetic_fourier.wav",
        word_seconds=0.34,
        word_gap_seconds=0.07,
        trailing_silence_seconds=2.3,
    )
    program = SceneProgram(
        trackers=[ScalarTrackerSpec(id="phase", initial_value=0.0)],
        objects=[
            TextVisualObject(
                id="title",
                text="Fourier motion is a chain of rotating vectors",
                position=(0.0, 3.18, 0.0),
                font_size=42,
                weight="bold",
                max_width=11.5,
            ),
            MathTexVisualObject(
                id="formula",
                formula_id="formula.fourier-sum",
                latex_parts=[
                    "z(t)",
                    "=",
                    "\\sum_{n\\in\\{1,3,5\\}} a_n e^{int}",
                ],
                part_roles=["changing", "foreground", "foreground"],
                position=(3.8, 2.1, 0.0),
                font_size=38,
                max_width=5.4,
            ),
            TrackedPointVisualObject(
                id="p0",
                tracker="phase",
                x="-2.4",
                y="-0.25",
                role="muted",
                radius=0.06,
            ),
            OrbitCircleVisualObject(
                id="orbit1",
                center_object="p0",
                radius=1.45,
                role="muted",
                opacity=0.45,
            ),
            TrackedPointVisualObject(
                id="p1",
                tracker="phase",
                x="-2.4 + 1.45*cos(t)",
                y="-0.25 + 1.45*sin(t)",
                role="changing",
                radius=0.08,
                assertion_time_values=[0.0, 3.141592653589793, 6.283185307179586],
                maximum_absolute_coordinate=6.0,
            ),
            ConnectorVisualObject(
                id="v1",
                start_object="p0",
                end_object="p1",
                role="changing",
                stroke_width=5,
            ),
            OrbitCircleVisualObject(
                id="orbit2",
                center_object="p1",
                radius=0.72,
                role="muted",
                opacity=0.4,
            ),
            TrackedPointVisualObject(
                id="p2",
                tracker="phase",
                x="-2.4 + 1.45*cos(t) + 0.72*cos(3*t)",
                y="-0.25 + 1.45*sin(t) + 0.72*sin(3*t)",
                role="fixed",
                radius=0.08,
                assertion_time_values=[0.0, 3.141592653589793, 6.283185307179586],
                maximum_absolute_coordinate=6.0,
            ),
            ConnectorVisualObject(
                id="v2",
                start_object="p1",
                end_object="p2",
                role="fixed",
                stroke_width=5,
            ),
            OrbitCircleVisualObject(
                id="orbit3",
                center_object="p2",
                radius=0.42,
                role="muted",
                opacity=0.35,
            ),
            TrackedPointVisualObject(
                id="p3",
                tracker="phase",
                x="-2.4 + 1.45*cos(t) + 0.72*cos(3*t) + 0.42*cos(5*t)",
                y="-0.25 + 1.45*sin(t) + 0.72*sin(3*t) + 0.42*sin(5*t)",
                role="positive",
                radius=0.1,
                assertion_time_values=[0.0, 3.141592653589793, 6.283185307179586],
                maximum_absolute_coordinate=6.0,
            ),
            ConnectorVisualObject(
                id="v3",
                start_object="p2",
                end_object="p3",
                role="secondary",
                stroke_width=5,
            ),
            TraceVisualObject(
                id="endpoint.trace",
                target="p3",
                role="positive",
                stroke_width=4,
                start_value=0.0,
                end_value=12.566370614359172,
                sample_count=480,
            ),
            TextVisualObject(
                id="caption",
                text="Every endpoint becomes the next vector's center.",
                position=(0.0, -3.25, 0.0),
                role="muted",
                font_size=24,
                max_width=11.0,
            ),
        ],
        cues=[
            ActionCue(
                id="headline",
                start_at=word(0),
                actions=[CreateAction(target="title", run_time=0.5)],
            ),
            ActionCue(
                id="first-vector",
                start_at=word(2),
                mode="parallel",
                actions=[
                    CreateAction(target="p0", run_time=0.6),
                    CreateAction(target="orbit1", run_time=0.6),
                    CreateAction(target="p1", run_time=0.6),
                    CreateAction(target="v1", run_time=0.6),
                ],
            ),
            ActionCue(
                id="second-vector",
                start_at=word(5),
                mode="parallel",
                actions=[
                    CreateAction(target="orbit2", run_time=0.6),
                    CreateAction(target="p2", run_time=0.6),
                    CreateAction(target="v2", run_time=0.6),
                ],
            ),
            ActionCue(
                id="third-vector",
                start_at=word(8),
                mode="parallel",
                actions=[
                    CreateAction(target="orbit3", run_time=0.6),
                    CreateAction(target="p3", run_time=0.6),
                    CreateAction(target="v3", run_time=0.6),
                ],
            ),
            ActionCue(
                id="formula-and-caption",
                start_at=word(11),
                mode="parallel",
                actions=[
                    CreateAction(target="formula", run_time=0.55),
                    CreateAction(target="caption", run_time=0.55),
                ],
            ),
            ActionCue(
                id="draw-curve",
                start_at=word(14),
                mode="parallel",
                actions=[
                    CreateAction(
                        target="endpoint.trace",
                        animation="create",
                        run_time=4.0,
                    ),
                    AnimateTrackerAction(
                        tracker="phase",
                        end_value=12.566370614359172,
                        rate_func="linear",
                        run_time=4.0,
                    )
                ],
            ),
        ],
    )
    return ProjectSpec(
        project_id="fourier-epicycle-chain",
        title="Fourier epicycles as dependency-driven motion",
        request=RequestSpec(
            content="Explain a Fourier sum as a connected chain of rotating vectors whose endpoint traces a curve.",
            audience="students who know sine and cosine",
            script_policy="locked",
            target_duration_seconds=10.7,
        ),
        narration=narration,
        math_ledger=MathLedger(
            formulas=[
                FormulaSpec(
                    id="formula.fourier-sum",
                    latex_parts=[
                        "z(t)",
                        "=",
                        "\\sum_{n\\in\\{1,3,5\\}} a_n e^{int}",
                    ],
                    plain_language="Three odd harmonics form one endpoint path.",
                )
            ]
        ),
        style=StyleTemplateRef(
            template_id="fourier-night",
            raw={
                "colors": {
                    "background": "#0d1117",
                    "foreground": "#f4f0e6",
                    "muted": "#77838e",
                },
                "semantic_colors": {
                    "primary": "#4aa7a1",
                    "changing": "#f0765b",
                    "fixed": "#72a1db",
                    "secondary": "#e0b65c",
                    "positive": "#78c879",
                },
                "typography": {
                    "font": "Avenir Next",
                    "title_size": 52,
                    "body_size": 27,
                    "math_size": 48,
                },
            },
        ),
        beats=[
            BeatSpec(
                id="epicycles",
                title="Build the chain",
                learning_objective="See how dependent rotating vectors form one trace.",
                narration_utterance_id="f1",
                duration_seconds=10.7,
                scene_program=program,
            )
        ],
        render=RenderSettings(
            renderer="cairo",
            quality="l",
            pixel_width=1280,
            pixel_height=720,
            frame_rate=24,
            seed=31,
        ),
    )


if __name__ == "__main__":
    destination = ROOT / "examples" / "fourier_featured_project.json"
    write_json_atomic(destination, build())
    print(destination)
