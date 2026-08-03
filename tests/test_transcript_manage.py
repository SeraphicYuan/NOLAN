"""Transcript library management — sources sidecar, per-video delete/detail, frame listing + delete.
(The crawl-level dedup is `if index.get_video_id('yt:<id>')` — implicitly covered: an ingested video's id
resolves, so the worker's skip fires; see the assert in test_delete_and_detail_on_real_index.)"""
import re
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


def test_source_url_resolves_every_reference_shape():
    """Every Sources tile links somewhere real. Archive tiles → the collection page (the `altcensored` /
    `television_inbox` class of tile, which is an archive.org collection the global tier pulled an item
    from, NOT a source anyone added). YouTube tiles → whatever shape the reference is in. A bare uploader
    NAME can't be resolved to a channel URL, so it degrades to a search and says so via exact=False."""
    from nolan import transcript_lib as tl
    assert tl.source_url("television_inbox", "archive") == ("https://archive.org/details/television_inbox", True)
    assert tl.source_url("https://archive.org/details/prelinger", "archive")[0].endswith("/details/prelinger")
    assert tl.source_url("https://www.youtube.com/bloomberg") == ("https://www.youtube.com/bloomberg", True)
    assert tl.source_url("youtube.com/bloomberg") == ("https://youtube.com/bloomberg", True)
    assert tl.source_url("@AmericanExperiencePBS") == ("https://www.youtube.com/@AmericanExperiencePBS", True)
    assert tl.source_url("UC" + "a" * 22) == ("https://www.youtube.com/channel/UC" + "a" * 22, True)
    url, exact = tl.source_url("Christian Sommer")                 # yt-dlp uploader name, not a handle
    assert exact is False and "search_query=Christian+Sommer" in url
    assert tl.source_url("") == ("", False)


def test_sources_view_links_and_derives_kind_from_the_catalog(tmp_path):
    """A derived tile's kind comes from what its videos ARE, so an archive collection can't be linked as a
    YouTube channel just because its id looks like a word."""
    from nolan import transcript_lib as tl
    tl.upsert_source("prelinger", label="Prelinger", kind="archive", copyright_free=True, catalog_dir=tmp_path)
    tl.upsert_source("https://www.youtube.com/bloomberg", label="Bloomberg", catalog_dir=tmp_path)
    tl.record_transcript("p1", {"title": "A"}, 1, "prelinger", kind="archive", catalog_dir=tmp_path)
    tl.record_transcript("p2", {"title": "B"}, 1, "prelinger", kind="archive", catalog_dir=tmp_path)
    tl.record_transcript("t1", {"title": "C"}, 1, "television_inbox", kind="archive", catalog_dir=tmp_path)
    rows = {r["channel"]: r for r in tl.sources_view(tmp_path)}
    assert rows["prelinger"]["managed"] is True and rows["prelinger"]["video_count"] == 2
    assert rows["prelinger"]["url"] == "https://archive.org/details/prelinger"
    assert rows["https://www.youtube.com/bloomberg"]["video_count"] == 0     # no catalog rows -> live count
    d = rows["television_inbox"]                                             # never added: derived tile
    assert d["managed"] is False and d["kind"] == "archive" and d["url_exact"] is True
    assert d["url"] == "https://archive.org/details/television_inbox"


def test_origin_names_why_each_tile_exists(tmp_path):
    """The chip has to answer "I never added this — why is it here?". An archive collection the global
    search attributed → `search`; a channel with videos but no source row → `unregistered`."""
    from nolan import transcript_lib as tl
    tl.upsert_source("prelinger", kind="archive", catalog_dir=tmp_path)
    tl.record_transcript("p1", {"title": "A"}, 1, "prelinger", kind="archive", catalog_dir=tmp_path)
    tl.record_transcript("t1", {"title": "B"}, 1, "television_inbox", kind="archive", catalog_dir=tmp_path)
    tl.record_transcript("y1", {"title": "C"}, 1, "https://www.youtube.com/bloomberg", catalog_dir=tmp_path)
    o = {r["channel"]: r["origin"] for r in tl.sources_view(tmp_path)}
    assert o["prelinger"] == "managed"
    assert o["television_inbox"] == "search"                     # archive.org's own collection, unchosen
    assert o["https://www.youtube.com/bloomberg"] == "unregistered"   # crawled, then the source was removed


def test_channel_facets_gate_promotion_on_a_resolvable_reference(tmp_path):
    """The Indexed-videos filter is where an unregistered channel lives. `promotable` is the honest gate:
    a bare uploader NAME can't be enumerated by list_channel, so offering to register it would create a
    source no sync could ever crawl."""
    from nolan import transcript_lib as tl
    tl.upsert_source("prelinger", kind="archive", catalog_dir=tmp_path)
    tl.record_transcript("p1", {"title": "A"}, 1, "prelinger", kind="archive", catalog_dir=tmp_path)
    tl.record_transcript("t1", {"title": "B"}, 1, "television_inbox", kind="archive", catalog_dir=tmp_path)
    tl.record_transcript("t2", {"title": "C"}, 1, "television_inbox", kind="archive", catalog_dir=tmp_path)
    tl.record_transcript("c1", {"title": "D"}, 1, "Christian Sommer", catalog_dir=tmp_path)
    f = {r["channel"]: r for r in tl.channel_facets(tmp_path)}
    assert [r["channel"] for r in tl.channel_facets(tmp_path)][0] == "television_inbox"   # biggest first
    assert f["prelinger"]["registered"] is True and f["prelinger"]["promotable"] is False
    assert f["television_inbox"]["registered"] is False and f["television_inbox"]["promotable"] is True
    assert f["Christian Sommer"]["promotable"] is False        # uploader name — no sync could crawl it
    assert f["Christian Sommer"]["url_exact"] is False


def test_sources_and_unregistered_channels_are_separate_lists(tmp_path):
    """The Sources registry holds ONLY what someone added; a channel that merely has videos is reported
    as a count and browsed on the video list. Nothing is hidden — the two together cover the catalog."""
    from nolan import transcript_lib as tl
    tl.upsert_source("prelinger", kind="archive", catalog_dir=tmp_path)
    tl.record_transcript("p1", {"title": "A"}, 1, "prelinger", kind="archive", catalog_dir=tmp_path)
    tl.record_transcript("t1", {"title": "B"}, 1, "television_inbox", kind="archive", catalog_dir=tmp_path)
    tl.record_transcript("y1", {"title": "C"}, 1, "https://www.youtube.com/bloomberg", catalog_dir=tmp_path)
    rows = tl.sources_view(tmp_path)
    managed = [r for r in rows if r["origin"] == "managed"]
    unreg = [r for r in rows if r["origin"] != "managed"]
    assert [r["channel"] for r in managed] == ["prelinger"]
    assert sorted(r["channel"] for r in unreg) == ["https://www.youtube.com/bloomberg", "television_inbox"]
    assert sum(r["video_count"] for r in rows) == len(tl.load_catalog(tmp_path))    # nothing dropped
    assert {r["channel"] for r in tl.channel_facets(tmp_path)} == {r["channel"] for r in rows}


def test_remove_source_only_unregisters_but_purge_clears_the_videos(tmp_path):
    """remove_source drops the sources.json row while the videos stay, so the channel doesn't vanish —
    it demotes to `unregistered` and lives on in the video list. purge_source deletes the videos too,
    which is the only thing that removes a channel from the library entirely."""
    from nolan import transcript_lib as tl
    from nolan.indexer import VideoIndex
    ch = "https://www.youtube.com/bloomberg"
    index = VideoIndex(tmp_path / "index.db")
    tl.upsert_source(ch, label="Bloomberg", catalog_dir=tmp_path)
    for v in ("b1", "b2"):
        tl.record_transcript(v, {"title": v}, 1, ch, catalog_dir=tmp_path)

    assert tl.remove_source(ch, catalog_dir=tmp_path) is True
    rows = {r["channel"]: r for r in tl.sources_view(tmp_path)}
    assert ch in rows and rows[ch]["origin"] == "unregistered" and rows[ch]["video_count"] == 2

    out = tl.purge_source(index, ch, catalog_dir=tmp_path)
    assert out["videos"] == 2 and out["deleted"] == 2 and out["errors"] == []
    assert tl.load_catalog(tmp_path) == {} and tl.sources_view(tmp_path) == []


