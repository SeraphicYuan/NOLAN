"""Build the deterministic narrated algebra acceptance fixture."""

from __future__ import annotations

from pathlib import Path

from math_animation.bundle import write_json_atomic
from math_animation.contracts import (
    ActionCue,
    AnnotationVisualObject,
    AxesVisualObject,
    BeatSpec,
    CircleVisualObject,
    CreateAction,
    FormulaSpec,
    FunctionGraphVisualObject,
    GroupVisualObject,
    LineVisualObject,
    MathLedger,
    MathTexVisualObject,
    PolygonVisualObject,
    ProjectSpec,
    RelativeLayout,
    RenderSettings,
    RequestSpec,
    ResponsiveVisualOverride,
    SceneProgram,
    StyleTemplateRef,
    TextVisualObject,
    TransformMathAction,
    WordAnchor,
)
from math_animation.synthetic import generate_synthetic_narration


ROOT = Path(__file__).resolve().parents[1]


def word(utterance: str, index: int) -> WordAnchor:
    return WordAnchor(
        utterance_id=utterance,
        word_index=index,
        edge="start",
    )


def _add_responsive_layout(program: SceneProgram) -> None:
    """Provide conservative authored variants for square and portrait delivery."""

    for item in program.objects:
        square_scale = 0.82
        portrait_scale = 0.52
        square_position = (
            item.position[0] * 0.72,
            item.position[1],
            item.position[2],
        )
        portrait_position = (
            item.position[0] * 0.36,
            item.position[1],
            item.position[2],
        )
        if isinstance(item, (FunctionGraphVisualObject, GroupVisualObject)):
            square_scale = portrait_scale = 1.0
        if isinstance(item, (TextVisualObject, MathTexVisualObject)):
            square_scale = 0.9
            portrait_scale = 0.68
        if item.id.endswith("title"):
            portrait_scale = 0.52
        if isinstance(item, AnnotationVisualObject):
            square_position = (-0.65, 0.0, 0.0)
            portrait_position = (-2.0, 0.0, 0.0)
            square_scale = 0.9
            portrait_scale = 0.7
        if item.id == "check.answer":
            square_position = (2.3, -2.5, 0.0)
            portrait_position = (0.0, -2.75, 0.0)
            portrait_scale = 0.72
        item.responsive = {
            "square": ResponsiveVisualOverride(
                position=square_position,
                scale=square_scale,
            ),
            "portrait": ResponsiveVisualOverride(
                position=portrait_position,
                scale=portrait_scale,
            ),
        }


