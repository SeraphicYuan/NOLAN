"""Topic memory — the LLM's decisions and the human's acceptances, persisted.

77% of a topic search's 33s is two LLM calls (expansion 17.8s, re-rank 7.5s) wrapping a ranking that costs
0.024s. These tests hold the line that the EXPENSIVE, STABLE part is remembered while the volatile ranking
is not, and that reuse never changes what the user sees — only what it cost.
"""
import asyncio


def test_slug_normalizes_wording_noise():
    """Case, punctuation, spacing and function words must not fork the memory — measured, BGE puts only
    0.919 between "lighthouses and coastal navigation" and "Lighthouses & coastal navigation!", below any
    sane paraphrase threshold, so the trivial case is normalized rather than left to the vectors."""
    from nolan import transcript_memory as mem
    assert mem.slug("Lighthouses & coastal navigation!") == mem.slug("lighthouses and coastal navigation")
    assert mem.slug("  The   ATOMIC age  ") == mem.slug("atomic age") == "atomic age"
    assert mem.slug("the space race") != mem.slug("the arms race")        # real difference survives
    assert mem.slug("the and of") == "the and of"                         # all stop-words → keep them


def test_expansion_cache_hit_and_refresh(monkeypatch, tmp_path):
    """A repeat search reuses the remembered queries (17.8s of LLM), reports `query_source='cache'` with the
    date, and the tab's "re-expand" button bypasses it."""
    from nolan import llm as nllm
    from nolan import transcript_lib as tl
    from nolan import transcript_memory as mem
    calls = []

    class FakeLLM:
        model = "qwen-test"

        async def generate(self, prompt, system_prompt=None):
            calls.append(prompt)
            return '{"queries":["q one","q two"]}'
    monkeypatch.setattr(nllm, "create_text_llm", lambda cfg, **k: FakeLLM())
    monkeypatch.setattr(tl, "_topic_suggestions",
                        lambda q, t, i, v, n, cd, cf, web=True, *a: {"suggestions": [], "queries": list(q)})

    d1 = asyncio.run(tl.suggest_by_topic("Ellis Island", None, None, None, catalog_dir=tmp_path))
    assert d1["query_source"] == "llm" and len(calls) == 1
    d2 = asyncio.run(tl.suggest_by_topic("ellis  island!", None, None, None, catalog_dir=tmp_path))
    assert d2["queries"] == ["q one", "q two"] and len(calls) == 1        # slug-normalized hit, no LLM
    assert d2["query_source"] == "cache" and d2["queries_cached_on"]
    d3 = asyncio.run(tl.suggest_by_topic("Ellis Island", None, None, None, catalog_dir=tmp_path,
                                         refresh_queries=True))
    assert len(calls) == 2 and d3["query_source"] == "llm"               # re-expand bypasses the cache
    assert mem.get_queries("ELLIS ISLAND", tmp_path)["model"] == "qwen-test"