def test_purge_reports_the_rows_it_could_not_delete(tmp_path):
    """No silent caps: a video that fails to delete keeps its catalog row and is NAMED, so the tile
    surviving with a smaller count is explained rather than mysterious."""
    from nolan import transcript_lib as tl
    from nolan.indexer import VideoIndex
    index = VideoIndex(tmp_path / "index.db")
    real = tl.delete_transcript
    tl.record_transcript("ok1", {"title": "A"}, 1, "coll", kind="archive", catalog_dir=tmp_path)
    tl.record_transcript("bad", {"title": "B"}, 1, "coll", kind="archive", catalog_dir=tmp_path)

    def boom(index, vid, catalog_dir=None):
        if vid == "bad":
            raise RuntimeError("locked")
        return real(index, vid, catalog_dir)
    tl.delete_transcript = boom
    try:
        out = tl.purge_source(index, "coll", catalog_dir=tmp_path)
    finally:
        tl.delete_transcript = real
    assert out["videos"] == 2 and out["deleted"] == 1 and len(out["errors"]) == 1
    assert "bad" in out["errors"][0] and "locked" in out["errors"][0]
    assert list(tl.load_catalog(tmp_path)) == ["bad"]            # the failure is still there, not swallowed


def test_record_transcript_stores_frame_count(tmp_path):
    from nolan import transcript_lib as tl
    tl.record_transcript("abc", {"title": "T", "url": "https://youtu.be/abc"}, 10, "Ch", frames=7, catalog_dir=tmp_path)
    e = tl.load_catalog(tmp_path)["abc"]
    assert e["windows"] == 10 and e["frames"] == 7 and e["broll"] is False
    tl.record_transcript("br", {"title": "Ocean Waves 4K"}, 1, "Stock", broll=True, catalog_dir=tmp_path)
    assert tl.load_catalog(tmp_path)["br"]["broll"] is True     # ready-b-roll short clip flag persists


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
    monkeypatch.setattr(tl, "survey_channel", lambda ch, lim=None, cd=None, refresh=False, kind="youtube", collection_free=False: survey)
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {})                 # empty library → nothing dropped
    out = tl.diverse_sample("ch", n=3)
    assert len(out["picks"]) == 3                                              # exactly n picks
    assert len({p["video_id"] for p in out["picks"]}) == 3                     # distinct videos
    assert all(p["verdict"] == "add" and p["topic"] for p in out["picks"])     # each carries a topic label
    assert out["distinct"] == 6 and out["groups"] == 3


def test_survey_persists_and_reuses(tmp_path, monkeypatch):
    """A full survey caches to surveys.json and is reused without re-crawling; in_library stays live; refresh
    re-crawls."""
    from nolan import transcript_lib as tl
    calls = {"n": 0}
    vids = [{"video_id": "a1", "url": "u1", "title": "Doc One"}, {"video_id": "a2", "url": "u2", "title": "Doc Two"}]

    def fake_list(ch, limit=None):
        calls["n"] += 1
        return vids
    monkeypatch.setattr(tl, "list_channel", fake_list)

    r1 = tl.survey_channel("ch", None, tmp_path)                               # first: crawls + caches
    assert calls["n"] == 1 and len(r1) == 2 and all(not x["in_library"] for x in r1)
    assert (tmp_path / "surveys.json").exists()
    r2 = tl.survey_channel("ch", None, tmp_path)                               # second: served from cache
    assert calls["n"] == 1 and [x["video_id"] for x in r2] == ["a1", "a2"]
    assert r2[0]["_cached"]                                                    # carries the fetch timestamp

    tl.record_transcript("a1", {"title": "Doc One", "url": "u1"}, 3, "Ch", catalog_dir=tmp_path)
    r3 = tl.survey_channel("ch", None, tmp_path)                               # in_library recomputed live off catalog
    assert calls["n"] == 1 and next(x for x in r3 if x["video_id"] == "a1")["in_library"] is True

    tl.survey_channel("ch", None, tmp_path, refresh=True)                      # refresh forces a re-crawl
    assert calls["n"] == 2


def test_distinct_candidates_caps_giant_channel(tmp_path, monkeypatch):
    """A ~50k-title channel must not embed every title: _distinct_candidates keeps the newest `cap` and
    reports the rest as dropped (no silent cap)."""
    from nolan import transcript_lib as tl
    survey = [{"video_id": f"v{i}", "url": "", "title": f"News clip number {i}", "in_library": False}
              for i in range(6000)]
    monkeypatch.setattr(tl, "survey_channel", lambda ch, lim=None, cd=None, refresh=False, kind="youtube", collection_free=False: survey)
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {})
    # stub the (expensive) embedding+clustering — this test is about the CAP, not the clustering
    monkeypatch.setattr(tl, "cluster_dedup_candidates",
                        lambda cand, lib, **kw: {"distinct": cand, "dropped_lib": 0,
                                                 "clusters": len(cand), "candidates": len(cand)})
    distinct, stats, _lib, _vecs = tl._distinct_candidates("big", cap=2500)
    assert stats["capped"] == 3500                                            # 6000 - 2500 dropped, reported
    assert stats["candidates"] == 2500 and len(distinct) <= 2500
    assert tl._distinct_candidates("big", cap=0)[1]["capped"] == 0            # cap=0 disables the bound


def test_archive_kind_dispatch_and_copyright_filter(tmp_path, monkeypatch):
    """Archive.org collections dispatch through the shared spine: survey_channel(kind='archive') pulls via the
    adapter, persists kind + rich fields (subject/copyright_free) under a kind-namespaced key, and the
    copyright-free filter drops non-free items."""
    from nolan import transcript_lib as tl
    from nolan import archive_source as ar
    items = [
        {"video_id": "a", "url": "ua", "title": "Atomic Power", "duration": 600, "subject": ["Atomic"],
         "license": "", "copyright_free": True, "description": ""},
        {"video_id": "b", "url": "ub", "title": "Beef Rings", "duration": None, "subject": [],
         "license": "", "copyright_free": False, "description": ""},
        {"video_id": "c", "url": "uc", "title": "Cars Advertising", "duration": 300, "subject": ["Cars"],
         "license": "cc", "copyright_free": True, "description": ""},
    ]
    monkeypatch.setattr(ar, "survey_collection",
                        lambda ref, limit=None, timeout=45.0, collection_free=False: (items, 3))
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {})

    rows = tl.survey_channel("prelinger", None, tmp_path, kind="archive")
    assert len(rows) == 3 and rows[0]["copyright_free"] is True
    assert "archive.org/services/img" in rows[0]["thumb"]                      # archive thumbnail, not youtube
    surveys = tl.load_surveys(tmp_path)
    assert "archive:prelinger" in surveys and surveys["archive:prelinger"]["kind"] == "archive"
    rows2 = tl.survey_channel("prelinger", None, tmp_path, kind="archive")     # cached read keeps rich fields
    assert rows2[0]["_cached"] and rows2[0]["subject"] == ["Atomic"]

    monkeypatch.setattr(tl, "cluster_dedup_candidates",
                        lambda cand, lib, **kw: {"distinct": cand, "dropped_lib": 0,
                                                 "clusters": len(cand), "candidates": len(cand)})
    distinct, stats, _lib, _vecs = tl._distinct_candidates("prelinger", tmp_path, kind="archive", copyright_free_only=True)
    assert stats["dropped_copyright"] == 1 and {d["video_id"] for d in distinct} == {"a", "c"}


def test_archive_pick_derivative_two_tier():
    """Two-tier resolution policy: clip -> highest-quality MP4 (HiRes _edit); caption -> the low-res _512kb.
    Keyed on size+format, NEVER the height field (which lies — a 172MB HiRes reports height=240)."""
    from nolan import archive_source as ar
    files = [
        {"name": "X.avi", "format": "Cinepack", "size": 31_000_000, "height": 320},        # skipped (avi)
        {"name": "X_512kb.mp4", "format": "512Kb MPEG4", "size": 39_000_000, "height": 240},
        {"name": "X.ia.mp4", "format": "h.264 IA", "size": 53_000_000, "height": 480},
        {"name": "X.mp4", "format": "MPEG4", "size": 57_000_000, "height": 480},
        {"name": "X_edit.mp4", "format": "HiRes MPEG4", "size": 172_000_000, "height": 240},  # HiRes; height lies
        {"name": "X.mpeg", "format": "MPEG2", "size": 256_000_000, "height": 368},
    ]
    assert ar.pick_derivative(files, "clip") == "X.ia.mp4"        # faststart h.264 (range-friendly), not HiRes/MPEG2
    assert ar.pick_derivative(files, "caption") == "X_512kb.mp4"  # the intended low derivative
    assert ar.pick_derivative([], "clip") is None
    no_h264 = [{"name": "X_edit.mp4", "format": "HiRes MPEG4", "size": 172_000_000, "height": 240},
               {"name": "Y.mpeg", "format": "MPEG2", "size": 256_000_000, "height": 0}]
    assert ar.pick_derivative(no_h264, "clip") == "X_edit.mp4"    # no h.264 -> largest MP4 (not the raw .mpeg)
    assert "download/X/X_edit.mp4" in ar.download_url("X", "X_edit.mp4")


