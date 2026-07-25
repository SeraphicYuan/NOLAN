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
    distinct, stats, _ = tl._distinct_candidates("big", cap=2500)
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
    distinct, stats, _ = tl._distinct_candidates("prelinger", tmp_path, kind="archive", copyright_free_only=True)
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
    distinct, stats, _ = tl._distinct_candidates("ch", min_sec=1200)          # 20 min floor
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
