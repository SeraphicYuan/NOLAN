"""LIBRARY BROADENING — "give me X more captioned videos, on subjects I don't have yet".

The transcript library grows one deliberate search at a time: you think of a topic, run the Topic tab, pick
from the shortlist. That is the right tool when you KNOW what you want; it is a poor tool for coverage,
because the topics you think of are the topics you already have.

This organ turns that loop into one call:

    propose_topics  (LLM, open-ended)   → topics the library does NOT already cover
    suggest_by_topic (per topic)        → the existing 3-tier ranked search, with the caller's filters
    breadth then depth (deterministic)  → one pick per topic first; only then a 2nd/3rd from the richest
                                          shortlists, so X picks span X subjects wherever possible

The LLM's topic list is a PROPOSAL: it passes a deterministic gate (drop anything near a topic already used
— cosine over BGE title vectors — and anything already in the catalog) before it can spend a search. The
picks themselves are a proposal too: the caller (the Topic tab, or a job) reviews them and dispatches the
ingest+caption, exactly as a hand-run search does. Nothing is ingested behind the user's back unless
`auto_dispatch` is asked for explicitly.

Used topics persist to ``topics_used.json`` so a second run broadens instead of repeating.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

FIT_RANK = {"high": 0, "medium": 1, "unjudged": 2, "": 2, "low": 3}
_TOPIC_DUP = 0.90                                    # cosine at which a proposed topic repeats an old one
# Relevance vs novelty in the depth pass. 0.5 is not a taste knob — it is the point where a PERFECTLY
# redundant candidate (cos 1.0) can never outrank a perfectly novel one, at any pool size. Above it the
# outcome depends on how deep the pool happens to be: at 0.7 a duplicate beat a distinct row in a 2-item
# pool (rank gap 0.5) and lost in a 12-item pool (rank gap 0.08) — same rule, opposite answer.
_MMR_LAMBDA = 0.5
# The families whose crawl carries a duration for EVERY row (measured on the live surveys: youtube 100%,
# youtube_cc 100%, archive 14.0%). Filtering by length costs nothing here and an HTTP round-trip per row
# on archive — so the sweep filters these and lets `_capture_visual_tier` enforce the rest after download.
LENGTH_RELIABLE_KINDS = ("youtube", "youtube_cc")


ALL_KINDS = ("archive", "youtube", "youtube_cc")      # every source family the library knows


def surveyed_kinds(catalog_dir: Optional[Path] = None) -> List[str]:
    """Every source family actually present in the surveys — the default acceptance set for a run.

    This used to be hardcoded to ``["archive"]`` behind an `or`, which meant the Topic tab's "archive only"
    checkbox did nothing when UNCHECKED (it sent `kinds:null`, which fell straight back to archive) — a
    broaden run could not pick a YouTube video at all.

    Falls back to every known family when no survey is readable: an EMPTY acceptance set would reject every
    candidate silently, which is the failure mode this whole function exists to remove."""
    from nolan.transcript_lib import load_surveys
    kinds = {(sv.get("kind") or "youtube") for sv in load_surveys(catalog_dir).values()}
    return sorted(k for k in kinds if k) or list(ALL_KINDS)


def _load_json_values(name: str, catalog_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Values of a transcript-library sidecar dict, or [] — used to fold every searched topic (not just
    broaden's own runs) into what the proposer is told to avoid."""
    from nolan import transcript_memory as mem
    return list(mem._load(name, catalog_dir).values())


def _used_file(catalog_dir: Optional[Path] = None) -> Path:
    from nolan.transcript_lib import TRANSCRIPT_DIR
    return (Path(catalog_dir) if catalog_dir else TRANSCRIPT_DIR) / "topics_used.json"


def load_used_topics(catalog_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    p = _used_file(catalog_dir)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("topics") or []
        except (json.JSONDecodeError, OSError):
            pass
    return []


def record_used_topics(topics: List[str], catalog_dir: Optional[Path] = None,
                       picked: Optional[Dict[str, int]] = None) -> None:
    """Append the topics a run actually SEARCHED (with how many picks each yielded) so the next run can
    propose different ones — and so a topic that keeps yielding nothing is visible."""
    used = load_used_topics(catalog_dir)
    now = _dt.datetime.now().isoformat(timespec="seconds")
    seen = {t.get("topic") for t in used}
    for t in topics:
        if t in seen:
            for row in used:
                if row.get("topic") == t:
                    row["picked"] = int(row.get("picked", 0)) + int((picked or {}).get(t, 0))
                    row["last_used"] = now
            continue
        used.append({"topic": t, "first_used": now, "last_used": now,
                     "picked": int((picked or {}).get(t, 0))})
    p = _used_file(catalog_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"topics": used}, indent=2, ensure_ascii=False), encoding="utf-8")


