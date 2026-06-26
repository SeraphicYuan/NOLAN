"""In-process job manager for hub-launched, CLI-backed operations.

The hub runs long operations (indexing, essay processing, asset matching,
rendering/assembly) as tracked background jobs so the browser can poll progress
without blocking. Jobs run in the hub's asyncio loop — the underlying NOLAN
modules are importable and already async/progress-aware, so no subprocess is
needed.

Usage (in a FastAPI route):

    jm = get_job_manager()
    job = jm.start("index", _do_index, video_path=..., progress=True)
    return {"job_id": job.id}

The worker coroutine receives a ``job`` keyword it can update via
``job.set_progress(...)`` / ``job.log(...)``; its return value becomes
``job.result``.
"""

from __future__ import annotations

import asyncio
import traceback
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import uuid4

# Monotonic counter for stable, sortable timestamps without Date.now()-style
# nondeterminism concerns (we just need ordering, not wall-clock).
_seq = 0


def _next_seq() -> int:
    global _seq
    _seq += 1
    return _seq


@dataclass
class Job:
    """A single tracked operation."""
    id: str
    type: str
    status: str = "pending"  # pending | running | done | error | cancelled
    progress: float = 0.0  # 0.0 - 1.0
    message: str = ""
    logs: List[str] = field(default_factory=list)
    result: Any = None
    error: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    seq: int = field(default_factory=_next_seq)
    _task: Optional[asyncio.Task] = None

    # --- worker-facing helpers -------------------------------------------------
    def set_progress(self, fraction: float, message: Optional[str] = None) -> None:
        self.progress = max(0.0, min(1.0, fraction))
        if message is not None:
            self.message = message
            self.log(message)

    def log(self, line: str) -> None:
        # Keep the log bounded so a runaway job can't grow memory unbounded.
        self.logs.append(line)
        if len(self.logs) > 1000:
            self.logs = self.logs[-1000:]

    # --- serialization ---------------------------------------------------------
    def to_dict(self, include_logs: bool = True, log_tail: int = 200) -> Dict[str, Any]:
        d = {
            "id": self.id,
            "type": self.type,
            "status": self.status,
            "progress": round(self.progress, 4),
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "meta": self.meta,
            "seq": self.seq,
        }
        if include_logs:
            d["logs"] = self.logs[-log_tail:]
            d["log_count"] = len(self.logs)
        return d


class JobManager:
    """Registry + launcher for background jobs in the hub event loop."""

    def __init__(self, max_jobs: int = 200):
        self._jobs: Dict[str, Job] = {}
        self._max_jobs = max_jobs

    def start(self, job_type: str, worker: Callable[..., Awaitable[Any]],
              meta: Optional[Dict[str, Any]] = None, **kwargs) -> Job:
        """Create a job and launch ``worker(job=job, **kwargs)`` as a task."""
        job = Job(id=uuid4().hex[:12], type=job_type, meta=meta or {})
        self._jobs[job.id] = job
        self._evict_if_needed()

        async def _runner():
            job.status = "running"
            try:
                job.result = await worker(job=job, **kwargs)
                if job.status == "running":
                    job.status = "done"
                    job.progress = 1.0
                    if not job.message:
                        job.message = "Completed"
            except asyncio.CancelledError:
                job.status = "cancelled"
                job.message = "Cancelled"
                raise
            except Exception as e:  # noqa: BLE001 - surface any failure to the UI
                job.status = "error"
                job.error = str(e)
                job.message = f"Error: {e}"
                job.log(traceback.format_exc())

        job._task = asyncio.get_event_loop().create_task(_runner())
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list(self, job_type: Optional[str] = None) -> List[Job]:
        jobs = sorted(self._jobs.values(), key=lambda j: j.seq, reverse=True)
        if job_type:
            jobs = [j for j in jobs if j.type == job_type]
        return jobs

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job and job._task and not job._task.done():
            job._task.cancel()
            return True
        return False

    def _evict_if_needed(self) -> None:
        if len(self._jobs) <= self._max_jobs:
            return
        # Drop the oldest finished jobs first.
        finished = sorted(
            (j for j in self._jobs.values() if j.status in ("done", "error", "cancelled")),
            key=lambda j: j.seq,
        )
        for j in finished[: len(self._jobs) - self._max_jobs]:
            self._jobs.pop(j.id, None)


_manager: Optional[JobManager] = None


def get_job_manager() -> JobManager:
    """Process-wide singleton job manager."""
    global _manager
    if _manager is None:
        _manager = JobManager()
    return _manager
