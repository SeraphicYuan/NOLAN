"""Unit tests for durable jobs: journal round-trip + startup reattach decisions (pure — no
event loop, no live tmux). The live resume path (attach/finalize) rides the already-proven
pipeline machinery; here we lock down the persistence + reattach *decisions*."""

import json
import time

from nolan.webui.jobs import Job, JobManager


def test_to_record_from_record_roundtrip():
    j = Job(id="abc", type="script-auto", status="running", progress=0.5,
            message="hi", meta={"slug": "x", "durable": True})
    j.logs = ["a", "b"]
    j2 = Job.from_record(j.to_record())
    assert j2.id == "abc" and j2.type == "script-auto" and j2.status == "running"
    assert j2.meta["slug"] == "x" and j2.progress == 0.5 and j2.logs == ["a", "b"]
    assert j2.created_at == j.created_at


def test_persist_only_durable(tmp_path):
    jm = JobManager(journal_dir=tmp_path)
    dur = Job(id="d1", type="script-auto", meta={"durable": True})
    jm._wire(dur); jm._jobs["d1"] = dur; jm._persist(dur)
    non = Job(id="n1", type="render", meta={})
    jm._wire(non); jm._jobs["n1"] = non; jm._persist(non)
    assert (tmp_path / "d1.json").exists()       # durable job journaled
    assert not (tmp_path / "n1.json").exists()   # ordinary job is NOT (can't resume it)


def test_load_journal_restores_jobs(tmp_path):
    rec = {"id": "d1", "type": "script-auto", "status": "running", "progress": 0.4,
           "message": "m", "logs": [], "meta": {"durable": True, "slug": "s"}, "seq": 5,
           "created_at": time.time(), "updated_at": time.time()}
    (tmp_path / "d1.json").write_text(json.dumps(rec), encoding="utf-8")
    jm = JobManager(journal_dir=tmp_path)
    loaded = jm.load_journal()
    assert len(loaded) == 1
    assert jm.get("d1").status == "running" and jm.get("d1").meta["slug"] == "s"


def test_reattach_resumes_fresh_and_fails_stale(tmp_path):
    now = time.time()
    fresh = {"id": "fresh", "type": "script-auto", "status": "running", "progress": 0.4,
             "message": "", "logs": [], "meta": {"durable": True, "slug": "s"}, "seq": 2,
             "created_at": now, "updated_at": now}
    stale = {"id": "stale", "type": "script-auto", "status": "running", "progress": 0.2,
             "message": "", "logs": [], "meta": {"durable": True, "slug": "s"}, "seq": 1,
             "created_at": 0.0, "updated_at": 1.0}
    done = {"id": "done", "type": "script-auto", "status": "done", "progress": 1.0,
            "message": "ok", "logs": [], "meta": {"durable": True, "slug": "s"}, "seq": 3,
            "created_at": now, "updated_at": now}
    for r in (fresh, stale, done):
        (tmp_path / f"{r['id']}.json").write_text(json.dumps(r), encoding="utf-8")

    jm = JobManager(journal_dir=tmp_path)
    calls = []

    def resolver(job):
        calls.append(job.id)
        return None   # None → not resumable; avoids spawning a task (no running loop in test)

    resumed = jm.reattach(resolver, max_age_s=3600)
    assert resumed == []                                   # resolver returned None → nothing launched
    assert calls == ["fresh"]                              # only the fresh in-flight job consulted
    assert jm.get("stale").status == "error" and "stale" in jm.get("stale").message
    assert jm.get("fresh").status == "error"               # resolver said no → interrupted
    assert jm.get("done").status == "done"                 # finished job reloaded as history, untouched
