"""Library broadening — LLM-proposed topics → X picks across as many subjects as possible."""
import asyncio


class _Idx:
    def transcript_video_ids(self):
        return set()


class _VS:
    def search(self, **k):
        return []


def _fake_suggest(by_topic):
    """A stand-in for the 3-tier search: returns the rows registered for each topic."""
    async def _s(topic, index, vs, config, n=12, catalog_dir=None, copyright_free_only=False,
                 queries=None, web=True, rerank=True, min_sec=0, max_sec=0, refresh_queries=False,
                 expand=True, length_kinds=None):
        return {"suggestions": by_topic.get(topic, []), "topic": topic}
    return _s


def _row(vid, fit="high", kind="archive", rrf=0.01, **kw):
    return {"video_id": vid, "title": vid, "url": "", "kind": kind, "channel": "prelinger",
            "copyright_free": True, "tier": "surveyed", "action": "ingest+caption", "fit": fit,
            "rrf": rrf, "score": 0.7, **kw}


def test_breadth_before_depth(monkeypatch, tmp_path):
    """X picks must SPAN X subjects wherever possible: one pick per topic first, and only when the topics
    are exhausted does a second pick from an already-covered topic count. That is the whole point of
    broadening — 20 videos from one rich topic is not coverage."""
    from nolan import transcript_broaden as tb
    from nolan import transcript_lib as tl
    rows = {"t1": [_row("a1"), _row("a2"), _row("a3")],
            "t2": [_row("b1"), _row("b2")],
            "t3": [_row("c1")]}
    monkeypatch.setattr(tl, "suggest_by_topic", _fake_suggest(rows))
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {})
    out = asyncio.run(tb.broaden_library(None, _Idx(), _VS(), count=5, topics=["t1", "t2", "t3"],
                                         catalog_dir=tmp_path))
    ids = [p["video_id"] for p in out["picks"]]
    assert ids[:3] == ["a1", "b1", "c1"]                    # breadth: one per topic before any second
    assert len(ids) == 5 and set(ids[3:]) <= {"a2", "b2"}   # then depth from the richest pools
    assert out["stats"]["depth_picks"] == 2
    assert [p.get("depth") for p in out["picks"][3:]] == [True, True]


def test_concurrency_changes_wall_clock_not_the_outcome(monkeypatch, tmp_path):
    """The per-topic searches run concurrently (each is two LLM calls + an archive round-trip; sequentially
    that was ~90s per fresh subject). Selection must stay deterministic: results are re-ordered back into
    the PLANNED topic order before any pick is taken, so a topic that finishes last still gets its breadth
    slot in order."""
    import asyncio as _a
    from nolan import transcript_broaden as tb
    from nolan import transcript_lib as tl
    rows = {"t1": [_row("a1"), _row("a2")], "t2": [_row("b1")], "t3": [_row("c1")]}
    order_finished = []

    async def slow_suggest(topic, index, vs, config, n=12, catalog_dir=None, copyright_free_only=False,
                           queries=None, web=True, rerank=True, min_sec=0, max_sec=0,
                           refresh_queries=False, expand=True, length_kinds=None):
        await _a.sleep({"t1": 0.06, "t2": 0.03, "t3": 0.0}[topic])   # finishes in REVERSE plan order
        order_finished.append(topic)
        return {"suggestions": rows[topic]}
    monkeypatch.setattr(tl, "suggest_by_topic", slow_suggest)
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {})

    out = _a.run(tb.broaden_library(None, _Idx(), _VS(), count=4, topics=["t1", "t2", "t3"],
                                    catalog_dir=tmp_path, concurrency=3))
    assert order_finished == ["t3", "t2", "t1"]                      # they really did overlap and invert
    assert [p["video_id"] for p in out["picks"]] == ["a1", "b1", "c1", "a2"]   # plan order, breadth first
    assert out["topics"] == ["t1", "t2", "t3"]

    seq = _a.run(tb.broaden_library(None, _Idx(), _VS(), count=4, topics=["t1", "t2", "t3"],
                                    catalog_dir=tmp_path, concurrency=1))
    assert [p["video_id"] for p in seq["picks"]] == [p["video_id"] for p in out["picks"]]