def test_judgements_reused_for_the_same_subject_only(monkeypatch, tmp_path):
    """Only rows this SUBJECT has never judged reach the LLM. A near-identical topic reuses (a film is
    high-fit *for a subject*), an unrelated topic re-judges — and a reused verdict must produce exactly the
    same visible row as a fresh one."""
    from nolan import llm as nllm
    from nolan import transcript_lib as tl
    from nolan import transcript_memory as mem
    asked = []

    class FakeLLM:
        model = "m1"

        async def generate(self, prompt, system_prompt=None):
            asked.append(prompt)
            ids = [ln.split(".")[0] for ln in prompt.splitlines() if ln[:1].isdigit()]
            return '{"items":[' + ",".join(f'{{"i":{i},"fit":"high","why":"w{i}"}}' for i in ids) + "]}"
    monkeypatch.setattr(nllm, "create_text_llm", lambda cfg, **k: FakeLLM())
    monkeypatch.setattr(tl, "_embed_titles",
                        lambda ts: [[1.0, 0.0] if "atomic" in t.lower() else [0.0, 1.0] for t in ts])
    rows = [{"video_id": "v1", "title": "Duck and Cover", "rrf": 0.02},
            {"video_id": "v2", "title": "Survival Under Atomic Attack", "rrf": 0.01}]

    kept, meta = asyncio.run(tl._rerank_suggestions(rows, "the atomic age", ["atomic"], None, tmp_path))
    assert meta["rerank_judged"] == 2 and meta["rerank_remembered"] == 0 and len(asked) == 1

    kept2, meta2 = asyncio.run(tl._rerank_suggestions(rows, "the atomic age", ["atomic"], None, tmp_path))
    assert len(asked) == 1                                            # nothing re-asked
    assert meta2["rerank_remembered"] == 2 and meta2["rerank_judged"] == 0
    assert [r["video_id"] for r in kept2] == [r["video_id"] for r in kept]      # identical visible result
    assert [r["fit"] for r in kept2] == ["high", "high"] and kept2[0]["why"] == kept[0]["why"]

    rows2 = rows + [{"video_id": "v3", "title": "Fallout shelters", "rrf": 0.005}]
    _k3, meta3 = asyncio.run(tl._rerank_suggestions(rows2, "atomic-age america", ["atomic"], None, tmp_path))
    assert len(asked) == 2 and meta3["rerank_remembered"] == 2 and meta3["rerank_judged"] == 1
    assert "v3" in asked[-1] or "Fallout" in asked[-1]                # ONLY the unjudged row was sent

    _k4, meta4 = asyncio.run(tl._rerank_suggestions(rows, "wedding etiquette films", ["weddings"],
                                                    None, tmp_path))
    assert len(asked) == 3 and meta4["rerank_remembered"] == 0        # different subject → re-judged
    assert len(mem.get_judgements("the atomic age", ["v1", "v2"], tmp_path)) == 2


def test_judgement_from_another_model_is_not_reused(tmp_path):
    """A verdict carries its model. Reuse is scoped to the same model so a ranking never silently mixes
    two judges' opinions."""
    from nolan import transcript_memory as mem
    mem.put_judgements("the space race", [{"video_id": "s1", "fit": "high", "why": "saturn v"}],
                       "model-a", tmp_path)
    assert mem.get_judgements("the space race", ["s1"], tmp_path, model="model-a")
    assert not mem.get_judgements("the space race", ["s1"], tmp_path, model="model-b")
    assert mem.get_judgements("the space race", ["s1"], tmp_path)["s1"]["model"] == "model-a"


def test_unusable_items_stop_being_offered(monkeypatch, tmp_path):
    """An item the pipeline PROVED it can't use (401/403 restricted derivative, 404) must leave the search.
    The ranking only knows it isn't in the catalog, so it keeps scoring well and getting picked again — one
    42-pick run hit 6 such items (CSPAN / Al Jazeera mirrors). Transient failures are NOT marked."""
    from nolan import transcript_lib as tl
    from nolan import transcript_memory as mem
    from nolan.webui.operations import _permanently_unusable
    import httpx

    class Resp:
        status_code = 401
    assert _permanently_unusable(RuntimeError("Client error '401 Unauthorized' for url ..."))
    assert _permanently_unusable(RuntimeError("Unable to download webpage: HTTP Error 404"))
    assert not _permanently_unusable(RuntimeError("ConnectTimeout: [WinError 10060] ..."))
    assert not _permanently_unusable(RuntimeError("Server error '503 Service Unavailable'"))

    mem.mark_unusable("restricted1", "401 Unauthorized", "A CSPAN mirror", tmp_path)
    mem.mark_unusable("restricted1", "401 Unauthorized", "A CSPAN mirror", tmp_path)   # idempotent-ish
    assert mem.unusable_ids(tmp_path) == {"restricted1"}
    rows = mem._load("unusable.json", tmp_path)
    assert rows["restricted1"]["hits"] == 2 and rows["restricted1"]["title"] == "A CSPAN mirror"

    monkeypatch.setattr(tl, "load_catalog", lambda cd=None: {})
    monkeypatch.setattr(tl, "copyright_free_ids", lambda cd=None: set())
    monkeypatch.setattr(tl, "load_surveys", lambda cd=None: {"archive:c": {"kind": "archive", "channel": "c",
        "titles": [{"video_id": "restricted1", "title": "diamond film", "url": ""},
                   {"video_id": "fine", "title": "diamond film two", "url": ""}]}})
    monkeypatch.setattr(tl, "_embed_titles", lambda ts: [[1.0, 0.0]] * len(ts))
    monkeypatch.setattr(tl, "_collapse_near_duplicates", lambda rows, vecs=None, thr=0.9: (rows, 0))
    d = tl._topic_suggestions(["diamond"], "diamond", _Idx(), _VS(), 6, tmp_path, web=False)
    assert [s["video_id"] for s in d["suggestions"]] == ["fine"]        # the restricted row is gone


