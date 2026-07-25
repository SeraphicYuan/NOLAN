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

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

FIT_RANK = {"high": 0, "medium": 1, "unjudged": 2, "": 2, "low": 3}
_TOPIC_DUP = 0.90                                    # cosine at which a proposed topic repeats an old one


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

    from nolan.llm import create_text_llm
    from nolan.transcript_lib import _embed_titles, load_catalog
    cat = load_catalog(catalog_dir)
    titles = [str(v.get("title") or "") for v in cat.values() if v.get("title")][:sample]
    used = [t.get("topic") for t in load_used_topics(catalog_dir) if t.get("topic")]
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
    llm = create_text_llm(config)
    out = await llm.generate(prompt, system_prompt=(
        "You plan the coverage of an archival footage library. You propose subjects it lacks."))
    st, en = out.find("{"), out.rfind("}")
    raw = [str(t).strip() for t in (json.loads(out[st:en + 1]).get("topics") or [])
           if str(t).strip()] if st >= 0 and en > st else []
    if not raw:
        return {"topics": [], "dropped": [], "seen": len(used), "model": getattr(llm, "model", "")}
    keep, dropped = [], []
    if used:                                          # gate: drop anything that repeats a searched topic
        uv = np.asarray(_embed_titles(used), dtype=np.float32)
        rv = np.asarray(_embed_titles(raw), dtype=np.float32)
        sims = (rv @ uv.T).max(axis=1)
        for t, s in zip(raw, sims):
            (dropped if float(s) >= _TOPIC_DUP else keep).append(t)
    else:
        keep = raw
    return {"topics": keep[:n], "dropped": dropped, "seen": len(used),
            "model": getattr(llm, "model", "") or type(llm).__name__}


async def broaden_library(config, index, vs, *, count: int = 20, theme: str = "",
                          topics: Optional[List[str]] = None, per_topic: int = 1,
                          min_sec: int = 0, max_sec: int = 0, copyright_free_only: bool = False,
                          kinds: Optional[List[str]] = None, web: bool = True, rerank: bool = True,
                          min_fit: str = "medium", catalog_dir: Optional[Path] = None,
                          progress: Optional[Callable[[float, str], None]] = None) -> Dict[str, Any]:
    """X picks across as many NEW subjects as possible, ready to ingest+caption.

    BREADTH FIRST: one pick per topic until every topic has been tried; only then DEPTH (the next-best
    unused pick from the richest shortlists) to reach `count`. `min_fit` holds the re-ranker's judgement as
    the bar ("high" | "medium" | any), `kinds` restricts the source family (e.g. ["archive"] for the
    PD-leaning archival tiers), and the length/copyright filters are passed straight through to the search.

    Returns {picks, topics, misses, stats} — a PROPOSAL. Dispatching it is the caller's move."""
    from nolan.transcript_lib import suggest_by_topic
    say = progress or (lambda f, m: None)
    want_kinds = set(kinds or ["archive"])
    bar = FIT_RANK.get(min_fit, 1)
    plan = list(topics or [])
    proposed: Dict[str, Any] = {}
    if not plan:
        say(0.02, "proposing topics…")
        # over-propose: some topics yield nothing the filters accept, and depth can't cover a dead topic
        proposed = await propose_topics(config, max(count, 8) + 6, theme, catalog_dir)
        plan = proposed.get("topics") or []
    if not plan:
        return {"picks": [], "topics": [], "misses": [["*", "no topics proposed"]],
                "stats": {"proposed": proposed}}

    from nolan.transcript_lib import load_catalog
    taken = set(load_catalog(catalog_dir).keys())
    picks: List[Dict[str, Any]] = []
    pools: List[tuple] = []
    misses: List[List[str]] = []
    searched: List[str] = []
    per_topic_count: Dict[str, int] = {}
    for i, t in enumerate(plan):
        if len(picks) >= count:
            break
        say(0.05 + 0.8 * (i / max(1, len(plan))), f"[{i + 1}/{len(plan)}] {t[:48]}")
        try:
            d = await suggest_by_topic(t, index, vs, config, n=12, catalog_dir=catalog_dir,
                                       copyright_free_only=copyright_free_only, web=web, rerank=rerank,
                                       min_sec=min_sec, max_sec=max_sec)
        except Exception as e:
            misses.append([t, f"{type(e).__name__}: {e}"[:120]])
            continue
        searched.append(t)
        cand = [s for s in (d.get("suggestions") or [])
                if s.get("kind") in want_kinds and s.get("video_id") not in taken
                and FIT_RANK.get(s.get("fit") or "", 2) <= bar]
        cand.sort(key=lambda s: (FIT_RANK.get(s.get("fit") or "", 2), -float(s.get("rrf") or 0)))
        if not cand:
            misses.append([t, "no candidate cleared the filters"])
            continue
        for p in cand[:max(1, per_topic)]:
            if len(picks) >= count:
                break
            taken.add(p["video_id"])
            picks.append({**p, "topic": t})
            per_topic_count[t] = per_topic_count.get(t, 0) + 1
        pools.append((t, [c for c in cand if c["video_id"] not in taken]))

    depth = 0
    while len(picks) < count and any(pool for _t, pool in pools):        # topics exhausted → go deeper
        for t, pool in pools:
            if len(picks) >= count:
                break
            while pool:
                p = pool.pop(0)
                if p["video_id"] in taken:
                    continue
                taken.add(p["video_id"])
                picks.append({**p, "topic": t, "depth": True})
                per_topic_count[t] = per_topic_count.get(t, 0) + 1
                depth += 1
                break
    if searched:
        record_used_topics(searched, catalog_dir, per_topic_count)
    say(1.0, f"{len(picks)} picks across {len(per_topic_count)} topics")
    return {"picks": picks, "topics": searched, "misses": misses,
            "stats": {"requested": count, "topics_tried": len(searched), "topics_with_picks":
                      len(per_topic_count), "depth_picks": depth, "proposed": proposed,
                      "filters": {"min_sec": min_sec, "max_sec": max_sec, "kinds": sorted(want_kinds),
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
