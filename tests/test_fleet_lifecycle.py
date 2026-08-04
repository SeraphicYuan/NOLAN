"""Two fleet defects, pinned.

Both were found by an experiment driving the fleet from Windows, and both are the kind that hide:
one fails only on the first call after an idle machine, the other never fails at all — it just
quietly lies on the board.
"""

import subprocess
import time

import pytest

from nolan import fleet


def test_the_first_wsl_call_gets_a_cold_boot_allowance(monkeypatch):
    """MEASURED: `wsl.exe tmux -V` costs 0.09-0.58s once the VM is warm, and exceeds the 8-second
    default on a COLD boot. So the first fleet call after an idle machine raised TimeoutExpired
    and every call after it succeeded — an intermittent that self-conceals on retry, which is how
    a real bug gets written off as a flake."""
    seen = []

    def _fake_run(argv, **kw):
        seen.append((argv, kw.get("timeout")))
        return subprocess.CompletedProcess(argv, 0, "tmux 3.4", "")

    monkeypatch.setattr(fleet.shutil, "which", lambda _: None)      # force the wsl.exe path
    monkeypatch.setattr(fleet.subprocess, "run", _fake_run)
    monkeypatch.setattr(fleet, "_wsl_warm", False)

    fleet._tmux(["-V"])
    assert seen[0][0][0] == "wsl.exe"
    assert seen[0][1] >= fleet._WSL_COLD_START_S, "first wsl call must survive a cold VM boot"

    fleet._tmux(["-V"])                                            # warm now
    assert seen[1][1] < fleet._WSL_COLD_START_S, "the allowance is for the FIRST call only"


def test_native_tmux_never_pays_the_cold_start_allowance(monkeypatch):
    """A WSL-side or Linux caller has no VM to boot; the allowance is scoped to the wsl.exe hop."""
    seen = []
    monkeypatch.setattr(fleet.shutil, "which", lambda _: "/usr/bin/tmux")
    monkeypatch.setattr(fleet.subprocess, "run",
                        lambda argv, **kw: seen.append(kw.get("timeout"))
                        or subprocess.CompletedProcess(argv, 0, "", ""))
    monkeypatch.setattr(fleet, "_wsl_warm", False)
    fleet._tmux(["-V"])
    assert seen[0] < fleet._WSL_COLD_START_S


def _status(dirpath, name, age_h):
    p = dirpath / f"{name}.json"
    p.write_text('{"state":"done","updated_at":%f}' % (time.time() - age_h * 3600),
                 encoding="utf-8")
    return p


def test_clear_ghosts_removes_only_dead_and_old(tmp_path, monkeypatch):
    """Six status files currently sit on the board with `session_alive: False`, the oldest 405
    hours — so a glance at the fleet shows six agents that do not exist. `reap_run_agents` covers
    only the ephemeral `nolan-run-*` namespace and never touches these."""
    monkeypatch.setattr(fleet, "FLEET_DIR", tmp_path)
    monkeypatch.setattr(fleet, "_live_sessions", lambda: ["nolan9"])

    _status(tmp_path, "nolan9", 500)      # ALIVE, however old its file looks
    _status(tmp_path, "nolan1", 500)      # dead + ancient  -> clear
    _status(tmp_path, "nolan2", 2)        # dead but recent -> keep

    cleared = fleet.clear_ghosts("nolan", older_than_s=86400)
    names = {c.split()[0] for c in cleared}
    assert names == {"nolan1"}, cleared
    assert (tmp_path / "nolan9.json").exists(), "a LIVE agent's status is never cleared"
    assert (tmp_path / "nolan2.json").exists(), "a recent report is the record of what it found"


def test_clear_ghosts_kills_nothing(tmp_path, monkeypatch):
    """A ghost has no session left to kill, and its status file is the only record of what the
    agent concluded — throwing that away is a different and less reversible act than reaping a
    session. So this function must never call `kill`."""
    monkeypatch.setattr(fleet, "FLEET_DIR", tmp_path)
    monkeypatch.setattr(fleet, "_live_sessions", lambda: [])
    monkeypatch.setattr(fleet, "kill", lambda *_a, **_k: pytest.fail("clear_ghosts must not kill"))
    _status(tmp_path, "nolan1", 500)
    assert fleet.clear_ghosts("nolan", older_than_s=86400)
