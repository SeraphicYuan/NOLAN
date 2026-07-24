"""Transcript library — index YouTube CHANNEL transcripts (captions only, NO video download) as a
lightweight DISCOVERY tier of the video library (VideoIndex, source_kind='transcript', has_footage=0).

A transcript-only row is searchable alongside real footage (same VectorSearch embeddings) so you can
find *which video, and roughly when*, a topic is discussed across whole channels — cheaply, without
storing or ingesting video. It is EXCLUDED from clips_library acquisition (the has_footage gate):
discovery, not a footage source. When you actually want the footage, clip-from-url the range and ingest
it — that becomes a has_footage=1 row.

Pipeline: list_channel -> fetch_transcript_with_cues (yt-dlp captions) -> chunk_transcript (overlapping
timestamped windows) -> ingest_transcript (VideoIndex rows). The caller embeds via VectorSearch so the
transcript joins the unified semantic search.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]                    # src/nolan/transcript_lib.py -> repo root
TRANSCRIPT_DIR = REPO / "projects" / "_library" / "transcripts"


def _catalog_file(catalog_dir: Optional[Path] = None) -> Path:
    return (Path(catalog_dir) if catalog_dir else TRANSCRIPT_DIR) / "catalog.json"


def load_catalog(catalog_dir: Optional[Path] = None) -> Dict[str, Any]:
    """The transcript library's DISPLAY sidecar {youtube_video_id: {title, channel, url, windows, …}}.
    The searchable segments live in VideoIndex; this holds what the browse/search UI shows (the videos
    table has no title/channel columns). Repo-anchored, NOT cwd."""
    p = _catalog_file(catalog_dir)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def record_transcript(video_id: str, meta: Dict[str, Any], windows_n: int, channel: Optional[str],
                      *, frames: int = 0, added: str = "", catalog_dir: Optional[Path] = None,
                      broll: bool = False, kind: str = "youtube", copyright_free: bool = False) -> None:
    """Upsert one transcript video's display metadata into the sidecar (keyed by the YouTube video id).
    `frames` = how many visual keyframes were captioned (drives the visual-coverage badge). `broll` = a ready
    b-roll short clip. `kind`/`copyright_free` = the source family + license status (so the acquire engine can
    mark the pooled asset: copyright-free stock/PD vs a copyrighted documentary reference)."""
    cat = load_catalog(catalog_dir)
    cat[str(video_id)] = {
        "video_id": str(video_id), "title": meta.get("title"),
        "channel": channel or meta.get("channel"), "url": meta.get("url"),
        "upload_date": meta.get("upload_date"), "language": meta.get("language"),
        "windows": int(windows_n), "frames": int(frames), "added": added, "broll": bool(broll),
        "kind": kind, "copyright_free": bool(copyright_free),
    }
    p = _catalog_file(catalog_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cat, indent=2, ensure_ascii=False), encoding="utf-8")


# ---- first-class SOURCES (channels you add over time) — a sidecar list, so a channel persists +
# is re-crawlable even if a crawl found nothing. projects/_library/transcripts/sources.json ------------

def _sources_file(catalog_dir: Optional[Path] = None) -> Path:
    return (Path(catalog_dir) if catalog_dir else TRANSCRIPT_DIR) / "sources.json"


def load_sources(catalog_dir: Optional[Path] = None) -> Dict[str, Any]:
    """{channel: {channel, label, added, last_crawled, video_count}} — the managed source list."""
    p = _sources_file(catalog_dir)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def upsert_source(channel: str, *, label: Optional[str] = None, last_crawled: Optional[str] = None,
                  video_count: Optional[int] = None, added: str = "", catalog_dir: Optional[Path] = None,
                  kind: Optional[str] = None, copyright_free: Optional[bool] = None) -> None:
    srcs = load_sources(catalog_dir)
    s = srcs.get(channel) or {"channel": channel, "added": added or last_crawled or ""}
    if label is not None:
        s["label"] = label
    if last_crawled is not None:
        s["last_crawled"] = last_crawled
    if video_count is not None:
        s["video_count"] = int(video_count)
    if kind is not None:
        s["kind"] = kind                                          # 'youtube' | 'archive'
    if copyright_free is not None:
        s["copyright_free"] = bool(copyright_free)                # collection-level PD/CC assertion (archive)
    s.setdefault("label", channel)
    s.setdefault("kind", "youtube")
    s.setdefault("added", s.get("last_crawled", ""))
    srcs[channel] = s
    p = _sources_file(catalog_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(srcs, indent=2, ensure_ascii=False), encoding="utf-8")


def remove_source(channel: str, catalog_dir: Optional[Path] = None) -> bool:
    """Drop a channel from the managed list (its already-indexed videos stay searchable)."""
    srcs = load_sources(catalog_dir)
    if channel in srcs:
        del srcs[channel]
        _sources_file(catalog_dir).write_text(json.dumps(srcs, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    return False


def delete_transcript(index, video_id: str, catalog_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Remove a transcript video EVERYWHERE: its VideoIndex rows (segments + video + Chroma vectors), its
    visual-tier frames, and the sidecar catalog entry. Returns a per-store summary."""
    from nolan import transcript_frames as tfr
    fp = f"yt:{video_id}"
    summary: Dict[str, Any] = {"video_id": video_id}
    vid = index.get_video_id(fp)
    if vid is not None:
        try:
            summary["db"] = index.delete_video(vid, delete_file=False)
        except Exception as e:
            summary["db_error"] = f"{type(e).__name__}: {e}"
        try:                                                  # drop embeddings (delete_video keeps no Chroma dep)
            from nolan.vector_search import VectorSearch
            VectorSearch(Path(index.db_path).parent / "vectors", index=index).delete_video_vectors(vid)
        except Exception:
            pass
    summary["frames"] = tfr.delete_frames_for_video(video_id)
    cat = load_catalog(catalog_dir)
    if str(video_id) in cat:
        del cat[str(video_id)]
        _catalog_file(catalog_dir).write_text(json.dumps(cat, indent=2, ensure_ascii=False), encoding="utf-8")
        summary["catalog"] = True
    return summary


