"""VideoIndex.delete_video — a COMPLETE cleanup of one ingested video. The schema declares ON DELETE
CASCADE but never sets PRAGMA foreign_keys=ON, so a bare `DELETE FROM videos` orphans segments/clusters/
shots — these tests prove delete_video leaves NOTHING behind, scoped to just that one video."""
import sqlite3

from nolan.indexer import VideoIndex


def _seed(db):
    """Two videos, each with the full derived-data footprint keyed three different ways."""
    idx = VideoIndex(db)                                     # creates the schema
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO videos (id, fingerprint, path, has_transcript) VALUES (1,'fp1','/v/a.mp4',1)")
        c.execute("INSERT INTO videos (id, fingerprint, path) VALUES (2,'fp2','/v/b.mp4')")
        for vid in (1, 2):
            c.execute("INSERT INTO segments (video_id, frame_description) VALUES (?, 'x')", (vid,))
            c.execute("INSERT INTO segments (video_id, frame_description) VALUES (?, 'y')", (vid,))
            c.execute("INSERT INTO clusters (video_id, cluster_index) VALUES (?, 0)", (vid,))
            c.execute("INSERT INTO shots (video_id, shot_index) VALUES (?, 0)", (vid,))
            c.execute("INSERT INTO video_projects (video_id, project_id) VALUES (?, 'proj')", (vid,))
        c.execute("INSERT INTO saved_clips (id, source_video_path, clip_start, clip_end) VALUES ('c1','/v/a.mp4',0,1)")
        c.execute("INSERT INTO saved_clips (id, source_video_path, clip_start, clip_end) VALUES ('c2','/v/b.mp4',0,1)")
        c.execute("INSERT INTO frame_cache (fingerprint, timestamp, inference_enabled) VALUES ('fp1',1.0,1)")
        c.execute("INSERT INTO frame_cache (fingerprint, timestamp, inference_enabled) VALUES ('fp2',1.0,1)")
        c.execute("INSERT INTO transcript_alignment_cache (fingerprint, transcript_hash, timestamps_hash, aligned_texts)"
                  " VALUES ('fp1','h','t','[]')")
        c.commit()
    return idx


# every table a video's data can live in, and the column it's keyed by
_TABLES = [("videos", "id", 1), ("segments", "video_id", 1), ("clusters", "video_id", 1),
           ("shots", "video_id", 1), ("video_projects", "video_id", 1),
           ("saved_clips", "source_video_path", "/v/a.mp4"),
           ("frame_cache", "fingerprint", "fp1"), ("transcript_alignment_cache", "fingerprint", "fp1")]


def test_delete_video_removes_everything_and_orphans_nothing(tmp_path):
    db = tmp_path / "lib.db"
    idx = _seed(db)
    summary = idx.delete_video(1)

    assert summary["found"] and summary["path"] == "/v/a.mp4"
    t = summary["tables"]
    assert t["videos"] == 1 and t["segments"] == 2 and t["clusters"] == 1 and t["shots"] == 1
    assert t["video_projects"] == 1 and t["saved_clips"] == 1 and t["frame_cache"] == 1
    assert t["transcript_alignment_cache"] == 1

    with sqlite3.connect(db) as c:
        for table, col, val in _TABLES:                     # video 1 gone from EVERY table — no orphans
            n = c.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", (val,)).fetchone()[0]
            assert n == 0, f"{table} orphaned {n} row(s) for the deleted video"


def test_delete_video_leaves_other_videos_untouched(tmp_path):
    db = tmp_path / "lib.db"
    idx = _seed(db)
    idx.delete_video(1)
    with sqlite3.connect(db) as c:                          # video 2's full footprint survives intact
        assert c.execute("SELECT COUNT(*) FROM videos WHERE id=2").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM segments WHERE video_id=2").fetchone()[0] == 2
        assert c.execute("SELECT COUNT(*) FROM shots WHERE video_id=2").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM saved_clips WHERE source_video_path='/v/b.mp4'").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM frame_cache WHERE fingerprint='fp2'").fetchone()[0] == 1


def test_delete_video_missing_id_is_safe(tmp_path):
    idx = _seed(tmp_path / "lib.db")
    assert idx.delete_video(999) == {"video_id": 999, "found": False}


def test_delete_video_route_end_to_end(tmp_path):
    """DELETE /api/library/videos/{path} resolves the path, removes the video + its rows, and 404s on miss."""
    from urllib.parse import quote
    from starlette.testclient import TestClient
    from nolan.hub import create_hub_app
    db = tmp_path / "lib.db"
    VideoIndex(db)
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO videos (id, fingerprint, path) VALUES (1,'fp','/v/a.mp4')")
        c.execute("INSERT INTO segments (video_id, frame_description) VALUES (1,'x')")
        c.execute("INSERT INTO shots (video_id, shot_index) VALUES (1,0)")
        c.commit()
    client = TestClient(create_hub_app(db_path=db, projects_dir=None))
    # unknown path -> 404
    assert client.delete("/api/library/videos/" + quote("/v/nope.mp4", safe="")).status_code == 404
    # real video -> removed, summary returned
    r = client.delete("/api/library/videos/" + quote("/v/a.mp4", safe=""))
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["found"] and s["tables"]["videos"] == 1 and s["tables"]["segments"] == 1 and s["tables"]["shots"] == 1
    with sqlite3.connect(db) as c:                          # gone from the DB (no orphaned segments/shots)
        assert c.execute("SELECT COUNT(*) FROM videos").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM segments").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM shots").fetchone()[0] == 0


def test_delete_video_file_removal_is_opt_in(tmp_path):
    db = tmp_path / "lib.db"
    idx = VideoIndex(db)
    vid_file = tmp_path / "clip.mp4"
    vid_file.write_bytes(b"\0" * 100)
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO videos (id, fingerprint, path) VALUES (1,'fp', ?)", (str(vid_file),))
        c.commit()
    # default: file is KEPT (never nuke footage silently)
    assert idx.delete_video(1)["file_deleted"] is False
    assert vid_file.exists()
    # re-seed + opt in: file removed
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO videos (id, fingerprint, path) VALUES (2,'fp2', ?)", (str(vid_file),))
        c.commit()
    assert idx.delete_video(2, delete_file=True)["file_deleted"] is True
    assert not vid_file.exists()
