"""KB index facade — keyword (FTS5) + semantic (Chroma/BGE) + hybrid search.

Combines :class:`InsightsStore` (durable, always available) with the optional
:class:`KBVectors` (needs the embedding model). Search modes:

- ``keyword``  — BM25 over the FTS index.
- ``semantic`` — cosine over BGE embeddings.
- ``hybrid``   — Reciprocal Rank Fusion of the two (default), lightly
  quality-weighted. This is the piece HERMES lacks (it offers keyword OR
  semantic, never fused).

Vectors load lazily and fail soft: keyword indexing/search always works even if
torch/chromadb aren't importable, so a distill never breaks on the derived index.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from . import sidecar
from .insights_store import InsightsStore, InsightRow

RRF_K = 60  # standard Reciprocal Rank Fusion constant

# mild quality weighting (multiplies the fused score) — evidence-aware ranking
_ARG_W = {"STRONG": 1.06, "MODERATE": 1.0, "WEAK": 0.94}
_FRESH_W = {"EVERGREEN": 1.03, "RECENT": 1.0, "TREND": 0.99, "BREAKING": 1.0}


@dataclass
class SearchHit:
    row: InsightRow
    score: float
    signals: List[str]      # which rankers matched: 'keyword' and/or 'semantic'


class KBIndex:
    def __init__(self, store: Optional[InsightsStore] = None):
        self.store = store or InsightsStore()
        self._vectors = None
        self._vectors_tried = False

    # -- lazy, fail-soft vector store --
    @property
    def vectors(self):
        if self._vectors is None and not self._vectors_tried:
            self._vectors_tried = True
            try:
                from .vectors import KBVectors
                self._vectors = KBVectors()
            except Exception as e:  # pragma: no cover - env-dependent
                print(f"[kb] semantic index unavailable ({e}); keyword-only.")
                self._vectors = None
        return self._vectors

    # ---------------------------------------------------------------- writes
    def index_record(self, record: dict, replace: bool = True) -> int:
        n = self.store.index_record(record, replace=replace)
        if self.vectors is not None:
            try:
                self.vectors.index_record(record, replace=replace)
            except Exception as e:  # pragma: no cover
                print(f"[kb] vector index update failed for {record.get('source_id')}: {e}")
        return n

    def remove_source(self, source_id: str) -> None:
        self.store.delete_source(source_id)
        if self.vectors is not None:
            self.vectors.delete_source(source_id)

    def reindex(self, with_vectors: bool = True) -> Dict[str, int]:
        """Rebuild the whole derived index from the structured sidecars."""
        self.store.clear()
        vec = self.vectors if with_vectors else None
        if vec is not None:
            vec.clear()
        n_sources = n_insights = 0
        for record in sidecar.iter_all():
            n_insights += self.store.index_record(record, replace=False)
            if vec is not None:
                try:
                    vec.index_record(record, replace=False)
                except Exception as e:  # pragma: no cover
                    print(f"[kb] vector reindex failed for {record.get('source_id')}: {e}")
            n_sources += 1
        return {"sources": n_sources, "insights": n_insights}

    # ---------------------------------------------------------------- search
    def search(self, query: str, *, mode: str = "hybrid",
               filters: Optional[dict] = None, k: int = 20) -> List[SearchHit]:
        query = (query or "").strip()
        if not query:
            # no query → faceted browse (most recent first)
            return [SearchHit(r, 0.0, []) for r in self.store.list(filters=filters, limit=k)]

        pool = max(k * 3, 30)  # retrieve deeper than k, then fuse + trim
        kw = [row.id for row, _ in self.store.keyword_search(query, filters=filters, limit=pool)]
        sem: List[str] = []
        if mode in ("semantic", "hybrid") and self.vectors is not None:
            sem = [iid for iid, _ in self.vectors.semantic_search(query, filters=filters, k=pool)]

        if mode == "keyword" or (mode == "hybrid" and not sem):
            rankings = {"keyword": kw}
        elif mode == "semantic":
            rankings = {"semantic": sem}
        else:
            rankings = {"keyword": kw, "semantic": sem}

        fused, signals = _rrf(rankings)
        # hydrate rows + apply mild quality weighting
        hits: List[SearchHit] = []
        for iid, base in fused.items():
            row = self.store.get(iid)
            if not row:
                continue
            qf = _ARG_W.get((row.argument_quality or "").upper(), 1.0) * \
                _FRESH_W.get((row.freshness or "").upper(), 1.0)
            hits.append(SearchHit(row, base * qf, sorted(signals[iid])))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]

    def facets(self, filters: Optional[dict] = None) -> Dict[str, Dict[str, int]]:
        return self.store.facets(filters)

    def count(self) -> int:
        return self.store.count()


def _rrf(rankings: Dict[str, List[str]], k: int = RRF_K):
    """Reciprocal Rank Fusion. Returns (scores, signals) keyed by id."""
    scores: Dict[str, float] = {}
    signals: Dict[str, set] = {}
    for name, ids in rankings.items():
        for rank, iid in enumerate(ids):
            scores[iid] = scores.get(iid, 0.0) + 1.0 / (k + rank + 1)
            signals.setdefault(iid, set()).add(name)
    return scores, signals
