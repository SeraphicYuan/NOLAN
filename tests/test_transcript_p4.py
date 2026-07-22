"""Transcript library P4 — the display sidecar, tier-scoped search, and the routes.

search_transcripts must return ONLY transcript-tier hits (scoped by transcript_video_ids), joined to the
display sidecar for titles + a timestamp deep-link. Routes register and serve through the ASGI layer."""
from pathlib import Path
from types import SimpleNamespace


def test_catalog_roundtrip(tmp_path):
    from nolan import transcript_lib as tl
    tl.record_transcript("vid1", {"title": "Markets Today", "channel": "Bloomberg",
                                  "url": "https://www.youtube.com/watch?v=vid1"}, 12, "Bloomberg",
                         added="2026-01-01T00:00:00", catalog_dir=tmp_path)
    cat = tl.load_catalog(tmp_path)
    assert cat["vid1"]["title"] == "Markets Today" and cat["vid1"]["windows"] == 12
    assert cat["vid1"]["channel"] == "Bloomberg"


def test_search_transcripts_scopes_to_tier_and_joins_titles(tmp_path):
    """Only transcript-tier hits are returned (a footage hit is dropped), each joined to the sidecar
    title with a &t= deep-link to the timestamp."""
    from nolan import transcript_lib as tl

    yid = "dQw4w9WgXcQ"                                   # a realistic 11-char id (extract_video_id validates length)
    url = f"https://www.youtube.com/watch?v={yid}"
    tl.record_transcript(yid, {"title": "Oil & Iran", "channel": "Bloomberg", "url": url}, 5,
                         "Bloomberg", catalog_dir=tmp_path)

    class FakeHit:
        def __init__(self, vid, path, start, score, desc):
            self.video_id, self.video_path, self.timestamp_start = vid, path, start
            self.score, self.description, self.transcript = score, desc, ""

    class FakeIndex:
        def transcript_video_ids(self):
            return {1}                                    # only db-id 1 is a transcript row

    class FakeVS:
        def search(self, query, limit, search_level):
            return [FakeHit(1, url, 95.0, 0.72, "oil prices spike"),
                    FakeHit(2, "/local/footage.mp4", 10.0, 0.9, "unrelated footage")]  # footage → dropped

    res = tl.search_transcripts("iran oil", FakeIndex(), FakeVS(), n=10, catalog_dir=tmp_path)
    assert len(res) == 1                                  # the footage hit (video_id 2) is excluded
    assert res[0]["title"] == "Oil & Iran"
    assert res[0]["watch_url"] == f"{url}&t=95s"          # timestamp deep-link
    assert res[0]["start"] == 95.0 and res[0]["score"] == 0.72


def test_transcripts_routes_register_and_serve():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from nolan.webui.jobs import get_job_manager
    from nolan.webui.routes import transcripts as tr_routes
    app = FastAPI()
    ctx = SimpleNamespace(templates_dir=Path("src/nolan/templates"), db_path=None,
                          job_manager=get_job_manager())
    tr_routes.register(app, ctx)
    c = TestClient(app)
    assert c.get("/api/transcripts/videos").status_code == 200      # browse works even with no db yet
    assert "videos" in c.get("/api/transcripts/videos").json()
    assert c.post("/api/transcripts/add-channel", json={}).status_code == 400   # channel required
