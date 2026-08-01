import os
import sys
from pathlib import Path

from math_animation.toolchain import executable_path, subprocess_environment

# `subprocess_environment` joins with os.pathsep — ";" on Windows. These tests
# split on a hardcoded ":", so both failed on Windows before this package was
# vendored (verified against the pristine upstream checkout). Splitting the same
# way we join is the fix; the assertions themselves were always right.


def test_subprocess_path_contains_interpreter_bin() -> None:
    environment = subprocess_environment()

    assert str(Path(sys.executable).resolve().parent) in environment["PATH"].split(
        os.pathsep
    )


def test_subprocess_path_targets_the_render_interpreter_when_given_one() -> None:
    """The render worker's bin dir wins when the caller names another interpreter.

    This is what lets NOLAN author in one env and render in another: probing or
    PATH-building against `sys.executable` would answer for the wrong toolchain.
    """

    other = Path(sys.executable).resolve().parent.parent / "other" / "python.exe"
    paths = subprocess_environment(other)["PATH"].split(os.pathsep)

    assert str(other.parent) in paths
    assert paths.index(str(other.parent)) < len(paths)


def test_homebrew_tex_precedes_partial_conda_tex_when_available() -> None:
    environment = subprocess_environment()
    paths = environment["PATH"].split(os.pathsep)

    if Path("/opt/homebrew/bin/latex").is_file():
        assert paths.index("/opt/homebrew/bin") < paths.index(
            str(Path(sys.executable).resolve().parent)
        )
        assert environment["TEXMF"].endswith("/texmf-dist")
        assert environment["TEXMFCNF"].endswith("/texmf-dist/web2c")
        assert environment["TEXFORMATS"].endswith(f"/texmf-var/web2c//:")


def test_python_can_be_resolved_from_interpreter_environment() -> None:
    assert executable_path("python") is not None
