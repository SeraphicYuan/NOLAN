"""The subprocess boundary to the Manim environment.

Manim drags pycairo, manimpango, moderngl, skia-pathops and a LaTeX toolchain,
and installing it into the pipeline env is not a preference question: it landed
numpy 2.5.1 and Pillow 12.3.0, both outside NOLAN's `numpy<2.3` / `Pillow<12`
pins. So it lives in its own conda env and NOLAN shells out for renders only —
the same shape as `npx hyperframes render` and ComfyUI.

Everything else in this package runs in-process with pydantic alone: compile,
math validation, pedagogy, the ledger, the timeline, the cache. Only the actual
Manim invocation and the LaTeX preflight cross the boundary, and the engine
takes the interpreter as a parameter (`vendor/math-animation/CLAUDE.md`).
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ordered candidates for the interpreter that owns Manim + LaTeX. The env var
# wins so a different machine (or a CI box) can point elsewhere without an edit.
_ENV_VAR = "NOLAN_MATHANIM_PYTHON"
_DEFAULT_CANDIDATES = (
    r"D:\env\mas\python.exe",
    r"D:\env\nolan\python.exe",   # if someone deliberately installed it alongside
)


class MathRenderError(RuntimeError):
    """A math clip could not be produced. The message names the cause."""


@dataclass
class RenderResult:
    clip: Path
    run_dir: Path
    duration_seconds: float
    math_status: str
    pedagogy_score: float
    notes: List[str] = field(default_factory=list)


def math_python() -> str:
    """The interpreter that renders. Raises with a fixable message if there is none."""

    override = os.environ.get(_ENV_VAR)
    if override:
        if not Path(override).is_file():
            raise MathRenderError(
                f"{_ENV_VAR}={override!r} does not exist. Point it at the python "
                f"that owns Manim, or unset it to use the default."
            )
        return override
    for candidate in _DEFAULT_CANDIDATES:
        if Path(candidate).is_file() and _has_manim(candidate):
            return candidate
    raise MathRenderError(
        "no interpreter with Manim was found. Install it once:\n"
        "  D:\\env\\mas\\Scripts\\pip.exe install -e \"vendor/math-animation[render]\"\n"
        "  winget install MiKTeX.MiKTeX      (LaTeX + dvisvgm, needed for equations)\n"
        f"then verify with `D:\\env\\mas\\python.exe -m math_animation doctor`, or set "
        f"{_ENV_VAR} to a different interpreter."
    )


def _has_manim(python_executable: str) -> bool:
    from math_animation.renderer import manim_available

    return manim_available(python_executable)


def toolchain_report(python_executable: Optional[str] = None) -> Dict[str, str]:
    """What the render env actually has — the `doctor` check, callable in-process.

    LaTeX is the one that bites: without it every equation fails deep inside a
    Manim subprocess, so it is worth answering before spending a render.
    """

    from math_animation.renderer import manim_available
    from math_animation.toolchain import executable_path, runtime_executable_path

    try:
        python_executable = python_executable or math_python()
    except MathRenderError as exc:
        return {"python": "missing", "detail": str(exc)}
    return {
        "python": python_executable,
        "manim": "available" if manim_available(python_executable) else "missing",
        "ffmpeg": executable_path("ffmpeg", python_executable) or "missing",
        "latex": runtime_executable_path("latex", python_executable) or "missing",
        "dvisvgm": runtime_executable_path("dvisvgm", python_executable) or "missing",
    }


def render_project(
    project: Any,
    *,
    runs_dir: Path,
    timeout_seconds: float = 900,
    review: bool = True,
) -> RenderResult:
    """Compile + render a one-beat project; return the clip and its evidence.

    Review runs SEPARATELY from the pipeline so a review failure degrades to a
    note instead of discarding a clip that already rendered. The review is
    evidence (collision boxes, blank/freeze probes) — valuable, but not a reason
    to throw away twenty seconds of Manim.
    """

    from math_animation.pipeline import AuthoringPipeline

    python_executable = math_python()
    # Only the templates that TYPESET something need TeX. A plotted function, a number line or a
    # geometric scene program renders fine without it, so demand it exactly when it is needed —
    # and say so before the Manim subprocess fails somewhere less legible.
    needs_latex = bool(project.math_ledger.formulas)
    if needs_latex and toolchain_report(python_executable).get("latex") == "missing":
        raise MathRenderError(
            f"{project.project_id!r} typesets {len(project.math_ledger.formulas)} formula(s), but "
            "LaTeX is missing from the render environment — every equation would fail inside Manim. "
            "Install it (`winget install MiKTeX.MiKTeX`) and re-check with "
            f"`{python_executable} -m math_animation doctor`. Templates that typeset nothing "
            "(function_plot, number_line, a geometric scene_program) render without it."
        )

    pipeline = AuthoringPipeline(
        runs_dir=runs_dir,
        render_timeout_seconds=timeout_seconds,
        python_executable=python_executable,
    )
    try:
        result = pipeline.run(project, render=True, compose=False, review=False)
    except Exception as exc:
        raise MathRenderError(
            f"math render failed for {project.project_id!r}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    clip = result.compilation.timeline.clips[0]
    produced = result.run_dir / clip.expected_media_path
    if not produced.is_file() or produced.stat().st_size < 2048:
        raise MathRenderError(
            f"math render produced no usable clip for {project.project_id!r} at "
            f"{produced} — see {result.run_dir / 'logs'}"
        )

    notes: List[str] = []
    if review:
        try:
            from math_animation.review import review_rendered_project

            review_rendered_project(
                project, result.compilation.timeline, result.run_dir, final_video=None
            )
        except Exception as exc:  # evidence is valuable; the clip is already made
            notes.append(
                f"rendered review skipped ({type(exc).__name__}: {exc}) — the clip "
                f"is fine, its collision/blank evidence is not available"
            )

    math_status = "unknown"
    report = result.run_dir / "math_validation.json"
    if report.is_file():
        import json

        try:
            math_status = json.loads(report.read_text(encoding="utf-8")).get(
                "status", "unknown"
            )
        except (json.JSONDecodeError, OSError):
            pass

    return RenderResult(
        clip=produced,
        run_dir=result.run_dir,
        duration_seconds=clip.duration_seconds,
        math_status=math_status,
        pedagogy_score=float(result.pedagogy.total_score),
        notes=notes,
    )


def clip_duration(path: Path) -> Optional[float]:
    """Container duration of a rendered clip, via NOLAN's own ffprobe wrapper.

    Used to VERIFY the frame-exactness the compiler promises rather than trust
    it. A math clip that came out short must fail loudly: the freeze-heal that
    rescues a short b-roll clip would boomerang this one, and a derivation
    played backwards is worse than an honest error.
    """

    try:
        from nolan.hf_qa import _ffmpeg, probe
    except ImportError:
        return None
    if not path.is_file():
        return None
    try:
        return float(probe(path, _ffmpeg()).duration)
    except Exception:
        return None


def stage_clip(source: Path, destination: Path) -> Path:
    """Copy a rendered clip into the composition's own assets, atomically."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    shutil.copy2(source, temporary)
    os.replace(temporary, destination)
    return destination
