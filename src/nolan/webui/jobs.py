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
import json
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import uuid4

# Monotonic counter for stable, sortable ordering (we just need ordering, not
# wall-clock). ``created_at``/``updated_at`` carry wall-clock for display + age.
_seq = 0


def _next_seq() -> int:
    global _seq
    _seq += 1
    return _seq


def _now_ts() -> float:
    return time.time()


def _json_safe(v: Any) -> Any:
    """Best-effort JSON-serializable form of a job result for the durable journal."""
    try:
        json.dumps(v)
        return v
    except (TypeError, ValueError):
        return str(v)


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
    created_at: float = field(default_factory=_now_ts)
    updated_at: float = field(default_factory=_now_ts)
    _task: Optional[asyncio.Task] = None
    # Set by the JobManager so mutations flush to the durable journal (durable jobs only).
    _persist_cb: Optional[Callable[[], None]] = field(default=None, repr=False, compare=False)
    _last_persist: float = field(default=0.0, repr=False, compare=False)

    # --- worker-facing helpers -------------------------------------------------
    def set_progress(self, fraction: float, message: Optional[str] = None) -> None:
        self.progress = max(0.0, min(1.0, fraction))
        if message is not None:
            self.message = message
            self.log(message)
        self._touch()

    def log(self, line: str) -> None:
        # Keep the log bounded so a runaway job can't grow memory unbounded.
        self.logs.append(line)
        if len(self.logs) > 1000:
            self.logs = self.logs[-1000:]
        self._touch()

    def _touch(self, *, force: bool = False) -> None:
        """Bump ``updated_at`` and flush to the journal (throttled unless ``force``)."""
        self.updated_at = _now_ts()
        cb = self._persist_cb
        if cb is None:
            return
        if force or (self.updated_at - self._last_persist) >= 8.0:
            self._last_persist = self.updated_at
            try:
                cb()
            except Exception:  # noqa: BLE001 - persistence must never break a job
                pass

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
            "created_at": round(self.created_at, 3),
            "updated_at": round(self.updated_at, 3),
        }
        if include_logs:
            d["logs"] = self.logs[-log_tail:]
            d["log_count"] = len(self.logs)
        return d

    def to_record(self) -> Dict[str, Any]:
        """Full durable serialization written to the on-disk journal."""
        return {
            "id": self.id, "type": self.type, "status": self.status,
            "progress": self.progress, "message": self.message,
            "logs": self.logs[-200:], "result": _json_safe(self.result),
            "error": self.error, "meta": self.meta, "seq": self.seq,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }

    @classmethod
    def from_record(cls, d: Dict[str, Any]) -> "Job":
        """Rebuild a Job from a journal record (no live task)."""
        j = cls(
            id=d["id"], type=d.get("type", "job"), status=d.get("status", "pending"),
            progress=float(d.get("progress", 0.0)), message=d.get("message", ""),
            logs=list(d.get("logs") or []), result=d.get("result"),
            error=d.get("error"), meta=dict(d.get("meta") or {}),
            seq=int(d.get("seq") or _next_seq()),
        )
        j.created_at = float(d.get("created_at") or _now_ts())
        j.updated_at = float(d.get("updated_at") or j.created_at)
        return j


