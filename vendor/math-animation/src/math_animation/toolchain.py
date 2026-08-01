"""Executable discovery and subprocess environments for render workers."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path


def candidate_bin_dirs(python_executable: str | Path | None = None) -> tuple[Path, ...]:
    """Return useful binary directories without assuming an activated shell.

    ``python_executable`` names the interpreter the toolchain belongs to. It
    defaults to this process; pass the render worker's interpreter when the
    render happens somewhere else, so LaTeX/dvisvgm/FFmpeg are looked for beside
    the Manim that will actually use them rather than beside the caller.
    """

    interpreter = Path(python_executable or sys.executable)
    candidates = [
        interpreter.resolve().parent,
        # a conda env on Windows keeps its console programs one level down
        interpreter.resolve().parent / "Scripts",
        interpreter.resolve().parent / "Library" / "bin",
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
    ]
    unique: list[Path] = []
    for candidate in candidates:
        if candidate.is_dir() and candidate not in unique:
            unique.append(candidate)
    return tuple(unique)


def executable_path(
    name: str, python_executable: str | Path | None = None
) -> str | None:
    """Find a render dependency in the interpreter environment or host PATH."""

    for directory in candidate_bin_dirs(python_executable):
        for candidate in (directory / name, directory / f"{name}.exe"):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    return shutil.which(name)


def subprocess_environment(
    python_executable: str | Path | None = None,
) -> dict[str, str]:
    """Build an environment that exposes a coherent TeX toolchain.

    Homebrew's TeX Live installation contains both ``latex`` and ``dvisvgm``.
    It must precede Conda's partial TeX package when Manim spawns subprocesses;
    Python itself is still selected explicitly with ``sys.executable`` and
    standalone composition resolves FFmpeg explicitly.
    """

    environment = os.environ.copy()
    existing_path = environment.get("PATH", "")
    directories = list(candidate_bin_dirs(python_executable))
    interpreter_bin = Path(python_executable or sys.executable).resolve().parent
    host_bins = [path for path in directories if path != interpreter_bin]
    prefixes = [str(path) for path in [*host_bins, interpreter_bin]]
    environment["PATH"] = os.pathsep.join(
        [*prefixes, *([existing_path] if existing_path else [])]
    )
    homebrew_texmf = Path("/opt/homebrew/opt/texlive/share/texmf-dist")
    if homebrew_texmf.is_dir():
        # Homebrew ships dvisvgm as a separate formula. Without these roots its
        # kpathsea lookup is based on the dvisvgm Cellar and misses TeX Live's
        # map/header files even though latex itself works.
        environment["TEXMFCNF"] = str(homebrew_texmf / "web2c")
        environment["TEXMF"] = str(homebrew_texmf)
        cache_root = Path(
            environment.get(
                "MATH_ANIMATION_TEXMF_CACHE",
                str(Path(tempfile.gettempdir()) / "math-animation-texmf"),
            )
        )
        texmf_var_writable = cache_root / "texmf-var"
        texmf_config = cache_root / "texmf-config"
        texmf_home = cache_root / "texmf-home"
        for directory in (texmf_var_writable, texmf_config, texmf_home):
            directory.mkdir(parents=True, exist_ok=True)
        environment["TEXMFVAR"] = str(texmf_var_writable)
        environment["TEXMFCONFIG"] = str(texmf_config)
        environment["TEXMFHOME"] = str(texmf_home)
        texmf_var = homebrew_texmf.parent / "texmf-var" / "web2c"
        format_roots = [f"{texmf_var_writable / 'web2c'}//"]
        if texmf_var.is_dir():
            format_roots.append(f"{texmf_var}//")
        environment["TEXFORMATS"] = os.pathsep.join([*format_roots, ""])
    return environment


def runtime_executable_path(
    name: str, python_executable: str | Path | None = None
) -> str | None:
    """Resolve a program exactly as a spawned Manim process will."""

    environment = subprocess_environment(python_executable)
    return shutil.which(name, path=environment["PATH"])
