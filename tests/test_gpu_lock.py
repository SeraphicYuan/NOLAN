"""The GPU mutex must be visible to every process, not just the hub.

`webui.jobs.get_gpu_lock()` was a bare `asyncio.Lock` — correct while every GPU consumer was a task on
the hub's one event loop (ComfyUI generation, OmniVoice TTS). A tmux fleet agent doing a batch edit is a
SEPARATE PROCESS: it calls ComfyUI directly and cannot see that lock, so an edit-time generation and a
hub-side voiceover retake could hit VRAM together. A lock only some contenders can see is not a lock.

The primitive is an O_CREAT|O_EXCL lockfile (not `fcntl` — this tree is worked from WSL and Windows,
and `fcntl` does not exist there).
"""
import json
import os
import socket
import time

import pytest

from nolan import gpu_lock as G


@pytest.fixture(autouse=True)
def isolated_lock_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NOLAN_LOCK_DIR", str(tmp_path / "locks"))
    G._local.depth = {}
    yield


def test_the_lock_is_a_file_every_process_can_see():
    assert G.status("gpu") is None
    with G.gpu_lock(owner="pytest"):
        st = G.status("gpu")
        assert st and st["pid"] == os.getpid() and st["owner"] == "pytest"
        assert (G.lock_dir() / "gpu.lock").exists(), "the mutex must be on the filesystem, not in a heap"
    assert G.status("gpu") is None, "released on exit"


def test_a_second_holder_waits_and_then_gets_it():
    import threading
    order = []

    def worker():
        with G.gpu_lock(owner="b"):
            order.append("b")

    with G.gpu_lock(owner="a"):
        t = threading.Thread(target=worker)
        t.start()
        time.sleep(0.3)
        order.append("a")
    t.join(timeout=5)
    assert order == ["a", "b"], "the second contender must not run while the first holds the GPU"


def test_a_timeout_reports_who_is_holding_it():
    """From ANOTHER thread — the same thread re-enters by design (see the re-entrancy test)."""
    import threading
    err = {}

    def impatient():
        try:
            with G.gpu_lock(owner="impatient", timeout=0.2):
                err["got"] = True
        except TimeoutError as e:
            err["msg"] = str(e)

    with G.gpu_lock(owner="long-render"):
        t = threading.Thread(target=impatient)
        t.start()
        t.join(timeout=5)
    assert "got" not in err, "a waiter must not acquire a held lock"
    assert "long-render" in err.get("msg", ""), "a stuck GPU must be attributable, not guessed at"


def test_reentrant_within_one_process():
    with G.gpu_lock(owner="outer"):
        with G.gpu_lock(owner="inner"):
            assert G.status("gpu")["owner"] == "outer"
        assert G.status("gpu") is not None, "the inner exit must not release the outer hold"
    assert G.status("gpu") is None


def test_a_dead_holder_does_not_wedge_the_gpu():
    """A killed agent must not hold the GPU until a human notices."""
    p = G.lock_dir() / "gpu.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pid": 999_999, "host": socket.gethostname(),
                             "owner": "killed-agent", "ts": time.time()}), encoding="utf-8")
    with G.gpu_lock(owner="next", timeout=3):
        assert G.status("gpu")["owner"] == "next"


def test_a_live_long_render_is_not_stolen_from():
    """Liveness is checked BEFORE age, so a legitimately long ComfyUI render keeps its lock."""
    p = G.lock_dir() / "gpu.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pid": os.getpid(), "host": socket.gethostname(),
                             "owner": "slow-render", "ts": time.time()}), encoding="utf-8")
    with pytest.raises(TimeoutError):
        with G.gpu_lock(owner="thief", timeout=0.2, stale_after=1e9):
            pass
    p.unlink(missing_ok=True)


def test_a_holder_on_another_host_is_never_declared_dead():
    p = G.lock_dir() / "gpu.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pid": 1, "host": "some-other-box", "owner": "remote",
                             "ts": time.time()}), encoding="utf-8")
    assert G.status("gpu")["alive"] is True, \
        "a shared filesystem must not let two machines steal each other's locks"
    p.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_async_holder_does_not_block_the_event_loop():
    import asyncio
    ticks = []

    async def ticker():
        for _ in range(4):
            await asyncio.sleep(0.05)
            ticks.append(1)

    async def holder():
        async with G.gpu_lock_async(owner="tts"):
            await asyncio.sleep(0.25)

    await asyncio.gather(ticker(), holder())
    assert len(ticks) == 4, "the hub must keep serving while a GPU job runs"


def test_the_generation_hook_takes_the_lock():
    """`acquire.context.generate` is the call site a fleet agent reaches from its OWN process —
    the exact path the hub's in-process lock could never cover."""
    import inspect
    from nolan.acquire import context
    src = inspect.getsource(context.build_context)
    assert "from nolan.gpu_lock import gpu_lock" in src
    assert 'gpu_lock(owner="acquire.generate")' in src


def test_the_hub_lock_now_also_takes_the_file_lock():
    import inspect
    from nolan.webui import jobs
    src = inspect.getsource(jobs._GpuLock)
    assert "gpu_lock_async" in src, "the hub must be visible to out-of-process contenders"