class _FakeIndex:
    def transcript_video_ids(self):
        return set()


class _FakeVS:
    def search(self, **k):
        return []


def test_suggest_topic_surveyed_tier(monkeypatch, tmp_path):
    """Tier-2 over the PERSISTED title-vector index: rank the surveyed-but-not-ingested corpus, drop
    off-topic (below the floor) + already-ingested, carry the source channel, label 'ingest+caption'."""
    from nolan import transcript_lib as tl
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {"x1": {"frames": 0, "title": "already"}})
    monkeypatch.setattr(tl, "copyright_free_ids", lambda cd=None: set())
    monkeypatch.setattr(tl, "load_surveys", lambda cd=None: {"youtube:c": {
        "kind": "youtube", "channel": "https://www.youtube.com/c", "titles": [
            {"video_id": "s1", "title": "Diamond mining industry", "url": "u1"},
            {"video_id": "s2", "title": "Cooking pasta at home", "url": "u2"},      # off-topic
            {"video_id": "x1", "title": "already ingested", "url": "u3"},           # in catalog → skip
        ]}})
    monkeypatch.setattr(tl, "_embed_titles",
                        lambda titles: [[1.0, 0.0] if "diamond" in t.lower() else [0.0, 1.0] for t in titles])
    d = tl._topic_suggestions(["diamond mining"], "diamond", _FakeIndex(), _FakeVS(), 6, tmp_path, web=False)
    sur = [s for s in d["suggestions"] if s["tier"] == "surveyed"]
    assert d["tier2_mode"] == "vectors" and d["tier2_corpus"] == 2      # x1 excluded (already ingested)
    assert any(s["video_id"] == "s1" and s["action"] == "ingest+caption"
               and s["channel"] == "https://www.youtube.com/c" for s in sur)
    assert not any(s["video_id"] in ("s2", "x1") for s in sur)   # off-topic dropped + already-ingested skipped


def test_topic_vector_index_is_persisted_and_incremental(monkeypatch, tmp_path):
    """The surveyed corpus is embedded ONCE and reused: a second search re-embeds nothing, and a NEW survey
    row tops the index up incrementally. This is what replaced the keyword prefilter + 1500-title budget —
    a search now ranks against the WHOLE corpus instead of the slice the budget could reach."""
    from nolan import transcript_lib as tl
    from nolan import transcript_vectors as tv
    titles = [{"video_id": f"s{i}", "title": f"Diamond film {i}", "url": ""} for i in range(5)]
    surveys = {"archive:c": {"kind": "archive", "channel": "prelinger", "titles": titles}}
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {})
    monkeypatch.setattr(tl, "copyright_free_ids", lambda cd=None: set())
    monkeypatch.setattr(tl, "load_surveys", lambda cd=None: surveys)
    embedded = []

    def fake_embed(ts):
        embedded.extend(ts)
        return [[1.0, 0.0]] * len(ts)
    monkeypatch.setattr(tl, "_embed_titles", fake_embed)

    assert tv.build(tmp_path)["indexed"] == 5 and len(embedded) == 5
    embedded.clear()
    tl._topic_suggestions(["diamond"], "diamond", _FakeIndex(), _FakeVS(), 3, tmp_path, web=False)
    assert embedded == ["diamond"]                                   # only the QUERY — no title re-embedded
    titles.append({"video_id": "s9", "title": "Diamond film 9", "url": ""})
    embedded.clear()
    d = tl._topic_suggestions(["diamond"], "diamond", _FakeIndex(), _FakeVS(), 3, tmp_path, web=False)
    assert "Diamond film 9" in embedded and len([t for t in embedded if t.startswith("Diamond")]) == 1
    assert d["tier2_corpus"] == 6 and d["tier2_pending"] == 0
    assert tv.status(tmp_path)["indexed"] == 6


def test_cold_index_falls_back_to_the_prefilter_and_says_so(monkeypatch, tmp_path):
    """With no vector index and more titles than can be embedded inside a request, tier 2 degrades to the
    keyword-prefilter path and REPORTS the degraded mode + what it dropped — never a silent substitution.
    The prefilter's budget is still spent ROUND-ROBIN, so one 48k-title channel can't starve the archives."""
    from nolan import transcript_lib as tl
    big = [{"video_id": f"b{i}", "title": "atomic bomb news", "url": f"ub{i}"} for i in range(100)]
    arch = [{"video_id": f"a{i}", "title": "Duck and Cover", "url": f"ua{i}",
             "subject": ["Civil defense", "Atomic"], "description": "civil defense film"} for i in range(20)]
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {})
    monkeypatch.setattr(tl, "copyright_free_ids", lambda cd=None: {f"a{i}" for i in range(20)})
    monkeypatch.setattr(tl, "load_surveys", lambda cd=None: {
        "bloomberg": {"titles": big},                              # LEGACY key (kind=None) — same videos…
        "youtube:bloomberg": {"kind": "youtube", "channel": "https://www.youtube.com/bloomberg",
                              "titles": big},                      # …as this kind-namespaced one
        "archive:prelinger": {"kind": "archive", "channel": "prelinger", "titles": arch},
    })
    monkeypatch.setattr(tl, "_PREFILT_BUDGET", 20)
    monkeypatch.setattr(tl, "_embed_titles", lambda titles: [[1.0, 0.0]] * len(titles))
    from nolan import transcript_vectors as tv
    monkeypatch.setattr(tv, "ensure", lambda corpus, cd=None, **k: ([], None, len(corpus)))   # cold index

    d = tl._topic_suggestions(["atomic bomb civil defense"], "civil defense", _FakeIndex(), _FakeVS(),
                              6, tmp_path, web=False)
    assert d["tier2_mode"].startswith("prefilter") and d["tier2_pending"] == 120
    assert d["prefilter_matches"] == 120 and d["prefiltered"] == 20     # 100 big + 20 archive, counted ONCE each
    assert d["prefilter_dropped"] == 100                                # reported, not silently swallowed
    assert d["prefilter_sources"] == {"archive:prelinger": 10, "youtube:bloomberg": 10}   # even split
    assert "bloomberg" not in d["prefilter_sources"]                    # legacy key deduped away by video_id


def test_archive_tier_searches_globally_and_skips_what_we_have(monkeypatch, tmp_path):
    """Tier 3 = GLOBAL archive.org: the reach the local collection surveys can't have. Hits already in the
    catalog or in a survey are dropped (they're tiers 1/2), the query is compacted to 3 content words
    (advancedsearch ANDs its terms), cf-only asks for an asserted licence, and results are ranked on the
    SAME title+subject scale as tier 2 and held to the same floor."""
    from nolan import archive_source as ar
    from nolan import transcript_lib as tl
    asked = []

    def fake_search(q, rows=40, sort="", **k):
        asked.append(q)
        return ([{"video_id": "known1", "url": "u", "title": "diamond doc", "duration": 60,
                  "subject": [], "description": "", "license": "", "copyright_free": True},
                 {"video_id": "surv1", "url": "u", "title": "diamond doc 2", "duration": 60,
                  "subject": [], "description": "", "license": "", "copyright_free": True},
                 {"video_id": "new1", "url": "https://archive.org/details/new1", "title": "diamond mine film",
                  "duration": 900, "subject": ["Mining"], "description": "a film about diamond mining",
                  "license": "publicdomain", "copyright_free": True},
                 {"video_id": "off1", "url": "u", "title": "unrelated cooking show", "duration": 60,
                  "subject": [], "description": "", "license": "", "copyright_free": True}], 4321)
    monkeypatch.setattr(ar, "search_items", fake_search)
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {"known1": {}})
    monkeypatch.setattr(tl, "load_surveys", lambda cd=None: {"archive:c": {"kind": "archive",
                                                                          "titles": [{"video_id": "surv1"}]}})
    monkeypatch.setattr(tl, "_embed_titles",
                        lambda ts: [[1.0, 0.0] if "diamond" in t.lower() else [0.0, 1.0] for t in ts])
    rows, meta = tl._archive_tier(["De Beers diamond mining history in South Africa"], tmp_path, False)
    assert asked == ["beers diamond mining"]                     # 3 content words, stopwords dropped
    assert [r["video_id"] for r in rows] == ["new1"]              # known/surveyed skipped, off-topic floored out
    assert rows[0]["tier"] == "archive" and rows[0]["action"] == "ingest+caption" and rows[0]["kind"] == "archive"
    assert meta["archive_matched"] == 4321 and meta["archive_fetched"] == 2

    asked.clear()
    tl._archive_tier(["diamond mining"], tmp_path, True)          # copyright-free only
    assert asked[0].startswith("diamond mining AND (licenseurl:[* TO *] OR collection:(")