def video_detail(index, video_id: str, catalog_dir: Optional[Path] = None) -> Dict[str, Any]:
    """A transcript video's drill-down: {meta, windows, frames, storyboard} — the transcript timeline joined
    to its ffmpeg snapshots + gemma captions (visual tier), each frame carrying its split-out structured
    fields (people/location/objects/story) + content_kind for the detail column + b-roll badge, plus the
    whole-video storyboard filmstrip (the free overview)."""
    import sqlite3

    from nolan import transcript_frames as tfr
    vid = index.get_video_id(f"yt:{video_id}")
    meta = load_catalog(catalog_dir).get(str(video_id), {"video_id": video_id})
    windows: List[Dict[str, Any]] = []
    if vid is not None:
        with sqlite3.connect(index.db_path) as c:
            for r in c.execute("SELECT timestamp_start, timestamp_end, transcript FROM segments "
                               "WHERE video_id=? ORDER BY timestamp_start", (vid,)):
                windows.append({"start": r[0], "end": r[1], "text": r[2] or ""})
    frames = tfr.frames_for_video(video_id)
    for f in frames:
        f.update(tfr.split_caption(f.get("caption", "")))         # summary/people/location/objects/story
    return {"meta": meta, "windows": windows, "frames": frames,
            "storyboard": tfr.list_storyboard(video_id)}


def search_transcripts(query: str, index, vs, n: int = 20,
                       catalog_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Semantic search SCOPED to the transcript tier → timestamped, titled results for the UI:
    [{title, channel, url, watch_url, start, snippet, score}]. Joins each hit's video (by YouTube id
    parsed from the URL) to the display sidecar; a watch_url deep-links to the timestamp on YouTube."""
    from nolan.youtube import extract_video_id
    cat = load_catalog(catalog_dir)
    t_ids = index.transcript_video_ids()
    if not t_ids:
        return []
    # Over-fetch: vs.search ranks across the WHOLE library (footage + transcripts), then we keep only the
    # transcript tier — so pull a wide candidate pool or footage hits can crowd transcript hits out before
    # the filter. (A Chroma where-filter scoped to transcript ids would be the tighter fix — follow-up.)
    hits = vs.search(query=query, limit=max(n * 8, 200), search_level="segments") or []
    out: List[Dict[str, Any]] = []
    seen = set()
    for h in hits:
        if getattr(h, "video_id", None) not in t_ids:
            continue
        url = getattr(h, "video_path", "") or ""
        yid = extract_video_id(url) or ""
        m = cat.get(yid, {})
        start = float(getattr(h, "timestamp_start", 0) or 0)
        key = (yid, round(start, 0))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "title": m.get("title") or yid or url, "channel": m.get("channel"),
            "url": url, "watch_url": (f"{url}&t={int(start)}s" if "watch?v=" in url else url),
            "start": round(start, 1), "score": round(float(getattr(h, "score", 0) or 0), 3),
            "snippet": (getattr(h, "description", "") or getattr(h, "transcript", "") or "")[:220],
        })
        if len(out) >= n:
            break
    return out


def _rrf_fuse(text_hits: List[Dict[str, Any]], visual_hits: List[Dict[str, Any]], n: int,
              bucket: float = 25.0, k: int = 60) -> List[Dict[str, Any]]:
    """Reciprocal-Rank Fusion of transcript-text hits (what's SAID) and visual-frame hits (what's SHOWN) at
    the MOMENT level (video + ~bucket-second window). Fuses by RANK, not score — the two BGE collections
    have different score scales so cosines aren't comparable; RRF (sum of 1/(k+rank)) is scale-agnostic. A
    moment that is BOTH discussed and shown gets both contributions and floats to the top."""
    from nolan.youtube import extract_video_id
    scores: Dict[tuple, Dict[str, Any]] = {}

    def _key(vid, start):
        return (vid, int(float(start or 0) // bucket))

    for rank, h in enumerate(text_hits):
        e = scores.setdefault(_key(extract_video_id(h.get("url", "")) or "", h.get("start")),
                              {"rrf": 0.0, "matched": set()})
        e["rrf"] += 1.0 / (k + rank + 1); e["matched"].add("said"); e.setdefault("text", h)
    for rank, h in enumerate(visual_hits):
        e = scores.setdefault(_key(h.get("video_id", ""), h.get("start")), {"rrf": 0.0, "matched": set()})
        e["rrf"] += 1.0 / (k + rank + 1); e["matched"].add("shown"); e.setdefault("visual", h)

    out: List[Dict[str, Any]] = []
    for (vid, _b), e in scores.items():
        v, t = e.get("visual"), e.get("text")
        out.append({
            "video_id": vid,
            "start": (v["start"] if v else t["start"]),
            "title": (v.get("title") if v else None) or (t.get("title") if t else "") or vid,
            "watch_url": (v.get("watch_url") if v else None) or (t.get("watch_url") if t else ""),
            "snippet": (t.get("snippet", "") if t else ""),
            "caption": (v.get("caption", "") if v else ""),
            "thumb": (v.get("thumb") if v else None),
            "content_kind": (v.get("content_kind", "") if v else ""),
            "asset_type": (v.get("asset_type", "") if v else ""),
            "matched": sorted(e["matched"]),
            "score": round(e["rrf"], 4),
        })
    out.sort(key=lambda x: -x["score"])
    return out[:n]


def search_both(query: str, index, vs, n: int = 25, content_kind: str = "",
                catalog_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """"Both" search — RRF blend of what's SAID (transcript) + what's SHOWN (frames) into one ranked list of
    MOMENTS. The killer result: moments both discussed AND shown rank top."""
    from nolan import transcript_frames as tfr
    text_hits = search_transcripts(query, index, vs, n=max(n, 20), catalog_dir=catalog_dir)
    visual_hits = tfr.visual_search(query, n=max(n, 20), content_kind=content_kind)
    return _rrf_fuse(text_hits, visual_hits, n)


def list_channel(channel: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Enumerate a channel's videos (newest first) without downloading — [{video_id, url, title, ...}]."""
    from nolan.youtube import YouTubeClient
    return YouTubeClient().list_channel_videos(channel, limit=limit)


