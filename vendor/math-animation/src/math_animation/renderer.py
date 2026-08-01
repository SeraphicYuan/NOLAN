"""Local Manim rendering for deterministic block-generated scenes."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from math_animation.contracts import ProjectSpec, TimelineClip
from math_animation.toolchain import subprocess_environment


class RenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderRecord:
    beat_id: str
    command: list[str]
    exit_code: int
    output_path: str
    stdout_path: str
    stderr_path: str
    elapsed_seconds: float

    def to_dict(self) -> dict:
        return {
            "beat_id": self.beat_id,
            "command": self.command,
            "exit_code": self.exit_code,
            "output_path": self.output_path,
            "stdout_path": self.stdout_path,
            "stderr_path": self.stderr_path,
            "elapsed_seconds": self.elapsed_seconds,
        }


_PROBE_CACHE: dict[str, bool] = {}


def manim_available(python_executable: str | Path | None = None) -> bool:
    """Is Manim importable by the interpreter that will actually render?

    With no argument this is the original in-process check. With one, it probes
    that OTHER interpreter — because the render subprocess need not be, and in
    NOLAN deliberately is not, the interpreter running the compiler: Manim drags
    pycairo/manimpango/moderngl/skia-pathops and a LaTeX toolchain, and the
    pipeline env that authors the screenplay has no business carrying them.
    Probing in-process would then answer for the wrong interpreter and fail
    later, deep inside a subprocess, with a confusing error.
    """

    if python_executable is None or str(python_executable) == sys.executable:
        return importlib.util.find_spec("manim") is not None
    key = str(python_executable)
    cached = _PROBE_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        completed = subprocess.run(
            [key, "-c", "import manim"],
            capture_output=True,
            timeout=120,
            check=False,
        )
        found = completed.returncode == 0
    except (OSError, subprocess.SubprocessError):
        found = False
    _PROBE_CACHE[key] = found
    return found


def _find_video(media_dir: Path, extension: str) -> Path | None:
    candidates = [
        path
        for path in media_dir.glob(f"**/*{extension}")
        if "partial_movie_files" not in {part.lower() for part in path.parts}
        and "sections" not in {part.lower() for part in path.parts}
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime_ns) if candidates else None


class ManimRenderer:
    """Render beat clips with Manim, optionally in a SEPARATE interpreter.

    ``python_executable`` defaults to this process, which is the standalone
    behaviour. Point it at another interpreter and the render becomes the
    isolated worker step `docs/ARCHITECTURE.md` asks for: the caller keeps a
    light authoring env and the heavy Manim/LaTeX stack lives on its own.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 1200,
        python_executable: str | Path | None = None,
    ):
        self.timeout_seconds = timeout_seconds
        self.python_executable = str(python_executable or sys.executable)

    def render_clip(
        self,
        project: ProjectSpec,
        run_dir: Path,
        clip: TimelineClip,
    ) -> RenderRecord:
        if not manim_available(self.python_executable):
            raise RenderError(
                f"Manim is not installed for {self.python_executable}. Install "
                "the render extra there: "
                f"{self.python_executable} -m pip install -e '.[render]'"
            )
        source_path = run_dir / clip.source_path
        media_dir = run_dir / "_manim_media" / clip.beat_id
        media_dir.mkdir(parents=True, exist_ok=True)
        log_dir = run_dir / "logs"
        log_dir.mkdir(exist_ok=True)
        stdout_path = log_dir / f"{clip.beat_id}.stdout.log"
        stderr_path = log_dir / f"{clip.beat_id}.stderr.log"
        command = [
            self.python_executable,
            "-m",
            "manim",
            f"-q{project.render.quality}",
            "--renderer",
            project.render.renderer,
            "--media_dir",
            str(media_dir),
            "--progress_bar",
            "none",
            "--seed",
            str(project.render.seed),
        ]
        if project.render.transparent:
            command.append("--transparent")
        command.extend([str(source_path), clip.scene_class])
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=run_dir,
                env=subprocess_environment(self.python_executable),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RenderError(
                f"Manim timed out rendering beat {clip.beat_id!r} after "
                f"{self.timeout_seconds:.0f}s"
            ) from exc
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        if completed.returncode:
            detail = (completed.stderr or completed.stdout)[-6000:]
            raise RenderError(
                f"Manim failed rendering beat {clip.beat_id!r} with exit "
                f"{completed.returncode}:\n{detail}"
            )
        extension = ".mov" if project.render.transparent else ".mp4"
        rendered = _find_video(media_dir, extension)
        if rendered is None or rendered.stat().st_size < 1024:
            raise RenderError(
                f"Manim produced no valid {extension} for beat {clip.beat_id!r}"
            )
        destination = run_dir / clip.expected_media_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rendered, destination)
        return RenderRecord(
            beat_id=clip.beat_id,
            command=command,
            exit_code=completed.returncode,
            output_path=destination.relative_to(run_dir).as_posix(),
            stdout_path=stdout_path.relative_to(run_dir).as_posix(),
            stderr_path=stderr_path.relative_to(run_dir).as_posix(),
            elapsed_seconds=time.perf_counter() - started,
        )
