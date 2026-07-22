"""Promote a library segment / saved clip → a project pool (manual pick, skips acquisition ranking).

The worker trims the chosen range from the source video (clipper, local) and registers it in the
project's pool.json exactly as clip-from-url does — so a promoted segment and a URL clip are
indistinguishable in the pool. Route validates comp + a resolvable range (or a saved clip)."""
import asyncio
from pathlib import Path
from types import SimpleNamespace


def test_promote_worker_trims_range_and_registers(tmp_path, monkeypatch):
    import nolan.clipper as clipper_mod
    import nolan.hyperframes.edit as hfedit_mod
    from nolan.webui import operations
    from nolan.webui.jobs import Job

    calls = {}

    def fake_clip(src, start, end, out, kind="local"):
        calls["clip"] = {"src": src, "start": start, "end": end, "out": str(out), "kind": kind}
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"x")
        return Path(out)

    monkeypatch.setattr(clipper_mod, "clip", fake_clip)
    monkeypatch.setattr(hfedit_mod, "comp_dir", lambda c: tmp_path / c)
    monkeypatch.setattr(hfedit_mod, "resolve_asset", lambda comp, path: calls.__setitem__("resolve", (comp, path)))

    src = tmp_path / "vid.mp4"
    src.write_bytes(b"v")

    async def run():
        return await operations.promote_to_pool(Job(id="p", type="promote-to-pool"),
                                                comp="mycomp", video_path=str(src), start=10.0, end=14.0)
    res = asyncio.run(run())
    assert res["ok"] and res["comp"] == "mycomp"
    # trimmed the EXACT range, as a LOCAL cut, into the comp's assets/ as .mp4
    assert calls["clip"]["start"] == 10.0 and calls["clip"]["end"] == 14.0 and calls["clip"]["kind"] == "local"
    assert "assets" in calls["clip"]["out"] and calls["clip"]["out"].endswith(".mp4")
    assert calls["resolve"][0] == "mycomp"          # registered into that project's pool


def test_promote_worker_missing_source_raises(tmp_path):
    from nolan.webui import operations
    from nolan.webui.jobs import Job
    import pytest
    with pytest.raises(RuntimeError):
        asyncio.run(operations.promote_to_pool(Job(id="p", type="promote-to-pool"),
                                               comp="c", video_path=str(tmp_path / "nope.mp4"), start=1, end=2))


def test_promote_route_validation(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from nolan.indexer import VideoIndex
    from nolan.webui.jobs import get_job_manager
    from nolan.webui.routes import library as lib_routes
    db = tmp_path / "library.db"
    VideoIndex(db)                                              # create the DB so the gated routes register
    app = FastAPI()
    ctx = SimpleNamespace(templates_dir=Path("src/nolan/templates"), db_path=db,
                          job_manager=get_job_manager(), repo_root=Path("."))
    lib_routes.register(app, ctx)
    c = TestClient(app)
    assert c.post("/api/library/promote-to-pool", json={}).status_code == 400                 # no comp
    assert c.post("/api/library/promote-to-pool", json={"comp": "x"}).status_code == 400       # no range
    assert c.post("/api/library/promote-to-pool",
                  json={"comp": "x", "video_path": "/v.mp4", "start": 5, "end": 2}).status_code == 400  # end<=start
    assert c.post("/api/library/promote-to-pool",
                  json={"comp": "x", "clip_id": "does-not-exist"}).status_code == 404          # bad clip id
