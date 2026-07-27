"""The LEXICAL channel over the transcript library — BM25 where the dense indexes cannot help.

Both existing indexes over this corpus are dense-only: `vector_search` embeds a segment's
description + transcript, and `transcript_frames.visual_search` blends CLIP appearance with BGE
over the gemma caption. Nothing anywhere penalises ZERO TERM OVERLAP, which is exactly why
"De Beers v. United States (2004)" retrieved WATERGATE at 0.713 — higher than a genuine
diamond-machinery hit at 0.704 on the same run. The score carries no topical signal, so no
threshold separates them (see docs/VIDEO_RETRIEVAL_PROGRAM.md for the measurements).

This module adds the missing half. It buys two things a dense index structurally cannot give:

  IDENTITY   A named entity is an exact string. "Kimberley" either appears in a title/transcript or
             it does not — no embedding blurs it into "a mine". This is the mode the whole
             acquisition seam has been failing (0 heroes delivered by keyassets Tier B).
  ABSTAIN    BM25 can return NOTHING. Zero term overlap is positive EVIDENCE OF ABSENCE, which is
             the one signal we have never had: a k-nearest index returns k rows for any query
             however wrong, and the shipped path answers an impossible beat with a mean of 4.75
             candidates and never once abstains (measured, eval/video_retrieval).

Era rides along for free. `year` is populated on only 8% of archive.org items so a structured era
filter is useless, but "1960s" is a TOKEN — nearly invisible to a dense vector, exactly matchable
by BM25 in a title, subject or caption.

DESIGN — a derived sidecar, never a second source of truth
    One rebuildable FTS5 index at projects/_library/transcripts/lexical.db over BOTH tiers with one
    schema, so a caller asks one question and gets segment and frame rows back in the same shape
    (which is also what makes RRF fusion with the dense channels well-defined). It owns no data:
    every row is derived from the VideoIndex segments table, the transcript-frame ImageLibrary and
    catalog.json, and `build()` drops and rebuilds. Deleting the file costs a rebuild, never data.

    Title is its OWN indexed column so it can be weighted independently — that is the named-mode
    lever, and it is the signal neither dense index sees at all (they embed segment text and frame
    captions; the film's title is never part of either).

Precedents copied deliberately: `kb/insights_store.py` (the `_match_expr` / bm25-join shape) and
`sound/catalog.py` (FTS5 over a catalog with UNINDEXED metadata columns).
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from nolan.transcript_lib import TRANSCRIPT_DIR

LEX_DB = TRANSCRIPT_DIR / "lexical.db"

# The FTS5 column list, in order. bm25() takes one weight per column, so this order is load-bearing.
_COLS = ["kind", "video_id", "url", "start", "end", "ref", "title", "text"]
_INDEXED = {"title", "text"}

_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS lex USING fts5(
    kind UNINDEXED, video_id UNINDEXED, url UNINDEXED,
    start UNINDEXED, "end" UNINDEXED, ref UNINDEXED,
    title, text,
    tokenize = "porter unicode61"
);
"""

# Stop words. A superset of `imagelib.store._STOP` (kept local rather than imported: this list has
# to grow with the QUERY dialect authored needs are written in — "footage", "shot", "clip" and
# friends are content words in a film catalogue but pure noise in a b-roll query, and matching them
# would hand back the whole corpus and destroy the abstain signal, which is the point of the module).
_STOP = {
    "the", "a", "an", "of", "and", "or", "in", "on", "to", "for", "with", "by", "at", "from",
    "is", "are", "was", "were", "its", "it", "this", "that", "as", "into", "s", "be", "been",
    "his", "her", "their", "our", "we", "you", "they", "he", "she", "them", "us", "over", "under",
    "shot", "shots", "footage", "clip", "clips", "video", "scene", "image", "picture", "close",
    "up", "view", "showing", "shows", "show", "b", "roll", "broll", "cut", "cuts", "style",
}


