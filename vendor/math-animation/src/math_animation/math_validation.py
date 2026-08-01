"""Deterministic mathematical artifact checks before visual compilation."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from math_animation.contracts import ProjectSpec, StrictModel


class MathValidationReport(StrictModel):
    status: Literal["passed", "needs_review", "failed"]
    checked_claims: list[str] = Field(default_factory=list)
    checked_formulas: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def _balanced_latex_braces(value: str) -> bool:
    depth = 0
    escaped = False
    for character in value:
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


_BLOCKED_LATEX_COMMANDS = (
    r"\input",
    r"\include",
    r"\openout",
    r"\read",
    r"\write18",
)


def validate_math(project: ProjectSpec) -> MathValidationReport:
    warnings: list[str] = []
    errors: list[str] = []
    checked_claims: list[str] = []
    checked_formulas: list[str] = []

    if not project.math_ledger.claims:
        warnings.append("the project contains no recorded mathematical claims")

    for claim in project.math_ledger.claims:
        checked_claims.append(claim.id)
        if claim.verification == "needs_review":
            warnings.append(f"claim {claim.id!r} still needs mathematical review")
        if claim.verification == "verified" and not claim.evidence:
            warnings.append(
                f"claim {claim.id!r} is marked verified without recorded evidence"
            )

    for formula in project.math_ledger.formulas:
        checked_formulas.append(formula.id)
        for index, part in enumerate(formula.latex_parts):
            if not part.strip():
                errors.append(
                    f"formula {formula.id!r} contains an empty LaTeX part at {index}"
                )
            elif not _balanced_latex_braces(part):
                errors.append(
                    f"formula {formula.id!r} has unbalanced braces in LaTeX part "
                    f"{index}"
                )
            elif any(command in part for command in _BLOCKED_LATEX_COMMANDS):
                errors.append(
                    f"formula {formula.id!r} contains a blocked LaTeX command "
                    f"in part {index}"
                )

    status: Literal["passed", "needs_review", "failed"]
    if errors:
        status = "failed"
    elif warnings:
        status = "needs_review"
    else:
        status = "passed"
    return MathValidationReport(
        status=status,
        checked_claims=checked_claims,
        checked_formulas=checked_formulas,
        warnings=warnings,
        errors=errors,
    )
