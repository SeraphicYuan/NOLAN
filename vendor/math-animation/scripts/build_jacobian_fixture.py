"""Build the Jacobian local-versus-global acceptance film."""

from __future__ import annotations

from pathlib import Path

from math_animation.bundle import write_json_atomic
from math_animation.contracts import (
    ActionCue,
    AnnotationVisualObject,
    ApplyMatrixAction,
    ArrowVisualObject,
    BeatSpec,
    CircleVisualObject,
    CreateAction,
    DotVisualObject,
    FormulaSpec,
    GroupVisualObject,
    LineVisualObject,
    MathLedger,
    MathTexVisualObject,
    PolygonVisualObject,
    ProjectSpec,
    RenderSettings,
    RequestSpec,
    SceneProgram,
    StyleTemplateRef,
    TextVisualObject,
    WordAnchor,
)
from math_animation.synthetic import generate_synthetic_narration


ROOT = Path(__file__).resolve().parents[1]


def word(utterance: str, index: int) -> WordAnchor:
    return WordAnchor(utterance_id=utterance, word_index=index)


def build_local_scene() -> SceneProgram:
    objects = [
        TextVisualObject(
            id="local.title",
            text="The Jacobian is a local linear lens",
            position=(0.0, 3.15, 0.0),
            font_size=43,
            weight="bold",
            max_width=11.5,
        )
    ]
    grid_members: list[str] = []
    for index, coordinate in enumerate((-1.2, -0.6, 0.0, 0.6, 1.2)):
        vertical_id = f"grid.v{index}"
        horizontal_id = f"grid.h{index}"
        objects.extend(
            [
                LineVisualObject(
                    id=vertical_id,
                    start=(coordinate, -1.2, 0.0),
                    end=(coordinate, 1.2, 0.0),
                    role="muted",
                    stroke_width=1.5,
                ),
                LineVisualObject(
                    id=horizontal_id,
                    start=(-1.2, coordinate, 0.0),
                    end=(1.2, coordinate, 0.0),
                    role="muted",
                    stroke_width=1.5,
                ),
            ]
        )
        grid_members.extend([vertical_id, horizontal_id])
    objects.extend(
        [
            PolygonVisualObject(
                id="local.square",
                vertices=[
                    (0.0, 0.0, 0.0),
                    (0.6, 0.0, 0.0),
                    (0.6, 0.6, 0.0),
                    (0.0, 0.6, 0.0),
                ],
                role="primary",
                fill_role="primary",
                fill_opacity=0.2,
                stroke_width=5,
            ),
            ArrowVisualObject(
                id="basis.x",
                start=(0.0, 0.0, 0.0),
                end=(0.6, 0.0, 0.0),
                role="changing",
                stroke_width=6,
            ),
            ArrowVisualObject(
                id="basis.y",
                start=(0.0, 0.0, 0.0),
                end=(0.0, 0.6, 0.0),
                role="fixed",
                stroke_width=6,
            ),
        ]
    )
    geometry_members = [
        *grid_members,
        "local.square",
        "basis.x",
        "basis.y",
    ]
    objects.extend(
        [
            GroupVisualObject(
                id="local.geometry",
                members=geometry_members,
                position=(-1.0, 0.0, 0.0),
            ),
            MathTexVisualObject(
                id="local.matrix",
                formula_id="formula.jacobian",
                latex_parts=[
                    "J",
                    "=",
                    "\\begin{pmatrix}2&1\\\\[2pt]1/2&3/2\\end{pmatrix}",
                ],
                part_roles=["changing", "foreground", "foreground"],
                position=(4.5, 0.7, 0.0),
                font_size=38,
                max_width=4.0,
            ),
            MathTexVisualObject(
                id="local.det",
                formula_id="formula.determinant",
                latex_parts=["\\det J", "=", "5/2"],
                part_roles=["changing", "foreground", "positive"],
                position=(4.5, -1.1, 0.0),
                font_size=40,
            ),
            TextVisualObject(
                id="local.caption",
                text="Area scales by 5/2 near this point.",
                position=(0.0, -3.25, 0.0),
                role="muted",
                font_size=24,
                max_width=11.0,
            ),
        ]
    )
    return SceneProgram(
        objects=objects,
        cues=[
            ActionCue(
                id="headline",
                start_at=word("j1", 0),
                actions=[CreateAction(target="local.title", run_time=0.5)],
            ),
            ActionCue(
                id="grid",
                start_at=word("j1", 3),
                actions=[CreateAction(target="local.geometry", run_time=0.8)],
            ),
            ActionCue(
                id="matrix",
                start_at=word("j1", 6),
                mode="parallel",
                actions=[
                    CreateAction(target="local.matrix", run_time=0.6),
                    CreateAction(target="local.det", run_time=0.6),
                ],
            ),
            ActionCue(
                id="deform",
                start_at=word("j1", 9),
                actions=[
                    ApplyMatrixAction(
                        target="local.geometry",
                        matrix=((2.0, 1.0), (0.5, 1.5)),
                        expected_determinant=2.5,
                        run_time=1.25,
                    )
                ],
            ),
            ActionCue(
                id="caption",
                start_at=word("j1", 14),
                actions=[CreateAction(target="local.caption", run_time=0.4)],
            ),
        ],
    )