def test_archive_copyright_free_uses_pd_collections_not_just_licence():
    """Only ~18% of even a wholly-PD archive collection carries a per-item `licenseurl`, so filtering the
    global search on that field alone found almost nothing (2 hits for a diamond topic). A PD-BY-NATURE
    collection (US federal works, Prelinger, CC series) is the same curator assertion the library already
    makes when a source is added copyright-free."""
    from nolan import archive_source as ar
    assert ar._row({"identifier": "x", "title": "t", "collection": ["prelinger", "movies"]})["copyright_free"]
    assert ar._row({"identifier": "x", "title": "t", "collection": ["opensource_movies"]})["copyright_free"] is False
    assert ar._row({"identifier": "x", "title": "t", "collection": ["opensource_movies"],
                    "licenseurl": "https://creativecommons.org/licenses/by/4.0/"})["copyright_free"]
    clause = ar.pd_collection_clause()
    assert clause.startswith("(licenseurl:[* TO *] OR collection:(") and "prelinger" in clause


def test_optional_length_filter(monkeypatch, tmp_path):
    """OPTIONAL length gate (off by default): a 90-second clip yields ~4 keyframes, often too thin to be
    worth captioning. Items with UNKNOWN duration are kept — the library never drops a real film over
    missing metadata — and whatever the gate removed is reported."""
    from nolan import transcript_lib as tl
    titles = [{"video_id": "short", "title": "diamond clip", "url": "", "duration": 90},
              {"video_id": "long", "title": "diamond film", "url": "", "duration": 1800},
              {"video_id": "epic", "title": "diamond series", "url": "", "duration": 9000},
              {"video_id": "unknown", "title": "diamond reel", "url": ""}]                # no duration
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {})
    monkeypatch.setattr(tl, "copyright_free_ids", lambda cd=None: set())
    monkeypatch.setattr(tl, "load_surveys", lambda cd=None: {"archive:c": {"kind": "archive",
                                                                          "channel": "c", "titles": titles}})
    monkeypatch.setattr(tl, "_embed_titles", lambda ts: [[1.0, 0.0]] * len(ts))
    monkeypatch.setattr(tl, "_collapse_near_duplicates", lambda rows, vecs=None, thr=0.9: (rows, 0))

    d = tl._topic_suggestions(["diamond"], "diamond", _FakeIndex(), _FakeVS(), 9, tmp_path, web=False)
    assert {s["video_id"] for s in d["suggestions"]} == {"short", "long", "epic", "unknown"}   # default: off
    assert d["length_dropped"] == 0

    d = tl._topic_suggestions(["diamond"], "diamond", _FakeIndex(), _FakeVS(), 9, tmp_path, web=False,
                              min_sec=300)
    assert {s["video_id"] for s in d["suggestions"]} == {"long", "epic", "unknown"}   # unknown SURVIVES
    assert d["length_dropped"] == 1
    assert [s.get("duration") for s in d["suggestions"] if s["video_id"] == "long"] == [1800]

    d = tl._topic_suggestions(["diamond"], "diamond", _FakeIndex(), _FakeVS(), 9, tmp_path, web=False,
                              min_sec=300, max_sec=3600)
    assert {s["video_id"] for s in d["suggestions"]} == {"long", "unknown"} and d["length_dropped"] == 2


def test_resolved_durations_are_paid_once(monkeypatch, tmp_path):
    """A runtime never changes, so a resolve is cached to disk. A filtered search was spending up to 50
    metadata round-trips (25 per tier) and ran ~2.5 min instead of ~25s; the second search must spend none.
    A genuine unknown is remembered too, so it isn't re-asked forever."""
    from nolan import archive_source as ar
    from nolan import transcript_lib as tl
    calls = []
    monkeypatch.setattr(ar, "resolve_duration", lambda i, timeout=20.0: (calls.append(i), 900)[1]
                        if i == "film" else (calls.append(i), None)[1])
    tl._DUR_CACHE.clear()
    assert tl.resolved_duration("film", tmp_path) == 900 and calls == ["film"]
    assert tl.resolved_duration("film", tmp_path) == 900 and calls == ["film"]      # memo, no second call
    assert tl.resolved_duration("nope", tmp_path) is None and calls == ["film", "nope"]
    assert tl.resolved_duration("nope", tmp_path) is None and calls == ["film", "nope"]   # unknown sticks
    tl._DUR_CACHE.clear()                                                            # cold process…
    assert tl.resolved_duration("film", tmp_path) == 900 and calls == ["film", "nope"]  # …still no call


def test_length_filter_resolves_unknown_archive_durations(monkeypatch, tmp_path):
    """An archive row whose crawl cached no `runtime` would sail through the gate on the unknown-is-kept
    rule — live, a 4-minute reel did exactly that. With a filter active, the duration is resolved from the
    metadata API for the few rows that reach the shortlist (bounded), so the gate actually bites."""
    from nolan import archive_source as ar
    from nolan import transcript_lib as tl
    asked = []

    def fake_resolve(ident, timeout=20.0):
        asked.append(ident)
        return 240 if ident == "reel" else 1200
    monkeypatch.setattr(ar, "resolve_duration", fake_resolve)
    titles = [{"video_id": "reel", "title": "diamond reel", "url": ""},        # no duration cached: really 4m
              {"video_id": "film", "title": "diamond film", "url": ""}]        # no duration cached: really 20m
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {})
    monkeypatch.setattr(tl, "copyright_free_ids", lambda cd=None: set())
    monkeypatch.setattr(tl, "load_surveys", lambda cd=None: {"archive:c": {"kind": "archive",
                                                                          "channel": "c", "titles": titles}})
    monkeypatch.setattr(tl, "_embed_titles", lambda ts: [[1.0, 0.0]] * len(ts))
    monkeypatch.setattr(tl, "_collapse_near_duplicates", lambda rows, vecs=None, thr=0.9: (rows, 0))

    d = tl._topic_suggestions(["diamond"], "diamond", _FakeIndex(), _FakeVS(), 9, tmp_path, web=False)
    assert not asked and len(d["suggestions"]) == 2          # NO filter → no metadata calls at all

    d = tl._topic_suggestions(["diamond"], "diamond", _FakeIndex(), _FakeVS(), 9, tmp_path, web=False,
                              min_sec=300)
    assert sorted(asked) == ["film", "reel"] and d["length_dropped"] == 1
    assert [s["video_id"] for s in d["suggestions"]] == ["film"] and d["suggestions"][0]["duration"] == 1200


def test_multivalued_archive_metadata_is_coerced_to_text(monkeypatch, tmp_path):
    """archive.org metadata is MULTI-VALUED: an item with two <description> entries returns a LIST. Every
    consumer downstream (keyword match, embed text, the re-rank prompt) assumes text — an uncoerced list
    crashed 7 of 20 topic searches in the sweep (`'list' object has no attribute 'replace'`)."""
    import asyncio
    from nolan import archive_source as ar
    from nolan import llm as nllm
    from nolan import transcript_lib as tl
    row = ar._row({"identifier": "x", "title": ["Main title", "alt title"],
                   "description": ["first para", "second para"], "subject": ["Mining"]})
    assert row["title"] == "Main title alt title" and row["description"] == "first para second para"

    class FakeLLM:
        model = "m"

        async def generate(self, prompt, system_prompt=None):
            assert "first para" in prompt                      # the list reached the prompt as text
            return '{"items":[{"i":0,"fit":"high","why":"ok"}]}'
    monkeypatch.setattr(nllm, "create_text_llm", lambda cfg, **k: FakeLLM())
    rows = [{"video_id": "x", "title": "t", "score": 0.6, "rrf": 0.01,
             "_desc": ["first para", "second para"], "_subject": ["Mining"]}]
    kept, meta = asyncio.run(tl._rerank_suggestions(rows, "mining", ["mining"], None, tmp_path))
    assert meta["reranked"] and kept[0]["fit"] == "high"


