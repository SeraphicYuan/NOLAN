"""Clip-from-URL → background library ingest (the seam that makes a clipped range searchable).

After a range is clipped, the route optionally enqueues a LIGHT background ingest job (operations.ingest,
which auto-embeds per step-1) so the clip becomes reusable across future projects — non-blocking, so a
clipping spree isn't held up, and isolated (a failed enqueue never fails the clip)."""
import asyncio
from pathlib import Path

from nolan.webui.jobs import get_job_manager
from nolan.webui.routes.clipper import queue_clip_ingest


def test_queue_clip_ingest_enqueues_ingest_job(tmp_path):
    async def run():
        return queue_clip_ingest(get_job_manager(), tmp_path / "library.db", None, tmp_path / "clip.mp4")
    jid = asyncio.run(run())
    assert jid, "expected an ingest job id"
    match = [j for j in get_job_manager().list(job_type="ingest") if j.id == jid]
    assert match, "clip ingest job not registered in the shared JobManager"
    assert match[0].meta.get("source") == "clipper"
    assert match[0].meta.get("target") == "clip.mp4"


def test_queue_clip_ingest_never_raises_on_bad_manager(tmp_path):
    """A broken/None job manager must not propagate — the clip is already saved; ingest is best-effort."""
    class Broken:
        def start(self, *a, **k):
            raise RuntimeError("manager down")
    assert queue_clip_ingest(Broken(), tmp_path / "lib.db", None, tmp_path / "c.mp4") is None