def build_global_scene() -> SceneProgram:
    return SceneProgram(
        objects=[
            TextVisualObject(
                id="global.title",
                text="Local reversibility is not global uniqueness",
                position=(0.0, 3.15, 0.0),
                font_size=42,
                weight="bold",
                max_width=11.5,
            ),
            CircleVisualObject(
                id="domain.circle",
                radius=2.0,
                position=(-3.2, 0.0, 0.0),
                role="muted",
                stroke_width=3,
            ),
            DotVisualObject(
                id="domain.a",
                position=(-3.2, 2.0, 0.0),
                role="changing",
                radius=0.12,
            ),
            DotVisualObject(
                id="domain.b",
                position=(-3.2, -2.0, 0.0),
                role="fixed",
                radius=0.12,
            ),
            TextVisualObject(
                id="domain.a-label",
                text="θ = 0",
                position=(-4.5, 2.0, 0.0),
                role="changing",
                font_size=24,
            ),
            TextVisualObject(
                id="domain.b-label",
                text="θ = 2π",
                position=(-4.6, -2.0, 0.0),
                role="fixed",
                font_size=24,
            ),
            DotVisualObject(
                id="range.point",
                position=(2.8, 0.0, 0.0),
                role="positive",
                radius=0.16,
            ),
            ArrowVisualObject(
                id="map.a",
                start=(-2.7, 1.7, 0.0),
                end=(2.55, 0.15, 0.0),
                role="changing",
                stroke_width=4,
            ),
            ArrowVisualObject(
                id="map.b",
                start=(-2.7, -1.7, 0.0),
                end=(2.55, -0.15, 0.0),
                role="fixed",
                stroke_width=4,
            ),
            GroupVisualObject(
                id="global.diagram",
                members=[
                    "domain.circle",
                    "domain.a",
                    "domain.b",
                    "domain.a-label",
                    "domain.b-label",
                    "range.point",
                    "map.a",
                    "map.b",
                ],
            ),
            MathTexVisualObject(
                id="global.map",
                formula_id="formula.polar-map",
                latex_parts=[
                    "F(r,\\theta)",
                    "=",
                    "(e^r\\cos\\theta,\\ e^r\\sin\\theta)",
                ],
                part_roles=["changing", "foreground", "foreground"],
                position=(1.8, 2.0, 0.0),
                font_size=35,
                max_width=6.0,
            ),
            MathTexVisualObject(
                id="global.collision",
                formula_id="formula.collision",
                latex_parts=["F(r,0)", "=", "F(r,2\\pi)"],
                part_roles=["changing", "foreground", "fixed"],
                position=(2.8, -1.0, 0.0),
                font_size=38,
                max_width=5.0,
            ),
            AnnotationVisualObject(
                id="global.note",
                text="Two inputs. One output.",
                point=(2.8, 0.0, 0.0),
                label_position=(4.2, 1.0, 0.0),
                role="positive",
                font_size=24,
                max_width=3.0,
            ),
            TextVisualObject(
                id="global.caption",
                text="A nonzero determinant guarantees a local inverse—not a global one.",
                position=(0.0, -3.25, 0.0),
                role="muted",
                font_size=23,
                max_width=11.0,
            ),
        ],
        cues=[
            ActionCue(
                id="headline",
                start_at=word("j2", 0),
                actions=[CreateAction(target="global.title", run_time=0.5)],
            ),
            ActionCue(
                id="map",
                start_at=word("j2", 3),
                mode="parallel",
                actions=[
                    CreateAction(target="global.diagram", run_time=0.8),
                    CreateAction(target="global.map", run_time=0.8),
                ],
            ),
            ActionCue(
                id="collision",
                start_at=word("j2", 8),
                mode="parallel",
                actions=[
                    CreateAction(target="global.collision", run_time=0.6),
                    CreateAction(target="global.note", run_time=0.6),
                ],
            ),
            ActionCue(
                id="conclusion",
                start_at=word("j2", 12),
                actions=[CreateAction(target="global.caption", run_time=0.5)],
            ),
        ],
    )


