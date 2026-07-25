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
    assert st["accept_rate"] == 1.0 and st["judged_topics"] == 1
