"""Auto-embed-on-ingest (the 'ingested => searchable' default for the hub /library path).

operations.ingest now chains a SEPARATE background embed job after indexing, via _queue_embed, so a
freshly-ingested video becomes semantically searchable without a manual sync-vectors step — matching
what the CLI `nolan index` already does. The chaining is isolated + loud: an embed-enqueue failure
must never lose the completed index, and an unqueueable video must be flagged (never silent-empty)."""
import asyncio
from pathlib import Path

from nolan.webui import operations
from nolan.webui.jobs import Job, get_job_manager


def test_queue_embed_enqueues_scoped_embed_job(tmp_path):
    """A resolvable video id → a real 'embed-video' job in the shared manager, scoped to that id."""
    class FakeIndex:
        def get_video_id_by_path(self, p):
            return 7

    async def run():
        job = Job(id="ing", type="ingest")
        jid = operations._queue_embed(FakeIndex(), tmp_path / "library.db", tmp_path / "v.mp4", job)
        return jid, job.logs

    jid, logs = asyncio.run(run())
    assert jid, "expected an embed job id"
    assert any("embedding queued" in ln for ln in logs)
    match = [j for j in get_job_manager().list(job_type="embed-video") if j.id == jid]
    assert match, "embed job not registered in the shared JobManager (would be invisible in /jobs)"
    assert match[0].meta.get("video") == "v.mp4"


def test_queue_embed_missing_id_is_loud_and_nonfatal(tmp_path):
    """No video id (e.g. path mismatch) → returns None and logs a LOUD recovery hint; never raises,
    so the completed index survives."""
    class FakeIndex:
        def get_video_id_by_path(self, p):
            return None

    job = Job(id="ing", type="ingest")
    jid = operations._queue_embed(FakeIndex(), tmp_path / "library.db", tmp_path / "v.mp4", job)
    assert jid is None
    assert any("reconcile-vectors" in ln for ln in job.logs)


def test_queue_embed_swallows_lookup_error(tmp_path):
    """An exception during id lookup must not propagate (index already written) — logged, returns None."""
    class ExplodingIndex:
        def get_video_id_by_path(self, p):
            raise RuntimeError("db locked")

    job = Job(id="ing", type="ingest")
    jid = operations._queue_embed(ExplodingIndex(), tmp_path / "library.db", tmp_path / "v.mp4", job)
    assert jid is None
    assert any("embed enqueue failed" in ln for ln in job.logs)


def test_ingest_defaults_embed_true():
    """The default is ON — the signature must default embed=True so ingest auto-embeds unless a caller
    (the route's no_embed escape hatch) explicitly turns it off."""
    import inspect
    sig = inspect.signature(operations.ingest)
    assert sig.parameters["embed"].default is True