class JobManager:
    """Registry + launcher for background jobs in the hub event loop."""

    def __init__(self, max_jobs: int = 200, journal_dir: Optional[Any] = "projects/_jobs"):
        self._jobs: Dict[str, Job] = {}
        self._max_jobs = max_jobs
        self._journal_dir: Optional[Path] = Path(journal_dir) if journal_dir else None

    # --- durable journal (durable jobs only) -----------------------------------
    def _wire(self, job: Job) -> None:
        job._persist_cb = lambda: self._persist(job)

    def _persist(self, job: Job) -> None:
        if self._journal_dir is None or not job.meta.get("durable"):
            return
        try:
            self._journal_dir.mkdir(parents=True, exist_ok=True)
            tmp = self._journal_dir / f".{job.id}.tmp"
            tmp.write_text(json.dumps(job.to_record(), ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._journal_dir / f"{job.id}.json")   # atomic swap
        except OSError:
            pass

    def _forget(self, job: Job) -> None:
        if self._journal_dir is None:
            return
        try:
            (self._journal_dir / f"{job.id}.json").unlink(missing_ok=True)
        except OSError:
            pass

    async def _run(self, job: Job, worker: Callable[..., Awaitable[Any]],
                   kwargs: Dict[str, Any]) -> None:
        job.status = "running"
        job._touch(force=True)
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
            job._touch(force=True)
            raise
        except Exception as e:  # noqa: BLE001 - surface any failure to the UI
            job.status = "error"
            job.error = str(e)
            job.message = f"Error: {e}"
            job.log(traceback.format_exc())
        finally:
            job._touch(force=True)

    def start(self, job_type: str, worker: Callable[..., Awaitable[Any]],
              meta: Optional[Dict[str, Any]] = None, durable: bool = False, **kwargs) -> Job:
        """Create a job and launch ``worker(job=job, **kwargs)`` as a task.

        ``durable=True`` journals the job to disk so a hub restart can reattach + resume it
        (see :meth:`reattach`)."""
        job = Job(id=uuid4().hex[:12], type=job_type, meta=meta or {})
        if durable:
            job.meta["durable"] = True
        self._jobs[job.id] = job
        self._wire(job)
        self._persist(job)
        self._evict_if_needed()
        job._task = asyncio.get_event_loop().create_task(self._run(job, worker, kwargs))
        return job

    def load_journal(self) -> List[Job]:
        """Reload persisted durable jobs into memory (once, at startup, before reattach)."""
        out: List[Job] = []
        if self._journal_dir is None or not self._journal_dir.exists():
            return out
        global _seq
        for p in sorted(self._journal_dir.glob("*.json")):
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            job = Job.from_record(rec)
            self._jobs[job.id] = job
            self._wire(job)
            _seq = max(_seq, job.seq)   # keep new jobs sorting after reloaded ones
            out.append(job)
        return out

    def reattach(self, resolver: Callable[[Job], Optional[Callable[..., Awaitable[Any]]]],
                 *, max_age_s: float = 3 * 3600) -> List[str]:
        """Reload the journal and resume in-flight durable jobs. ``resolver(job)`` returns a
        worker already bound with its kwargs + ``resume=True`` (invoked as ``worker(job=job)``),
        or ``None`` if the job can't be resumed. Jobs older than ``max_age_s`` are marked failed
        rather than resurrected."""
        resumed: List[str] = []
        for job in self.load_journal():
            if job.status not in ("running", "pending") or not job.meta.get("durable"):
                continue
            age = max(0.0, _now_ts() - float(job.updated_at or job.created_at))
            worker = None if age > max_age_s else resolver(job)
            if worker is None:
                job.status = "error"
                job.message = ("interrupted by restart (stale — re-run)" if age > max_age_s
                               else "interrupted by restart — re-run")
                job._touch(force=True)
                continue
            job.meta["resumed"] = True
            job.status = "running"
            job.message = "resuming after restart…"
            job._touch(force=True)
            job._task = asyncio.get_event_loop().create_task(self._run(job, worker, {}))
            resumed.append(job.id)
        return resumed

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
            self._forget(j)


_manager: Optional[JobManager] = None


def get_job_manager() -> JobManager:
    """Process-wide singleton job manager."""
    global _manager
    if _manager is None:
        _manager = JobManager()
    return _manager


# Process-wide GPU serialization. Both ComfyUI image generation and local TTS
# (OmniVoice) compete for the single GPU's VRAM. They run as tasks on the one hub
# event loop, so a shared asyncio.Lock is enough to ensure only one GPU-heavy job
# runs at a time. Acquire it around the actual GPU work:
#     from nolan.webui.jobs import get_gpu_lock
#     async with get_gpu_lock():
#         ...  # GPU inference (ComfyUI generate / OmniVoice batch)
_gpu_lock: Optional["asyncio.Lock"] = None


def get_gpu_lock() -> "asyncio.Lock":
    """Process-wide async lock serializing GPU work (ComfyUI vs TTS)."""
    global _gpu_lock
    if _gpu_lock is None:
        _gpu_lock = asyncio.Lock()
    return _gpu_lock
