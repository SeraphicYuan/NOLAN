"""Run the article render toolchain (node / npm / scaffold.sh) in WSL.

NOLAN runs on Windows Python; the reacticle build toolchain is validated under
WSL (node v22, Linux esbuild binaries, the `--no-bin-links` DrvFs workaround).
So we bridge Windows -> WSL with `wsl.exe bash -lc` (login shell, so the user's
nvm-managed node is on PATH), mirroring how `orchestrator.claude_runner` bridges
to WSL claude. On a Linux host we just run bash directly.
"""
from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path


def to_wsl_path(p) -> str:
    """`D:\\a\\b` -> `/mnt/d/a/b`; passthrough for already-POSIX paths."""
    s = str(p)
    if len(s) >= 3 and s[1] == ":" and s[2] in ("\\", "/"):
        return f"/mnt/{s[0].lower()}/{s[3:].replace(chr(92), '/')}"
    return s.replace("\\", "/")


@dataclass
class ShellResult:
    code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def _argv(full: str) -> list[str]:
    return ["wsl.exe", "bash", "-lc", full] if os.name == "nt" else ["bash", "-lc", full]


def _raw(full: str, timeout: int = 60) -> ShellResult:
    """Run a bash -lc string with no node-PATH fixup (used to resolve node)."""
    proc = subprocess.run(_argv(full), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return ShellResult(proc.returncode, proc.stdout or "", proc.stderr or "")


# Login shells expose the system node (often too old for Vite). Resolve the newest
# nvm-managed node ONCE and prepend it to PATH for every toolchain command.
_NODE_PREFIX: str | None = None


def _node_prefix() -> str:
    global _NODE_PREFIX
    if _NODE_PREFIX is None:
        r = _raw("ls -d ~/.nvm/versions/node/*/bin 2>/dev/null | sort -V | tail -1")
        binpath = r.stdout.strip()
        _NODE_PREFIX = f'export PATH="{binpath}:$PATH"; ' if binpath else ""
    return _NODE_PREFIX


def run(cmd: str, cwd, timeout: int = 1800, check: bool = False) -> ShellResult:
    """Run a shell `cmd` inside `cwd` (a Windows or POSIX path) via WSL bash."""
    wsl_cwd = to_wsl_path(cwd)
    full = f"{_node_prefix()}cd {shlex.quote(wsl_cwd)} && {cmd}"
    proc = subprocess.run(_argv(full), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    res = ShellResult(proc.returncode, proc.stdout or "", proc.stderr or "")
    if check and not res.ok:
        raise ShellError(cmd, res)
    return res


class ShellError(RuntimeError):
    def __init__(self, cmd: str, res: ShellResult):
        self.cmd, self.res = cmd, res
        tail = (res.stderr or res.stdout or "")[-800:]
        super().__init__(f"shell failed ({res.code}): {cmd}\n{tail}")


# Windows Chrome for headless screenshots / PDF (the only browser we have).
def chrome_exe() -> str | None:
    for p in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ):
        if Path(p).exists():
            return p
    return None
