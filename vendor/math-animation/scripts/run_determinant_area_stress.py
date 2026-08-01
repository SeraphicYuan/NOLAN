"""Render a stateful Manim explainer for why determinant measures area."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from math_animation.bundle import write_json_atomic
from math_animation.contracts import (
    ActionCue,
    AnnotationVisualObject,
    ApplyMatrixAction,
    ArrowVisualObject,
    AxesVisualObject,
    BeatSpec,
    CreateAction,
    DotVisualObject,
    FadeOutAction,
    FormulaSpec,
    GroupVisualObject,
    MathClaim,
    MathLedger,
    MathTexVisualObject,
    PolygonVisualObject,
    ProjectSpec,
    RenderSettings,
    RequestSpec,
    SceneProgram,
    StyleTemplateRef,
    TextVisualObject,
    TransformMathAction,
    WordAnchor,
)
from math_animation.pedagogy import evaluate_pedagogy
from math_animation.pipeline import AuthoringPipeline
from run_vertex_form_featured import (
    _contact_sheet,
    _system_speech_narration,
)


ROOT = Path(__file__).resolve().parents[1]


def _word(utterance_id: str, index: int) -> WordAnchor:
    return WordAnchor(
        utterance_id=utterance_id,
        word_index=index,
        edge="start",
    )


def _duration(narration, utterance_id: str) -> float:
    utterance = next(
        item
        for item in narration.utterances
        if item.id == utterance_id
    )
    return (
        utterance.words[-1].end_seconds
        - utterance.words[0].start_seconds
    )


def _axes(identifier: str) -> AxesVisualObject:
    return AxesVisualObject(
        id=identifier,
        x_range=(-4.0, 4.0, 1.0),
        y_range=(-3.0, 3.0, 1.0),
        x_length=10.0,
        y_length=6.5,
        role="muted",
        tips=False,
    )


def _area_tripling_scene() -> SceneProgram:
    return SceneProgram(
        minimum_effective_font_size=22,
        objects=[
            _axes("triple.axes"),
            PolygonVisualObject(
                id="triple.square",
                vertices=[
                    (-1.0, -1.0, 0.0),
                    (1.0, -1.0, 0.0),
                    (1.0, 1.0, 0.0),
                    (-1.0, 1.0, 0.0),
                ],
                role="primary",
                fill_role="primary",
                fill_opacity=0.22,
                stroke_width=5,
            ),
            ArrowVisualObject(
                id="triple.e1",
                start=(0.0, 0.0, 0.0),
                end=(1.0, 0.0, 0.0),
                role="changing",
                stroke_width=7,
            ),
            ArrowVisualObject(
                id="triple.e2",
                start=(0.0, 0.0, 0.0),
                end=(0.0, 1.0, 0.0),
                role="fixed",
                stroke_width=7,
            ),
            GroupVisualObject(
                id="triple.region",
                members=["triple.square", "triple.e1", "triple.e2"],
            ),
            TextVisualObject(
                id="triple.unit",
                text="Unit square",
                position=(0.0, -2.25, 0.0),
                role="muted",
                font_size=28,
            ),
            MathTexVisualObject(
                id="triple.formula",
                formula_id="matrix.A",
                latex_parts=[
                    r"A=\begin{bmatrix}2&1\\0&\frac{3}{2}\end{bmatrix}"
                ],
                position=(-4.7, 2.65, 0.0),
                font_size=48,
                max_width=4.2,
            ),
            AnnotationVisualObject(
                id="triple.result",
                text="Area triples",
                point=(1.5, 0.8, 0.0),
                label_position=(4.7, 2.2, 0.0),
                role="positive",
                font_size=30,
                max_width=2.8,
            ),
        ],
        cues=[
            ActionCue(
                id="triple.show-unit",
                start_at=_word("triple.words", 0),
                mode="parallel",
                actions=[
                    CreateAction(target="triple.axes", run_time=0.8),
                    CreateAction(target="triple.region", run_time=0.8),
                    CreateAction(target="triple.unit", run_time=0.8),
                ],
            ),
            ActionCue(
                id="triple.show-matrix",
                start_at=_word("triple.words", 5),
                actions=[
                    CreateAction(
                        target="triple.formula",
                        animation="write",
                        run_time=0.75,
                    )
                ],
            ),
            ActionCue(
                id="triple.apply-matrix",
                start_at=_word("triple.words", 14),
                mode="parallel",
                actions=[
                    ApplyMatrixAction(
                        target="triple.region",
                        matrix=((2.0, 1.0), (0.0, 1.5)),
                        expected_determinant=3.0,
                        run_time=1.5,
                    ),
                    TransformMathAction(
                        target="triple.formula",
                        formula_id="det.A",
                        latex_parts=[r"|\det A|=|3|=3"],
                        run_time=1.5,
                    ),
                    FadeOutAction(target="triple.unit", run_time=1.5),
                ],
            ),
            ActionCue(
                id="triple.explain-result",
                start_at=_word("triple.words", 24),
                actions=[
                    CreateAction(
                        target="triple.result",
                        animation="fade_in",
                        run_time=0.7,
                    )
                ],
            ),
        ],
    )


def _orientation_scene() -> SceneProgram:
    return SceneProgram(
        minimum_effective_font_size=22,
        objects=[
            _axes("flip.axes"),
            PolygonVisualObject(
                id="flip.triangle",
                vertices=[
                    (-1.6, -1.0, 0.0),
                    (1.25, -0.65, 0.0),
                    (0.35, 1.45, 0.0),
                ],
                role="primary",
                fill_role="primary",
                fill_opacity=0.24,
                stroke_width=5,
            ),
            DotVisualObject(
                id="flip.p1",
                position=(-1.6, -1.0, 0.0),
                role="changing",
                radius=0.11,
            ),
            DotVisualObject(
                id="flip.p2",
                position=(1.25, -0.65, 0.0),
                role="fixed",
                radius=0.11,
            ),
            DotVisualObject(
                id="flip.p3",
                position=(0.35, 1.45, 0.0),
                role="positive",
                radius=0.11,
            ),
            GroupVisualObject(
                id="flip.shape",
                members=[
                    "flip.triangle",
                    "flip.p1",
                    "flip.p2",
                    "flip.p3",
                ],
            ),
            TextVisualObject(
                id="flip.orientation",
                text="1 → 2 → 3",
                position=(0.0, -2.35, 0.0),
                role="muted",
                font_size=30,
            ),
            MathTexVisualObject(
                id="flip.formula",
                formula_id="matrix.B",
                latex_parts=[
                    r"B=\begin{bmatrix}-1&0\\0&1\end{bmatrix}"
                ],
                position=(-4.7, 2.65, 0.0),
                font_size=50,
                max_width=4.0,
            ),
            AnnotationVisualObject(
                id="flip.result",
                text="Same area • orientation flips",
                point=(-1.0, 0.8, 0.0),
                label_position=(4.45, 2.15, 0.0),
                role="changing",
                font_size=27,
                max_width=4.4,
            ),
        ],
        cues=[
            ActionCue(
                id="flip.show-shape",
                start_at=_word("flip.words", 0),
                mode="parallel",
                actions=[
                    CreateAction(target="flip.axes", run_time=0.8),
                    CreateAction(target="flip.shape", run_time=0.8),
                    CreateAction(target="flip.orientation", run_time=0.8),
                ],
            ),
            ActionCue(
                id="flip.show-matrix",
                start_at=_word("flip.words", 9),
                actions=[
                    CreateAction(
                        target="flip.formula",
                        animation="write",
                        run_time=0.75,
                    )
                ],
            ),
            ActionCue(
                id="flip.reflect",
                start_at=_word("flip.words", 14),
                mode="parallel",
                actions=[
                    ApplyMatrixAction(
                        target="flip.shape",
                        matrix=((-1.0, 0.0), (0.0, 1.0)),
                        expected_determinant=-1.0,
                        run_time=1.4,
                    ),
                    TransformMathAction(
                        target="flip.formula",
                        formula_id="det.B",
                        latex_parts=[r"\det B=-1"],
                        run_time=1.4,
                    ),
                    FadeOutAction(
                        target="flip.orientation",
                        run_time=1.4,
                    ),
                ],
            ),
            ActionCue(
                id="flip.explain-result",
                start_at=_word("flip.words", 23),
                actions=[
                    CreateAction(
                        target="flip.result",
                        animation="fade_in",
                        run_time=0.7,
                    )
                ],
            ),
        ],
    )


def _collapse_scene() -> SceneProgram:
    return SceneProgram(
        minimum_effective_font_size=22,
        objects=[
            _axes("collapse.axes"),
            PolygonVisualObject(
                id="collapse.square",
                vertices=[
                    (-1.0, -1.0, 0.0),
                    (1.0, -1.0, 0.0),
                    (1.0, 1.0, 0.0),
                    (-1.0, 1.0, 0.0),
                ],
                role="primary",
                fill_role="primary",
                fill_opacity=0.22,
                stroke_width=5,
            ),
            ArrowVisualObject(
                id="collapse.e1",
                start=(0.0, 0.0, 0.0),
                end=(1.0, 0.0, 0.0),
                role="changing",
                stroke_width=7,
            ),
            ArrowVisualObject(
                id="collapse.e2",
                start=(0.0, 0.0, 0.0),
                end=(0.0, 1.0, 0.0),
                role="fixed",
                stroke_width=7,
            ),
            GroupVisualObject(
                id="collapse.region",
                members=[
                    "collapse.square",
                    "collapse.e1",
                    "collapse.e2",
                ],
            ),
            MathTexVisualObject(
                id="collapse.formula",
                formula_id="matrix.C",
                latex_parts=[
                    r"C=\begin{bmatrix}1&1\\1&1\end{bmatrix}"
                ],
                position=(-4.7, 2.65, 0.0),
                font_size=50,
                max_width=4.0,
            ),
            AnnotationVisualObject(
                id="collapse.result",
                text="Area collapses to zero",
                point=(1.1, 1.1, 0.0),
                label_position=(4.55, 2.05, 0.0),
                role="changing",
                font_size=27,
                max_width=3.5,
            ),
        ],
        cues=[
            ActionCue(
                id="collapse.show-square",
                start_at=_word("collapse.words", 0),
                mode="parallel",
                actions=[
                    CreateAction(target="collapse.axes", run_time=0.8),
                    CreateAction(target="collapse.region", run_time=0.8),
                ],
            ),
            ActionCue(
                id="collapse.show-matrix",
                start_at=_word("collapse.words", 5),
                actions=[
                    CreateAction(
                        target="collapse.formula",
                        animation="write",
                        run_time=0.75,
                    )
                ],
            ),
            ActionCue(
                id="collapse.flatten",
                start_at=_word("collapse.words", 11),
                mode="parallel",
                actions=[
                    ApplyMatrixAction(
                        target="collapse.region",
                        matrix=((1.0, 1.0), (1.0, 1.0)),
                        expected_determinant=0.0,
                        run_time=1.5,
                    ),
                    TransformMathAction(
                        target="collapse.formula",
                        formula_id="det.C",
                        latex_parts=[r"\det C=0"],
                        run_time=1.5,
                    ),
                ],
            ),
            ActionCue(
                id="collapse.explain-result",
                start_at=_word("collapse.words", 18),
                actions=[
                    CreateAction(
                        target="collapse.result",
                        animation="fade_in",
                        run_time=0.7,
                    )
                ],
            ),
            ActionCue(
                id="collapse.generalize",
                start_at=_word("collapse.words", 23),
                actions=[
                    TransformMathAction(
                        target="collapse.formula",
                        formula_id="det.general",
                        latex_parts=[
                            r"\text{area scale}=|\det M|"
                        ],
                        run_time=1.0,
                    )
                ],
            ),
        ],
    )


def _build_project() -> tuple[ProjectSpec, str]:
    utterances = [
        (
            "triple.words",
            "Begin with a unit square. This matrix stretches one direction "
            "and shears the other. The square becomes a parallelogram with "
            "three times the area, exactly the absolute determinant.",
        ),
        (
            "flip.words",
            "A reflection flips the orientation of an asymmetric shape. Its "
            "determinant is negative one. The sign records the flip, while "
            "the absolute value preserves the area.",
        ),
        (
            "collapse.words",
            "A singular matrix sends both basis directions onto the same "
            "line. The square collapses, its area becomes zero, and so does "
            "the determinant. Absolute determinant is the universal area "
            "scale.",
        ),
    ]
    narration, narration_mode = _system_speech_narration(
        utterances,
        ROOT / "examples" / "assets" / "determinant_area_narration.wav",
        rate=205,
        gap_seconds=0.5,
    )
    formulas = [
        FormulaSpec(
            id="matrix.A",
            latex_parts=[
                r"A=\begin{bmatrix}2&1\\0&\frac{3}{2}\end{bmatrix}"
            ],
            plain_language="A shear and stretch with determinant three.",
        ),
        FormulaSpec(
            id="det.A",
            latex_parts=[r"|\det A|=|3|=3"],
            plain_language="The transformation triples area.",
        ),
        FormulaSpec(
            id="matrix.B",
            latex_parts=[
                r"B=\begin{bmatrix}-1&0\\0&1\end{bmatrix}"
            ],
            plain_language="A reflection across the vertical axis.",
        ),
        FormulaSpec(
            id="det.B",
            latex_parts=[r"\det B=-1"],
            plain_language="The negative sign records orientation reversal.",
        ),
        FormulaSpec(
            id="matrix.C",
            latex_parts=[
                r"C=\begin{bmatrix}1&1\\1&1\end{bmatrix}"
            ],
            plain_language="Both basis directions map to the same line.",
        ),
        FormulaSpec(
            id="det.C",
            latex_parts=[r"\det C=0"],
            plain_language="A singular map collapses planar area.",
        ),
        FormulaSpec(
            id="det.general",
            latex_parts=[r"\text{area scale}=|\det M|"],
            plain_language="Absolute determinant is the planar area scale.",
        ),
    ]
    claims = [
        MathClaim(
            id="claim.area-scale",
            statement=(
                "For a two-dimensional linear map, absolute determinant is "
                "the multiplicative area scale."
            ),
            verification="verified",
            assumptions=["The map is linear and acts on planar area."],
            evidence=["Direct determinant calculations in all three beats."],
        ),
        MathClaim(
            id="claim.orientation",
            statement=(
                "A negative determinant reverses orientation while its "
                "absolute value remains the area scale."
            ),
            verification="verified",
            evidence=["Reflection matrix B has determinant negative one."],
        ),
    ]
    script = "\n\n".join(text for _, text in utterances)
    project = ProjectSpec(
        project_id="determinant-area-stress",
        title="Why the determinant measures area",
        request=RequestSpec(
            source_kind="script",
            content=script,
            audience="introductory linear algebra learners",
            script_policy="locked",
            target_duration_seconds=sum(
                _duration(narration, utterance_id)
                for utterance_id, _ in utterances
            )
            + 1.0,
        ),
        math_ledger=MathLedger(
            claims=claims,
            formulas=formulas,
        ),
        narration=narration,
        style=StyleTemplateRef(
            template_id="linear-algebra-neon",
            raw={
                "colors": {
                    "background": "#07101c",
                    "foreground": "#f3f0e8",
                    "muted": "#52687d",
                },
                "semantic_colors": {
                    "primary": "#4ecdc4",
                    "changing": "#ff7a68",
                    "fixed": "#7da7ff",
                    "positive": "#92d36e",
                },
                "typography": {
                    "font": "Avenir Next",
                    "title_size": 46,
                    "body_size": 28,
                    "math_size": 58,
                },
            },
        ),
        beats=[
            BeatSpec(
                id="area-triples",
                title="Determinant three",
                learning_objective=(
                    "Transform a unit square and connect determinant three "
                    "to the resulting area multiplier."
                ),
                narration_utterance_id="triple.words",
                duration_seconds=_duration(narration, "triple.words"),
                scene_program=_area_tripling_scene(),
            ),
            BeatSpec(
                id="orientation-flips",
                title="The sign records orientation",
                learning_objective=(
                    "Transform an asymmetric shape to show why a negative "
                    "determinant reverses orientation."
                ),
                narration_utterance_id="flip.words",
                duration_seconds=_duration(narration, "flip.words"),
                scene_program=_orientation_scene(),
            ),
            BeatSpec(
                id="area-collapses",
                title="Singular means zero area",
                learning_objective=(
                    "Transform a square into a line and connect the collapse "
                    "to determinant zero."
                ),
                narration_utterance_id="collapse.words",
                duration_seconds=_duration(narration, "collapse.words"),
                scene_program=_collapse_scene(),
            ),
        ],
        render=RenderSettings(
            renderer="cairo",
            quality="l",
            pixel_width=960,
            pixel_height=540,
            frame_rate=24,
            seed=149,
        ),
    )
    return project, narration_mode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("/tmp/math-animation-determinant-area-stress"),
    )
    args = parser.parse_args()

    project, narration_mode = _build_project()
    pedagogy = evaluate_pedagogy(project)
    examples_dir = ROOT / "examples" / "determinant_area_stress"
    examples_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(examples_dir / "project.json", project)
    write_json_atomic(examples_dir / "pedagogy.json", pedagogy)

    result = AuthoringPipeline(
        runs_dir=args.runs_dir,
        render_timeout_seconds=900,
    ).run(
        project,
        render=True,
        compose=True,
        minimum_pedagogy_score=0.85,
        use_cache=False,
    )
    review = json.loads(
        (result.run_dir / "review" / "report.json").read_text(encoding="utf-8")
    )
    performance = json.loads(
        (result.run_dir / "performance.json").read_text(encoding="utf-8")
    )
    assert result.final_video is not None
    video = ROOT / "artifacts" / "determinant_area_stress.mp4"
    keyframes = ROOT / "artifacts" / "determinant_area_stress_keyframes.png"
    review_artifact = (
        ROOT / "artifacts" / "determinant_area_stress_review.json"
    )
    shutil.copy2(result.final_video, video)
    _contact_sheet(result.run_dir, keyframes)
    write_json_atomic(review_artifact, review)

    object_count = sum(
        len(beat.scene_program.objects)
        for beat in project.beats
        if beat.scene_program is not None
    )
    cue_count = sum(
        len(beat.scene_program.cues)
        for beat in project.beats
        if beat.scene_program is not None
    )
    action_count = sum(
        len(cue.actions)
        for beat in project.beats
        if beat.scene_program is not None
        for cue in beat.scene_program.cues
    )
    passed = (
        pedagogy.total_score >= 0.85
        and review["status"] == "passed"
        and not review["warnings"]
        and not review["errors"]
        and len(result.manifest.renders) == 3
    )
    report = {
        "schema_version": "math-animation.determinant-stress-report.v1",
        "status": "passed" if passed else "failed",
        "topic": "Why the determinant measures area",
        "narration_mode": narration_mode,
        "alignment_note": (
            "Local system TTS uses proportional per-word timing for this "
            "standalone test; Nolan alignment remains authoritative."
        ),
        "beat_count": len(project.beats),
        "scene_program_count": len(project.beats),
        "object_count": object_count,
        "cue_count": cue_count,
        "action_count": action_count,
        "manim_features": [
            "persistent object groups",
            "parallel create and transform cues",
            "word-anchored timing",
            "matrix transformations with determinant assertions",
            "polygon area deformation",
            "orientation reversal",
            "singular collapse",
            "TransformMatchingTex equations",
            "semantic color roles",
            "arrow annotations",
        ],
        "pedagogy_status": pedagogy.status,
        "pedagogy_score": pedagogy.total_score,
        "dimension_scores": {
            item.dimension: item.score for item in pedagogy.dimensions
        },
        "review_status": review["status"],
        "review_warning_count": len(review["warnings"]),
        "review_error_count": len(review["errors"]),
        "fresh_render_count": sum(
            not bool(item.get("cache_hit"))
            for item in result.manifest.renders
        ),
        "performance": performance,
        "final_video_media": review["final_video_media"],
        "custom_python_rate": 0.0,
        "run_dir": str(result.run_dir),
        "video_artifact": str(video),
        "keyframes_artifact": str(keyframes),
        "review_artifact": str(review_artifact),
    }
    destination = ROOT / "artifacts" / "determinant_area_stress_report.json"
    write_json_atomic(destination, report)
    print(destination)
    print(video)
    print(keyframes)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
