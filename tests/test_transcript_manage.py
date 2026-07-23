"""Transcript library management — sources sidecar, per-video delete/detail, frame listing + delete.
(The crawl-level dedup is `if index.get_video_id('yt:<id>')` — implicitly covered: an ingested video's id
resolves, so the worker's skip fires; see the assert in test_delete_and_detail_on_real_index.)"""
import sqlite3
from pathlib import Path


def test_sources_sidecar_roundtrip(tmp_path):
    from nolan import transcript_lib as tl
    ch = "https://youtube.com/@bloomberg"
    tl.upsert_source(ch, label="Bloomberg", last_crawled="2026-01-01T00:00:00", video_count=3, catalog_dir=tmp_path)
    s = tl.load_sources(tmp_path)
    assert ch in s and s[ch]["label"] == "Bloomberg" and s[ch]["video_count"] == 3
    tl.upsert_source(ch, video_count=5, catalog_dir=tmp_path)                 # upsert updates in place
    assert tl.load_sources(tmp_path)[ch]["video_count"] == 5 and tl.load_sources(tmp_path)[ch]["label"] == "Bloomberg"
    assert tl.remove_source(ch, catalog_dir=tmp_path) is True
    assert tl.load_sources(tmp_path) == {}


def test_record_transcript_stores_frame_count(tmp_path):
    from nolan import transcript_lib as tl
    tl.record_transcript("abc", {"title": "T", "url": "https://youtu.be/abc"}, 10, "Ch", frames=7, catalog_dir=tmp_path)
    e = tl.load_catalog(tmp_path)["abc"]
    assert e["windows"] == 10 and e["frames"] == 7


def test_delete_and_detail_on_real_index(tmp_path):
    from nolan import transcript_lib as tl
    from nolan.indexer import VideoIndex
    db = tmp_path / "library.db"
    idx = VideoIndex(db)
    meta = {"video_id": "vidXYZ", "title": "Markets", "url": "https://www.youtube.com/watch?v=vidXYZ"}
    windows = [{"start": 0.0, "end": 20.0, "text": "hello markets"}, {"start": 15.0, "end": 35.0, "text": "more"}]
    tl.ingest_transcript(idx, meta, windows)
    tl.record_transcript("vidXYZ", meta, 2, "MyChannel", frames=0, catalog_dir=tmp_path)
    assert idx.get_video_id("yt:vidXYZ") is not None                          # dedup check would find it → skip on re-crawl

    d = tl.video_detail(idx, "vidXYZ", catalog_dir=tmp_path)                  # detail joins the transcript windows
    assert len(d["windows"]) == 2 and d["windows"][0]["text"] == "hello markets"
    assert d["meta"]["title"] == "Markets" and d["frames"] == []

    summ = tl.delete_transcript(idx, "vidXYZ", catalog_dir=tmp_path)          # delete removes DB rows + catalog
    assert summ.get("catalog") is True
    assert idx.get_video_id("yt:vidXYZ") is None
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT COUNT(*) FROM segments").fetchone()[0] == 0
    assert "vidXYZ" not in tl.load_catalog(tmp_path)


def test_topic_cluster_labels_and_medoid():
    """topic_cluster groups near-subject titles, labels each by distinctive keywords, flags a medoid."""
    from nolan import transcript_lib as tl
    titles = ["FDR presidency documentary", "FDR path to the White House",
              "Kissinger secret war on Cambodia", "How WWII shaped Kissinger",
              "The My Lai Massacre and the Vietnam War"]
    items = [{"video_id": f"v{i}", "url": "", "title": t} for i, t in enumerate(titles)]
    groups = tl.topic_cluster(items, 3)
    assert len(groups) == 3
    assert sum(g["size"] for g in groups) == len(items)                        # partition, nothing dropped
    for g in groups:
        assert g["label"] and g["label"] != "misc"                            # every cluster gets a keyword label
        assert any(it["video_id"] == g["medoid_id"] for it in g["items"])     # medoid is a member
    # the two FDR titles should land together (tight subject)
    fdr = next(g for g in groups if any("FDR" in (it["title"] or "") for it in g["items"]))
    assert sum(1 for it in fdr["items"] if "FDR" in it["title"]) == 2


def test_diverse_sample_one_per_topic(tmp_path, monkeypatch):
    """diverse_sample = NO-LLM recommender: exactly n topic clusters → one medoid each (max spread)."""
    from nolan import transcript_lib as tl
    survey = [{"video_id": f"v{i}", "url": "", "title": t, "in_library": False}
              for i, t in enumerate(["FDR presidency", "FDR White House years", "Kissinger Cambodia war",
                                      "Kissinger and Nixon", "Apollo 11 moon landing", "Dust Bowl migration"])]
    monkeypatch.setattr(tl, "survey_channel", lambda ch, lim=None, cd=None: survey)
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {})                 # empty library → nothing dropped
    out = tl.diverse_sample("ch", n=3)
    assert len(out["picks"]) == 3                                              # exactly n picks
    assert len({p["video_id"] for p in out["picks"]}) == 3                     # distinct videos
    assert all(p["verdict"] == "add" and p["topic"] for p in out["picks"])     # each carries a topic label
    assert out["distinct"] == 6 and out["groups"] == 3


def test_frames_for_video_and_delete(tmp_path):
    from PIL import Image

    from nolan import transcript_frames as tf
    store = tmp_path / "fstore"
    fdir = tmp_path / "f"
    fdir.mkdir()
    a = fdir / "a.jpg"
    Image.new("RGB", (64, 48), (10, 200, 10)).save(a)                        # distinct bytes per video (sha256 dedup)
    b = fdir / "b.jpg"
    Image.new("RGB", (64, 48), (200, 10, 10)).save(b)
    tf.embed_frames([(30.0, a)], "vidAAA", "https://www.youtube.com/watch?v=vidAAA",
                    kind="keyframe", base_dir=store, captions=["a green scene"])
    tf.embed_frames([(60.0, b)], "vidBBB", "https://www.youtube.com/watch?v=vidBBB", kind="keyframe", base_dir=store)

    fr = tf.frames_for_video("vidAAA", base_dir=store)
    assert len(fr) == 1 and fr[0]["t"] == 30.0 and fr[0]["caption"] == "a green scene"
    assert Path(fr[0]["thumb"]).exists()
    assert tf.delete_frames_for_video("vidAAA", base_dir=store) == 1          # deletes only vidAAA
    assert tf.frames_for_video("vidAAA", base_dir=store) == []
    assert len(tf.frames_for_video("vidBBB", base_dir=store)) == 1            # other video untouched