async def propose_topics(config, n: int = 20, theme: str = "", catalog_dir: Optional[Path] = None,
                         sample: int = 60) -> Dict[str, Any]:
    """LLM-proposed topics the library does NOT already cover. Shown a sample of what IS in the library plus
    every topic already searched, and asked for subjects a video essay could actually be built from.

    Deterministic gate: near-duplicates of already-used topics are dropped (BGE cosine >= 0.90), so a run
    can't burn its budget re-searching the same ground. Returns {topics, dropped, seen}."""
    import numpy as np

    from nolan import transcript_memory as mem
    from nolan.llm import create_text_llm
    from nolan.transcript_lib import _embed_titles, load_catalog, topic_cluster
    cat = load_catalog(catalog_dir)
    rows = [v for v in cat.values() if v.get("title")]
    # a DIVERSE sample, not the first N: the head of a catalog is whatever was ingested first, which tells
    # the model nothing about the library's spread. Cluster the titles and show one medoid per cluster.
    if len(rows) > sample:
        try:
            groups = topic_cluster([{"video_id": v.get("video_id"), "title": v.get("title")} for v in rows],
                                   sample)
            by_id = {v.get("video_id"): v for v in rows}
            rows = [by_id[g["medoid_id"]] for g in groups if g.get("medoid_id") in by_id]
        except Exception:
            rows = rows[:sample]
    titles = [str(v.get("title") or "") for v in rows][:sample]
    # every topic ALREADY SEARCHED — from broaden's own history AND from any hand-run Topic-tab search
    # (the expansion cache records those), plus the subjects whose picks were actually accepted
    used = [t.get("topic") for t in load_used_topics(catalog_dir) if t.get("topic")]
    seen_topics = {t for t in used}
    for row in _load_json_values("topic_queries.json", catalog_dir):
        if row.get("topic") and row["topic"] not in seen_topics:
            seen_topics.add(row["topic"])
            used.append(row["topic"])
    for row in mem.load_accepted(catalog_dir):
        if row.get("topic") and row["topic"] not in seen_topics:
            seen_topics.add(row["topic"])
            used.append(row["topic"])
    prompt = (
        (f'Theme to stay within: "{theme}".\n\n' if theme else "")
        + "A transcript/footage library already holds these videos:\n"
        + "\n".join(f"- {t[:90]}" for t in titles)
        + ("\n\nTopics already searched (do NOT repeat these):\n"
           + "\n".join(f"- {t[:90]}" for t in used[-80:]) if used else "")
        + f"\n\nPropose {n} NEW topics to BROADEN this library — subjects a documentary video essay could be "
          "built from, that the list above does not already cover. Each topic should be a short phrase "
          "(4-10 words) naming a subject, era or industry, not a question. Favour subjects with real "
          "archival footage.\n"
          'Respond ONLY JSON: {"topics":["...","..."]}')
    model, err = "", ""
    raw: List[str] = []
    try:
        llm = create_text_llm(config)
        model = getattr(llm, "model", "") or type(llm).__name__
        out = await llm.generate(prompt, system_prompt=(
            "You plan the coverage of an archival footage library. You propose subjects it lacks."))
        st, en = out.find("{"), out.rfind("}")
        if st >= 0 and en > st:
            raw = [str(t).strip() for t in (json.loads(out[st:en + 1]).get("topics") or []) if str(t).strip()]
        if not raw:
            err = "the model returned no parseable topics"      # observed live: one transient empty reply
    except Exception as e:                                      # loud, like the expansion path — an empty
        err = f"{type(e).__name__}: {e}"[:160]                   # proposal used to read as "0 topics"
    if not raw:
        return {"topics": [], "dropped": [], "seen": len(used), "model": model, "error": err}
    keep, dropped = [], []
    if used:                                          # gate: drop anything that repeats a searched topic
        uv = np.asarray(_embed_titles(used), dtype=np.float32)
        rv = np.asarray(_embed_titles(raw), dtype=np.float32)
        sims = (rv @ uv.T).max(axis=1)
        for t, s in zip(raw, sims):
            (dropped if float(s) >= _TOPIC_DUP else keep).append(t)
    else:
        keep = raw
    return {"topics": keep[:n], "dropped": dropped, "seen": len(used), "model": model, "error": ""}