def test_tiers_are_fused_by_rank_not_raw_score():
    """Tier scores live on different scales (segment cosine vs title cosine), so they're fused by RANK.
    A tier's top hit must reach the head of the list even when its raw score is numerically lower."""
    from nolan import transcript_lib as tl
    ingested = [{"video_id": "i1", "title": "a", "score": 0.51, "tier": "ingested"}]      # segment cosine
    surveyed = [{"video_id": "s1", "title": "b", "score": 0.72, "tier": "surveyed"},      # title cosine
                {"video_id": "s2", "title": "c", "score": 0.70, "tier": "surveyed"}]
    fused = tl._fuse_by_rank({"ingested": ingested, "surveyed": surveyed}, 5)
    assert [r["video_id"] for r in fused[:2]] == ["i1", "s1"]     # both rank-1s before the rank-2
    assert fused[0]["rrf"] == fused[1]["rrf"] and fused[2]["rrf"] < fused[0]["rrf"]
    assert fused[0]["score"] == 0.51                             # raw score preserved for display


def test_near_duplicate_reels_collapse():
    """The same film's parts/re-uploads collapse to ONE row (live: 6 of the top 10 cf hits were parts of one
    commercial reel). The best-scoring member survives, and supplied vectors are reused (no re-embedding)."""
    from nolan import transcript_lib as tl
    rows = [{"video_id": "a", "title": "Classic TV Commercials (Part II)", "score": 0.71},
            {"video_id": "b", "title": "Classic TV Commercials (Part III)", "score": 0.73},
            {"video_id": "c", "title": "Duck and Cover", "score": 0.60}]
    vecs = [[1.0, 0.0], [0.999, 0.045], [0.0, 1.0]]
    kept, collapsed = tl._collapse_near_duplicates(rows, vecs)
    assert collapsed == 1 and [r["video_id"] for r in kept] == ["b", "c"]     # best-scoring twin kept


def test_rerank_drops_false_matches_and_fails_open(monkeypatch, tmp_path):
    """The LLM re-rank is a GATE around a proposal: only rows judged `off` are dropped (and counted), the
    rest keep their fused order annotated with fit + why. Cosine alone ranked "Bob Diamond" (a banker) at
    0.609 for a diamonds topic. Any LLM failure is fail-open — the cosine ranking stands and says why."""
    import asyncio
    from nolan import llm as nllm
    from nolan import transcript_lib as tl
    rows = [{"video_id": "a", "title": "Bob Diamond: Rewards in Africa", "score": 0.61, "rrf": 0.02},
            {"video_id": "b", "title": "How De Beers cuts diamonds", "score": 0.60, "rrf": 0.016}]

    class FakeLLM:
        model = "qwen-test"

        async def generate(self, prompt, system_prompt=None):
            assert "Bob Diamond" in prompt and "De Beers" in prompt
            return '{"items":[{"i":0,"fit":"off","why":"a banker, not the gem"},' \
                   '{"i":1,"fit":"high","why":"cutting and polishing footage"}]}'
    monkeypatch.setattr(nllm, "create_text_llm", lambda cfg, **k: FakeLLM())
    kept, meta = asyncio.run(tl._rerank_suggestions(rows, "diamonds", ["diamond cartel"], None, tmp_path))
    assert [r["video_id"] for r in kept] == ["b"] and meta["rerank_dropped"] == 1
    assert kept[0]["fit"] == "high" and kept[0]["why"] == "cutting and polishing footage"
    assert meta["reranked"] and meta["reranker"] == "qwen-test" and meta["rerank_judged"] == 2

    monkeypatch.setattr(nllm, "create_text_llm",
                        lambda cfg, **k: (_ for _ in ()).throw(RuntimeError("no key")))
    kept2, meta2 = asyncio.run(tl._rerank_suggestions(rows, "diamonds", ["diamond cartel"], None, tmp_path))
    assert [r["video_id"] for r in kept2] == ["b"] and meta2["rerank_remembered"] == 2   # memory answered it
    assert "rerank_error" not in meta2 and kept2[0]["fit_remembered"] is True            # no LLM needed
    rows3 = rows + [{"video_id": "c", "title": "Kimberley mine", "score": 0.5, "rrf": 0.01}]
    kept3, meta3 = asyncio.run(tl._rerank_suggestions(rows3, "diamonds", ["diamond cartel"], None, tmp_path))
    assert "no key" in meta3["rerank_error"] and meta3["rerank_remembered"] == 2         # partial failure:
    assert [r["video_id"] for r in kept3] == ["b", "c"]                                  # memory still stands
    kept4, meta4 = asyncio.run(tl._rerank_suggestions(rows, "an unrelated subject", ["x"], None, tmp_path))
    assert kept4 == rows and not meta4["reranked"] and "no key" in meta4["rerank_error"]  # nothing remembered


def test_record_transcript_provenance_is_sticky(tmp_path):
    """kind / copyright_free / broll are only overwritten when the caller ASSERTS them. They used to default
    to ('youtube', False, False), so a re-caption (which knows nothing about the source family) re-labelled a
    Prelinger PD film as copyrighted YouTube — poisoning the acquire engine's provenance marking."""
    from nolan import transcript_lib as tl
    meta = {"title": "Duck and Cover", "url": "https://archive.org/details/duckandcover"}
    tl.record_transcript("dc1", meta, 12, "prelinger", frames=0, added="t0", catalog_dir=tmp_path,
                         kind="archive", copyright_free=True)
    tl.record_transcript("dc1", meta, 12, "prelinger", frames=44, added="t0", catalog_dir=tmp_path)  # re-caption
    row = tl.load_catalog(tmp_path)["dc1"]
    assert row["kind"] == "archive" and row["copyright_free"] is True and row["frames"] == 44
    tl.record_transcript("dc1", meta, 12, "prelinger", frames=44, added="t0", catalog_dir=tmp_path,
                         copyright_free=False)                       # an explicit assertion still wins
    assert tl.load_catalog(tmp_path)["dc1"]["copyright_free"] is False
    tl.record_transcript("new1", meta, 3, "c", catalog_dir=tmp_path)  # a NEW row keeps the old defaults
    new = tl.load_catalog(tmp_path)["new1"]
    assert new["kind"] == "youtube" and new["copyright_free"] is False and new["broll"] is False


def test_keyword_prefilter_matches_at_word_start_only():
    """The prefilter matches WHOLE WORDS (plus common inflections), not any substring: plain `in` made "ring"
    hit "manufacturing", "car" hit "scarcity"/"carbon", "ore" hit "score" — junk that ate the embed budget
    (live: 7,107 keyword "matches" for a diamond topic → 3,527 real ones). Plurals/tenses still match."""
    from nolan import transcript_lib as tl
    m = tl._kw_matcher({"ring", "car", "ore", "mine", "diamond"})
    hit = lambda s: set(m.findall(s.lower()))                              # noqa: E731
    assert not hit("carbon rod manufacturing") and not hit("scarcity of labor") and not hit("score board")
    assert hit("rings of saturn") == {"ring"}                              # plural
    assert hit("mined the diamonds") == {"mine", "diamond"}                # tense + plural
    assert hit("a miner at the car park") == {"mine", "car"}
    assert tl._kw_matcher(set()) is None


