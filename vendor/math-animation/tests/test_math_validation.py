from __future__ import annotations

from math_animation.contracts import (
    BeatSpec,
    FormulaSpec,
    MathClaim,
    MathLedger,
    ProjectSpec,
    RequestSpec,
    TitleCardBlock,
)
from math_animation.math_validation import validate_math


def test_math_validation_surfaces_unreviewed_claims() -> None:
    project = ProjectSpec(
        project_id="math-review",
        title="Math review",
        request=RequestSpec(content="Review this claim"),
        math_ledger=MathLedger(
            claims=[
                MathClaim(
                    id="claim.derivative",
                    statement="The derivative is a limiting secant slope.",
                )
            ],
            formulas=[
                FormulaSpec(
                    id="formula.derivative",
                    latex_parts=[r"f'(a)", "=", r"\lim_{h\to0}"],
                    plain_language="The derivative is the limiting slope.",
                )
            ],
        ),
        beats=[
            BeatSpec(
                id="intro",
                title="Intro",
                learning_objective="Introduce the idea.",
                duration_seconds=2.0,
                blocks=[
                    TitleCardBlock(
                        id="intro.title",
                        title="Derivative",
                        run_time=1.0,
                        hold_seconds=0.65,
                    )
                ],
            )
        ],
    )
    report = validate_math(project)
    assert report.status == "needs_review"
    assert "claim.derivative" in report.warnings[0]


def test_empty_math_ledger_needs_review() -> None:
    project = ProjectSpec(
        project_id="empty-ledger",
        title="Empty ledger",
        request=RequestSpec(content="A mathematical statement"),
        beats=[
            BeatSpec(
                id="intro",
                title="Intro",
                learning_objective="Introduce the idea.",
                duration_seconds=2.0,
                blocks=[
                    TitleCardBlock(
                        id="intro.title",
                        title="A statement",
                        run_time=1.0,
                        hold_seconds=0.65,
                    )
                ],
            )
        ],
    )
    assert validate_math(project).status == "needs_review"


def test_unsafe_latex_io_command_is_rejected() -> None:
    project = ProjectSpec(
        project_id="unsafe-latex",
        title="Unsafe",
        request=RequestSpec(content="unsafe"),
        math_ledger=MathLedger(
            formulas=[
                FormulaSpec(
                    id="unsafe",
                    latex_parts=[r"\input{/etc/passwd}"],
                    plain_language="unsafe",
                )
            ]
        ),
        beats=[
            BeatSpec(
                id="intro",
                title="Intro",
                learning_objective="test",
                duration_seconds=1.0,
                blocks=[
                    TitleCardBlock(
                        id="title",
                        title="Unsafe",
                        run_time=0.5,
                    )
                ],
            )
        ],
    )
    report = validate_math(project)
    assert report.status == "failed"
    assert "blocked LaTeX command" in report.errors[0]
