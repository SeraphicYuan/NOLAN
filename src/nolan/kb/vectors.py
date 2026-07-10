"""Semantic index for KB insights — ChromaDB + BGE embeddings.

Reuses NOLAN's standard text-embedding stack (``BAAI/bge-base-en-v1.5`` via
Chroma's SentenceTransformer embedding function — the same model the video
library's :mod:`nolan.vector_search` uses) so the whole system speaks one
embedding space. Vectors live in the derived, rebuildable ``_kb_data/chroma``
store; the atomic insight note is the embedded chunk.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from . import paths

EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
# BGE retrieval convention: prefix the *query* (not the documents) — matches vector_search.py.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
COLLECTION = "nolan_kb_insights"

_META_FIELDS = ("source_id", "category", "nolan_hook", "difficulty", "freshness", "source_type")


def embed_text(ins: dict) -> str:
    """Compose the text we embed for one insight — the parts that carry meaning."""
    parts = [
        ins.get("title", ""), ins.get("technique", ""), ins.get("core_idea", ""),
        ins.get("how_to_apply", ""), " ".join(ins.get("tags") or []),
    ]
    return "\n".join(p for p in parts if p).strip()


def _chroma_where(filters: Optional[dict]) -> Optional[dict]:
    clauses = []
    for fld in _META_FIELDS:
        val = (filters or {}).get(fld)
        if val:
            clauses.append({fld: val})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


class KBVectors:
    def __init__(self):
        import chromadb
        from chromadb.config import Settings
        from chromadb.utils import embedding_functions
        paths.CHROMA.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(paths.CHROMA), settings=Settings(anonymized_telemetry=False))
        self._ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL)
        self.col = self.client.get_or_create_collection(
            name=COLLECTION, embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"})

    def delete_source(self, source_id: str) -> None:
        try:
            self.col.delete(where={"source_id": source_id})
        except Exception:
            pass

    def index_record(self, record: dict, replace: bool = True) -> int:
        if replace:
            self.delete_source(record["source_id"])
        ids, docs, metas = [], [], []
        for ins in record.get("insights", []):
            text = embed_text(ins)
            if not text:
                continue
            ids.append(ins["id"])
            docs.append(text)
            metas.append({
                "source_id": record["source_id"],
                "category": ins.get("category", ""),
                "nolan_hook": ins.get("nolan_hook", ""),
                "difficulty": ins.get("difficulty", ""),
                "freshness": record.get("freshness", ""),
                "source_type": record.get("source_type", ""),
            })
        if ids:
            self.col.upsert(ids=ids, documents=docs, metadatas=metas)
        return len(ids)

    def clear(self) -> None:
        # drop + recreate the collection
        try:
            self.client.delete_collection(COLLECTION)
        except Exception:
            pass
        self.col = self.client.get_or_create_collection(
            name=COLLECTION, embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"})

    def semantic_search(self, query: str, filters: Optional[dict] = None,
                        k: int = 30) -> List[Tuple[str, float]]:
        """Return [(insight_id, distance)] best-first (lower cosine distance = better)."""
        if not (query or "").strip():
            return []
        res = self.col.query(
            query_texts=[QUERY_PREFIX + query], n_results=k,
            where=_chroma_where(filters))
        ids = (res.get("ids") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        return list(zip(ids, dists))

    def count(self) -> int:
        try:
            return self.col.count()
        except Exception:
            return 0


_SHARED = None


def shared():
    """Process-wide KBVectors singleton — loads the embedding model once so web
    search doesn't reload ~400MB per request. Returns None if unavailable."""
    global _SHARED
    if _SHARED is None:
        try:
            _SHARED = KBVectors()
        except Exception as e:  # pragma: no cover - env-dependent
            print(f"[kb] shared vectors unavailable: {e}")
            _SHARED = False
    return _SHARED or None