def test_topic_cf_filter_runs_before_the_rank_cut(monkeypatch, tmp_path):
    """`copyright-free only` must not be starved by a fixed top-N slice: the cf rows sit BELOW a wall of
    copyrighted ones, so filtering after the cut returned a handful where dozens qualified (live: 231 ranked
    → 8 kept). The walk now stops at the floor or at enough KEPT rows, whichever comes first."""
    import numpy as np
    from nolan import transcript_lib as tl
    paid = [{"video_id": f"p{i}", "title": f"diamond news {i}", "url": ""} for i in range(50)]
    free = [{"video_id": f"f{i}", "title": f"diamond film {i}", "url": ""} for i in range(30)]
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {})
    monkeypatch.setattr(tl, "copyright_free_ids", lambda cd=None: {f"f{i}" for i in range(30)})
    monkeypatch.setattr(tl, "load_surveys", lambda cd=None: {
        "youtube:paid": {"kind": "youtube", "channel": "c1", "titles": paid},
        "archive:free": {"kind": "archive", "channel": "c2", "titles": free}})
    # every paid row scores ABOVE every free row, and all clear the 0.42 floor
    order = {f"diamond news {i}": 0.90 for i in range(50)}
    order.update({f"diamond film {i}": 0.50 for i in range(30)})
    monkeypatch.setattr(tl, "_embed_titles",
                        lambda ts: [[1.0, 0.0] if "diamond mining" in t else [order.get(t, 0.0), 0.0] for t in ts])

    class FakeIndex:
        def transcript_video_ids(self):
            return set()

    class FakeVS:
        def search(self, **k):
            return []
    d = tl._topic_suggestions(["diamond mining"], "diamond", FakeIndex(), FakeVS(), 6, tmp_path, True,
                              web=False)
    assert d["surveyed"] == 30 and all(s["copyright_free"] for s in d["suggestions"])   # every free row
    assert {s["video_id"] for s in d["suggestions"]} <= {f"f{i}" for i in range(30)}    # no paid row leaked


def test_suggest_by_topic_query_provenance(monkeypatch, tmp_path):
    """WHOSE queries ran is reported, and human-edited queries SKIP the LLM entirely: edited > expansion >
    the raw topic. A failed expansion says so (`expand_error`) instead of silently searching the bare topic."""
    import asyncio
    from nolan import llm as nllm
    from nolan import transcript_lib as tl
    calls = []

    class FakeLLM:
        model = "qwen-test"

        async def generate(self, prompt, system_prompt=None):
            calls.append(prompt)
            return '{"queries":["expanded one","expanded two"]}'

    monkeypatch.setattr(nllm, "create_text_llm", lambda cfg, **k: FakeLLM())
    monkeypatch.setattr(tl, "_topic_suggestions",
                        lambda q, t, i, v, n, cd, cf, web=True, *a: {"suggestions": [], "queries": list(q)})

    d = asyncio.run(tl.suggest_by_topic("diamonds, De Beers", None, None, None, catalog_dir=tmp_path))
    assert d["queries"] == ["expanded one", "expanded two"] and len(calls) == 1
    assert d["query_source"] == "llm" and d["expanded"] and d["expander"] == "qwen-test"

    d = asyncio.run(tl.suggest_by_topic("diamonds", None, None, None, catalog_dir=tmp_path,
                                   queries=["jewelry store window", " "]))
    assert d["queries"] == ["jewelry store window"] and len(calls) == 1      # LLM NOT called again
    assert d["query_source"] == "edited" and not d["expanded"] and d["expander"] == ""

    monkeypatch.setattr(nllm, "create_text_llm", lambda cfg, **k: (_ for _ in ()).throw(RuntimeError("no key")))
    d = asyncio.run(tl.suggest_by_topic("diamonds, De Beers", None, None, None, catalog_dir=tmp_path,
                                   refresh_queries=True))
    assert d["queries"] == ["diamonds", "De Beers"]                          # fell back to the typed topic
    assert d["query_source"] == "topic" and "no key" in d["expand_error"]    # loud, not silent


def test_copyright_free_ids_from_sources_and_surveys(monkeypatch):
    """copyright_free_ids = the video ids belonging to a copyright-free source (youtube_cc, or an archive
    collection ADDED copyright-free) — derived from sources × surveys, so the acquire engine marks provenance
    correctly even for rows ingested before per-video flags. Documentary youtube + non-free archive excluded."""
    from nolan import transcript_lib as tl
    monkeypatch.setattr(tl, "load_sources", lambda cd=None: {
        "https://youtube.com/@FreeStock": {"kind": "youtube_cc", "copyright_free": True},
        "https://youtube.com/@Docs": {"kind": "youtube", "copyright_free": False},        # documentary
        "prelinger": {"kind": "archive", "copyright_free": True},
        "somecoll": {"kind": "archive", "copyright_free": False},                          # archive, not asserted free
    })
    monkeypatch.setattr(tl, "load_surveys", lambda cd=None: {
        "youtube_cc:@freestock": {"kind": "youtube_cc", "channel": "https://youtube.com/@FreeStock",
                                  "titles": [{"video_id": "f1"}, {"video_id": "f2"}]},
        "youtube:@docs": {"kind": "youtube", "channel": "https://youtube.com/@Docs", "titles": [{"video_id": "d1"}]},
        "archive:prelinger": {"kind": "archive", "channel": "prelinger", "titles": [{"video_id": "p1"}]},
        "archive:somecoll": {"kind": "archive", "channel": "somecoll", "titles": [{"video_id": "s1"}]},
    })
    assert tl.copyright_free_ids() == {"f1", "f2", "p1"}   # cc stock + free-archive only; not docs, not non-free coll


def test_youtube_cc_family_separate_and_copyright_free(tmp_path, monkeypatch):
    """Copyright-free YouTube channels: youtube MECHANICS but a SEPARATE family (kind-namespaced cache key,
    distinct from documentary youtube of the same channel) with all videos copyright-free."""
    from nolan import transcript_lib as tl
    vids = [{"video_id": "s1", "url": "u1", "title": "Waterfalls Drone Nature", "duration": 300},
            {"video_id": "s2", "url": "u2", "title": "Beaches Sea View", "duration": 420}]
    monkeypatch.setattr(tl, "list_channel", lambda ch, limit=None: vids)
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {})

    rows = tl.survey_channel("@FreeHD", None, tmp_path, kind="youtube_cc", collection_free=True)
    assert len(rows) == 2 and all(r.get("copyright_free") for r in rows)
    assert "i.ytimg.com" in rows[0]["thumb"]                     # youtube thumbnail (youtube mechanics)
    surveys = tl.load_surveys(tmp_path)
    assert "youtube_cc:@freehd" in surveys and "youtube:@freehd" not in surveys   # separate family key

    rows2 = tl.survey_channel("@FreeHD", None, tmp_path, kind="youtube")   # documentary youtube = different row
    assert not rows2[0].get("copyright_free")
    assert "youtube:@freehd" in tl.load_surveys(tmp_path)


def test_length_filter_drops_short_and_keeps_unknown(tmp_path, monkeypatch):
    """min_sec/max_sec gate on duration; runs BEFORE the newest-cap; unknown duration (None) is kept."""
    from nolan import transcript_lib as tl
    survey = [{"video_id": "d1", "url": "", "title": "Long documentary", "duration": 3600, "in_library": False},
              {"video_id": "d2", "url": "", "title": "Short promo clip", "duration": 90, "in_library": False},
              {"video_id": "d3", "url": "", "title": "Mid feature", "duration": 1500, "in_library": False},
              {"video_id": "d4", "url": "", "title": "Unknown length", "duration": None, "in_library": False}]
    monkeypatch.setattr(tl, "survey_channel", lambda ch, lim=None, cd=None, refresh=False, kind="youtube", collection_free=False: survey)
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {})
    monkeypatch.setattr(tl, "cluster_dedup_candidates",                        # isolate the length gate
                        lambda cand, lib, **kw: {"distinct": cand, "dropped_lib": 0,
                                                 "clusters": len(cand), "candidates": len(cand)})
    distinct, stats, _lib, _vecs = tl._distinct_candidates("ch", min_sec=1200)          # 20 min floor
    ids = {d["video_id"] for d in distinct}
    assert ids == {"d1", "d3", "d4"}                                          # d2 (90s) dropped; d4 (None) kept
    assert stats["dropped_length"] == 1
    assert tl._distinct_candidates("ch")[1]["dropped_length"] == 0            # no filter → nothing dropped


def test_coverage_map_gaps_and_strength(tmp_path, monkeypatch):
    """coverage_map clusters library + all-channel candidates into topics; a topic with library rows reads as
    covered, one with only available rows reads as a gap."""
    from nolan import transcript_lib as tl
    # library strongly covers space history; channel offers space + a totally new subject (economics)
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None:
                        {"L1": {"title": "Apollo 11 moon landing"}, "L2": {"title": "The Apollo space program"}})
    chan = [{"video_id": "n1", "url": "", "title": "Apollo astronauts training", "in_library": False},
            {"video_id": "n2", "url": "", "title": "The Great Depression economy", "in_library": False},
            {"video_id": "n3", "url": "", "title": "Wall Street crash and banking", "in_library": False}]
    monkeypatch.setattr(tl, "survey_channel", lambda ch, lim=None, cd=None, refresh=False, kind="youtube", collection_free=False: chan)
    monkeypatch.setattr(tl, "load_sources", lambda cd=None: {"chX": {"label": "TestChan"}})

    cov = tl.coverage_map(k=2, catalog_dir=tmp_path)
    assert cov["lib_total"] == 2 and cov["available_total"] == 3
    assert len(cov["topics"]) == 2
    gaps = [t for t in cov["topics"] if t["lib_count"] == 0 and t["available"] > 0]
    covered = [t for t in cov["topics"] if t["lib_count"] > 0]
    assert gaps and covered                                                   # both a gap and a covered topic exist
    assert cov["gaps"] == len(gaps)
    assert all(any(c["label"] == "TestChan" for c in t["channels"]) for t in gaps)  # gap attributes its channel


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