_CLUSTER_TARGET = 150            # ~titles per cluster; k is derived from corpus size, never fixed
_CLUSTER_MAX = 300               # KMeans ceiling — beyond this the clustering costs more than it buys
_MIN_REAL_TITLES = 0.5           # a cluster of raw scan ids is not a subject
_MIN_UNIQ_TOKENS = 0.45          # ...and neither is a numbered RUN of the same title


def _topic_worthy(items: List[Dict[str, Any]]) -> bool:
    """Is this cluster a SUBJECT, or just a run of catalogue numbers?

    Measured on the live Prelinger clustering, two distinct junk shapes appear and one test can't catch
    both. Raw-scan clusters ("001000", "001002", "001004") score a PERFECT unique-token ratio precisely
    because every id differs — they are caught by `_real_title` instead. Boilerplate runs ("Home Movie:
    001139", "Home Movie: 10409") pass `_real_title` on the word "Home" — they are caught by the token
    ratio (0.024-0.355 measured, against 0.58-0.72 for real subject clusters)."""
    from nolan.transcript_lib import _real_title, _tok
    titles = [str(i.get("title") or "") for i in items]
    if not titles:
        return False
    real = sum(1 for i in items if _real_title(i.get("title"), i.get("video_id")))
    if real / len(titles) < _MIN_REAL_TITLES:
        return False
    toks = [w for t in titles for w in _tok(t)]
    return bool(toks) and (len(set(toks)) / len(toks)) >= _MIN_UNIQ_TOKENS


