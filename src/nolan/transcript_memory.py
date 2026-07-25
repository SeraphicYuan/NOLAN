"""What the LLM has already decided about this library — and what the human then accepted.

A topic search costs ~33s, and MEASURED, 77% of that is two LLM calls: expanding the topic into queries
(17.8s) and judging the shortlist for topical fit (7.5s). The ranking they wrap is essentially free — the
60k-title vector scan is 0.024s. So the thing worth persisting is not the ranking (which goes stale the
moment a survey or an ingest lands, and would then silently hide new material) but the LLM's OUTPUT, which
is about a topic and a video and stays true as the library grows:

* ``topic_queries.json``    — topic → the queries an expansion produced (+ model, date).
* ``topic_judgements.json`` — (topic, video) → fit + why (+ model, date). The re-rank asks the LLM only
  about rows it has never judged, so cost falls as coverage builds and a video stops flip-flopping between
  ``high`` and ``low`` from run to run.
* ``picks_accepted.json``   — the videos a human actually ingested off a shortlist. Free ground truth for
  every threshold in the system (the 0.42 floor, the re-rank prompt, the fit bar), previously thrown away.
* ``topic_vectors.npz``     — one BGE vector per known topic, so a judgement can be reused for a topic that
  is near-identical but not string-identical ("the atomic bomb and the nuclear age" vs "the atomic age").

REUSE IS SCOPED BY TOPIC ON PURPOSE. A film is high-fit *for a subject*, not in general, so a judgement is
reused only for the same topic slug or one whose vector is >= ``REUSE_THR`` — anything else is re-judged. A
judgement from a different model is kept for provenance but never silently mixed into a fresh ranking.

JSON is right at this volume (~36 judgements per search); past ~50k rows this wants SQLite.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REUSE_THR = 0.95                                  # cosine at which two topics count as the same subject
_WS = re.compile(r"[^a-z0-9]+")
# function words are dropped from the KEY so wording noise can't fork the memory. Measured: BGE scores
# "lighthouses and coastal navigation" vs "Lighthouses & coastal navigation!" at 0.919 — the same subject,
# below any sane paraphrase threshold. Normalize the trivial case away; leave real paraphrase to the vectors.
_STOP = {"the", "a", "an", "and", "of", "in", "on", "for", "to", "with", "its", "at", "by", "from"}


def _dir(catalog_dir: Optional[Path] = None) -> Path:
    from nolan.transcript_lib import TRANSCRIPT_DIR
    return Path(catalog_dir) if catalog_dir else TRANSCRIPT_DIR


def slug(topic: str) -> str:
    """Normalized topic key — case, punctuation, spacing and function words can't fork the memory."""
    words = _WS.sub(" ", (topic or "").lower()).split()
    kept = [w for w in words if w not in _STOP]
    return " ".join(kept or words)                # a topic made only of stop-words keeps them


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _load(name: str, catalog_dir: Optional[Path] = None) -> Dict[str, Any]:
    p = _dir(catalog_dir) / name
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save(name: str, data: Dict[str, Any], catalog_dir: Optional[Path] = None) -> None:
    d = _dir(catalog_dir)
    d.mkdir(parents=True, exist_ok=True)
    p, tmp = d / name, d / (name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)                            # atomic — several agents share this tree


# ---------------------------------------------------------------- query expansion cache