def test_big_collection_is_date_split_not_truncated(monkeypatch):
    """A collection past advancedsearch's ~10k deep-paging window is enumerated COMPLETELY by splitting on
    publicdate. The scrape API would page past 10k in one query but drops runtime/licenseurl, so it can't
    feed the length filter or the copyright gate — hence the split.

    The fake models a real corpus: TOTAL items with publicdates spread over the search range, filtered by
    whatever range the query asks for. So it exercises the actual recursion, and completeness is a real
    assertion rather than an artefact of the stub."""
    import datetime
    from nolan import archive_source as ar
    TOTAL = 25000
    LO, HI = datetime.date(1996, 1, 1), datetime.date.today() + datetime.timedelta(days=1)
    SPAN = HI.toordinal() - LO.toordinal()
    CORPUS = [(i, LO.toordinal() + (i * SPAN) // TOTAL) for i in range(TOTAL)]   # (id, publicdate ordinal)

    def matching(q):
        m = re.search(r"publicdate:\[(\S+) TO (\S+)\]", q)
        if not m:
            return CORPUS
        a = datetime.date.fromisoformat(m.group(1)).toordinal()
        b = datetime.date.fromisoformat(m.group(2)).toordinal()
        return [c for c in CORPUS if a <= c[1] <= b]

    class FakeResp:
        def __init__(self, docs, num): self._d, self._n = docs, num
        def raise_for_status(self): pass
        def json(self): return {"response": {"numFound": self._n, "docs": self._d}}

    class FakeClient:
        def __init__(self): self.count_queries = []
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, params=None):
            p = dict((k, v) for k, v in params)
            q, rows, page = p["q"], int(p["rows"]), int(p.get("page", 1))
            hits = matching(q)
            if rows == 0:
                self.count_queries.append(q)
                return FakeResp([], len(hits))
            hits = sorted(hits, key=lambda c: -c[1])              # publicdate desc, as the real sort does
            page_docs = hits[(page - 1) * rows: page * rows]
            return FakeResp([{"identifier": f"item{i}", "title": f"t{i}", "mediatype": "movies"}
                             for i, _ in page_docs], len(hits))

    fake = FakeClient()
    monkeypatch.setattr(ar.httpx, "Client", lambda **kw: fake)
    rows, total = ar.survey_collection("giant")
    assert total == TOTAL                                    # the true size is reported, not the window
    assert len({r["video_id"] for r in rows}) == len(rows)    # overlapping boundaries can't double-count
    assert len(rows) == TOTAL                                # EVERY item reached, not the newest 10k
    assert any("publicdate" in q for q in fake.count_queries)   # it split rather than truncating


def test_small_collection_is_not_split(monkeypatch):
    """The split is only paid for when it is needed — a collection inside the window uses one plain query."""
    from nolan import archive_source as ar

    class FakeResp:
        def __init__(self, docs, num): self._d, self._n = docs, num
        def raise_for_status(self): pass
        def json(self): return {"response": {"numFound": self._n, "docs": self._d}}

    seen = []

    class FakeClient:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, params=None):
            p = dict((k, v) for k, v in params)
            seen.append(p["q"])
            if int(p["rows"]) == 0:
                return FakeResp([], 300)
            return FakeResp([{"identifier": f"i{i}", "title": f"t{i}", "mediatype": "movies"}
                             for i in range(300)], 300)

    monkeypatch.setattr(ar.httpx, "Client", lambda **kw: FakeClient())
    rows, total = ar.survey_collection("small")
    assert (len(rows), total) == (300, 300)
    assert not any("publicdate:" in q for q in seen)


def test_clustering_reuses_the_persisted_title_vectors(tmp_path, monkeypatch):
    """The 118 MB title index existed and no clustering path read it — topic_cluster took a `vecs`
    argument whose docstring promised exactly this reuse, and every caller re-embedded instead. This
    pins the wiring: with a warm index, a Curate clustering run embeds NOTHING."""
    import numpy as np
    from nolan import transcript_lib as tl
    from nolan import transcript_vectors as tvec

    titles = [{"video_id": f"v{i}", "url": f"u{i}", "title": f"Subject number {i} explained"}
              for i in range(12)]
    tl.save_survey("coll", titles, tmp_path, kind="archive", total=len(titles))
    tvec.build(tmp_path)                                        # warm the persisted index

    calls = {"n": 0}
    real = tl._embed_titles

    def counting(ts):
        calls["n"] += len(ts)
        return real(ts)
    monkeypatch.setattr(tl, "_embed_titles", counting)

    out = tl.topic_view("coll", k=3, catalog_dir=tmp_path, kind="archive")
    assert out["k"] >= 1 and out["distinct"] > 0
    assert out["vec_reused"] == len(titles) and out["vec_embedded"] == 0
    assert calls["n"] == 0, f"re-embedded {calls['n']} titles that were already in the index"


def test_vectors_for_reembeds_only_what_changed(tmp_path):
    """A stored vector is reused only while the row's embed text still matches its signature — an
    edited title must never be clustered against its stale vector."""
    from nolan import transcript_lib as tl
    from nolan import transcript_vectors as tvec
    rows = [{"video_id": "a", "url": "u", "title": "Bridges of the Rhine"},
            {"video_id": "b", "url": "u", "title": "Tunnels under London"}]
    tl.save_survey("coll", rows, tmp_path, kind="archive", total=2)
    tvec.build(tmp_path)

    _m, reused, embedded = tvec.vectors_for(rows, tmp_path)
    assert (reused, embedded) == (2, 0)

    edited = [dict(rows[0], title="Bridges of the Rhine (restored)"), rows[1]]
    _m, reused, embedded = tvec.vectors_for(edited, tmp_path)
    assert (reused, embedded) == (1, 1)                         # only the changed title is re-embedded

    unknown = rows + [{"video_id": "zzz", "url": "u", "title": "Never surveyed"}]
    _m, reused, embedded = tvec.vectors_for(unknown, tmp_path)
    assert (reused, embedded) == (2, 1)


def test_reused_vectors_still_collapse_near_duplicates(tmp_path):
    """Reusing the index changes the vector space for ARCHIVE rows — it embeds `title + subject`, the
    old path embedded title only. Measured on 3,000 Prelinger rows that is an improvement, not a
    regression: near-duplicate collapse holds (417 multi-item clusters vs 404), while catalogue-number
    titles stop over-merging (a 31-film blob of unrelated 'Home Movie: 0102xx' items becomes 19).
    YouTube surveys carry no subject, so their vectors are title-only either way — unchanged."""
    from nolan import transcript_lib as tl
    from nolan import transcript_vectors as tvec
    rows = ([{"video_id": f"d{i}", "url": "u", "title": "Bridge Building Part One",
              "subject": ["Engineering"]} for i in range(3)]
            + [{"video_id": "x1", "url": "u", "title": "Deep Sea Fishing", "subject": ["Ocean"]},
               {"video_id": "x2", "url": "u", "title": "Alpine Railways", "subject": ["Trains"]}])
    tl.save_survey("coll", rows, tmp_path, kind="archive", total=len(rows))
    tvec.build(tmp_path)
    vecs, reused, embedded = tvec.vectors_for(rows, tmp_path)
    assert (reused, embedded) == (len(rows), 0)
    dd = tl.cluster_dedup_candidates(rows, [], cand_vecs=vecs)
    assert dd["clusters"] == 3                       # the 3 identical titles collapse; the 2 others don't
    assert max(d["cluster_size"] for d in dd["distinct"]) == 3

    # youtube rows have no subject -> the index's embed text IS the bare title
    assert tvec.embed_text("Alpine Railways", None) == "Alpine Railways"