def _surveys_file(catalog_dir: Optional[Path] = None) -> Path:
    return (Path(catalog_dir) if catalog_dir else TRANSCRIPT_DIR) / "surveys.json"


def _channel_key(channel: str) -> str:
    """Normalize a channel reference so `youtube.com/bloomberg`, `@bloomberg`, trailing-slash etc. share a
    cache row. Not a resolver — just a stable-ish key for the persisted title list."""
    c = (channel or "").strip().lower().rstrip("/")
    for pre in ("https://", "http://", "www.", "m.", "youtube.com/", "youtu.be/"):
        if c.startswith(pre):
            c = c[len(pre):]
    return c or (channel or "").strip().lower()


def load_surveys(catalog_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Persisted channel title lists: {key: {channel, label, fetched, count, titles:[{video_id,url,title}]}}."""
    p = _surveys_file(catalog_dir)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _survey_key(ref: str, kind: str) -> str:
    """Cache/coverage key, namespaced by source kind so families (documentary `youtube`, copyright-free
    `youtube_cc`, `archive` collections) never collide (and coverage scopes by kind via the `kind:` prefix)."""
    if kind == "archive":
        from nolan import archive_source as ar
        return f"archive:{ar.collection_ref(ref)}"
    return f"{kind}:{_channel_key(ref)}"


def _thumb_for(video_id: str, kind: str) -> str:
    return (f"https://archive.org/services/img/{video_id}" if kind == "archive"
            else f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg")


def save_survey(channel: str, titles: List[Dict[str, Any]], catalog_dir: Optional[Path] = None,
                kind: str = "youtube", total: int = 0) -> str:
    """Store a source's full title list to the surveys sidecar (so we never re-crawl to browse). Archive rows
    also persist the rich free metadata (subject/license/copyright_free/description). Returns the fetch time."""
    import datetime
    surveys = load_surveys(catalog_dir)
    fetched = datetime.datetime.now().isoformat(timespec="seconds")
    rows = []
    for t in titles:
        if not t.get("video_id"):
            continue
        row = {"video_id": t["video_id"], "url": t.get("url"), "title": t.get("title") or t["video_id"],
               "duration": t.get("duration")}
        if t.get("copyright_free"):
            row["copyright_free"] = True                          # copyright-free families (archive / youtube_cc)
        if kind == "archive":
            row.update(subject=t.get("subject") or [], license=t.get("license") or "",
                       description=t.get("description") or "")
        rows.append(row)
    surveys[_survey_key(channel, kind)] = {"channel": channel, "kind": kind, "label": channel,
                                           "fetched": fetched, "count": len(rows),
                                           "total": total or len(rows), "titles": rows}
    p = _surveys_file(catalog_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(surveys, indent=2, ensure_ascii=False), encoding="utf-8")
    return fetched


def copyright_free_ids(catalog_dir: Optional[Path] = None) -> set:
    """Set of transcript-library video_ids that belong to a COPYRIGHT-FREE source — the youtube_cc stock
    family, or an archive.org collection added copyright-free — derived from sources.json × the persisted
    surveys. Lets the acquire engine mark provenance correctly even for rows ingested before per-video
    copyright flags existed (no re-ingest needed)."""
    srcs = load_sources(catalog_dir)
    free_yt = {_channel_key(ref) for ref, s in srcs.items()
               if s.get("kind") == "youtube_cc" and s.get("copyright_free")}
    from nolan import archive_source as ar
    free_coll = {ar.collection_ref(ref) for ref, s in srcs.items()
                 if s.get("kind") == "archive" and s.get("copyright_free")}
    ids: set = set()
    for _key, sv in load_surveys(catalog_dir).items():
        kd, ch = sv.get("kind"), (sv.get("channel") or "")
        free = ((kd == "youtube_cc" and _channel_key(ch) in free_yt)
                or (kd == "archive" and ar.collection_ref(ch) in free_coll))
        if free:
            for t in sv.get("titles", []):
                if t.get("video_id"):
                    ids.add(t["video_id"])
    return ids


def survey_channel(channel: str, limit: Optional[int] = None, catalog_dir: Optional[Path] = None,
                   refresh: bool = False, kind: str = "youtube",
                   collection_free: bool = False) -> List[Dict[str, Any]]:
    """CHEAP survey: all of a source's videos (titles only, NO download/transcript) with an `in_library` flag.
    Dispatches on `kind`: a YouTube channel (yt-dlp flat crawl) or an archive.org collection (advancedsearch;
    rich free metadata — subject/license/copyright_free — via `archive_source`). PERSISTED — a full survey is
    cached to surveys.json (kind-namespaced key) and reused until `refresh=True`. `in_library` is recomputed
    live from the catalog on every read (never stored — it changes as you ingest)."""
    cat = load_catalog(catalog_dir)
    have = set(cat.keys())
    full = not limit
    if full and not refresh:
        cached = load_surveys(catalog_dir).get(_survey_key(channel, kind))
        if cached and cached.get("titles"):
            return [{**r, "thumb": _thumb_for(r["video_id"], kind),
                     "in_library": r["video_id"] in have, "_cached": cached.get("fetched", "")}
                    for r in cached["titles"]]
    total = 0
    if kind == "archive":
        from nolan import archive_source as ar
        items, total = ar.survey_collection(channel, limit, collection_free=collection_free)
        rows = [{"video_id": v["video_id"], "url": v["url"], "title": v["title"], "duration": v.get("duration"),
                 "subject": v.get("subject") or [], "license": v.get("license") or "",
                 "copyright_free": bool(v.get("copyright_free")), "description": v.get("description") or ""}
                for v in items]
    else:                                                        # youtube channels (documentary or youtube_cc)
        rows = [{"video_id": v.get("video_id"), "url": v.get("url"),
                 "title": v.get("title") or v.get("video_id"), "duration": v.get("duration"),
                 **({"copyright_free": True} if collection_free else {})}
                for v in list_channel(channel, limit) if v.get("video_id")]
    if full:
        save_survey(channel, rows, catalog_dir, kind=kind, total=total)   # persist the full crawl for next time
    return [{**r, "thumb": _thumb_for(r["video_id"], kind),
             "in_library": r["video_id"] in have} for r in rows]


_BGE = None


def _bge_model():
    global _BGE
    if _BGE is None:
        from sentence_transformers import SentenceTransformer
        from nolan.imagelib.embeddings import DESC_MODEL
        _BGE = SentenceTransformer(DESC_MODEL)
    return _BGE


def _embed_titles(titles):
    """BGE-embed + L2-normalize titles -> vectors (cosine == dot product)."""
    if not titles:
        return []
    vecs = _bge_model().encode(list(titles), normalize_embeddings=True, show_progress_bar=False)
    return [list(map(float, v)) for v in vecs]


def cluster_dedup_candidates(cand, lib_titles, thr_lib=0.87, thr_dup=0.90):
    """Deterministic, SCALABLE title dedup (BGE, no LLM -- handles 1000s of titles the LLM can't):
    (1) DROP candidates whose nearest LIBRARY title is >= thr_lib (already covered); (2) leader-CLUSTER the
    survivors at the TIGHT thr_dup so only near-DUPLICATE titles group (series parts / trailers / re-uploads /
    near-identical wording -- NOT same-subject-different-angle), keeping ONE rep (shortest title) per cluster.
    Returns {distinct, dropped_lib, clusters, candidates}."""
    if not cand:
        return {"distinct": [], "dropped_lib": 0, "clusters": 0, "candidates": 0}
    import numpy as np
    cv = np.asarray(_embed_titles([c.get("title") or "" for c in cand]), dtype=np.float32)  # (n, d) unit vecs
    # (1) drop candidates near an existing library title -- one vectorized (n x m) cosine matrix, max per row
    if lib_titles:
        lv = np.asarray(_embed_titles(lib_titles), dtype=np.float32)
        keep = (cv @ lv.T).max(axis=1) < thr_lib
    else:
        keep = np.ones(len(cv), dtype=bool)
    dropped = int((~keep).sum())
    surv_idx = [i for i in range(len(cand)) if keep[i]]
    # (2) leader-cluster survivors at thr_dup. The inner "max cosine to any leader" is a BLAS matvec against a
    # preallocated leader matrix -- O(n * leaders * d) but vectorized, so ~1000x the old pure-Python cos loop
    # (which made a 2500-title channel take minutes). Deterministic: survivors kept in original order.
    groups: List[List[Dict[str, Any]]] = []
    leaders = np.empty((len(surv_idx), cv.shape[1]), dtype=np.float32) if surv_idx else np.empty((0, cv.shape[1]), dtype=np.float32)
    ng = 0
    for i in surv_idx:
        v = cv[i]
        if ng:
            sims = leaders[:ng] @ v
            j = int(sims.argmax())
            if sims[j] >= thr_dup:
                groups[j].append(cand[i])
                continue
        leaders[ng] = v; ng += 1
        groups.append([cand[i]])
    distinct = []
    for grp in groups:
        rep = min(grp, key=lambda c: len(c.get("title") or ""))
        distinct.append({**rep, "cluster_size": len(grp),
                         "cluster_titles": [g["title"] for g in grp if g is not rep][:4]})
    return {"distinct": distinct, "dropped_lib": dropped, "clusters": len(groups), "candidates": len(cand)}


async def recommend_from_channel(channel, config, limit=250, catalog_dir=None, model="",
                                 min_sec=0, max_sec=0, kind="youtube", copyright_free_only=False,
                                 collection_free=False):
    """Recommend a DIVERSE add-list in TWO layers: (1) `_distinct_candidates` -- survey → drop library-covered
    → optional COPYRIGHT-FREE + LENGTH filters → newest-cap → BGE cluster_dedup collapses near-dups at ANY
    scale; (2) the config text LLM (deepseek) tags the DISTINCT survivors by topic, writes the coverage/gap
    note, and does the final semantic add/skip. Titles-first."""
    import json

    from nolan.llm import create_text_llm
    distinct, stats, lib_titles = _distinct_candidates(channel, catalog_dir, limit=limit, min_sec=min_sec,
                                                       max_sec=max_sec, kind=kind,
                                                       copyright_free_only=copyright_free_only,
                                                       collection_free=collection_free)
    if not distinct:
        return {"coverage": "Nothing new -- every distinct topic on this channel is already covered.",
                "items": [], "add": 0, **stats}
    sys_p = ("You curate a BROAD documentary library spanning ALL topics (history, business, arts, sports, "
             "science, nature, culture, biography, war, politics, tech, society, crime, religion...). Quality "
             "is assured (documentary channels). Exact near-duplicate titles were pre-removed. Maximize TOPIC "
             "BREADTH -- ADD is the strong default; different people/events/eras/subjects are ALL distinct.")
    _nl = chr(10)
    parts = [
        "EXISTING LIBRARY (" + str(len(lib_titles)) + " videos) titles:",
        _nl.join("- " + t for t in lib_titles[:400]),
        "",
        "DISTINCT CANDIDATES (id | title) -- already de-duplicated:",
        _nl.join(s["video_id"] + " | " + (s["title"] or "") for s in distinct),
        "",
        ("For EACH candidate output JSON. Verdict 'add' by DEFAULT. Only 'skip' when: (a) it is a trailer / "
         "fragment / not a full documentary; (b) the existing library already covers that SPECIFIC subject; or "
         "(c) several candidates cover the SAME SPECIFIC person/event (e.g. 4 Kissinger docs) -- keep the 1-2 "
         "most distinct, skip the rest. CRUCIAL: different people/events/eras are DISTINCT and must be ADDED "
         "(FDR is NOT redundant with JFK; a different war/company/scandal is NOT redundant -- do not dedup by "
         "broad category). Short `topic` + one-line `reason`. Also a 1-2 sentence `coverage` note: topics the "
         "library is THIN on that this channel fills."),
        ('Respond ONLY with JSON: {"coverage":"...","items":[{"video_id":"...","topic":"...",'
         '"verdict":"add|skip","reason":"..."}]}'),
    ]
    llm = create_text_llm(config, model=(model or None))
    out = await llm.generate(_nl.join(parts), system_prompt=sys_p)
    st, en = out.find("{"), out.rfind("}")
    try:
        data = json.loads(out[st:en + 1]) if st >= 0 and en > st else {}
    except Exception:
        data = {}
    by_id = {s["video_id"]: s for s in distinct}
    items = []
    for it in (data.get("items") or []):
        srow = by_id.get(it.get("video_id"))
        if srow:
            items.append({**srow, "topic": (it.get("topic") or "").strip(),
                          "verdict": (it.get("verdict") or "add").strip().lower(),
                          "reason": (it.get("reason") or "").strip()})
    add = sum(1 for i in items if i["verdict"] == "add")
    return {"coverage": (data.get("coverage") or "").strip(), "items": items, "add": add, **stats}


# ---------------------------------------------------------------------------
# Topic modelling (no-LLM): cluster a channel's DISTINCT titles into topics so an
# editor can browse by subject, hand-pick, or draw a maximally-diverse sample
# (one per topic) WITHOUT paying the LLM. Reuses the same BGE title embeddings.
# ---------------------------------------------------------------------------
import re as _re

# generic documentary/channel boilerplate that must NOT become a topic label
_TOPIC_STOP = set((
    "the a an of to in on for and or with from at by as is are was were be been being this that these those "
    "how why what when who whom which where you your we our it its his her their they them he she i my me "
    "full documentary official trailer part chapter episode video hd 4k series story history the1 vs feat ft "
    "american experience pbs bloomberg frontline nova bbc history channel documentaries doc films film movie "
    "complete extended edition remastered english subtitles subtitle new watch free online all about into "
    "one two three four five making behind scenes special report episode1 season live stream"
).split())


def _tok(title: str) -> List[str]:
    return [w for w in _re.findall(r"[a-z0-9']{3,}", (title or "").lower())
            if w not in _TOPIC_STOP and not w.isdigit()]


_FRAGMENT = _re.compile(r"\b(promo|preview|trailer|teaser|title sequence|coming (to|soon)|clip \d|"
                        r"sneak peek|sneak peek|behind the scenes|extended audio description|\basl\b)\b", _re.I)


def _is_fragment(title: str) -> bool:
    """Promo / trailer / clip / ASL-variant — a poor 'representative' pick even if it's a cluster medoid."""
    return bool(_FRAGMENT.search(title or ""))


def _topic_label(titles: List[str], gdf: Dict[str, int], n_docs: int) -> str:
    """Cheap TF-IDF-ish label for a cluster: the words most distinctive to it."""
    import math
    from collections import Counter
    c: Counter = Counter()
    for t in titles:
        for w in set(_tok(t)):
            c[w] += 1
    if not c:
        return "misc"
    scored = sorted(c.items(), key=lambda kv: kv[1] * math.log((n_docs + 1) / (gdf.get(kv[0], 1))),
                    reverse=True)
    top = [w for w, _ in scored[:3]]
    return " · ".join(top) if top else "misc"


def topic_cluster(distinct: List[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    """Cluster the DISTINCT candidate titles into `k` topic groups (agglomerative, cosine on the
    normalized BGE title vectors). Each group carries a keyword `label`, its `size`, and a `medoid`
    (the title closest to the cluster centroid — the single most representative pick). No LLM."""
    if not distinct:
        return []
    import numpy as np
    from collections import Counter
    vecs = _embed_titles([d.get("title") or "" for d in distinct])
    X = np.asarray(vecs, dtype=float)
    k = max(1, min(int(k), len(distinct)))
    if k <= 1 or len(distinct) <= 2:
        labels = [0] * len(distinct)
    else:
        # Spherical KMeans (vectors are L2-normalized → euclidean KMeans == cosine). KMeans gives
        # BALANCED partitions — essential for "one representative per topic": agglomerative average-linkage
        # chains 900 titles into one 500-item blob + tiny satellites, which collapses the diversity spread.
        from sklearn.cluster import KMeans
        labels = KMeans(n_clusters=k, random_state=0, n_init=4).fit_predict(X).tolist()
    gdf: Counter = Counter()
    for d in distinct:
        for w in set(_tok(d.get("title") or "")):
            gdf[w] += 1
    buckets: Dict[int, List[int]] = {}
    for i, lab in enumerate(labels):
        buckets.setdefault(int(lab), []).append(i)
    out = []
    for lab, idxs in buckets.items():
        sub = X[idxs]
        centroid = sub.mean(axis=0)
        sims = sub @ centroid                                  # unit vectors → dot == cosine to centroid
        # Representative = most central title, but skip promos/trailers/clips when a full doc is available.
        order = sorted(range(len(idxs)), key=lambda j: -sims[j])
        full = [j for j in order if not _is_fragment(distinct[idxs[j]].get("title") or "")]
        medoid_local = (full or order)[0]
        medoid_id = distinct[idxs[medoid_local]].get("video_id")
        items = [distinct[i] for i in idxs]
        out.append({"cluster_id": int(lab),
                    "label": _topic_label([distinct[i].get("title") or "" for i in idxs], gdf, len(distinct)),
                    "size": len(idxs), "medoid_id": medoid_id, "items": items})
    out.sort(key=lambda g: -g["size"])
    return out


# Embedding/clustering ceiling: a channel like Bloomberg's main feed has ~50k videos -- embedding all of
# them with BGE would hang. We keep the NEWEST this-many candidates (survey is newest-first) and report
# the rest as dropped (never a silent cap -- the invariant). Recent uploads are the useful frontier.
MAX_CANDIDATES = 2500


def _real_title(title: Optional[str], ident: Optional[str]) -> bool:
    """True if a title is a real catalogued title, not an uncatalogued scan id. archive.org collections have
    many raw-scan items whose 'title' IS the identifier (e.g. '001350 001', '000766') — junk for curation."""
    t = (title or "").strip()
    if not t or t == (ident or "").strip():
        return False
    return bool(_re.search(r"[A-Za-z]{3,}", t))               # at least one real (3+ letter) word


def _dur_ok(d: Optional[int], min_sec: int, max_sec: int) -> bool:
    """Length gate. Unknown duration (None — e.g. rows cached before the field existed) is KEPT so a real doc
    is never silently dropped over missing metadata."""
    if d is None:
        return True
    if min_sec and d < min_sec:
        return False
    if max_sec and d > max_sec:
        return False
    return True


def _distinct_candidates(channel: str, catalog_dir: Optional[Path] = None, limit: int = 0,
                         refresh: bool = False, cap: int = MAX_CANDIDATES,
                         min_sec: int = 0, max_sec: int = 0, kind: str = "youtube",
                         copyright_free_only: bool = False,
                         collection_free: bool = False) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[str]]:
    """Survey → drop already-in-library → (optional COPYRIGHT-FREE + LENGTH filters) → cluster_dedup (collapse
    near-identical titles) → the DISTINCT add-candidates that both the LLM recommender and the topic view
    operate on. Shared spine across source kinds (youtube channel / archive collection). The filters run BEFORE
    the newest-`cap` bound, so on a giant source you keep the newest real docs, not clips."""
    survey = survey_channel(channel, None, catalog_dir, refresh=refresh, kind=kind, collection_free=collection_free)
    cand = [s for s in survey if not s["in_library"]]
    dropped_junk = 0
    if kind == "archive":                                          # drop uncatalogued raw-scan items (title == id)
        kept = [s for s in cand if _real_title(s.get("title"), s.get("video_id"))]
        dropped_junk = len(cand) - len(kept)
        cand = kept
    dropped_copyright = 0
    if copyright_free_only:
        kept = [s for s in cand if s.get("copyright_free")]
        dropped_copyright = len(cand) - len(kept)
        cand = kept
    dropped_len = 0
    if min_sec or max_sec:
        kept = [s for s in cand if _dur_ok(s.get("duration"), min_sec, max_sec)]
        dropped_len = len(cand) - len(kept)
        cand = kept
    capped = 0
    if cap and len(cand) > cap:
        capped = len(cand) - cap
        cand = cand[:cap]                                        # newest-first -> keep the most recent cap
    lib_titles = [e.get("title") or "" for e in load_catalog(catalog_dir).values() if e.get("title")]
    dd = cluster_dedup_candidates(cand, lib_titles)
    distinct = dd["distinct"][:limit] if limit else dd["distinct"]
    cached = survey[0].get("_cached", "") if survey else ""
    stats = {"total": len(survey), "candidates": dd["candidates"], "dropped_redundant": dd["dropped_lib"],
             "dup_clusters": dd["clusters"], "distinct": len(dd["distinct"]), "cached": cached,
             "capped": capped, "dropped_length": dropped_len, "dropped_copyright": dropped_copyright,
             "dropped_junk": dropped_junk}
    return distinct, stats, lib_titles


def topic_view(channel: str, k: int = 0, catalog_dir: Optional[Path] = None,
               refresh: bool = False, min_sec: int = 0, max_sec: int = 0, kind: str = "youtube",
               copyright_free_only: bool = False, collection_free: bool = False) -> Dict[str, Any]:
    """Browse a source BY TOPIC: distinct candidates grouped into ~k topic clusters (auto ≈ n/8 when
    k=0), each labelled by its distinctive keywords, medoid pre-flagged. For hand-selection. No LLM."""
    distinct, stats, _ = _distinct_candidates(channel, catalog_dir, refresh=refresh, min_sec=min_sec,
                                              max_sec=max_sec, kind=kind, copyright_free_only=copyright_free_only,
                                              collection_free=collection_free)
    if not distinct:
        return {"groups": [], "k": 0, **stats}
    if not k:
        k = max(4, min(40, round(len(distinct) / 8) or 1))
    groups = topic_cluster(distinct, k)
    return {"groups": groups, "k": len(groups), **stats}


def diverse_sample(channel: str, n: int = 20, catalog_dir: Optional[Path] = None,
                   refresh: bool = False, min_sec: int = 0, max_sec: int = 0, kind: str = "youtube",
                   copyright_free_only: bool = False, collection_free: bool = False) -> Dict[str, Any]:
    """NO-LLM recommender: cluster the distinct candidates into exactly `n` topics and return the medoid
    of each — n picks spread maximally across the source's subject space, for zero API cost."""
    distinct, stats, _ = _distinct_candidates(channel, catalog_dir, refresh=refresh, min_sec=min_sec,
                                              max_sec=max_sec, kind=kind, copyright_free_only=copyright_free_only,
                                              collection_free=collection_free)
    if not distinct:
        return {"picks": [], "groups": 0, **stats}
    n = max(1, min(int(n), len(distinct)))
    groups = topic_cluster(distinct, n)
    picks = []
    for g in groups:
        med = next((it for it in g["items"] if it.get("video_id") == g["medoid_id"]), g["items"][0])
        picks.append({**med, "topic": g["label"], "verdict": "add", "cluster_size": g["size"]})
    return {"picks": picks, "groups": len(groups), **stats}


def coverage_map(channels: Optional[List[str]] = None, k: int = 0, catalog_dir: Optional[Path] = None,
                 refresh: bool = False, per_channel_limit: int = 0, min_sec: int = 0, max_sec: int = 0,
                 kind: str = "youtube", copyright_free_only: bool = False) -> Dict[str, Any]:
    """COVERAGE map for ONE source kind (youtube channels OR archive collections — kept SEPARATE because their
    metadata differs). Clusters the UNION of (library titles + every source's available-but-not-yet-ingested
    titles) into topics, reporting per topic how much the LIBRARY covers vs what's still AVAILABLE and from
    which source. Titles come from the persisted surveys. No LLM. `channels=None` → registered sources of this
    kind ∪ cached surveys of this kind."""
    import numpy as np
    from collections import Counter

    srcs = load_sources(catalog_dir)
    if channels is None:
        chans = [(ref, s) for ref, s in srcs.items() if (s.get("kind") or "youtube") == kind]
        seen = {ref for ref, _ in chans}
        for skey, row in load_surveys(catalog_dir).items():
            if (row.get("kind") or "youtube") != kind:
                continue
            c = row.get("channel") or skey
            if c not in seen:
                chans.append((c, {})); seen.add(c)
    else:
        chans = [(c, srcs.get(c, {})) for c in channels]

    cat = load_catalog(catalog_dir)
    lib_titles = [e.get("title") or "" for e in cat.values() if e.get("title")]
    # library rows first (in_library=True), then each source's distinct new candidates
    rows: List[Dict[str, Any]] = [{"title": t, "in_lib": True, "channel": ""} for t in lib_titles]
    per_channel = []
    for ch, src in chans:
        cfree = bool(src.get("copyright_free")) if kind == "archive" else False
        distinct, st, _ = _distinct_candidates(ch, catalog_dir, refresh=refresh, min_sec=min_sec, max_sec=max_sec,
                                               kind=kind, copyright_free_only=copyright_free_only,
                                               collection_free=cfree)
        label = (src or {}).get("label") or ch
        per_channel.append({"channel": ch, "label": label, "available": len(distinct),
                            "total": st.get("total", 0), "cached": st.get("cached", ""),
                            "capped": st.get("capped", 0)})
        for d in distinct:
            rows.append({"title": d.get("title") or "", "in_lib": False, "channel": label,
                         "video_id": d.get("video_id"), "url": d.get("url"), "duration": d.get("duration")})
    if len(rows) < 3:
        return {"topics": [], "channels": per_channel, "k": 0,
                "lib_total": len(lib_titles), "available_total": sum(c["available"] for c in per_channel)}

    if not k:
        k = max(8, min(60, round(len(rows) / 22) or 1))
    vecs = _embed_titles([r["title"] for r in rows])
    X = np.asarray(vecs, dtype=float)
    k = max(1, min(int(k), len(rows)))
    if k <= 1:
        labels = [0] * len(rows)
    else:
        from sklearn.cluster import KMeans
        labels = KMeans(n_clusters=k, random_state=0, n_init=4).fit_predict(X).tolist()

    gdf: Counter = Counter()
    for r in rows:
        for w in set(_tok(r["title"])):
            gdf[w] += 1
    buckets: Dict[int, List[int]] = {}
    for i, lab in enumerate(labels):
        buckets.setdefault(int(lab), []).append(i)
    topics = []
    for lab, idxs in buckets.items():
        members = [rows[i] for i in idxs]
        lib_n = sum(1 for m in members if m["in_lib"])
        new_m = [m for m in members if not m["in_lib"]]
        ch_counts = Counter(m["channel"] for m in new_m)
        # a couple of representative new titles (prefer full docs)
        samples = sorted(new_m, key=lambda m: _is_fragment(m["title"]))[:6]
        topics.append({
            "label": _topic_label([m["title"] for m in members], gdf, len(rows)),
            "size": len(members), "lib_count": lib_n, "available": len(new_m),
            "channels": [{"label": c, "count": n} for c, n in ch_counts.most_common()],
            "samples": [{"video_id": s.get("video_id"), "url": s.get("url"), "title": s["title"],
                         "channel": s["channel"], "duration": s.get("duration")} for s in samples],
        })
    # biggest opportunities first: uncovered topics with the most available, then thinly-covered
    topics.sort(key=lambda t: (t["lib_count"] > 0, -(t["available"]), t["lib_count"]))
    return {"topics": topics, "channels": per_channel, "k": len(topics),
            "lib_total": len(lib_titles), "available_total": sum(c["available"] for c in per_channel),
            "gaps": sum(1 for t in topics if t["lib_count"] == 0 and t["available"] > 0)}


def fetch_transcript_with_cues(url: str, out_dir: Optional[Path] = None) -> Tuple[Dict[str, Any], Any]:
    """Download ONLY a video's captions (no video) → (metadata, Transcript-with-cues).

    Reuses YouTubeClient.fetch_transcript (429-safe single-language pick; it writes the sub file) and
    re-loads the written .srt/.vtt for per-CUE timing — fetch_transcript itself returns flattened text
    only. Returns (meta, None) when no captions exist (a soft miss, not an error). meta carries
    {video_id, title, channel, upload_date, language, url}.
    """
    from nolan.transcript import TranscriptLoader
    from nolan.youtube import YouTubeClient
    out = Path(out_dir) if out_dir else Path(tempfile.mkdtemp())
    out.mkdir(parents=True, exist_ok=True)
    try:
        meta = YouTubeClient().fetch_transcript(url, out_dir=out)
    except RuntimeError:
        return ({"url": url}, None)                            # no captions available for this video
    vid = meta.get("video_id", "")
    subs = sorted(out.glob(f"{vid}*.srt")) + sorted(out.glob(f"{vid}*.vtt"))
    transcript = TranscriptLoader.load(subs[0]) if subs else None
    meta["url"] = url
    return (meta, transcript)


def chunk_transcript(transcript, window_s: float = 45.0, overlap_s: float = 10.0) -> List[Dict[str, Any]]:
    """Overlapping timestamped windows from cues → [{start, end, text}]. A window accumulates cues until
    it spans ~window_s; the next window starts ~overlap_s before the previous end (a sliding window), so
    a topic that straddles a boundary stays retrievable. Deterministic (unit-testable with fake cues)."""
    chunks = list(getattr(transcript, "chunks", []) or [])
    n = len(chunks)
    if n == 0:
        return []
    windows: List[Dict[str, Any]] = []
    i = 0
    while i < n:
        w_start = chunks[i].start
        j = i
        texts: List[str] = []
        while j < n and (chunks[j].end - w_start) <= window_s:
            texts.append((chunks[j].text or "").strip())
            j += 1
        if j == i:                                             # one cue longer than the whole window
            texts.append((chunks[i].text or "").strip())
            j = i + 1
        w_end = chunks[j - 1].end
        text = " ".join(t for t in texts if t).strip()
        if text:
            windows.append({"start": round(float(w_start), 2), "end": round(float(w_end), 2), "text": text})
        target = w_end - overlap_s                             # slide back by the overlap, but always progress
        nxt = i + 1
        while nxt < n and chunks[nxt].start < target:
            nxt += 1
        i = max(nxt, i + 1)
    return windows


def ingest_transcript(index, meta: Dict[str, Any], windows: List[Dict[str, Any]],
                      channel: Optional[str] = None) -> Optional[int]:
    """Insert a transcript-only video (source_kind='transcript', has_footage=0, path=the YouTube URL) +
    its window 'segments' into VideoIndex. Idempotent by fingerprint 'yt:<video_id>' — a re-index clears
    the old windows first, so it replaces rather than duplicates. Returns the video_id (None if there are
    no windows). The caller embeds via VectorSearch to make it searchable."""
    vid = meta.get("video_id")
    if not vid or not windows:
        return None
    fp = f"yt:{vid}"
    url = meta.get("url") or f"https://www.youtube.com/watch?v={vid}"
    duration = float(windows[-1]["end"])
    video_id = index.add_video(path=url, duration=duration, checksum=fp, fingerprint=fp, project_id=None)
    index.mark_source_tier(video_id, source_kind="transcript", has_footage=0)
    index.clear_segments(video_id)                            # idempotent re-index (replace, not append)
    segs = [{
        "timestamp_start": w["start"], "timestamp_end": w["end"],
        "frame_description": "",                               # transcript-only → no vision description
        "transcript": w["text"], "combined_summary": w["text"],   # combined_summary = the primary embedded text
        "inferred_context": None, "sample_reason": "transcript-window",
    } for w in windows]
    index.add_segments_bulk(video_id, segs)
    return video_id
