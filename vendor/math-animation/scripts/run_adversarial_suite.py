"""Exercise failure paths that must stop before producing a bad deliverable."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from math_animation.bundle import write_json_atomic
from math_animation.contracts import (
    ActionCue,
    AssetRef,
    BeatSpec,
    CreateAction,
    FormulaSpec,
    IntervalVisualObject,
    MathLedger,
    MathTexVisualObject,
    NarrationInput,
    ParametricSurfaceVisualObject,
    ProjectSpec,
    RenderSettings,
    RequestSpec,
    ResponsiveVisualOverride,
    SceneProgram,
    TextVisualObject,
)
from math_animation.pipeline import AuthoringPipeline


ROOT = Path(__file__).resolve().parents[1]
RUNS = Path("/tmp/math-animation-adversarial")


def _project(
    visual,
    *,
    project_id: str,
    render: RenderSettings | None = None,
    ledger: MathLedger | None = None,
    narration: NarrationInput | None = None,
    assets: list[AssetRef] | None = None,
) -> ProjectSpec:
    return ProjectSpec(
        project_id=project_id,
        title=project_id,
        request=RequestSpec(content=project_id),
        math_ledger=ledger or MathLedger(),
        narration=narration or NarrationInput(),
        assets=assets or [],
        beats=[
            BeatSpec(
                id="beat",
                title="Beat",
                learning_objective="Exercise a failure path.",
                duration_seconds=0.8,
                scene_program=SceneProgram(
                    scene_kind=(
                        "3d"
                        if isinstance(visual, ParametricSurfaceVisualObject)
                        else "2d"
                    ),
                    objects=[visual],
                    cues=[
                        ActionCue(
                            id="show",
                            actions=[
                                CreateAction(target=visual.id, run_time=0.4)
                            ],
                        )
                    ],
                ),
            )
        ],
        render=render or RenderSettings(
            quality="l",
            pixel_width=320,
            pixel_height=240,
            frame_rate=12,
        ),
    )


def _expect_failure(
    name: str,
    operation: Callable[[], object],
    expected: str,
) -> dict[str, str]:
    try:
        operation()
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        if expected.lower() not in detail.lower():
            return {
                "name": name,
                "status": "wrong_failure",
                "detail": detail,
                "expected": expected,
            }
        return {"name": name, "status": "passed", "detail": detail}
    return {
        "name": name,
        "status": "unexpected_success",
        "detail": f"expected failure containing {expected!r}",
    }


def main() -> int:
    cases: list[dict[str, str]] = []
    cases.append(
        _expect_failure(
            "interval-width-mismatch",
            lambda: IntervalVisualObject(
                id="bad-interval",
                start=0,
                end=2,
                expected_width=3,
            ),
            "interval width",
        )
    )

    undersized = TextVisualObject(
        id="tiny",
        text="Too small",
        responsive={
            "portrait": ResponsiveVisualOverride(scale=0.1),
        },
    )
    cases.append(
        _expect_failure(
            "responsive-font-too-small",
            lambda: AuthoringPipeline(runs_dir=RUNS).run(
                _project(
                    undersized,
                    project_id="tiny-font",
                    render=RenderSettings(
                        pixel_width=360,
                        pixel_height=640,
                    ),
                )
            ),
            "effective font size",
        )
    )

    malformed = MathTexVisualObject(
        id="bad-math",
        formula_id="bad-formula",
        latex_parts=[r"\definitelyNotARealCommand{x}"],
    )
    malformed_project = _project(
        malformed,
        project_id="malformed-latex",
        ledger=MathLedger(
            formulas=[
                FormulaSpec(
                    id="bad-formula",
                    latex_parts=[r"\definitelyNotARealCommand{x}"],
                    plain_language="Malformed on purpose.",
                )
            ]
        ),
    )
    cases.append(
        _expect_failure(
            "malformed-latex",
            lambda: AuthoringPipeline(runs_dir=RUNS).run(
                malformed_project,
                render=True,
                use_cache=False,
            ),
            "LaTeX preflight failed",
        )
    )

    nonfinite = ParametricSurfaceVisualObject(
        id="nonfinite",
        u_range=(-1.0, 1.0),
        v_range=(-1.0, 1.0),
        x="u",
        y="v",
        z="1/(u-u)",
        resolution=(4, 4),
        assertion_samples=3,
    )
    cases.append(
        _expect_failure(
            "nonfinite-surface",
            lambda: AuthoringPipeline(runs_dir=RUNS).run(
                _project(nonfinite, project_id="nonfinite-surface"),
                render=True,
                use_cache=False,
            ),
            "contains non-finite samples",
        )
    )

    missing_asset = AssetRef(
        id="missing",
        path="/tmp/math-animation-definitely-missing.png",
        media_type="image",
    )
    cases.append(
        _expect_failure(
            "missing-asset",
            lambda: AuthoringPipeline(runs_dir=RUNS).run(
                _project(
                    TextVisualObject(id="title", text="Missing asset"),
                    project_id="missing-asset",
                    assets=[missing_asset],
                ),
                render=True,
                use_cache=False,
            ),
            "missing local input",
        )
    )

    missing_audio_project = _project(
        TextVisualObject(id="title", text="Missing audio"),
        project_id="missing-audio",
        narration=NarrationInput(
            audio_path="/tmp/math-animation-definitely-missing.wav"
        ),
    )
    cases.append(
        _expect_failure(
            "missing-audio",
            lambda: AuthoringPipeline(runs_dir=RUNS).run(
                missing_audio_project,
                render=True,
                compose=True,
                use_cache=False,
            ),
            "narration audio",
        )
    )

    timeout_project = _project(
        TextVisualObject(id="title", text="Timeout"),
        project_id="render-timeout",
    )
    cases.append(
        _expect_failure(
            "render-timeout",
            lambda: AuthoringPipeline(
                runs_dir=RUNS,
                render_timeout_seconds=0.001,
            ).run(
                timeout_project,
                render=True,
                use_cache=False,
            ),
            "timed out",
        )
    )

    status = (
        "passed"
        if all(case["status"] == "passed" for case in cases)
        else "failed"
    )
    report = {
        "schema_version": "math-animation.adversarial.v1",
        "status": status,
        "cases": cases,
    }
    destination = ROOT / "artifacts" / "adversarial_report.json"
    write_json_atomic(destination, report)
    print(destination)
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