def corpus_topics(k: int = 0, catalog_dir: Optional[Path] = None,
                  kinds: Optional[List[str]] = None, want: int = 20) -> Dict[str, Any]:
    """Topics DERIVED from the surveyed corpus — the coverage gaps that are actually SERVABLE.

    `propose_topics` asks an LLM for subjects the library lacks, then gates out anything close to a topic
    already searched. With the global archive tier off, those two halves fight each other: the better it
    broadens, the more likely each topic returns zero, because the corpus it searches is 83% Bloomberg/PBS
    plus 10k Prelinger and an open-ended proposer will keep naming things none of them cover.

    So invert it. Cluster what the surveys ALREADY hold, subtract the clusters the captioned catalog already
    represents, and what remains is the gap — every topic guaranteed to have candidates behind it. No LLM,
    and no query expansion needed downstream either: a cluster's keyword label is already corpus-shaped, so
    it embeds against the title index without the rescue an LLM-written prose topic needs.

    Clustering reuses the PERSISTED `title_vectors.npz` (`vecs=` on `topic_cluster`), so the 60k-row corpus
    costs no embedding.

    Clustered PER SOURCE FAMILY, then interleaved. Measured on the live corpus: 48,765 of the 60,259 rows
    (81%) are one Bloomberg feed, so a single global clustering returns nothing but finance interview clips
    ("says · ceo · growth") and the archive/PD material never surfaces. Round-robin across the families the
    caller selected gives breadth across SOURCES, not just across whoever crawled the most.

    The searched topic is the cluster's MEDOID TITLE, not its keyword label: the medoid is a real title from
    the corpus, so it embeds against the title index by construction, while a TF-IDF word triple is both a
    worse query and unreadable. The label rides along for display.

    Returns {topics, groups, error} — groups carry size + catalog coverage so a caller can show WHY each
    topic was chosen."""
    from collections import Counter

    import numpy as np

    from nolan import transcript_lib as tl
    from nolan import transcript_memory as mem
    from nolan import transcript_vectors as tvec
    cat = tl.load_catalog(catalog_dir)
    corpus = tvec.rows(catalog_dir, exclude=set(cat.keys()) | mem.unusable_ids(catalog_dir))
    if kinds:
        want_k = set(kinds)
        corpus = {v: r for v, r in corpus.items() if r.get("kind") in want_k}
    if not corpus:
        return {"topics": [], "groups": [], "error": "no surveyed rows for those source families"}
    ids, mat, pending = tvec.ensure(corpus, catalog_dir)
    if mat is None or not len(ids):
        return {"topics": [], "groups": [], "error": "the title-vector index is empty — build it first"}
    pos = {v: i for i, v in enumerate(ids)}
    cat_titles = [str(v.get("title") or "") for v in cat.values() if v.get("title")]
    C = np.asarray(tl._embed_titles(cat_titles), dtype=np.float32) if cat_titles else None

    by_kind: Dict[str, List[str]] = {}
    for v in ids:
        by_kind.setdefault(corpus[v].get("kind") or "youtube", []).append(v)

    per_family: Dict[str, List[Dict[str, Any]]] = {}
    dropped: Dict[str, int] = {}
    n_clusters = 0
    for kind, vids in sorted(by_kind.items()):
        sub = [{"video_id": v, "title": corpus[v]["title"]} for v in vids]
        kk = int(k) if k else max(4, min(_CLUSTER_MAX, len(sub) // _CLUSTER_TARGET))
        groups = tl.topic_cluster(sub, min(kk, len(sub)), vecs=np.asarray([mat[pos[v]] for v in vids]))
        if not groups:
            continue
        n_clusters += len(groups)
        # coverage: assign every captioned row to its nearest cluster medoid within this family
        med = [g.get("medoid_id") for g in groups]
        M = np.asarray([mat[pos[m]] for m in med if m in pos], dtype=np.float32)
        covered: Counter = Counter()
        if C is not None and len(M):
            for j in (C @ M.T).argmax(axis=1):
                covered[int(j)] += 1
        rows = []
        for j, g in enumerate(groups):
            items = g.get("items") or []
            if not _topic_worthy(items):
                dropped[kind] = dropped.get(kind, 0) + 1     # no silent cap: report what was rejected
                continue
            mid = g.get("medoid_id")
            title = next((i.get("title") for i in items if i.get("video_id") == mid), "")
            if not title:
                continue
            n_cov = int(covered.get(j, 0))
            rows.append({"topic": title, "label": g.get("label") or "", "kind": kind,
                         "size": int(g.get("size") or 0), "covered": n_cov,
                         "ratio": n_cov / max(1, int(g.get("size") or 1))})
        # least-covered first, and among equals the biggest cluster — most unmined material per search
        rows.sort(key=lambda g: (g["ratio"], -g["size"]))
        per_family[kind] = rows

    # Globally least-covered first, but no family may take more than `cap` of the plan. Strict round-robin
    # was worse: with 3 families it promoted an ALREADY 100%-captioned stock-footage cluster over an
    # untouched archive one purely to keep its turn.
    import math
    cap = max(2, math.ceil(want / max(1, len(per_family))) + 2) if len(per_family) > 1 else want
    ranked = sorted([r for rows in per_family.values() for r in rows],
                    key=lambda g: (g["ratio"], -g["size"]))
    out: List[Dict[str, Any]] = []
    used: Dict[str, int] = {}
    for r in ranked:
        if len(out) >= want:
            break
        if used.get(r["kind"], 0) >= cap:
            continue
        used[r["kind"]] = used.get(r["kind"], 0) + 1
        out.append(r)
    return {"topics": [g["topic"] for g in out], "groups": out, "clusters": n_clusters,
            "corpus": len(ids), "families": {k2: len(v) for k2, v in by_kind.items()},
            "dropped_clusters": dropped, "family_cap": cap, "pending": pending, "error": ""}


def _mmr_order(pool: List[Dict[str, Any]], vec_of: Dict[str, Any], chosen: List[Any],
               lam: float = _MMR_LAMBDA):
    """Maximal Marginal Relevance over the shortlist's title vectors: the next depth pick is the one that
    is still well-ranked but LEAST like what we already hold.

    ``score = lam * rel - (1 - lam) * max cos(candidate, chosen)`` where `rel` is the candidate's existing
    fit-then-RRF position (so the established preference order is preserved) and `chosen` is
    already-picked-this-run PLUS the captioned library. Two dedup guards already existed — exact video id
    (`taken`) and near-identical titles within a tier (`_collapse_near_duplicates`) — and this fills the band
    between them: a fifth Prelinger car-safety film with a different title.

    Returns the pool re-ordered; falls back to the incoming order if vectors are unavailable."""
    import numpy as np
    if not pool:
        return pool
    if not chosen:
        return list(pool)
    V = np.asarray(chosen, dtype=np.float32)
    n = len(pool)
    scored = []
    for rank, c in enumerate(pool):
        v = vec_of.get(c.get("video_id"))
        rel = 1.0 - (rank / max(1, n))
        red = float(np.max(V @ np.asarray(v, dtype=np.float32))) if v is not None else 0.0
        scored.append((lam * rel - (1.0 - lam) * red, rank, c))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [c for _s, _r, c in scored]


async def broaden_library(config, index, vs, *, count: int = 20, theme: str = "",
                          topics: Optional[List[str]] = None, per_topic: int = 1,
                          min_sec: int = 0, max_sec: int = 0, copyright_free_only: bool = False,
                          kinds: Optional[List[str]] = None, web: bool = False, rerank: bool = True,
                          min_fit: str = "medium", catalog_dir: Optional[Path] = None,
                          concurrency: int = 4, topic_source: str = "corpus", expand: bool = False,
                          length_kinds: Optional[List[str]] = LENGTH_RELIABLE_KINDS,
                          progress: Optional[Callable[[float, str], None]] = None) -> Dict[str, Any]:
    """X picks across as many NEW subjects as possible, ready to ingest+caption.

    BREADTH FIRST: one pick per topic until every topic has been tried; only then DEPTH (the next-best
    unused pick from the richest shortlists) to reach `count`. `min_fit` holds the re-ranker's judgement as
    the bar ("high" | "medium" | any), `kinds` restricts the source family (e.g. ["archive"] for the
    PD-leaning archival tiers), and the length/copyright filters are passed straight through to the search.

    Returns {picks, topics, misses, stats} — a PROPOSAL. Dispatching it is the caller's move."""
    from nolan.transcript_lib import expand_topics_batch, suggest_by_topic
    say = progress or (lambda f, m: None)
    want_kinds = set(kinds) if kinds else set(surveyed_kinds(catalog_dir))
    bar = FIT_RANK.get(min_fit, 1)
    plan = list(topics or [])
    proposed: Dict[str, Any] = {}
    if not plan:
        # over-propose: some topics yield nothing the filters accept, and depth can't cover a dead topic
        n_want = max(count, 8) + 6
        if topic_source == "corpus":
            say(0.02, "clustering the surveyed corpus…")
            proposed = corpus_topics(catalog_dir=catalog_dir, kinds=sorted(want_kinds), want=n_want)
        else:
            say(0.02, "proposing topics…")
            proposed = await propose_topics(config, n_want, theme, catalog_dir)
        plan = proposed.get("topics") or []
    if not plan:
        why = (proposed or {}).get("error") or "no topics proposed"
        return {"picks": [], "topics": [], "misses": [["*", why]], "stats": {"proposed": proposed}}

    # ONE expansion call for the whole plan instead of one per topic (19.7s each, serially = ~10 min on a
    # 30-topic run). It PREWARMS the same cache `suggest_by_topic` reads, so the per-topic path is unchanged.
    expansion: Dict[str, Any] = {}
    if expand:
        say(0.04, f"expanding {len(plan)} topics in one call…")
        expansion = await expand_topics_batch(plan, config, catalog_dir)

    from nolan.transcript_lib import load_catalog
    taken = set(load_catalog(catalog_dir).keys())
    picks: List[Dict[str, Any]] = []
    pools: List[tuple] = []
    misses: List[List[str]] = []
    searched: List[str] = []
    per_topic_count: Dict[str, int] = {}

    # The per-topic searches are INDEPENDENT and IO-bound (two LLM calls + an archive round-trip each), so
    # they run with bounded concurrency — sequentially they cost ~90s per fresh subject, i.e. 45 minutes for
    # a 30-topic run. SELECTION stays deterministic: results are re-ordered back into the planned topic
    # order before any pick is taken, so concurrency changes the wall-clock, never the outcome.
    sem = asyncio.Semaphore(max(1, int(concurrency)))
    done = {"n": 0}

    async def _one(idx, topic):
        async with sem:
            try:
                d = await suggest_by_topic(topic, index, vs, config, n=12, catalog_dir=catalog_dir,
                                           copyright_free_only=copyright_free_only, web=web, rerank=rerank,
                                           min_sec=min_sec, max_sec=max_sec, expand=expand,
                                           length_kinds=length_kinds)
            except Exception as e:
                d = {"_error": f"{type(e).__name__}: {e}"[:120]}
            done["n"] += 1
            say(0.05 + 0.8 * (done["n"] / max(1, len(plan))), f"[{done['n']}/{len(plan)}] {topic[:48]}")
            return idx, topic, d

    results = await asyncio.gather(*[_one(i, t) for i, t in enumerate(plan)])
    for _idx, t, d in sorted(results, key=lambda r: r[0]):
        if d.get("_error"):
            misses.append([t, d["_error"]])
            continue
        searched.append(t)
        cand = [s for s in (d.get("suggestions") or [])
                if s.get("kind") in want_kinds and s.get("video_id") not in taken
                and FIT_RANK.get(s.get("fit") or "", 2) <= bar]
        cand.sort(key=lambda s: (FIT_RANK.get(s.get("fit") or "", 2), -float(s.get("rrf") or 0)))
        if not cand:
            misses.append([t, "no candidate cleared the filters"])
            continue
        if len(picks) < count:
            for p in cand[:max(1, per_topic)]:
                if len(picks) >= count:
                    break
                taken.add(p["video_id"])
                picks.append({**p, "topic": t})
                per_topic_count[t] = per_topic_count.get(t, 0) + 1
        pools.append((t, [c for c in cand if c["video_id"] not in taken]))

    # --- DEPTH, diversified. Vectors for every shortlisted title + the captioned library, embedded once. ---
    vec_of: Dict[str, Any] = {}
    chosen: List[Any] = []
    mmr_on = False
    try:
        import numpy as np

        from nolan.transcript_lib import _embed_titles, load_catalog as _lc
        cand_ids, cand_titles = [], []
        for _t, pool in pools:
            for c in pool:
                if c["video_id"] not in vec_of and c["video_id"] not in cand_ids:
                    cand_ids.append(c["video_id"])
                    cand_titles.append(str(c.get("title") or ""))
        lib_titles = [str(v.get("title") or "") for v in _lc(catalog_dir).values() if v.get("title")]
        picked_titles = [str(p.get("title") or "") for p in picks]
        allv = _embed_titles(cand_titles + lib_titles + picked_titles) if cand_titles else []
        if len(allv):
            A = np.asarray(allv, dtype=np.float32)
            for i, vid in enumerate(cand_ids):
                vec_of[vid] = A[i]
            chosen = list(A[len(cand_ids):])            # library + this run's breadth picks
            mmr_on = True
    except Exception as e:                              # a diversity metric must never break the run
        misses.append(["*", f"diversity off: {type(e).__name__}: {e}"[:120]])

    depth = 0
    while len(picks) < count and any(pool for _t, pool in pools):        # topics exhausted → go deeper
        for i, (t, pool) in enumerate(pools):
            if len(picks) >= count:
                break
            if mmr_on and pool:
                pools[i] = (t, _mmr_order(pool, vec_of, chosen))
                pool = pools[i][1]
            while pool:
                p = pool.pop(0)
                if p["video_id"] in taken:
                    continue
                taken.add(p["video_id"])
                picks.append({**p, "topic": t, "depth": True})
                per_topic_count[t] = per_topic_count.get(t, 0) + 1
                if mmr_on and vec_of.get(p["video_id"]) is not None:
                    chosen.append(vec_of[p["video_id"]])
                depth += 1
                break
    if searched:
        record_used_topics(searched, catalog_dir, per_topic_count)
    say(1.0, f"{len(picks)} picks across {len(per_topic_count)} topics")
    return {"picks": picks, "topics": searched, "misses": misses,
            "stats": {"requested": count, "topics_tried": len(searched), "topics_with_picks":
                      len(per_topic_count), "depth_picks": depth, "proposed": proposed,
                      "topic_source": topic_source, "expansion": expansion, "diversity": mmr_on,
                      "filters": {"min_sec": min_sec, "max_sec": max_sec, "kinds": sorted(want_kinds),
                                  "length_kinds": (sorted(length_kinds) if length_kinds is not None
                                                   else "all"), "web": bool(web), "expand": bool(expand),
                                  "copyright_free_only": copyright_free_only, "min_fit": min_fit}}}


def dispatch_groups(picks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group picks into ingest calls the way the Topic tab does — by (kind, source, copyright status), so
    each batch records the right provenance instead of falling back to defaults."""
    groups: Dict[tuple, Dict[str, Any]] = {}
    for p in picks:
        key = (p.get("kind") or "archive", p.get("channel") or "", bool(p.get("copyright_free")))
        g = groups.setdefault(key, {"kind": key[0], "collection": key[1], "copyright_free": key[2],
                                    "videos": []})
        g["videos"].append({"video_id": p["video_id"], "url": p.get("url") or "",
                            "title": p.get("title") or p["video_id"], "channel": p.get("channel") or ""})
    return list(groups.values())