def build() -> ProjectSpec:
    narration = generate_synthetic_narration(
        [
            (
                "u1",
                "An equation is a balance with equal weight on both sides",
            ),
            (
                "u2",
                "Remove five from both sides then divide both sides by three",
            ),
            (
                "u3",
                "The solution five is where the two sides agree",
            ),
        ],
        ROOT / "examples" / "assets" / "synthetic_algebra.wav",
        word_seconds=0.36,
        word_gap_seconds=0.08,
        utterance_gap_seconds=0.5,
        trailing_silence_seconds=0.6,
    )
    formulas = [
        FormulaSpec(
            id="formula.balance",
            latex_parts=["3x+5", "=", "20"],
            plain_language="The two expressions have equal value.",
        ),
        FormulaSpec(
            id="formula.subtract",
            latex_parts=["3x", "=", "15"],
            plain_language="Subtracting five from both sides preserves equality.",
        ),
        FormulaSpec(
            id="formula.solution",
            latex_parts=["x", "=", "5"],
            plain_language="Dividing both sides by three isolates x.",
        ),
    ]
    balance_scene = SceneProgram(
        objects=[
            TextVisualObject(
                id="title",
                text="An equation is a balance",
                position=(0.0, 3.0, 0.0),
                font_size=44,
                weight="bold",
                max_width=11.0,
            ),
            LineVisualObject(
                id="beam",
                start=(-3.0, 0.0, 0.0),
                end=(3.0, 0.0, 0.0),
                role="foreground",
                stroke_width=7,
            ),
            PolygonVisualObject(
                id="fulcrum",
                vertices=[(-0.5, -1.4, 0.0), (0.5, -1.4, 0.0), (0.0, 0.0, 0.0)],
                role="secondary",
                fill_role="secondary",
                fill_opacity=0.25,
            ),
            CircleVisualObject(
                id="left.weight",
                radius=0.42,
                position=(-2.1, 0.58, 0.0),
                role="changing",
                fill_role="changing",
                fill_opacity=0.2,
            ),
            CircleVisualObject(
                id="right.weight",
                radius=0.42,
                position=(2.1, 0.58, 0.0),
                role="fixed",
                fill_role="fixed",
                fill_opacity=0.2,
            ),
            GroupVisualObject(
                id="balance.diagram",
                members=["beam", "fulcrum", "left.weight", "right.weight"],
            ),
            MathTexVisualObject(
                id="balance.equation",
                formula_id="formula.balance",
                latex_parts=["3x+5", "=", "20"],
                part_roles=["changing", "foreground", "fixed"],
                position=(0.0, -2.55, 0.0),
                font_size=42,
            ),
        ],
        cues=[
            ActionCue(
                id="title",
                start_at=word("u1", 0),
                actions=[CreateAction(target="title", run_time=0.4)],
            ),
            ActionCue(
                id="balance",
                start_at=word("u1", 2),
                actions=[CreateAction(target="balance.diagram", run_time=0.7)],
            ),
            ActionCue(
                id="equation",
                start_at=word("u1", 6),
                actions=[CreateAction(target="balance.equation", run_time=0.6)],
            ),
        ],
    )
    solve_scene = SceneProgram(
        objects=[
            MathTexVisualObject(
                id="solve.equation",
                formula_id="formula.balance",
                latex_parts=["3x+5", "=", "20"],
                part_roles=["changing", "foreground", "fixed"],
                position=(0.0, 0.5, 0.0),
                font_size=62,
                max_width=10.0,
            ),
            TextVisualObject(
                id="solve.caption",
                text="Whatever we do, we do to both sides.",
                role="muted",
                font_size=26,
                max_width=10.5,
                layout=RelativeLayout(
                    relative_to="solve.equation",
                    direction="down",
                    buffer=0.8,
                ),
            ),
        ],
        cues=[
            ActionCue(
                id="show-rule",
                start_at=word("u2", 0),
                mode="parallel",
                actions=[
                    CreateAction(target="solve.equation", run_time=0.5),
                    CreateAction(target="solve.caption", run_time=0.5),
                ],
            ),
            ActionCue(
                id="subtract-five",
                start_at=word("u2", 3),
                actions=[
                    TransformMathAction(
                        target="solve.equation",
                        formula_id="formula.subtract",
                        latex_parts=["3x", "=", "15"],
                        part_roles=["changing", "foreground", "fixed"],
                        run_time=0.8,
                    )
                ],
            ),
            ActionCue(
                id="divide-three",
                start_at=word("u2", 7),
                actions=[
                    TransformMathAction(
                        target="solve.equation",
                        formula_id="formula.solution",
                        latex_parts=["x", "=", "5"],
                        part_roles=["changing", "foreground", "positive"],
                        run_time=0.8,
                    )
                ],
            ),
        ],
    )
    check_scene = SceneProgram(
        objects=[
            AxesVisualObject(
                id="check.axes",
                x_range=(-1.0, 7.0, 1.0),
                y_range=(-2.0, 24.0, 5.0),
                x_length=8.0,
                y_length=4.8,
                position=(-0.7, 0.1, 0.0),
            ),
            FunctionGraphVisualObject(
                id="check.left",
                axes="check.axes",
                expression="3*x+5",
                x_range=(-1.0, 7.0),
                role="changing",
            ),
            FunctionGraphVisualObject(
                id="check.right",
                axes="check.axes",
                expression="20",
                x_range=(-1.0, 7.0),
                role="fixed",
            ),
            AnnotationVisualObject(
                id="check.annotation",
                text="They meet at x = 5",
                point=(1.3, 1.76, 0.0),
                label_position=(3.7, 2.45, 0.0),
                role="positive",
                font_size=25,
                max_width=3.2,
            ),
            MathTexVisualObject(
                id="check.answer",
                formula_id="formula.solution",
                latex_parts=["x", "=", "5"],
                part_roles=["changing", "foreground", "positive"],
                position=(4.7, -2.5, 0.0),
                font_size=44,
            ),
        ],
        cues=[
            ActionCue(
                id="graphs",
                start_at=word("u3", 0),
                mode="parallel",
                actions=[
                    CreateAction(target="check.axes", run_time=0.6),
                    CreateAction(target="check.left", run_time=0.6),
                    CreateAction(target="check.right", run_time=0.6),
                ],
            ),
            ActionCue(
                id="intersection",
                start_at=word("u3", 3),
                actions=[
                    CreateAction(target="check.annotation", run_time=0.6)
                ],
            ),
            ActionCue(
                id="answer",
                start_at=word("u3", 7),
                actions=[CreateAction(target="check.answer", run_time=0.45)],
            ),
        ],
    )
    for scene in (balance_scene, solve_scene, check_scene):
        _add_responsive_layout(scene)
    return ProjectSpec(
        project_id="synthetic-nolan-algebra",
        title="Solving an equation means preserving balance",
        request=RequestSpec(
            source_kind="screenplay",
            content="Use a balance, symbolic transformations, and a graph to solve 3x+5=20.",
            audience="beginning algebra students",
            script_policy="locked",
            target_duration_seconds=15.1,
        ),
        math_ledger=MathLedger(formulas=formulas),
        narration=narration,
        style=StyleTemplateRef(
            template_id="synthetic-nolan-light",
            raw={
                "colors": {
                    "background": "#f5efe3",
                    "foreground": "#211b17",
                    "muted": "#71685e",
                },
                "semantic_colors": {
                    "primary": "#256b68",
                    "changing": "#b64e3b",
                    "fixed": "#416188",
                    "secondary": "#9a772f",
                    "positive": "#4d7a4c",
                },
                "typography": {
                    "font": "Avenir Next",
                    "title_size": 54,
                    "body_size": 27,
                    "math_size": 52,
                },
            },
        ),
        beats=[
            BeatSpec(
                id="balance",
                title="Equality is balance",
                learning_objective="Interpret equality as preserved balance.",
                narration_utterance_id="u1",
                duration_seconds=4.9,
                scene_program=balance_scene,
            ),
            BeatSpec(
                id="solve",
                title="Apply equal operations",
                learning_objective="Solve while preserving equality.",
                narration_utterance_id="u2",
                duration_seconds=5.0,
                scene_program=solve_scene,
            ),
            BeatSpec(
                id="check",
                title="Verify the intersection",
                learning_objective="Interpret the solution as agreement.",
                narration_utterance_id="u3",
                duration_seconds=4.5,
                scene_program=check_scene,
            ),
        ],
        render=RenderSettings(
            renderer="cairo",
            quality="l",
            pixel_width=1280,
            pixel_height=720,
            frame_rate=24,
            seed=23,
        ),
    )


if __name__ == "__main__":
    destination = ROOT / "examples" / "synthetic_nolan_algebra.json"
    write_json_atomic(destination, build())
    print(destination)
