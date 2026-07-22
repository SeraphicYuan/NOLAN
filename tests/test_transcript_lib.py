"""Transcript library P1 — the schema tier (v9 source_kind/has_footage), overlapping chunking, and
ingest as a transcript-only VideoIndex row (searchable but gated OUT of footage acquisition)."""
import sqlite3
from types import SimpleNamespace

from nolan.indexer import VideoIndex
from nolan.transcript_lib import chunk_transcript, ingest_transcript


def _transcript(cues):
    return SimpleNamespace(chunks=[SimpleNamespace(start=s, end=e, text=t) for s, e, t in cues])


def test_v9_tier_columns_and_footage_gate(tmp_path):
    db = tmp_path / "library.db"
    idx = VideoIndex(db)
    with sqlite3.connect(db) as c:
        cols = {r[1] for r in c.execute("PRAGMA table_info(videos)")}
        ver = c.execute("SELECT version FROM schema_version").fetchone()[0]
    assert ver == VideoIndex.SCHEMA_VERSION >= 9
    assert {"source_kind", "has_footage"} <= cols
    # a normal add_video defaults to the FOOTAGE tier; a marked one drops out of the footage set
    fid = idx.add_video(path="/v.mp4", duration=10, checksum="c", fingerprint="fp-full")
    tid = idx.add_video(path="https://youtu.be/x", duration=20, checksum="yt:x", fingerprint="yt:x")
    idx.mark_source_tier(tid, "transcript", 0)
    footage = idx.footage_video_ids()
    assert fid in footage and tid not in footage
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT source_kind FROM videos WHERE id=?", (fid,)).fetchone()[0] == "full"


def test_chunk_transcript_overlapping_windows():
    cues = [(i * 5.0, i * 5.0 + 5, f"cue{i}") for i in range(12)]     # 0..60s, 5s cues
    w = chunk_transcript(_transcript(cues), window_s=20, overlap_s=5)
    assert w, "expected windows"
    assert all(win["end"] > win["start"] for win in w)
    assert w[0]["start"] == 0.0 and "cue0" in w[0]["text"]
    assert w[-1]["end"] >= 55.0                                       # covers to the end
    assert any(w[i + 1]["start"] < w[i]["end"] for i in range(len(w) - 1)), "windows must overlap"
    assert all(win["end"] - win["start"] <= 25 for win in w)          # ~window_s bounded


def test_chunk_handles_empty_and_oversized_cue():
    assert chunk_transcript(_transcript([])) == []
    big = chunk_transcript(_transcript([(0.0, 120.0, "one very long cue")]), window_s=30)
    assert len(big) == 1 and big[0]["end"] == 120.0                   # a single over-long cue still yields one window


def test_ingest_transcript_creates_gated_rows_and_is_idempotent(tmp_path):
    db = tmp_path / "library.db"
    idx = VideoIndex(db)
    meta = {"video_id": "abc123", "title": "T", "url": "https://youtu.be/abc123"}
    windows = [{"start": 0.0, "end": 20.0, "text": "hello world"},
               {"start": 15.0, "end": 35.0, "text": "more text about markets"}]
    vid = ingest_transcript(idx, meta, windows)
    assert vid and vid not in idx.footage_video_ids()                # transcript tier excluded from footage
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT COUNT(*) FROM segments WHERE video_id=?", (vid,)).fetchone()[0] == 2
        assert c.execute("SELECT source_kind, has_footage FROM videos WHERE id=?", (vid,)).fetchone() == ("transcript", 0)
        assert c.execute("SELECT path FROM videos WHERE id=?", (vid,)).fetchone()[0] == "https://youtu.be/abc123"
    # re-ingest the same video → same id (fingerprint dedup) + NO duplicated segments (clear-then-insert)
    vid2 = ingest_transcript(idx, meta, windows)
    assert vid2 == vid
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT COUNT(*) FROM segments WHERE video_id=?", (vid,)).fetchone()[0] == 2


def test_ingest_no_windows_returns_none(tmp_path):
    idx = VideoIndex(tmp_path / "library.db")
    assert ingest_transcript(idx, {"video_id": "x"}, []) is None


def test_v8_to_v9_upgrade_preserves_existing_rows(tmp_path):
    """Simulate an EXISTING v8 database (videos table WITHOUT the new columns) and confirm opening it
    migrates in place: both columns are added and every pre-existing row defaults to the footage tier
    (has_footage=1) — the real-library upgrade path, non-destructive."""
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE schema_version (version INTEGER)")
        c.execute("INSERT INTO schema_version (version) VALUES (8)")
        c.execute("""CREATE TABLE videos (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     fingerprint TEXT UNIQUE NOT NULL, path TEXT, duration REAL, checksum TEXT,
                     indexed_at TEXT, has_transcript INTEGER DEFAULT 0, project_id TEXT)""")
        c.execute("INSERT INTO videos (fingerprint, path, duration) VALUES ('old1', '/a.mp4', 12.0)")
        c.commit()
    idx = VideoIndex(db)                                       # opening runs the v8 -> v9 migration
    with sqlite3.connect(db) as c:
        cols = {r[1] for r in c.execute("PRAGMA table_info(videos)")}
        assert {"source_kind", "has_footage"} <= cols
        assert c.execute("SELECT version FROM schema_version").fetchone()[0] == 9
        row = c.execute("SELECT source_kind, has_footage FROM videos WHERE fingerprint='old1'").fetchone()
    assert row == ("full", 1)                                 # existing footage row keeps footage tier
    old_id = next(iter(idx.footage_video_ids()))
    assert old_id                                             # and is in the acquisition-eligible set
