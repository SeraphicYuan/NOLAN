"""Persisted BGE title vectors for the SURVEYED (crawled but not-yet-ingested) catalogue.

The topic search used to be shaped entirely around the cost of embedding: a keyword prefilter, a 1500-title
embed budget, and a round-robin split of that budget across sources — machinery whose only job was to avoid
re-embedding the same titles on every request. It also bounded recall: a topic could only ever be ranked
against the slice the budget reached.

The titles are STATIC (surveys.json is a persisted crawl), so their vectors are computed ONCE and stored:

* ``rows(catalog_dir)`` — the deduped surveyed corpus ``{video_id: row}``. Kind-namespaced survey keys are
  read first so a video that appears under both a legacy un-namespaced key and its namespaced twin is
  counted once, with its ``kind`` known. ONE definition of "the surveyed corpus", shared by the search and
  the index builder — they cannot drift.
* ``ensure(...)`` — the vectors for those rows, embedding whatever is missing or stale (each row carries a
  signature of its embed text, so an edited title is re-embedded, not silently kept). Refuses to embed more
  than ``max_inline`` rows inside a request and REPORTS the shortfall instead — a cold index degrades the
  search loudly rather than hanging it.
* ``build(...)`` — the full (re)build, for the CLI / a background job.

Stored as float16 in ``projects/_library/transcripts/title_vectors.npz`` (~1.5 KB/title): the vectors are
L2-normalized so cosine is a dot product, and the fp16 round-trip costs ~1e-3 of similarity — far below the
0.42 relevance floor it feeds.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

MODEL_TAG = "bge-base-en-v1.5"


def _vec_file(catalog_dir: Optional[Path] = None) -> Path:
    from nolan.transcript_lib import TRANSCRIPT_DIR
    return (Path(catalog_dir) if catalog_dir else TRANSCRIPT_DIR) / "title_vectors.npz"


def embed_text(title: str, subject: Optional[List[str]] = None) -> str:
    """What we EMBED for a surveyed video: title + subject tags. Archive rows also carry a description, but
    that prose dilutes a short-title vector below the relevance floor — it stays a keyword/re-rank signal."""
    subj = " ".join(str(s) for s in (subject or []))
    return ((title or "") + " " + subj).strip()[:200]


def _sig(text: str) -> str:
    return hashlib.blake2b((text or "").encode("utf-8", "ignore"), digest_size=8).hexdigest()


def rows(catalog_dir: Optional[Path] = None, exclude: Optional[set] = None) -> Dict[str, Dict[str, Any]]:
    """The deduped surveyed corpus: ``{video_id: {title, url, kind, channel, subject, description,
    copyright_free, text, sig}}``. ``exclude`` (typically the ingested catalog's ids) is dropped up front."""
    from nolan import transcript_lib as tl
    surveys = tl.load_surveys(catalog_dir)
    free_ids = tl.copyright_free_ids(catalog_dir)
    skip = exclude or set()
    # kind-namespaced keys first: the legacy un-namespaced twin has kind=None, and first-seen wins
    ordered = sorted(surveys.items(), key=lambda kv: (":" not in kv[0], kv[0]))
    out: Dict[str, Dict[str, Any]] = {}
    for _key, sv in ordered:
        kd = sv.get("kind") or "youtube"
        chan = sv.get("channel") or ""
        for t in sv.get("titles", []):
            vid = t.get("video_id")
            if not vid or vid in skip or vid in out:
                continue
            from nolan.archive_source import _as_text
            title = _as_text(t.get("title")) or vid       # archive metadata is multi-valued (list) at times
            subject = (t.get("subject") or []) if kd == "archive" else []
            txt = embed_text(title, subject)
            out[vid] = {"video_id": vid, "title": title, "url": t.get("url") or "", "kind": kd,
                        "channel": chan, "subject": subject, "duration": t.get("duration"),
                        "description": _as_text(t.get("description")) if kd == "archive" else "",
                        "copyright_free": (vid in free_ids) or bool(t.get("copyright_free")),
                        "text": txt, "sig": _sig(txt)}
    return out


_CACHE: Dict[str, Tuple[float, int, Dict[str, str], Any]] = {}      # path → (mtime, size, sigs, matrix)


def load(catalog_dir: Optional[Path] = None):
    """``(ids, sigs, matrix)`` from disk (float32, L2-normalized), or ``(None, {}, None)`` when unbuilt.
    Memory-cached per (mtime, size) — a rebuild invalidates it."""
    import numpy as np
    p = _vec_file(catalog_dir)
    if not p.exists():
        return None, {}, None
    try:
        st = p.stat()
        hit = _CACHE.get(str(p))
        if hit and hit[0] == st.st_mtime and hit[1] == st.st_size:
            return hit[3][0], hit[2], hit[3][1]
        with np.load(p, allow_pickle=False) as z:
            ids = [str(x) for x in z["ids"]]
            sigs = [str(x) for x in z["sigs"]]
            mat = np.asarray(z["vecs"], dtype=np.float32)
        sig_map = dict(zip(ids, sigs))
        _CACHE[str(p)] = (st.st_mtime, st.st_size, sig_map, (ids, mat))
        return ids, sig_map, mat
    except Exception:
        return None, {}, None


def _save(ids: List[str], sigs: List[str], mat, catalog_dir: Optional[Path] = None) -> Path:
    import numpy as np
    p = _vec_file(catalog_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    np.savez(p, ids=np.array(ids, dtype=object).astype("U"), sigs=np.array(sigs, dtype=object).astype("U"),
             vecs=np.asarray(mat, dtype=np.float16), model=np.array([MODEL_TAG]))
    _CACHE.pop(str(p), None)
    return p


def ensure(corpus: Dict[str, Dict[str, Any]], catalog_dir: Optional[Path] = None,
           max_inline: int = 1500, progress: Optional[Callable[[int, int], None]] = None):
    """``(ids, matrix, pending)`` covering ``corpus``. Missing/stale rows are embedded inline while there are
    at most ``max_inline`` of them (a normal incremental top-up); beyond that nothing is embedded and
    ``pending`` reports how many titles the index does NOT cover, so the caller can fall back and SAY so
    rather than block a request on a multi-minute cold build."""
    import numpy as np
    from nolan.transcript_lib import _embed_titles
    ids, sig_map, mat = load(catalog_dir)
    ids = ids or []
    have = {vid: i for i, vid in enumerate(ids)}
    stale = [vid for vid, r in corpus.items()
             if vid not in have or sig_map.get(vid) != r["sig"]]
    if stale and len(stale) > max_inline:
        if mat is None:
            return [], None, len(stale)
        keep = [(vid, i) for vid, i in have.items() if vid in corpus and sig_map.get(vid) == corpus[vid]["sig"]]
        if not keep:
            return [], None, len(stale)
        idx = np.array([i for _v, i in keep], dtype=np.int64)
        return [v for v, _i in keep], mat[idx], len(stale)
    if stale:
        vecs = []
        for start in range(0, len(stale), 512):
            chunk = stale[start:start + 512]
            vecs.extend(_embed_titles([corpus[v]["text"] for v in chunk]))
            if progress:
                progress(min(start + 512, len(stale)), len(stale))
        new = np.asarray(vecs, dtype=np.float32)
        fresh = [(vid, i) for vid, i in have.items() if vid not in set(stale)]
        old_ids = [v for v, _i in fresh]
        old_sigs = [sig_map[v] for v in old_ids]
        old_mat = mat[np.array([i for _v, i in fresh], dtype=np.int64)] if (mat is not None and fresh) \
            else np.zeros((0, new.shape[1]), dtype=np.float32)
        ids = old_ids + stale
        sigs = old_sigs + [corpus[v]["sig"] for v in stale]
        mat = np.vstack([old_mat, new]) if len(old_mat) else new
        _save(ids, sigs, mat, catalog_dir)
        have = {vid: i for i, vid in enumerate(ids)}
    sel = [(vid, have[vid]) for vid in corpus if vid in have]
    if not sel:
        return [], None, len(stale)
    idx = np.array([i for _v, i in sel], dtype=np.int64)
    return [v for v, _i in sel], mat[idx], 0


def build(catalog_dir: Optional[Path] = None,
          progress: Optional[Callable[[int, int], None]] = None) -> Dict[str, Any]:
    """Full (re)build over the whole surveyed corpus — the CLI / background-job entry point."""
    corpus = rows(catalog_dir)
    ids, mat, pending = ensure(corpus, catalog_dir, max_inline=len(corpus) + 1, progress=progress)
    return {"titles": len(corpus), "indexed": len(ids), "pending": pending,
            "file": str(_vec_file(catalog_dir)), "model": MODEL_TAG,
            "dim": int(mat.shape[1]) if mat is not None and len(mat) else 0}


def status(catalog_dir: Optional[Path] = None) -> Dict[str, Any]:
    """What the index covers vs the surveyed corpus — the honest coverage line for the UI."""
    corpus = rows(catalog_dir)
    ids, sig_map, _mat = load(catalog_dir)
    fresh = sum(1 for vid, r in corpus.items() if sig_map.get(vid) == r["sig"])
    p = _vec_file(catalog_dir)
    return {"surveyed": len(corpus), "indexed": fresh, "pending": len(corpus) - fresh,
            "built": bool(ids), "file": str(p), "bytes": p.stat().st_size if p.exists() else 0}