def test_filters_and_already_in_library(monkeypatch, tmp_path):
    """`kinds` and `min_fit` gate what may be picked, and anything already in the catalog is never
    re-proposed. A topic where nothing clears the filters is REPORTED, not silently skipped."""
    from nolan import transcript_broaden as tb
    from nolan import transcript_lib as tl
    rows = {"t1": [_row("yt1", kind="youtube"), _row("lowfit", fit="low"), _row("good", fit="medium")],
            "t2": [_row("already")],
            "t3": [_row("nope", fit="low")]}
    monkeypatch.setattr(tl, "suggest_by_topic", _fake_suggest(rows))
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {"already": {"title": "in library"}})
    out = asyncio.run(tb.broaden_library(None, _Idx(), _VS(), count=5, topics=["t1", "t2", "t3"],
                                         kinds=["archive"], min_fit="medium", catalog_dir=tmp_path))
    assert [p["video_id"] for p in out["picks"]] == ["good"]        # youtube + low-fit + in-library excluded
    assert {m[0] for m in out["misses"]} == {"t2", "t3"}
    assert out["stats"]["filters"]["kinds"] == ["archive"] and out["stats"]["filters"]["min_fit"] == "medium"


def test_proposed_topics_drop_repeats_and_persist(monkeypatch, tmp_path):
    """The LLM's topic list is a PROPOSAL behind a deterministic gate: topics that repeat one already
    searched are dropped before they can spend a search, and every searched topic is recorded so the NEXT
    run broadens instead of circling."""
    from nolan import llm as nllm
    from nolan import transcript_broaden as tb
    from nolan import transcript_lib as tl
    tb.record_used_topics(["the atomic bomb and the nuclear age"], tmp_path)

    class FakeLLM:
        model = "qwen-test"

        async def generate(self, prompt, system_prompt=None):
            assert "do NOT repeat" in prompt                       # the used list reaches the prompt
            return '{"topics":["the atomic bomb and the nuclear age","deep sea exploration"]}'
    monkeypatch.setattr(nllm, "create_text_llm", lambda cfg, **k: FakeLLM())
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {"v": {"title": "A film"}})
    monkeypatch.setattr(tl, "_embed_titles",
                        lambda ts: [[1.0, 0.0] if "atomic" in t.lower() else [0.0, 1.0] for t in ts])
    out = asyncio.run(tb.propose_topics(None, 10, "", tmp_path))
    assert out["topics"] == ["deep sea exploration"]                # the repeat never becomes a search
    assert out["dropped"] == ["the atomic bomb and the nuclear age"] and out["model"] == "qwen-test"

    monkeypatch.setattr(tl, "suggest_by_topic", _fake_suggest({"deep sea exploration": [_row("d1")]}))
    res = asyncio.run(tb.broaden_library(None, _Idx(), _VS(), count=1, catalog_dir=tmp_path,
                                         topic_source="llm"))   # the corpus proposer is now the default
    assert [p["video_id"] for p in res["picks"]] == ["d1"]
    used = {t["topic"]: t for t in tb.load_used_topics(tmp_path)}
    assert used["deep sea exploration"]["picked"] == 1              # recorded with what it yielded
    assert "the atomic bomb and the nuclear age" in used            # the earlier run's topic survives


def test_dispatch_groups_carry_provenance():
    """Picks group into ingest calls by (kind, source, copyright status) — the same grouping the Topic tab
    uses, so a batch can't record a PD archive film as a copyrighted YouTube row."""
    from nolan import transcript_broaden as tb
    picks = [_row("a", channel="prelinger"), _row("b", channel="prelinger"),
             _row("c", channel="", copyright_free=False)]
    groups = tb.dispatch_groups(picks)
    assert len(groups) == 2
    pre = next(g for g in groups if g["collection"] == "prelinger")
    assert pre["copyright_free"] is True and len(pre["videos"]) == 2 and pre["kind"] == "archive"
    other = next(g for g in groups if g["collection"] == "")
    assert other["copyright_free"] is False and [v["video_id"] for v in other["videos"]] == ["c"]