class _Idx:
    def transcript_video_ids(self):
        return set()


class _VS:
    def search(self, **k):
        return []


def test_accept_rate_measures_what_the_human_could_take(tmp_path):
    """`off` rows are dropped BEFORE anyone sees them, so counting acceptances against every judgement reads
    as a damningly low rate for a re-ranker doing its job. The rate is measured against the rows that were
    actually shown, and broken out for the ones it called `high`."""
    from nolan import transcript_memory as mem
    mem.put_judgements("the space race", [{"video_id": "a", "fit": "high"}, {"video_id": "b", "fit": "high"},
                                          {"video_id": "c", "fit": "medium"},
                                          {"video_id": "d", "fit": "off"}, {"video_id": "e", "fit": "off"}],
                       "m", tmp_path)
    mem.record_accepted([{"video_id": "a", "topic": "the space race", "fit": "high"}], "topic", tmp_path)
    st = mem.stats(tmp_path)
    assert st["judgements"] == 5 and st["dropped_off"] == 2 and st["shown"] == 3
    assert st["accept_rate"] == round(1 / 3, 3)          # 1 of 3 SHOWN — not 1 of 5 judged
    assert st["accept_rate_high"] == 0.5                 # of the two it called high, one was taken
    assert st["accepted_fits"] == {"high": 1}


def test_acceptance_ledger_is_ground_truth(tmp_path):
    """What the human actually ingested off a shortlist — recorded once per (video, topic), and reportable
    as an accept-rate against what the model proposed."""
    from nolan import transcript_memory as mem
    picks = [{"video_id": "a", "title": "A film", "topic": "the space race", "tier": "archive",
              "fit": "high", "score": 0.7, "copyright_free": True},
             {"video_id": "b", "title": "B film", "topic": "the space race", "tier": "surveyed",
              "fit": "medium", "score": 0.6}]
    assert mem.record_accepted(picks, "broaden", tmp_path) == 2
    assert mem.record_accepted(picks, "broaden", tmp_path) == 0            # idempotent per (video, topic)
    assert mem.record_accepted([{**picks[0], "topic": "another subject"}], "topic", tmp_path) == 1
    rows = mem.load_accepted(tmp_path)
    assert len(rows) == 3 and {r["source"] for r in rows} == {"broaden", "topic"}
    mem.put_judgements("the space race", [{"video_id": "a", "fit": "high"},
                                          {"video_id": "b", "fit": "medium"},
                                          {"video_id": "c", "fit": "low"}], "m", tmp_path)
    st = mem.stats(tmp_path)
    assert st["judgements"] == 3 and st["accepted"] == 3 and st["fits"]["high"] == 1
    assert st["accept_rate"] == 1.0 and st["judged_topics"] == 1 and st["shown"] == 3