def _tokens(text: str) -> List[str]:
    """Lowercased content tokens — punctuation stripped, stop-words and single chars dropped."""
    return [t for t in re.sub(r"[^\w\s]", " ", (text or "").lower()).split()
            if len(t) > 1 and t not in _STOP]


def _stem(w: str) -> str:
    """A light suffix strip, matching what the index's `porter` tokenizer already did to the text.

    The index stems; a Python-side token comparison does not, so `penguins` would miss a stored
    `penguin` and the coverage metric would under-count exactly the rare tokens it depends on.
    """
    for suf in ("ing", "ies", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


def _match_expr(query: str, fields: Optional[str] = None) -> Optional[str]:
    """A safe FTS5 MATCH expression: prefix-match every distinctive token, OR-ed.

    OR, not AND (the KB store AND-s because an insight query is 2-3 precise words). A b-roll query
    is a sentence — "1970s courtroom, wood panelling, men in suits" — and no single document
    contains every token, so AND would abstain on nearly everything and the channel would be dead.
    OR-ing keeps recall and lets bm25 do the discriminating: a row matching four query terms
    outranks one matching a single common term. Zero rows then means what we want it to mean —
    not one distinctive token of this query appears anywhere in the corpus.
    """
    toks = _tokens(query)
    if not toks:
        return None
    expr = " OR ".join(f'"{t}"*' for t in dict.fromkeys(toks))
    if fields:                       # column filter, e.g. fields="title" for identity anchoring
        return f"{{{fields}}} : ({expr})"
    return expr


def _connect(db: Optional[Path] = None) -> sqlite3.Connection:
    p = Path(db or LEX_DB)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _src_id(url: str) -> str:
    """The youtube / archive id embedded in a URL — the key catalog.json is keyed by."""
    from nolan import archive_source as ar
    from nolan.youtube import extract_video_id as yid
    return ar.collection_ref(url) if "archive.org" in (url or "") else (yid(url or "") or "")


def _seg_text(row: sqlite3.Row) -> str:
    """Everything a segment knows, fused into one searchable string.

    `inferred_context` is JSON holding people / location / objects — the identity-bearing fields,
    and the ones a dense embedding of the summary alone smears away.
    """
    import json
    parts = [row["combined_summary"] or "", row["transcript"] or "", row["frame_description"] or ""]
    raw = row["inferred_context"] or ""
    if raw:
        try:
            ctx = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(ctx, dict):
                for key in ("people", "location", "objects", "story_context"):
                    v = ctx.get(key)
                    parts.append(" ".join(v) if isinstance(v, list) else str(v or ""))
        except Exception:
            parts.append(str(raw))
    return " ".join(p for p in parts if p).strip()


def build(clips_db: Optional[Path] = None, base_dir=None, db: Optional[Path] = None,
          verbose: bool = True) -> Dict[str, int]:
    """Rebuild the lexical index from the two tiers. Full rebuild — it derives, it never owns.

    Returns counts, and reports what it could NOT index (a row with no resolvable title or no text
    is dropped, and saying so is the difference between a thin index and a broken one).
    """
    from nolan import transcript_lib as tl
    from nolan.transcript_frames import _parse_tags, frame_lib
    from nolan.indexer import VideoIndex

    cat = tl.load_catalog()
    stats = {"segments": 0, "frames": 0, "videos": 0, "no_title": 0, "no_text": 0}
    conn = _connect(db)
    conn.execute("DELETE FROM lex")

    # ---- tier 1: transcript SEGMENTS (what is said) -------------------------------------------
    if clips_db is None:
        from nolan.acquire.context import _resolve_clips_db
        from nolan.config import load_config
        clips_db = _resolve_clips_db(load_config())
    rows: List[tuple] = []
    if clips_db and Path(clips_db).exists():
        vindex = VideoIndex(Path(clips_db))
        footage = vindex.footage_video_ids()      # real footage is clips_library's job, not this tier
        with sqlite3.connect(str(clips_db)) as c:
            c.row_factory = sqlite3.Row
            seen_videos = set()
            for r in c.execute(
                    "SELECT s.*, v.path AS url, v.id AS vid FROM segments s "
                    "JOIN videos v ON v.id = s.video_id"):
                if r["vid"] in footage:
                    continue
                url = str(r["url"] or "")
                if not url.startswith(("http://", "https://")):
                    continue
                sid = _src_id(url)
                title = str((cat.get(sid) or {}).get("title") or "")
                if not title:
                    stats["no_title"] += 1
                text = _seg_text(r)
                if not text:
                    stats["no_text"] += 1
                    continue
                seen_videos.add(sid or url)
                rows.append(("segment", sid, url, float(r["timestamp_start"] or 0),
                             float(r["timestamp_end"] or 0), f"seg:{r['id']}", title, text))
        stats["segments"] = len(rows)

    # ---- tier 2: frame CAPTIONS (what is shown) -----------------------------------------------
    # One pass over the frame catalog, not `frames_for_video` per video: that helper rescans the
    # whole catalog for each id, which is O(videos x frames) on a store this tier grows fastest.
    lib = frame_lib(base_dir=base_dir)
    nframe = 0
    for a in lib.catalog.list(status="active"):
        tg = _parse_tags(getattr(a, "tags", "") or "")
        vid = tg.get("video_id") or ""
        if not vid:
            continue
        cap = (getattr(a, "description", "") or "").strip()
        if not cap:
            stats["no_text"] += 1
            continue
        e = cat.get(vid) or {}
        title = str(e.get("title") or "")
        if not title:
            stats["no_title"] += 1
        url = str(e.get("url") or "")
        t = float(tg.get("t", 0) or 0)
        rows.append(("frame", vid, url, t, t, f"frm:{a.id}", title, cap))
        nframe += 1
    stats["frames"] = nframe
    stats["videos"] = len({r[1] for r in rows if r[1]})

    conn.executemany(f"INSERT INTO lex ({', '.join(chr(34) + c + chr(34) for c in _COLS)}) "
                     f"VALUES ({', '.join('?' * len(_COLS))})", rows)
    conn.commit()
    conn.close()
    if verbose:
        print(f"[fts] indexed {stats['segments']} segments + {stats['frames']} frame captions "
              f"across {stats['videos']} videos -> {Path(db or LEX_DB).name}")
        if stats["no_title"] or stats["no_text"]:
            print(f"[fts] dropped {stats['no_text']} empty-text rows; "
                  f"{stats['no_title']} rows have no catalog title (indexed, but invisible to a "
                  f"title-weighted query)")
    return stats


def search(query: str, k: int = 12, kind: Optional[str] = None, fields: Optional[str] = None,
           w_title: float = 4.0, w_text: float = 1.0,
           db: Optional[Path] = None) -> List[Dict[str, Any]]:
    """BM25 over the corpus. Returns [] when NOT ONE distinctive query token appears anywhere.

    That empty list is the product, as much as the hits are: it is the abstain signal, and unlike
    a similarity floor it does not expire as the library grows (a term either occurs or it does
    not; it is not a max-of-N statistic).

    `w_title` defaults high because a film's title is the identity signal — "Kimberley" in a title
    means the film is ABOUT Kimberley, while the same token in one transcript segment may be a
    passing mention. Callers routing a `look` query should flatten it (w_title=1.0).
    """
    expr = _match_expr(query, fields=fields)
    if not expr:
        return []
    weights = ", ".join(str(w_title if c == "title" else w_text if c == "text" else 0.0)
                        for c in _COLS)
    sql = (f'SELECT kind, video_id, url, start, "end", ref, title, text, '
           f"bm25(lex, {weights}) AS rank FROM lex WHERE lex MATCH ?")
    args: List[Any] = [expr]
    if kind:
        sql += " AND kind = ?"
        args.append(kind)
    sql += " ORDER BY rank LIMIT ?"          # bm25(): more negative = better
    args.append(int(k))
    conn = _connect(db)
    try:
        out = []
        for r in conn.execute(sql, args):
            d = dict(r)
            d["start"] = float(d["start"] or 0)
            d["end"] = float(d["end"] or 0)
            d["score"] = -float(d.pop("rank"))       # flip so higher = better, like every other channel
            out.append(d)
        return out
    finally:
        conn.close()


def support(query: str, db: Optional[Path] = None) -> Dict[str, Any]:
    """How much of this query does the corpus contain AT ALL? The abstain decision, priced in IDF.

    "Does the OR-query return rows" is far too weak a test, and running it proved it: against this
    corpus "sushi preparation in a Tokyo restaurant" returns three confident rows, because
    `restaurant` and `preparation` both occur in a 1940s hotel-staffing film while `sushi` and
    `tokyo` occur nowhere. Matching the common half of a query is not support — the RARE tokens are
    what a query is about.

    So weight each token by IDF and ask what fraction of the query's INFORMATION the corpus holds.
    An absent token scores the maximum idf and dominates, which is exactly right: a beat naming
    something we have never indexed is a beat we cannot serve.

    Unlike a similarity floor this does not expire as the library grows. It asks whether terms
    OCCUR, not how big a cosine got, so it is not a max-of-N statistic. And when growth does flip a
    token from absent to present, the library genuinely acquired that subject — the signal moves
    for the right reason.

    Measured PER DOCUMENT, not across the corpus — that distinction is the whole metric. Asking
    "do these terms exist anywhere" scores "close-up of hands knitting a wool scarf" at 1.000
    against a library holding no knitting whatsoever, because `knit`, `wool` and `scarf` each turn
    up in three unrelated films. Support means ONE document covers the query, so this takes the
    best single row's coverage.

    Returns {cover, corpus_cover, df, missing, best} — `missing` (tokens absent from the whole
    corpus) is the honest explanation a caller prints when it declines to spend a download.
    """
    import math
    toks = list(dict.fromkeys(_tokens(query)))
    if not toks:
        return {"cover": 0.0, "corpus_cover": 0.0, "df": {}, "missing": [], "tokens": [],
                "best": None}
    conn = _connect(db)
    try:
        n = conn.execute("SELECT count(*) FROM lex").fetchone()[0] or 1
        df = {t: conn.execute("SELECT count(*) FROM lex WHERE lex MATCH ?",
                              (f'"{t}"*',)).fetchone()[0] for t in toks}
    finally:
        conn.close()
    idf = {t: math.log(n / (1 + df[t])) for t in toks}
    total = sum(idf.values()) or 1.0
    corpus_cover = sum(v for t, v in idf.items() if df[t] > 0) / total

    best, best_cover = None, 0.0
    for row in search(query, k=20, db=db):
        words = {_stem(w) for w in _tokens(f"{row['title']} {row['text']}")}
        got = sum(idf[t] for t in toks if _stem(t) in words)
        if got / total > best_cover:
            best_cover, best = got / total, row
    return {"cover": round(best_cover, 3), "corpus_cover": round(corpus_cover, 3), "df": df,
            "missing": [t for t in toks if df[t] == 0], "tokens": toks, "best": best}


def has_support(query: str, min_cover: float = 0.6, db: Optional[Path] = None) -> bool:
    """Is there enough lexical evidence to be worth spending a download on?

    The cheap half of the abstain decision: a handful of index probes, no ranking, no bytes moved.
    """
    return support(query, db=db)["cover"] >= min_cover


def stats(db: Optional[Path] = None) -> Dict[str, int]:
    """Row counts by tier — for the honesty print (`coverage`), never for a decision."""
    conn = _connect(db)
    try:
        out = {"total": conn.execute("SELECT count(*) FROM lex").fetchone()[0]}
        for kind in ("segment", "frame"):
            out[kind] = conn.execute("SELECT count(*) FROM lex WHERE kind = ?", (kind,)).fetchone()[0]
        return out
    finally:
        conn.close()
