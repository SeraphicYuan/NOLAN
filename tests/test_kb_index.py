"""KB index: insights table, FTS5 keyword search, facets, RRF fusion, reindex.

Offline — exercises the SQLite/FTS layer and the fusion logic without loading the
embedding model (semantic path is covered by the CLI smoke against the real vault).
"""
import importlib


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("NOLAN_KB_VAULT", str(tmp_path / "vault"))
    from nolan.kb import paths
    importlib.reload(paths)
    paths.ensure_dirs()
    from nolan.kb import sidecar
    importlib.reload(sidecar)
    import nolan.kb.insights_store as ins_store
    importlib.reload(ins_store)
    import nolan.kb.index as index
    importlib.reload(index)
    return index, ins_store, sidecar


def _record(source_id="s1"):
    return {
        "source_id": source_id, "source_type": "youtube", "title": "7 Cuts",
        "url": "http://x", "argument_quality": "STRONG", "freshness": "EVERGREEN",
        "insights": [
            {"id": f"{source_id}__01", "seq": 1, "path": "p", "title": "Flow cut on continuous motion",
             "category": "editing", "technique": "Match movement direction",
             "core_idea": "Continue motion across the cut so the edit feels invisible and seamless.",
             "how_to_apply": "Cut where the motion vector matches.", "difficulty": "medium",
             "nolan_hook": "editing", "tags": ["continuity", "motion"]},
            {"id": f"{source_id}__02", "seq": 2, "path": "p", "title": "Deploy risers to build anticipation",
             "category": "sound-design-sfx", "technique": "Rising SFX",
             "core_idea": "A riser builds tension and anticipation into an impact.",
             "how_to_apply": "Place a riser a beat before the reveal.", "difficulty": "easy",
             "nolan_hook": "sound", "tags": ["riser", "tension"]},
        ],
    }


def test_keyword_search_and_facets(tmp_path, monkeypatch):
    index, ins_store, _ = _fresh(tmp_path, monkeypatch)
    store = ins_store.InsightsStore()
    assert store.index_record(_record()) == 2
    assert store.count() == 2

    hits = store.keyword_search("flow cut")
    assert hits and hits[0][0].title.startswith("Flow cut")

    # filter by facet
    filtered = store.keyword_search("riser tension", filters={"category": "sound-design-sfx"})
    assert len(filtered) == 1 and filtered[0][0].category == "sound-design-sfx"

    facets = store.facets()
    assert facets["category"]["editing"] == 1
    assert facets["nolan_hook"]["sound"] == 1


def test_delete_and_replace(tmp_path, monkeypatch):
    index, ins_store, _ = _fresh(tmp_path, monkeypatch)
    store = ins_store.InsightsStore()
    store.index_record(_record())
    store.index_record(_record(), replace=True)   # re-distill: no duplication
    assert store.count() == 2
    store.delete_source("s1")
    assert store.count() == 0
    assert store.keyword_search("flow") == []     # FTS pruned too


def test_rrf_fuses_and_orders():
    from nolan.kb.index import _rrf
    scores, signals = _rrf({"keyword": ["a", "b", "c"], "semantic": ["b", "a", "d"]})
    # 'b' (ranks 1,0) and 'a' (ranks 0,1) both appear in both rankers → top two
    top2 = sorted(scores, key=lambda k: scores[k], reverse=True)[:2]
    assert set(top2) == {"a", "b"}
    assert signals["a"] == {"keyword", "semantic"}
    assert signals["d"] == {"semantic"}


def test_search_keyword_mode_and_reindex(tmp_path, monkeypatch):
    index, ins_store, sidecar = _fresh(tmp_path, monkeypatch)
    # keyword mode never touches the vector store
    idx = index.KBIndex()
    idx.store.index_record(_record())
    hits = idx.search("invisible seamless cut", mode="keyword", k=5)
    assert hits and hits[0].row.id == "s1__01"
    assert "keyword" in hits[0].signals

    # reindex(with_vectors=False) rebuilds the store purely from sidecars
    sidecar.write(_record("s2"))
    res = idx.reindex(with_vectors=False)
    assert res == {"sources": 1, "insights": 2}
    assert idx.store.count() == 2
    assert idx.search("riser", mode="keyword", k=5)[0].row.source_id == "s2"