def get_queries(topic: str, catalog_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """The cached expansion for a topic, or None. 17.8s of LLM per hit."""
    return _load("topic_queries.json", catalog_dir).get(slug(topic))


def put_queries(topic: str, queries: List[str], model: str = "",
                catalog_dir: Optional[Path] = None) -> None:
    if not (topic or "").strip() or not queries:
        return
    data = _load("topic_queries.json", catalog_dir)
    data[slug(topic)] = {"topic": topic, "queries": list(queries), "model": model, "date": _now()}
    _save("topic_queries.json", data, catalog_dir)


# ---------------------------------------------------------------- topic vectors (near-identical reuse)

def _vec_file(catalog_dir: Optional[Path] = None) -> Path:
    return _dir(catalog_dir) / "topic_vectors.npz"


def topic_vectors(catalog_dir: Optional[Path] = None) -> Tuple[List[str], Any]:
    import numpy as np
    p = _vec_file(catalog_dir)
    if not p.exists():
        return [], None
    try:
        with np.load(p, allow_pickle=False) as z:
            return [str(x) for x in z["slugs"]], np.asarray(z["vecs"], dtype=np.float32)
    except Exception:
        return [], None


def remember_topic(topic: str, catalog_dir: Optional[Path] = None) -> None:
    """Embed a topic once so later searches can spot a near-identical subject (one short string, ~5ms)."""
    import numpy as np

    from nolan.transcript_lib import _embed_titles
    s = slug(topic)
    if not s:
        return
    slugs, mat = topic_vectors(catalog_dir)
    if s in slugs:
        return
    v = np.asarray(_embed_titles([topic]), dtype=np.float32)
    mat = v if mat is None or not len(mat) else np.vstack([mat, v])
    slugs = slugs + [s]
    d = _dir(catalog_dir)
    d.mkdir(parents=True, exist_ok=True)
    np.savez(_vec_file(catalog_dir), slugs=np.array(slugs, dtype=object).astype("U"),
             vecs=np.asarray(mat, dtype=np.float32))


def equivalent_topics(topic: str, thr: float = REUSE_THR,
                      catalog_dir: Optional[Path] = None) -> List[str]:
    """Known topic slugs whose subject is the same as `topic` (cosine >= thr), best first, incl. itself."""
    import numpy as np
    s = slug(topic)
    slugs, mat = topic_vectors(catalog_dir)
    out = [s] if s in slugs else []
    if mat is None or not len(slugs):
        return out
    from nolan.transcript_lib import _embed_titles
    v = np.asarray(_embed_titles([topic]), dtype=np.float32)[0]
    sims = mat @ v
    for i in np.argsort(-sims):
        if float(sims[i]) < thr:
            break
        if slugs[i] not in out:
            out.append(slugs[i])
    return out


# ---------------------------------------------------------------- re-rank judgements

def _jkey(topic_slug: str, video_id: str) -> str:
    return f"{topic_slug}||{video_id}"


def get_judgements(topic: str, video_ids: List[str], catalog_dir: Optional[Path] = None,
                   model: str = "", reuse_thr: float = REUSE_THR) -> Dict[str, Dict[str, Any]]:
    """Existing judgements for these videos on this SUBJECT (exact slug, then near-identical topics).
    A row judged by a different model is not reused — provenance stays honest."""
    data = _load("topic_judgements.json", catalog_dir)
    if not data:
        return {}
    keys = [slug(topic)]
    if reuse_thr < 1.0:
        keys = equivalent_topics(topic, reuse_thr, catalog_dir) or keys
    out: Dict[str, Dict[str, Any]] = {}
    for vid in video_ids:
        for k in keys:
            row = data.get(_jkey(k, vid))
            if row and (not model or not row.get("model") or row.get("model") == model):
                out[vid] = {**row, "reused_from": k if k != slug(topic) else ""}
                break
    return out


def put_judgements(topic: str, rows: List[Dict[str, Any]], model: str = "",
                   catalog_dir: Optional[Path] = None) -> int:
    """Persist fresh judgements ({video_id, fit, why}) for a topic. Returns how many were written."""
    fresh = [r for r in rows if r.get("video_id") and r.get("fit")]
    if not fresh:
        return 0
    data = _load("topic_judgements.json", catalog_dir)
    s, now = slug(topic), _now()
    for r in fresh:
        data[_jkey(s, r["video_id"])] = {"topic": topic, "video_id": r["video_id"],
                                         "fit": r["fit"], "why": (r.get("why") or "")[:160],
                                         "model": model, "date": now}
    _save("topic_judgements.json", data, catalog_dir)
    remember_topic(topic, catalog_dir)
    return len(fresh)


# ---------------------------------------------------------------- acceptance ledger

def record_accepted(picks: List[Dict[str, Any]], source: str = "topic",
                    catalog_dir: Optional[Path] = None) -> int:
    """What the human actually ingested off a shortlist — the only GROUND TRUTH in this loop, and the
    signal every threshold here (the 0.42 floor, the fit bar, the re-rank prompt) should eventually be
    tuned against. Keyed by (video_id, topic) so re-accepting the same row doesn't inflate the count."""
    if not picks:
        return 0
    data = _load("picks_accepted.json", catalog_dir)
    now = _now()
    n = 0
    for p in picks:
        vid = p.get("video_id")
        if not vid:
            continue
        key = _jkey(slug(p.get("topic") or ""), vid)
        if key in data:
            continue
        data[key] = {"video_id": vid, "title": p.get("title") or vid, "topic": p.get("topic") or "",
                     "tier": p.get("tier") or "", "kind": p.get("kind") or "", "fit": p.get("fit") or "",
                     "score": p.get("score"), "rrf": p.get("rrf"),
                     "copyright_free": bool(p.get("copyright_free")), "source": source, "date": now}
        n += 1
    if n:
        _save("picks_accepted.json", data, catalog_dir)
    return n


def load_accepted(catalog_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    return sorted(_load("picks_accepted.json", catalog_dir).values(),
                  key=lambda r: r.get("date") or "", reverse=True)


def mark_unusable(video_id: str, reason: str, title: str = "",
                  catalog_dir: Optional[Path] = None) -> None:
    """Remember an item the pipeline CANNOT use — an access-restricted archive derivative (401/403), a
    missing file (404), a dead download.

    Without this the search keeps recommending it: the ranking only knows the item is not in the catalog,
    so a permanently unusable row scores well and gets picked again on every future topic that touches it.
    Live, one 42-pick run surfaced 6 such items (CSPAN / Al Jazeera recordings mirrored on archive.org)."""
    if not video_id:
        return
    data = _load("unusable.json", catalog_dir)
    row = data.get(video_id) or {"video_id": video_id, "first_seen": _now(), "hits": 0}
    row.update({"reason": str(reason)[:160], "title": title or row.get("title", ""),
                "last_seen": _now(), "hits": int(row.get("hits", 0)) + 1})
    data[video_id] = row
    _save("unusable.json", data, catalog_dir)


def unusable_ids(catalog_dir: Optional[Path] = None) -> set:
    """Ids the search must not offer again (see `mark_unusable`)."""
    return set(_load("unusable.json", catalog_dir).keys())


def coverage(catalog_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Per-SUBJECT coverage: what each searched topic yielded, and how much high-fit material it found that
    nobody has taken yet.

    Growing a library by topic has a blind spot — you see the shortlist you're looking at, never the ones
    you left on the table. `remaining_high` is that: rows this subject's re-ranker called `high` or `medium`
    which are still not in the catalog, i.e. exactly where a SECOND pick would pay without a new search."""
    from nolan.transcript_lib import load_catalog
    have = set(load_catalog(catalog_dir).keys())
    j = _load("topic_judgements.json", catalog_dir)
    acc = _load("picks_accepted.json", catalog_dir)
    by: Dict[str, Dict[str, Any]] = {}
    for r in j.values():
        t = r.get("topic") or ""
        e = by.setdefault(slug(t), {"topic": t, "judged": 0, "high": 0, "medium": 0, "off": 0,
                                    "accepted": 0, "in_library": 0, "remaining_high": 0})
        e["judged"] += 1
        fit = str(r.get("fit") or "")
        if fit in ("high", "medium", "off"):
            e[fit] += 1
        if r.get("video_id") in have:
            e["in_library"] += 1
        elif fit in ("high", "medium"):
            e["remaining_high"] += 1
    for r in acc.values():
        e = by.get(slug(r.get("topic") or ""))
        if e:
            e["accepted"] += 1
    rows = sorted(by.values(), key=lambda e: -e["remaining_high"])
    return {"topics": rows, "count": len(rows),
            "with_material_left": sum(1 for e in rows if e["remaining_high"]),
            "total_remaining_high": sum(e["remaining_high"] for e in rows)}


def stats(catalog_dir: Optional[Path] = None) -> Dict[str, Any]:
    """What the memory holds — surfaced in the Topic tab so the cache is never a black box.

    `accept_rate` is measured against the rows a human could actually have taken (`off` rows were dropped
    before they were ever shown), and broken down per fit. Counting acceptances against EVERY judgement
    including the drops reads as a damningly low number for a re-ranker that is doing its job — the useful
    question is "of the rows it called high, how many did I take?"."""
    j = _load("topic_judgements.json", catalog_dir)
    q = _load("topic_queries.json", catalog_dir)
    acc = _load("picks_accepted.json", catalog_dir)
    fits: Dict[str, int] = {}
    for r in j.values():
        f = str(r.get("fit") or "?")
        fits[f] = fits.get(f, 0) + 1
    shown = sum(n for f, n in fits.items() if f != "off")
    acc_fits: Dict[str, int] = {}
    for r in acc.values():
        f = str(r.get("fit") or "?")
        acc_fits[f] = acc_fits.get(f, 0) + 1
    return {"judgements": len(j), "judged_topics": len({r.get("topic") for r in j.values()}),
            "expansions": len(q), "accepted": len(acc),
            "accepted_topics": len({r.get("topic") for r in acc.values() if r.get("topic")}),
            "fits": fits, "accepted_fits": acc_fits, "shown": shown,
            "dropped_off": fits.get("off", 0),
            "accept_rate": (round(len(acc) / shown, 3) if shown else None),
            "accept_rate_high": (round(acc_fits.get("high", 0) / fits["high"], 3)
                                 if fits.get("high") else None)}
