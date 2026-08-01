"""Local render-worker preflight for files and LaTeX."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from math_animation.contracts import (
    EquationRevealBlock,
    MathTexVisualObject,
    ProjectSpec,
    TransformMathAction,
)
from math_animation.toolchain import executable_path, subprocess_environment


class PreflightError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_local_inputs(project: ProjectSpec, *, require_audio: bool) -> None:
    missing: list[str] = []
    if require_audio and project.narration.audio_path:
        audio = Path(project.narration.audio_path)
        if not audio.is_file():
            missing.append(f"narration audio: {audio}")
    for asset in project.assets:
        path = Path(asset.path)
        if not path.is_file():
            missing.append(f"asset {asset.id!r}: {path}")
            continue
        if asset.sha256 is not None:
            actual = _sha256(path)
            if actual.lower() != asset.sha256.lower():
                raise PreflightError(
                    f"asset {asset.id!r} checksum mismatch: "
                    f"expected {asset.sha256}, got {actual}"
                )
    if missing:
        raise PreflightError("missing local input(s): " + "; ".join(missing))


def _formula_inputs(project: ProjectSpec) -> list[tuple[str, list[str]]]:
    formulas: list[tuple[str, list[str]]] = [
        (formula.id, formula.latex_parts)
        for formula in project.math_ledger.formulas
    ]
    for beat in project.beats:
        for block in beat.blocks:
            if isinstance(block, EquationRevealBlock):
                formulas.append((f"block:{beat.id}/{block.id}", block.latex_parts))
        if beat.scene_program is None:
            continue
        for item in beat.scene_program.objects:
            if isinstance(item, MathTexVisualObject):
                formulas.append((f"object:{beat.id}/{item.id}", item.latex_parts))
        for cue in beat.scene_program.cues:
            for action in cue.actions:
                if isinstance(action, TransformMathAction):
                    formulas.append(
                        (f"action:{beat.id}/{cue.id}", action.latex_parts)
                    )
    unique: dict[tuple[str, ...], str] = {}
    for label, parts in formulas:
        unique.setdefault(tuple(parts), label)
    return [(label, list(parts)) for parts, label in unique.items()]


def validate_latex(
    project: ProjectSpec,
    run_dir: Path,
    python_executable: str | Path | None = None,
) -> dict[str, object]:
    """Compile every unique formula before any expensive scene render begins.

    ``python_executable`` names the render worker's interpreter, so the LaTeX
    this preflight exercises is the same one Manim will call. Preflighting with
    the caller's toolchain would prove nothing about the renderer's.
    """

    # Ask what needs compiling BEFORE demanding the compiler. A project with no formulas — a plotted
    # function, a number line, a geometric scene — renders perfectly without any TeX at all, and
    # refusing it for a missing `latex` sent an entirely satisfiable render away.
    # the caller writes its report into run_dir/preflight/, so that directory has to exist on
    # EVERY path out of here, including the no-formulas one
    destination = run_dir / "preflight" / "latex"
    destination.mkdir(parents=True, exist_ok=True)
    formulas = _formula_inputs(project)
    if not formulas:
        return {
            "schema_version": "math-animation.latex-preflight.v1",
            "status": "passed",
            "checked": [],
            "compiler_invocations": 0,
        }
    latex = executable_path("latex", python_executable)
    if latex is None:
        raise PreflightError("latex executable is required for formula preflight")

    def compile_document(tex_path: Path, body: list[str]) -> subprocess.CompletedProcess:
        source = "\n".join(
            [
                r"\documentclass[preview]{standalone}",
                r"\usepackage{amsmath}",
                r"\usepackage{amssymb}",
                r"\begin{document}",
                *body,
                r"\end{document}",
                "",
            ]
        )
        tex_path.write_text(source, encoding="utf-8")
        return subprocess.run(
            [
                latex,
                "-no-shell-escape",
                "-interaction=batchmode",
                "-halt-on-error",
                f"-output-directory={destination}",
                str(tex_path),
            ],
            env=subprocess_environment(python_executable),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    batch = destination / "all.tex"
    completed = compile_document(
        batch,
        [
            "$" + " ".join(parts) + r"$\par"
            for _, parts in formulas
        ],
    )
    if not completed.returncode:
        return {
            "schema_version": "math-animation.latex-preflight.v1",
            "status": "passed",
            "checked": [label for label, _ in formulas],
            "compiler_invocations": 1,
        }

    # The normal path is one compiler invocation. Only isolate formulas after a
    # batch failure so the error names the exact object/action/ledger entry.
    for index, (label, parts) in enumerate(formulas):
        tex_path = destination / f"{index:03d}.tex"
        completed = compile_document(
            tex_path,
            ["$" + " ".join(parts) + "$"],
        )
        if completed.returncode:
            log_path = destination / f"{index:03d}.log"
            detail = (
                log_path.read_text(encoding="utf-8", errors="replace")
                if log_path.is_file()
                else completed.stderr or completed.stdout
            )
            raise PreflightError(
                f"LaTeX preflight failed for {label!r}: {detail[-2500:]}"
            )
    raise PreflightError(
        "LaTeX batch preflight failed, but every isolated formula compiled; "
        "inspect preflight/latex/all.log for the document-level conflict"
    )
