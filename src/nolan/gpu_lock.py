"""One GPU, one job at a time — ACROSS PROCESSES.

`webui.jobs.get_gpu_lock()` is an `asyncio.Lock` living in the hub process. That was sufficient while
every GPU consumer was a task on the hub's event loop: ComfyUI generation and OmniVoice TTS both ran
there and took turns.

It stopped being sufficient the moment agents joined the loop. A tmux fleet agent doing a batch edit is
a SEPARATE PROCESS: it imports `nolan.acquire`, calls ComfyUI directly, and never touches the hub's
lock. So an edit-time generation and a hub-side voiceover retake can start at the same instant and
fight over VRAM — and the more parallel the batch loop gets, the more agents there are to collide. A
lock that only some of the contenders can see is not a lock.

So the real mutex is a LOCKFILE, which every process on the machine can see:

    from nolan.gpu_lock import gpu_lock          # sync
    with gpu_lock("comfyui"):
        ...
    from nolan.gpu_lock import gpu_lock_async    # async (does not block the event loop)
    async with gpu_lock_async("tts"):
        ...

`webui.jobs.get_gpu_lock()` is kept and now wraps this, so in-process callers keep their existing
semantics AND become visible to out-of-process ones. Two layers on purpose: the asyncio lock still does
the cheap in-process serialisation, the file lock covers everyone else.

Design notes, each paid for by a failure mode:
  * O_CREAT|O_EXCL, not `fcntl` — this repo is worked from WSL and Windows and `fcntl` does not exist
    on Windows.
  * The holder writes `{pid, host, owner, ts}`, so a stuck lock can be attributed instead of guessed at.
  * A lock is broken when its holder is GONE (pid not alive on this host) or when it is older than
    `stale_after`. A killed agent must not wedge the GPU until someone notices; equally, a legitimately
    long ComfyUI render must not have its lock stolen at an arbitrary timeout — hence checking liveness
    FIRST and treating age as the fallback for a cross-host or unreadable holder.
  * Re-entrant per process: nested acquisitions of the same lock name count up and release once.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import socket
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

# 40 minutes: longer than any single ComfyUI batch or TTS section we produce, short enough that a
# machine left with an orphaned lockfile recovers without a human.
DEFAULT_STALE_AFTER = 2400.0

_local = threading.local()


def lock_dir() -> Path:
    """Where the lockfiles live. Machine-wide (not repo-relative) on purpose: the contenders are the
    hub, fleet agents and CLI runs, which do not share a working directory."""
    d = Path(os.environ.get("NOLAN_LOCK_DIR") or (Path(tempfile.gettempdir()) / "nolan-locks"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pid_alive(pid: int) -> bool:
    """Is this pid running on this machine?

    NOT `os.kill(pid, 0)`. On Windows CPython maps `os.kill` to **TerminateProcess** for any signal
    other than CTRL_C/CTRL_BREAK — so the POSIX liveness idiom is, on the platform this hub actually
    runs on, either an access-denied error (reported as "dead", which then STEALS a live lock) or an
    attempt to kill the holder. It was observed returning "dead" for the calling process's own pid.
    Windows gets `OpenProcess` + `GetExitCodeProcess` instead.

    Every uncertain answer resolves to ALIVE. Waiting a little too long for an abandoned lock costs
    seconds; declaring a live holder dead costs two jobs in the same VRAM."""
    if os.name == "nt":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION, STILL_ACTIVE, ERROR_ACCESS_DENIED = 0x1000, 259, 5
        k = ctypes.windll.kernel32
        h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return k.GetLastError() == ERROR_ACCESS_DENIED      # exists, we just can't query it
        try:
            code = ctypes.c_ulong()
            if k.GetExitCodeProcess(h, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
            return True
        finally:
            k.CloseHandle(h)
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True                                             # exists, owned by someone else
    except (OSError, ValueError, TypeError):
        return True


def _alive(pid: int, host: str) -> bool:
    """Is the recorded holder still running HERE? A holder on a DIFFERENT host always counts as alive,
    so a shared filesystem cannot make two machines steal each other's locks."""
    if host != socket.gethostname():
        return True
    return _pid_alive(pid)


