"""The math-provenance gate — the rules, separate from the step that runs them.

NOLAN already HARD-BLOCKS a data block whose numbers trace to nothing. A wrong
equation in a mathematics explainer is the same failure with higher stakes: the
viewer cannot check it, the whole video is the claim, and a plausible-looking
false step is indistinguishable from a true one at 1080p. So a math scene ships
only when every formula it displays traces to the scene's own authored ledger and
the mathematics is structurally sound.

Three rules, each with the thing it prevents:

  UNAUTHORABLE   the scene does not satisfy its template's contract, so nothing
                 can be built from it (`registry.validate_scene_data`).
  OFF_LEDGER     a `scene_program` paints LaTeX that is not in `data.formulas`.
                 Templates cannot do this — they reference the ledger by index —
                 but a bespoke program carries its own `latex_parts`, and that is
                 exactly the door an invented formula would walk through.
  INVALID_MATH   `math_validation` says `failed`: an empty LaTeX part, unbalanced
                 braces, or a blocked TeX command (`\\input`, `\\write18`).

`assumed` claims — a formula the author wrote without a citation — are ADVISORY,
listed and not blocked. Demanding a citation for `y = x^2 - 6x + 5` would train
authors to paste a fake one, and a gate people learn to defeat is worse than no
gate (docs/WIRING_CHECKLIST.md #11).

Escape for a knowing exception: `HF_ALLOW_UNVERIFIED_MATH=1`.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List

ESCAPE_ENV = "HF_ALLOW_UNVERIFIED_MATH"

# Reasons, so a caller can group and count without matching on prose.
UNAUTHORABLE = "unauthorable"
OFF_LEDGER = "off_ledger"
INVALID_MATH = "invalid_math"

_WS = re.compile(r"\s+")


def _normalize_latex(value: str) -> str:
    """Compare LaTeX by content, not by whitespace.

    `y = x^2` and `y=x^2` are the same formula; a ledger check that called them
    different would fire on every scene and become noise.
    """

    return _WS.sub("", str(value or ""))


def program_latex(program: Any) -> List[str]:
    """Every LaTeX string a SceneProgram will paint.

    Walks the whole structure rather than a fixed key list: MathTex lives on
    objects, `transform_math` carries its own `latex_parts` on an action, and a
    key tuple that missed either would leave exactly the hole this gate exists to
    close (the `visible_text` lesson in `nolan/block_registry.py`).
    """

    found: List[str] = []

    def walk(node: Any, depth: int = 0) -> None:
        if depth > 12:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "latex_parts" and isinstance(value, list):
                    found.extend(str(v) for v in value if isinstance(v, str))
                else:
                    walk(value, depth + 1)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value, depth + 1)

    walk(program)
    return found


def scene_findings(data: Dict[str, Any], where: str) -> List[Dict[str, str]]:
    """Every blocking problem with ONE math scene's authored data.

    Returns dicts of {reason, where, message} — empty means the scene may ship.
    """

    from nolan.mathanim import registry

    findings: List[Dict[str, str]] = []
    for message in registry.validate_scene_data(data, where):
        findings.append({"reason": UNAUTHORABLE, "where": where, "message": message})
    if findings:
        return findings  # nothing else is meaningful until the shape is right

    ledger = {
        _normalize_latex(f.get("latex"))
        for f in (data.get("formulas") or [])
        if isinstance(f, dict)
    }
    if str(data.get("template")) == "scene_program":
        program = (data.get("params") or {}).get("program")
        for latex in program_latex(program):
            if _normalize_latex(latex) not in ledger:
                findings.append(
                    {
                        "reason": OFF_LEDGER,
                        "where": where,
                        "message": (
                            f"the scene program paints {latex!r}, which is not in "
                            f"data.formulas. Add it to the ledger (with what it "
                            f"says, and a citation if you have one) — every formula "
                            f"on screen has to trace to something the author wrote down"
                        ),
                    }
                )
    return findings


def project_findings(project: Any, where: str) -> List[Dict[str, str]]:
    """Blocking problems the ENGINE finds once the scene is built.

    Runs the engine's own `validate_math` rather than re-checking LaTeX here: it
    already knows about unbalanced braces and the TeX commands that read files or
    shell out, and a second implementation would drift from it.
    """

    from math_animation.math_validation import validate_math

    report = validate_math(project)
    if report.status != "failed":
        return []
    return [
        {"reason": INVALID_MATH, "where": where, "message": error}
        for error in report.errors
    ]


def advisories(project: Any, where: str) -> List[str]:
    """Non-blocking notes: which claims rest on the author rather than a source."""

    assumed = [
        claim.id
        for claim in project.math_ledger.claims
        if claim.verification == "assumed"
    ]
    if not assumed:
        return []
    return [
        f"{where}: {len(assumed)} formula(s) are authored assumptions with no "
        f"citation ({', '.join(assumed)}). Add `verified: \"<source>\"` to a "
        f"formula once you have one."
    ]


def escaped() -> bool:
    return bool(os.environ.get(ESCAPE_ENV))


def format_block(findings: Iterable[Dict[str, str]]) -> str:
    """The message the HARD gate raises with — every finding, and what to do."""

    items = list(findings)
    detail = "\n".join(f"    {f['where']}: {f['message']}" for f in items)
    return (
        f"MATH-PROVENANCE GATE — {len(items)} math scene problem(s) that must not "
        f"ship:\n{detail}\n"
        f"  A formula the viewer cannot check has to trace to one the author wrote "
        f"down. Fix the scene's `data.formulas` / `data.params`, or set "
        f"{ESCAPE_ENV}=1 for a knowing exception."
    )