def test_kinds_default_accepts_every_surveyed_family(monkeypatch, tmp_path):
    """The source control must actually control the source. `kinds=None` used to fall back to `["archive"]`,
    so the Topic tab's "archive only" checkbox did NOTHING when unchecked and a broaden run could not pick a
    YouTube video at all. An unspecified `kinds` now means every family the surveys hold."""
    from nolan import transcript_broaden as tb
    from nolan import transcript_lib as tl
    rows = {"t1": [_row("yt1", kind="youtube"), _row("cc1", kind="youtube_cc"), _row("ar1")]}
    monkeypatch.setattr(tl, "suggest_by_topic", _fake_suggest(rows))
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {})
    out = asyncio.run(tb.broaden_library(None, _Idx(), _VS(), count=3, topics=["t1"], catalog_dir=tmp_path))
    assert {p["kind"] for p in out["picks"]} == {"youtube", "youtube_cc", "archive"}
    # ...and an explicit restriction is still honoured
    only = asyncio.run(tb.broaden_library(None, _Idx(), _VS(), count=3, topics=["t1"],
                                          kinds=["archive"], catalog_dir=tmp_path))
    assert [p["video_id"] for p in only["picks"]] == ["ar1"]


def test_no_survey_still_accepts_rather_than_silently_rejecting(tmp_path):
    """An empty acceptance set would reject every candidate with no error — the exact silent cap this
    function exists to remove. With no readable survey it falls back to every known family."""
    from nolan import transcript_broaden as tb
    assert set(tb.surveyed_kinds(tmp_path)) == set(tb.ALL_KINDS)


def test_length_filter_applies_per_source_family():
    """youtube rows carry a duration 100% of the time; archive rows 14%, and asking costs a throttled
    metadata call each. So a sweep filters the reliable families and lets the caption stage enforce the
    rest on the REAL runtime."""
    from nolan.transcript_lib import _len_on
    assert _len_on("archive", None) and _len_on("youtube", None)          # None = the old behaviour, all
    assert _len_on("youtube", ["youtube", "youtube_cc"])
    assert not _len_on("archive", ["youtube", "youtube_cc"])


def test_topic_worthy_rejects_catalogue_number_runs():
    """Two distinct junk shapes, and one test cannot catch both: raw-scan clusters score a PERFECT unique
    token ratio precisely because every id differs, while boilerplate runs pass the real-title test on the
    word 'Home'. Both must be rejected; a genuine subject cluster must not be."""
    from nolan import transcript_broaden as tb
    scans = [{"video_id": v, "title": v} for v in ("001000", "001002", "001004", "001017")]
    boiler = [{"video_id": f"h{i}", "title": f"Home Movie: 00{i}"} for i in range(12)]
    real = [{"video_id": "a", "title": "Safety: In Danger Out of Doors"},
            {"video_id": "b", "title": "Let Us Break Bread Together"},
            {"video_id": "c", "title": "The Challenge of Ideas"},
            {"video_id": "d", "title": "A Word to the Wives"}]
    assert not tb._topic_worthy(scans)
    assert not tb._topic_worthy(boiler)
    assert tb._topic_worthy(real)


def test_depth_picks_are_diversified_against_what_we_hold(monkeypatch, tmp_path):
    """The depth pass must not stack near-identical subjects. Exact-id dedup and near-identical-title
    collapse already existed; MMR fills the band between them — given a redundant top-ranked candidate and a
    dissimilar lower-ranked one, the dissimilar one wins its slot."""
    from nolan import transcript_broaden as tb
    from nolan import transcript_lib as tl
    # one topic: breadth takes the first, depth must then choose between a near-twin and a distant row
    rows = {"t1": [_row("seed", rrf=0.9), _row("twin", rrf=0.5), _row("far", rrf=0.4)]}
    monkeypatch.setattr(tl, "suggest_by_topic", _fake_suggest(rows))
    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {})
    monkeypatch.setattr(tl, "_embed_titles",
                        lambda ts: [[1.0, 0.0] if t in ("seed", "twin") else [0.0, 1.0] for t in ts])
    out = asyncio.run(tb.broaden_library(None, _Idx(), _VS(), count=2, topics=["t1"], catalog_dir=tmp_path))
    assert out["stats"]["diversity"] is True
    assert [p["video_id"] for p in out["picks"]] == ["seed", "far"]      # 'twin' loses to the novel row