def _holder(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def status(name: str = "gpu") -> Optional[dict]:
    """Who holds the lock right now (with `age` and `alive`), or None if it is free."""
    p = lock_dir() / f"{name}.lock"
    if not p.exists():
        return None
    h = _holder(p) or {}
    try:
        age = time.time() - p.stat().st_mtime
    except OSError:
        age = 0.0
    return {**h, "age": round(age, 1),
            "alive": _alive(int(h.get("pid", -1) or -1), str(h.get("host", "")))}


def _try_acquire(path: Path, owner: str) -> bool:
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    try:
        os.write(fd, json.dumps({"pid": os.getpid(), "host": socket.gethostname(),
                                 "owner": owner, "ts": round(time.time(), 3)}).encode())
    finally:
        os.close(fd)
    return True


def _break_if_dead(path: Path, stale_after: float) -> bool:
    """Remove an abandoned lock. True if it was broken."""
    h = _holder(path)
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return False
    dead = h is not None and not _alive(int(h.get("pid", -1) or -1), str(h.get("host", "")))
    if dead or age > stale_after or h is None:
        path.unlink(missing_ok=True)
        return True
    return False


@contextlib.contextmanager
def gpu_lock(owner: str = "?", name: str = "gpu", timeout: Optional[float] = None,
             stale_after: float = DEFAULT_STALE_AFTER, poll: float = 0.25):
    """Hold the machine-wide GPU lock for the duration of the block. Blocks until acquired.

    `timeout=None` waits indefinitely — the right default for GPU work, because giving up and running
    anyway is exactly the VRAM collision this exists to prevent. Pass a timeout only where proceeding
    without the GPU is a real option, and handle the `TimeoutError`."""
    depth = getattr(_local, "depth", {})
    if depth.get(name):                                   # re-entrant within one process
        depth[name] += 1
        _local.depth = depth
        try:
            yield
        finally:
            depth[name] -= 1
        return
    path = lock_dir() / f"{name}.lock"
    deadline = None if timeout is None else time.time() + timeout
    while not _try_acquire(path, owner):
        if not _break_if_dead(path, stale_after):
            if deadline is not None and time.time() > deadline:
                raise TimeoutError(f"GPU lock {name!r} held by {status(name)} — waited {timeout}s")
            time.sleep(poll)
    depth[name] = 1
    _local.depth = depth
    try:
        yield
    finally:
        depth[name] = 0
        _local.depth = depth
        path.unlink(missing_ok=True)


@contextlib.asynccontextmanager
async def gpu_lock_async(owner: str = "?", name: str = "gpu", timeout: Optional[float] = None,
                         stale_after: float = DEFAULT_STALE_AFTER, poll: float = 0.25):
    """`gpu_lock` for async callers — the wait is `asyncio.sleep`, so the hub's event loop keeps
    serving requests while a fleet agent holds the GPU."""
    depth = getattr(_local, "depth", {})
    if depth.get(name):
        depth[name] += 1
        _local.depth = depth
        try:
            yield
        finally:
            depth[name] -= 1
        return
    path = lock_dir() / f"{name}.lock"
    deadline = None if timeout is None else time.time() + timeout
    while not _try_acquire(path, owner):
        if not _break_if_dead(path, stale_after):
            if deadline is not None and time.time() > deadline:
                raise TimeoutError(f"GPU lock {name!r} held by {status(name)} — waited {timeout}s")
            await asyncio.sleep(poll)
    depth[name] = 1
    _local.depth = depth
    try:
        yield
    finally:
        depth[name] = 0
        _local.depth = depth
        path.unlink(missing_ok=True)
