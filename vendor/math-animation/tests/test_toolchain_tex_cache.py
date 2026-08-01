from __future__ import annotations

from pathlib import Path

import pytest

from math_animation.toolchain import subprocess_environment

# TEXMFVAR / TEXMFCONFIG / TEXMFHOME are set only inside the Homebrew TeX Live
# branch of `subprocess_environment`. Off macOS that root does not exist, the
# branch never runs, and this file asserted a KeyError — it failed on Windows
# before this package was vendored (verified against the pristine upstream
# checkout). A skip is the honest shape: the claim is about a toolchain layout
# that is genuinely absent, not one this platform violates.
_HOMEBREW_TEXMF = Path("/opt/homebrew/opt/texlive/share/texmf-dist")

requires_homebrew_texlive = pytest.mark.skipif(
    not _HOMEBREW_TEXMF.is_dir(),
    reason=f"no Homebrew TeX Live at {_HOMEBREW_TEXMF} — the branch never runs",
)


@requires_homebrew_texlive
def test_tex_generated_state_uses_writable_cache() -> None:
    environment = subprocess_environment()

    assert Path(environment["TEXMFVAR"]).is_dir()
    assert Path(environment["TEXMFCONFIG"]).is_dir()
    assert Path(environment["TEXMFHOME"]).is_dir()
    assert "/opt/homebrew/Cellar" not in environment["TEXMFVAR"]
    assert environment["TEXFORMATS"].startswith(
        f"{Path(environment['TEXMFVAR']) / 'web2c'}//"
    )


def test_no_tex_overrides_are_invented_without_a_texmf_root() -> None:
    """The other direction: where the branch does NOT run, nothing is fabricated.

    A TEXMFVAR pointing at a directory that does not exist would send a spawned
    LaTeX hunting for formats in the wrong place — worse than leaving the host's
    own TeX configuration alone, which is what MiKTeX on Windows needs.
    """

    if _HOMEBREW_TEXMF.is_dir():
        pytest.skip("Homebrew TeX Live present — covered by the test above")
    environment = subprocess_environment()
    for key in ("TEXMFVAR", "TEXMFCONFIG", "TEXMFHOME", "TEXMF", "TEXMFCNF"):
        assert key not in environment or Path(environment[key]).exists(), (
            f"{key} points at a path that does not exist"
        )
    assert environment["PATH"]