def build() -> ProjectSpec:
    narration = generate_synthetic_narration(
        [
            (
                "j1",
                "Near one point a smooth map behaves like its Jacobian matrix and scales area by its determinant",
            ),
            (
                "j2",
                "But local reversal cannot stop distant inputs from meeting at the same global output point",
            ),
        ],
        ROOT / "examples" / "assets" / "synthetic_jacobian.wav",
        word_seconds=0.33,
        word_gap_seconds=0.07,
        utterance_gap_seconds=0.5,
        trailing_silence_seconds=0.7,
    )
    return ProjectSpec(
        project_id="jacobian-local-global",
        title="The Jacobian: local certainty versus global truth",
        request=RequestSpec(
            content="Explain geometrically why a nonzero Jacobian is a local, not global, guarantee.",
            audience="multivariable calculus students",
            script_policy="locked",
            target_duration_seconds=12.5,
        ),
        narration=narration,
        math_ledger=MathLedger(
            formulas=[
                FormulaSpec(
                    id="formula.jacobian",
                    latex_parts=[
                        "J",
                        "=",
                        "\\begin{pmatrix}2&1\\\\[2pt]1/2&3/2\\end{pmatrix}",
                    ],
                    plain_language="A concrete local linearization.",
                ),
                FormulaSpec(
                    id="formula.determinant",
                    latex_parts=["\\det J", "=", "5/2"],
                    plain_language="The local oriented area scale is five halves.",
                ),
                FormulaSpec(
                    id="formula.polar-map",
                    latex_parts=[
                        "F(r,\\theta)",
                        "=",
                        "(e^r\\cos\\theta,\\ e^r\\sin\\theta)",
                    ],
                    plain_language="A locally invertible polar exponential map.",
                ),
                FormulaSpec(
                    id="formula.collision",
                    latex_parts=["F(r,0)", "=", "F(r,2\\pi)"],
                    plain_language="Periodicity identifies distinct angular inputs.",
                ),
            ]
        ),
        style=StyleTemplateRef(
            template_id="jacobian-dark",
            raw={
                "colors": {
                    "background": "#111416",
                    "foreground": "#f4f1e8",
                    "muted": "#8d989d",
                },
                "semantic_colors": {
                    "primary": "#4da9a4",
                    "changing": "#ef7b5d",
                    "fixed": "#6e9bd1",
                    "secondary": "#d7ad54",
                    "positive": "#7fc47a",
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
                id="local",
                title="The local linear map",
                learning_objective="See the determinant as local area scale.",
                narration_utterance_id="j1",
                duration_seconds=7.0,
                scene_program=build_local_scene(),
            ),
            BeatSpec(
                id="global",
                title="The global caveat",
                learning_objective="Distinguish local inversion from global uniqueness.",
                narration_utterance_id="j2",
                duration_seconds=6.5,
                scene_program=build_global_scene(),
            ),
        ],
        render=RenderSettings(
            renderer="cairo",
            quality="l",
            pixel_width=1280,
            pixel_height=720,
            frame_rate=24,
            seed=29,
        ),
    )


if __name__ == "__main__":
    destination = ROOT / "examples" / "jacobian_featured_project.json"
    write_json_atomic(destination, build())
    print(destination)