def test_search_scope_goes_into_the_query_not_after_it(tmp_path, monkeypatch):
    """The old path ranked the WHOLE library and kept the transcript rows afterwards, so as real
    footage grows the transcript hits get crowded out of the candidate pool before the filter sees
    them — quietly fewer results, never an error. The scope is now a Chroma `$in` in the query."""
    from nolan import transcript_lib as tl

    class FakeIndex:
        db_path = str(tmp_path / "i.db")
        def transcript_video_ids(self): return {1, 2, 3}
        def get_video_id(self, fp): return {"yt:a": 1, "yt:b": 2, "yt:c": 3}.get(fp)

    seen = {}

    class FakeVS:
        def search(self, query, limit, search_level, video_ids=None, **kw):
            seen["limit"], seen["ids"] = limit, video_ids
            return []

    tl.record_transcript("a", {"title": "A", "url": "https://youtu.be/a"}, 1, "chan1", catalog_dir=tmp_path)
    tl.record_transcript("b", {"title": "B", "url": "https://youtu.be/b"}, 1, "chan2", catalog_dir=tmp_path)
    tl.record_transcript("c", {"title": "C", "url": "https://youtu.be/c"}, 1, "chan1", catalog_dir=tmp_path)

    tl.search_transcripts("q", FakeIndex(), FakeVS(), n=10, catalog_dir=tmp_path)
    assert seen["ids"] == [1, 2, 3]                     # the transcript tier, pushed into the query
    assert seen["limit"] == 10                          # no 8x over-fetch to survive post-filtering

    tl.search_transcripts("q", FakeIndex(), FakeVS(), n=10, catalog_dir=tmp_path, channels=["chan1"])
    assert seen["ids"] == [1, 3]                        # only that source's videos

    # a channel with nothing indexed must return nothing, never fall back to the whole library
    assert tl.search_transcripts("q", FakeIndex(), FakeVS(), n=10, catalog_dir=tmp_path,
                                 channels=["nope"]) == []


def test_empty_scope_cannot_degrade_into_an_unfiltered_search():
    """An empty allow-list is an impossible condition, not a dropped filter."""
    from nolan.vector_search import VectorSearch
    w = VectorSearch.__dict__["_build_where_filter"](object.__new__(VectorSearch), None, None, None, [])
    assert w == {"video_id": {"$lt": 0}}
    w = VectorSearch.__dict__["_build_where_filter"](object.__new__(VectorSearch), None, None, None, [7, 9])
    assert w == {"video_id": {"$in": [7, 9]}}


def test_coverage_reports_what_the_six_sample_preview_withholds(tmp_path, monkeypatch):
    """Six samples per topic was a hard server-side truncation, so member seven was unreachable by any
    UI. The list view now states the true count, and `detail` returns one topic in full."""
    from nolan import transcript_lib as tl
    from nolan import transcript_vectors as tvec
    rows = [{"video_id": f"v{i}", "url": "u", "title": f"Steam locomotive engine number {i}"}
            for i in range(14)]
    tl.save_survey("chan", rows, tmp_path, kind="youtube", total=len(rows))
    tvec.build(tmp_path)
    monkeypatch.setattr(tl, "load_sources", lambda cd=None: {"chan": {"label": "Chan"}})

    cov = tl.coverage_map(None, k=2, catalog_dir=tmp_path, kind="youtube")
    big = max(cov["topics"], key=lambda t: t["available"])
    assert big["sample_total"] == big["available"] > 6
    assert len(big["samples"]) == 6 and big["detail"] is False

    full = tl.coverage_map(None, k=2, catalog_dir=tmp_path, kind="youtube", detail=big["label"])
    got = next(t for t in full["topics"] if t["label"] == big["label"])
    assert got["detail"] is True and len(got["samples"]) == got["sample_total"]


def test_search_joins_archive_hits_to_their_catalog_row(tmp_path):
    """The catalog key is a YouTube id OR an archive.org identifier. Joining only on the YouTube shape
    left every archive hit — most of this library — displaying its own raw URL as the title, with no
    channel, and no timestamp deep-link."""
    from nolan import transcript_lib as tl
    ident = "0007_American_Frontier_07_30_37_00"
    url = f"https://archive.org/details/{ident}"
    tl.record_transcript(ident, {"title": "American Frontier", "url": url}, 3, "prelinger",
                         kind="archive", catalog_dir=tmp_path)

    class Hit:
        video_id, video_path, timestamp_start = 1, url, 607.1
        score, description, transcript = 0.69, "the oil companies came in", ""

    class FakeIndex:
        def transcript_video_ids(self): return {1}
        def get_video_id(self, fp): return 1

    class FakeVS:
        def search(self, query, limit, search_level, video_ids=None, **kw): return [Hit()]

    r = tl.search_transcripts("oil", FakeIndex(), FakeVS(), n=5, catalog_dir=tmp_path)[0]
    assert r["title"] == "American Frontier" and r["channel"] == "prelinger"
    assert r["watch_url"] == f"{url}#start/607"          # archive deep-links by fragment, not &t=


def test_backfill_attributes_channelless_rows_from_the_surveys(tmp_path):
    """An ingest from Curate fell back to `collection`, which is archive-only — so a youtube_cc pick
    landed with channel=None and then belonged to no source: absent from every channel facet, not
    scopable, not promotable, not purgeable. The surveys record which source each video_id came from,
    so it is recoverable. A row that CANNOT be attributed is left alone and counted, never guessed."""
    from nolan import transcript_lib as tl
    ch = "https://www.youtube.com/@HikingFex"
    tl.save_survey(ch, [{"video_id": "a", "url": "u", "title": "Trail"},
                        {"video_id": "b", "url": "u", "title": "Ridge"}], tmp_path, kind="youtube_cc")
    tl.record_transcript("a", {"title": "Trail"}, 1, None, catalog_dir=tmp_path)
    tl.record_transcript("b", {"title": "Ridge"}, 1, None, catalog_dir=tmp_path)
    tl.record_transcript("orphan", {"title": "?"}, 1, None, catalog_dir=tmp_path)

    out = tl.backfill_channels(tmp_path)
    assert out["fixed"] == 2 and out["still_unknown"] == 1
    assert out["by_channel"] == {ch: 2}
    cat = tl.load_catalog(tmp_path)
    assert cat["a"]["channel"] == ch and cat["b"]["channel"] == ch
    assert not cat["orphan"]["channel"]              # untouched, not invented
    assert tl.backfill_channels(tmp_path)["fixed"] == 0        # idempotent


def test_ingest_falls_back_to_the_browsed_source_not_just_a_collection(tmp_path, monkeypatch):
    """The regression that produced those rows: `v.get("channel") or collection`, where `collection`
    is only ever set for archive. The caller always knows which source it was browsing."""
    import inspect
    from nolan.webui import operations
    src = inspect.getsource(operations.ingest_videos)
    assert "or collection or source" in src, "the browsed source must be the final fallback"
    assert "source: str" in str(inspect.signature(operations.ingest_videos)) or \
           "source" in inspect.signature(operations.ingest_videos).parameters


def test_a_broken_extractor_is_a_moment_not_a_property_of_the_video():
    """The unusable ledger is one-way: nothing re-offers a row once it is in there.

    yt-dlp's Vimeo support is broken upstream (#17271) and raises "Failed to fetch macos OAuth
    token: HTTP Error 401: Unauthorized". That matched the 401 rule, so ingesting the 150
    topdocumentaryfilms Vimeo rows would have blacklisted every one of them permanently — for a bug
    that will be fixed upstream, with no way back short of hand-editing the ledger. The status code
    there describes yt-dlp's own auth handshake, not the video."""
    from nolan.webui.operations import _permanently_unusable

    vimeo = Exception("ERROR: [vimeo] 58341318: Failed to fetch macos OAuth token: "
                      "HTTP Error 401: Unauthorized")
    assert _permanently_unusable(vimeo) is False, "a broken extractor must stay retryable"
    assert _permanently_unusable(Exception("unable to fetch new OAuth tokens")) is False
    assert _permanently_unusable(Exception("The web client only works when logged-in")) is False

    # the real item-level failures must still be permanent, or the ledger stops doing its job
    assert _permanently_unusable(Exception("HTTP Error 404: Not Found")) is True
    assert _permanently_unusable(Exception("HTTP Error 403: Forbidden")) is True
    assert _permanently_unusable(Exception("HTTP Error 401: Unauthorized")) is True
    # ...and a transient one is still retried
    assert _permanently_unusable(Exception("HTTP Error 503: Service Unavailable")) is False
