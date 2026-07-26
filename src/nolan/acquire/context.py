"""build_context — wire the engine's injected callables to the real NOLAN organs, each degrading to
None (that source/scorer is skipped) if unavailable. Keeps the engine pure + testable."""
from __future__ import annotations

import asyncio
import hashlib
import urllib.request
from pathlib import Path
from typing import List, Optional

from .engine import Candidate, Context


def _stock_client(cfg):
    from .shared import build_search_client
    return build_search_client(cfg)


def _valid_image(path: Path) -> bool:
    from .shared import valid_image
    return valid_image(path)


def clean_media_inplace(path, cfg=None):
    from .shared import clean_media_inplace as _clean
    return _clean(path, cfg)


def _ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _fetch_video_segment(url: str, out: Path, clip_seconds: int, duration=None) -> bool:
    """Fetch ONLY a short segment from the video URL. ffmpeg range-seeks, so grabbing 20s of a
    21-minute archive.org film costs ~20s of bytes, not 800 MB. `-c copy` first (fast); re-encode
    fallback for odd codecs / mid-GOP starts."""
    import subprocess
    ff = _ffmpeg()
    offset = 0.0
    if duration and duration > clip_seconds * 2:          # skip title cards / intros on long sources
        offset = round(min(12.0, duration * 0.08), 2)
    headers = "User-Agent: Mozilla/5.0\r\nReferer: https://www.google.com/\r\n"
    base = [ff, "-y", "-headers", headers, "-ss", str(offset), "-i", url, "-t", str(clip_seconds)]
    for tail in (["-c", "copy", "-movflags", "+faststart"],
                 ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-an"]):
        try:
            subprocess.run(base + tail + [str(out)], capture_output=True, timeout=180)
        except Exception:
            continue
        if out.exists() and out.stat().st_size > 20000:
            return True
        out.unlink(missing_ok=True)
    return False


def _extract_midframe(video_path) -> Optional[Path]:
    """One mid-frame of a local clip → temp jpg, for the cheap CLIP relevance check. Caller unlinks it."""
    import os as _os
    import subprocess
    import tempfile
    p = Path(video_path)
    if not p.exists():
        return None
    fd, out = tempfile.mkstemp(suffix=".jpg")
    _os.close(fd)
    out = Path(out)
    try:
        subprocess.run([_ffmpeg(), "-y", "-ss", "0.5", "-i", str(p), "-frames:v", "1",
                        "-vf", "scale=384:-1", "-q:v", "4", str(out)], capture_output=True, timeout=30)
    except Exception:
        out.unlink(missing_ok=True)
        return None
    return out if (out.exists() and out.stat().st_size > 800) else None


def _clip_window(seg_start, seg_end, clip_seconds, lead: float = 0.1, min_dur: float = 2.5,
                 max_shot: float = 5.0):
    """Trim window for a local library clip. Start ON the matched segment — a small inset PAST the cut-in,
    never a pre-roll into the PREVIOUS shot — and hold a SHORT, single-shot-likely window (≤ max_shot),
    which the pre-render freeze-heal boomerang-loops to fill the scene. The old window began 0.4s BEFORE
    the segment (dipping into the previous documentary shot) AND ran the full clip_seconds (~30s), so a
    scene ground opened on the wrong shot and then cut repeatedly as it played through the source's
    internal cuts — the homer 'flash'. Segments here are NOT single-shot (5–30s spans), so a short window
    from the segment start beats a long play-through; a true single-shot trim needs the `shots` table
    (follow-up: partial coverage). `clip_seconds` is retained for signature stability."""
    seg = max(0.0, float(seg_end) - float(seg_start))
    start = max(0.0, float(seg_start) + lead)
    dur = round(min(max(min_dur, seg or min_dur), float(max_shot)), 2)   # [min_dur, max_shot]
    return round(start, 2), dur


def _resolve_clips_db(cfg) -> Optional[Path]:
    """The video-library DB from config (indexing.database). `load_config()` is now CWD-robust — it
    walks up to the repo-root nolan.yaml — so cfg carries the right path whether acquisition runs from
    the repo root or the bridge dir (was the holbein/homer CWD-config bug, fixed centrally in config.py)."""
    try:
        d = getattr(getattr(cfg, "indexing", None), "database", "") or ""
        return Path(d).expanduser() if d else None
    except Exception:
        return None


def gen_style_for(theme: str) -> str:
    """Default ComfyUI/Fooocus generation style for a NOLAN theme — dark/moody themes get the confirmed
    'Dark Moody Atmosphere' style, everything else keeps 'Cinematic'. Was hardcoded to 'Cinematic', so
    dark essays got a mismatched bright-cinematic look. The new-essay form can override per-project."""
    t = (theme or "").lower()
    dark = t in {"dark-botanical", "midnight-press", "monochrome-print"} or \
        any(k in t for k in ("dark", "midnight", "noir", "night"))
    return "Dark Moody Atmosphere" if dark else "Cinematic"


def build_context(cfg, *, clip_seconds=None, want_stock=True, want_library=True, want_clip=True, want_gen=True,
                  want_clips_library=True, want_transcript_lib=True, want_transcript_frames=True,
                  clip_lib_max=4, clip_lib_min_sim=0.55,
                  gen_style="Cinematic", clean_transcript_clips=True, project_dir=None) -> Context:
    ctx = Context()
    # default the video-segment length from the config (was hardcoded 20, ignoring cfg.clip_seconds)
    if clip_seconds is None:
        clip_seconds = int(getattr(cfg, "clip_seconds", 30) or 30)

    # --- stock: multi-provider search + gated download -------------------------------------------
    if want_stock:
        try:
            client = _stock_client(cfg)

            def search_stock(need, n):
                mt = need.get("media_type", "image")
                seen, cands = set(), []
                for q in (need.get("queries") or [need.get("query", "")]):
                    if not q:
                        continue
                    try:
                        for res in client.search_assets(q, media_type=mt, sources=need.get("sources"),
                                                        max_results=max(6, n)):
                            key = getattr(res, "source_url", None) or getattr(res, "url", None)
                            if key in seen:
                                continue
                            seen.add(key)
                            cands.append(Candidate(ref=str(key), source=f"stock:{res.source}", modality=mt,
                                                   meta={"_res": res, "source": res.source, "source_url": res.source_url,
                                                         "photographer": res.photographer, "license": res.license,
                                                         "width": res.width, "height": res.height, "duration": res.duration}))
                    except Exception:
                        continue
                    if len(cands) >= n * 4:                # collect a WIDE pool across providers…
                        break
                # …then round-robin by source so the returned set SPANS providers (search_assets merges
                # ddgs-first, so a naive top-n is all ddgs and the curated tiers never enter the ranking).
                from collections import OrderedDict
                buckets = OrderedDict()
                for c in cands:
                    buckets.setdefault(c.source, []).append(c)
                out = []
                while any(buckets.values()) and len(out) < n:
                    for b in buckets.values():
                        if b and len(out) < n:
                            out.append(b.pop(0))
                return out

            def download(c: Candidate, dest: Path):
                res = c.meta.get("_res")
                if res is None:
                    return False
                base = hashlib.md5(c.ref.encode()).hexdigest()[:12]
                if c.modality == "video":
                    (dest / "videos").mkdir(parents=True, exist_ok=True)
                    out = dest / "videos" / f"{base}.mp4"
                    res2 = client.resolve_video(res) or res
                    if not getattr(res2, "url", None):
                        return False
                    from nolan.asset_gate import check_candidate
                    if not check_candidate(res2, tier="stock").ok:
                        return False
                    if _fetch_video_segment(res2.url, out, clip_seconds, getattr(res2, "duration", None)):
                        c.path = out
                        return True
                    return False
                out = dest / f"{base}.jpg"
                res2 = client.resolve_asset(res)
                if client.download_image(res2, out) is None or not _valid_image(out):
                    out.unlink(missing_ok=True)
                    return False
                c.path = out
                return True

            ctx.search_stock, ctx.download = search_stock, download
        except Exception:
            pass

    # --- library: CLIP search over the saved image store -----------------------------------------
    if want_library:
        try:
            from nolan.imagelib.store import ImageLibrary
            _lib = ImageLibrary("global")
            # Loud at the boundary: the library base is now CWD-independent, so 0 active here means the
            # library is genuinely empty (ingest never ran) — NOT a working-directory mixup. A silent
            # empty library was how the headline feature died on the default path (POST_MORTEM #1).
            _st = _lib.stats()
            _active = int(_st.get("active", 0) or 0)
            print(f"[acquire] library: {_active} active / {_st.get('total', 0)} total @ {_st.get('base')}", flush=True)
            if _active == 0:
                print(f"⚠ [acquire] global library is EMPTY (0 active assets) @ {_st.get('base')} — "
                      "library-first needs will find NOTHING (run ingest?).", flush=True)
            _warned = {"empty_hit": False}

            def search_library(query, n):
                # Merge two retrievers: a lexical TITLE match (leads for NAMED works — CLIP clusters all
                # of a named series at ~0.3 and can't pick 'THE PLOUGHMAN') + CLIP visual similarity
                # (fills / covers un-named queries). Title-matched assets CLIP would never surface get
                # ADDED to the pool; title_cover rides in meta so the engine can let it stand in for
                # relevance (see engine.acquire_need) instead of leaning on the VLM cull.
                merged = {}                                 # asset_id -> (LibraryHit, title_cover)
                for h in (_lib.search_by_title(query, k=n) or []):
                    merged[h.asset.id] = (h, float(h.score))
                for h in (_lib.search(query, k=n) or []):
                    if h.asset.id not in merged:
                        merged[h.asset.id] = (h, 0.0)
                out = []
                for h, tcover in merged.values():
                    try:
                        p = _lib.abs_path(h.asset)          # LibraryHit.asset.path is store-relative
                    except Exception:
                        continue
                    if p.exists():
                        out.append(Candidate(ref=str(p), source="library", modality="image", path=p,
                                             meta={"license": getattr(h.asset, "license", "library"), "source": "library",
                                                   "title": getattr(h.asset, "title", None),
                                                   "title_cover": round(tcover, 3)},
                                             relevance=float(getattr(h, "score", 0) or 0)))
                # A library-first need returning 0 while the store is non-empty is a real signal (the
                # CLIP collection is unembedded/misconfigured), not a normal miss — say so once, loud.
                if not out and _active > 0 and not _warned["empty_hit"]:
                    _warned["empty_hit"] = True
                    print(f"⚠ [acquire] library returned 0 hits for {query!r} despite {_active} active assets "
                          "— the CLIP collection may be unembedded/misconfigured (warned once).", flush=True)
                return out
            ctx.search_library = search_library
        except Exception as e:
            print(f"⚠ [acquire] library source unavailable — skipped ({type(e).__name__}: {e})", flush=True)

    # --- clips_library: LOCAL video library — semantic retrieval over rich per-clip metadata ------
    # The vector store embeds each segment's description + transcript + people + location, so a beat's
    # text finds the FOOTAGE THAT MEANS THE SAME THING (not a filename or CLIP-image match). Only clips
    # clearing the similarity floor become candidates (so off-topic projects pay ~nothing), and each is
    # trimmed to a b-roll window on disk in download(). This is the local half of the video pool.
    if want_clips_library:
        _db = _resolve_clips_db(cfg)
        if not _db or not _db.exists():
            print(f"⚠ [acquire] clips_library db not found @ {_db} — source skipped "
                  "(check indexing.database / run `nolan index`).", flush=True)
        else:
            try:
                from nolan.indexer import VideoIndex
                from nolan.vector_search import VectorSearch
                _vindex = VideoIndex(_db)
                _vsearch = VectorSearch(db_path=_db.parent / "vectors", index=_vindex)
                _footage_ids = _vindex.footage_video_ids()   # has_footage=1 rows only; transcript-only rows
                _vstats = _vsearch.get_stats()               # (has_footage=0) are a DISCOVERY tier, never footage
                _nseg = int(_vstats.get("segments", 0) or 0)
                print(f"[acquire] clips_library: {_nseg} segments / {_vstats.get('clusters', 0)} clusters "
                      f"@ {_db} (≤{clip_lib_max}/need, sim≥{clip_lib_min_sim})", flush=True)
                if _nseg == 0:
                    print(f"⚠ [acquire] clips_library vector store EMPTY @ {_db.parent / 'vectors'} — "
                          "run `nolan sync-vectors` (clips source will find nothing).", flush=True)
                _ff = _ffmpeg()
                _repo = Path(__file__).resolve().parents[3]

                def _resolve_src(vp: str):
                    vp = (vp or "").replace("\\", "/")
                    if not vp:
                        return None
                    p = Path(vp)
                    if p.is_absolute() and p.exists():
                        return p
                    cand = _repo / vp                        # DB paths are often repo-relative (Windows sep)
                    return cand if cand.exists() else None

                def search_clips(need, n):
                    queries = [q for q in (need.get("queries") or [need.get("query", "")]) if q][:6]
                    if not queries:
                        return []
                    best = {}                                # (src, ~start) -> best-scoring SemanticSearchResult
                    for q in queries:
                        try:
                            hits = _vsearch.search(query=q, limit=max(6, n), search_level="segments",
                                                   project_id=None) or []
                        except Exception:
                            continue
                        for r in hits:
                            if float(getattr(r, "score", 0) or 0) < clip_lib_min_sim:
                                continue
                            _vid = getattr(r, "video_id", None)
                            if _vid is not None and _vid not in _footage_ids:
                                continue                     # transcript tier: searchable, but NOT acquirable footage
                            if not _resolve_src(getattr(r, "video_path", "")):
                                continue
                            key = (r.video_path, round(float(r.timestamp_start), 1))
                            if key not in best or r.score > best[key].score:
                                best[key] = r
                    # prefer SHORT, single-shot-likely segments: a 25s montage inherits the source's
                    # internal cuts (the homer 'flash'), a 3-5s segment is usually one continuous shot.
                    # Mild penalty (compressed similarity band) so a much-better long match still wins.
                    def _eff(r):
                        span = max(0.0, float(r.timestamp_end) - float(r.timestamp_start))
                        return float(r.score) - 0.006 * max(0.0, span - 5.0)
                    ranked = sorted(best.values(), key=_eff, reverse=True)[:clip_lib_max]
                    out = []
                    for r in ranked:
                        src = _resolve_src(r.video_path)
                        start, dur = _clip_window(r.timestamp_start, r.timestamp_end, clip_seconds)
                        out.append(Candidate(
                            ref=f"{src}#{start:.1f}", source="clips_library", modality="video",
                            path=None,                       # materialised (trimmed) in download()
                            relevance=float(r.score),        # similarity feeds the engine score for video
                            meta={"source": "clips_library (local)", "license": "library",
                                  "description": r.description, "transcript": r.transcript,
                                  "people": r.people, "location": r.location,
                                  "source_video": str(src), "clip_start": start,
                                  "clip_dur": dur, "similarity": round(float(r.score), 3)}))
                    return out
                ctx.search_clips = search_clips

                # materialise a clips_library candidate by trimming its source video locally (copy-first,
                # re-encode fallback) — the local twin of _fetch_video_segment, no network.
                _prev_download = ctx.download

                def _download(c: Candidate, dest: Path):
                    if c.source != "clips_library":
                        return _prev_download(c, dest) if _prev_download else False
                    src = c.meta.get("source_video")
                    if not src or not Path(src).exists():
                        return False
                    import subprocess
                    (dest / "videos").mkdir(parents=True, exist_ok=True)
                    out = dest / "videos" / (hashlib.md5(c.ref.encode()).hexdigest()[:12] + ".mp4")
                    base = [_ff, "-y", "-ss", f"{float(c.meta.get('clip_start', 0)):.3f}", "-i", str(src),
                            "-t", f"{float(c.meta.get('clip_dur', clip_seconds)):.3f}"]
                    for tail in (["-c", "copy", "-movflags", "+faststart", "-an"],
                                 ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-an"]):
                        try:
                            subprocess.run(base + tail + [str(out)], capture_output=True, timeout=120)
                        except Exception:
                            continue
                        if out.exists() and out.stat().st_size > 20000:
                            c.path = out
                            return True
                        out.unlink(missing_ok=True)
                    return False
                ctx.download = _download
            except Exception as e:
                print(f"⚠ [acquire] clips_library source unavailable — skipped ({type(e).__name__}: {e})", flush=True)

    # --- transcript_lib: the transcript library as a DOWNLOADABLE b-roll source (ALL families) ----------
    # Same VideoIndex as clips_library, but its DISCOVERY tier (has_footage=0): documentary YouTube, the
    # copyright-free youtube_cc stock family, and archive.org public-domain collections. A semantic hit is
    # materialised by DOWNLOADING JUST ITS RANGE from the source URL (the feedback-2 mechanism) and MARKED
    # with its copyright status (copyright-free stock/PD vs a copyrighted documentary reference) so the pool
    # records provenance. Chains onto search_clips/download (dispatch by c.source), no engine slot needed.
    if want_transcript_lib or want_transcript_frames:
        _tdb = _resolve_clips_db(cfg)
        if _tdb and _tdb.exists():
            try:
                from nolan import transcript_frames as _tfr
                from nolan import transcript_lib as _tl
                from nolan.indexer import VideoIndex
                from nolan.vector_search import VectorSearch
                _tvindex = VideoIndex(_tdb)
                _tvsearch = VectorSearch(db_path=_tdb.parent / "vectors", index=_tvindex)
                _tfootage = set(_tvindex.footage_video_ids())     # exclude real footage (clips_library's job)
                _tcat = _tl.load_catalog()                        # SOURCE-id -> {url, copyright_free, kind, channel}
                _tfree = _tl.copyright_free_ids()                 # SOURCE ids in a copyright-free source (× surveys)
                from nolan import archive_source as _ar
                from nolan.youtube import extract_video_id as _yid

                def _src_id(url):                                 # the youtube / archive id embedded in the URL
                    return _ar.collection_ref(url) if "archive.org" in (url or "") else (_yid(url or "") or "")

                def _copyright_of(url):                           # DB video_id is an int; copyright keys off the URL id
                    sid = _src_id(url)
                    e = _tcat.get(sid) or {}
                    ch, kind = (e.get("channel") or ""), (e.get("kind") or "youtube")
                    is_arch = "archive.org" in (url or "").lower()
                    if sid in _tfree or e.get("copyright_free") or is_arch:
                        k = kind if kind != "youtube" else ("archive" if is_arch else "youtube_cc")
                        return True, k, ch
                    return False, "youtube", ch

                # DEDUP vs the HERO pool: keyassets runs FIRST and claims the ranges it pulled, so the
                # b-roll fan-out must not re-download the same shot under a second name (both land in
                # capture/assets and both reach the author's menu).
                #
                # Read LAZILY, per search — never snapshot at context-build time. A snapshot silently
                # couples correctness to call order: `build_context` runs before the caller releases the
                # previous build's claims, so a rebuild saw all of them as taken and skipped nearly every
                # clip (measured: transcript_lib fell from 9 pooled items to 1). Re-reading a small JSON
                # per need costs nothing and also honours claims written during this run.
                from .shared import load_claims, range_is_claimed, record_claim

                def _search_transcript_lib(need, n):
                    queries = [q for q in (need.get("queries") or [need.get("query", "")]) if q][:6]
                    if not queries:
                        return []
                    claims = load_claims(project_dir) if project_dir else []
                    best = {}
                    for q in queries:
                        try:
                            hits = _tvsearch.search(query=q, limit=max(6, n), search_level="segments",
                                                    project_id=None) or []
                        except Exception:
                            continue
                        for r in hits:
                            if float(getattr(r, "score", 0) or 0) < clip_lib_min_sim:
                                continue
                            vid = getattr(r, "video_id", None)
                            if vid is None or vid in _tfootage:   # keep ONLY the discovery/transcript tier
                                continue
                            url = getattr(r, "video_path", "")
                            if not str(url).startswith(("http://", "https://")):
                                continue
                            key = (url, round(float(r.timestamp_start), 1))
                            if key not in best or r.score > best[key].score:
                                best[key] = r
                    ranked = sorted(best.values(), key=lambda r: float(r.score), reverse=True)[:clip_lib_max]
                    out = []
                    for r in ranked:
                        url = r.video_path
                        start, dur = _clip_window(r.timestamp_start, r.timestamp_end, clip_seconds)
                        dup = range_is_claimed(claims, url, start, dur)
                        if dup:                       # the hero pool already pulled this shot — don't twin it
                            print(f"  [acquire] skip {url.rsplit('/', 1)[-1]}@{start:.0f}s — already claimed "
                                  f"by {dup.get('owner')} ({dup.get('file')})", flush=True)
                            continue
                        cfree, kind, channel = _copyright_of(url)
                        lic = ("public-domain / CC — copyright-free" if cfree
                               else f"copyrighted — YouTube ({channel})" if channel else "copyrighted — YouTube")
                        out.append(Candidate(
                            ref=f"{url}#{start:.1f}", source="transcript_lib", modality="video", path=None,
                            relevance=float(r.score),
                            meta={"source": f"transcript_lib ({kind})", "license": lic,
                                  "copyright_free": cfree, "kind": kind, "channel": channel,
                                  "description": r.description, "transcript": r.transcript,
                                  "source_url": str(url), "clip_start": start, "clip_dur": dur,
                                  "similarity": round(float(r.score), 3)}))
                    return out

                def _shot_window(vid, t0, default=5.0):
                    """The REAL shot this keyframe opens: from its own timestamp to the NEXT keyframe.

                    Keyframes come from `detect_cuts` → `plan_shots`, i.e. one per detected shot, so the
                    gap to the next frame IS the shot length. This is the thing `_clip_window`'s docstring
                    says it cannot do from a transcript segment ("a true single-shot trim needs the `shots`
                    table") — the captioned frame tier is that table."""
                    try:
                        fr = [f["t"] for f in _tfr.frames_for_video(vid) if f.get("kind") == "keyframe"]
                    except Exception:
                        fr = []
                    nxt = next((t for t in sorted(fr) if t > t0 + 0.4), None)
                    dur = (nxt - t0) if nxt else default
                    return max(2.0, min(float(dur), 12.0))          # a shot, not a play-through

                def _search_transcript_frames(need, n):
                    """The SHOWN tier: retrieve by what a frame LOOKS like, not by what is said over it.

                    Same corpus and same download path as `_search_transcript_lib` — a different index.
                    Measured on a real diamond-v2 beat ("open pit excavation machinery"): the segment tier
                    anchored the super-pit documentary at 0.0s, its title card, because that is where the
                    narrator SAYS the topic; the frame tier returned 62.0s (shovel bucket), 66.2s (operator
                    controls) and 97.4s (the Komatsu truck). Same video — the right seconds.

                    `content_kind="broll"` is the filter the segment tier structurally cannot apply: gemma
                    labelled each shot, so a talking head can be excluded before it is ever downloaded."""
                    queries = [q for q in (need.get("queries") or [need.get("query", "")]) if q][:4]
                    if not queries:
                        return []
                    claims = load_claims(project_dir) if project_dir else []
                    best, per_video = {}, {}
                    for q in queries:
                        try:
                            hits = _tfr.visual_search(q, max(6, n), content_kind="broll") or []
                        except Exception:
                            continue
                        for r in hits:
                            vid = r.get("video_id") or ""
                            # TAIL-TRIM, same as the segment tier. The frame store is k-NEAREST: it returns
                            # `k` captions for ANY query however weak — measured live, "Odysseus and the
                            # ancient Greek epic" retrieved the 1936 Berlin Olympics at 0.52 and Lindbergh
                            # at 0.53, against 0.62-0.71 for genuine hits on a diamond beat. Not a topic
                            # gate (that is the downstream CLIP frame floor + the VLM); a junk cut that
                            # stops us spending a DOWNLOAD on the Olympics.
                            if float(r.get("score") or 0) < clip_lib_min_sim:
                                continue
                            # the catalog URL is authoritative — visual_search's watch_url carries a `&t=`
                            # display suffix, and re-parsing that here would be a second URL dialect
                            url = ((_tcat.get(vid) or {}).get("url") or "").strip()
                            if not vid or not url.startswith(("http://", "https://")):
                                continue
                            key = (vid, round(float(r.get("start") or 0), 1))
                            if key not in best or float(r.get("score") or 0) > float(best[key].get("score") or 0):
                                best[key] = r
                    ranked = sorted(best.values(), key=lambda r: -float(r.get("score") or 0))
                    out = []
                    for r in ranked:
                        if len(out) >= clip_lib_max:
                            break
                        vid = r["video_id"]
                        if per_video.get(vid, 0) >= 2:        # never let one film fill a beat
                            continue
                        url = (_tcat.get(vid) or {}).get("url") or ""
                        start = float(r.get("start") or 0)
                        dur = _shot_window(vid, start)
                        dup = range_is_claimed(claims, url, start, dur)
                        if dup:                               # same ledger as the segment tier + heroes
                            print(f"  [acquire] skip frame {vid}@{start:.0f}s — already claimed by "
                                  f"{dup.get('owner')} ({dup.get('file')})", flush=True)
                            continue
                        per_video[vid] = per_video.get(vid, 0) + 1
                        cfree, kind, channel = _copyright_of(url)
                        lic = ("public-domain / CC — copyright-free" if cfree
                               else f"copyrighted — YouTube ({channel})" if channel else "copyrighted — YouTube")
                        out.append(Candidate(
                            ref=f"{url}#{start:.1f}", source="transcript_frames", modality="video", path=None,
                            relevance=float(r.get("score") or 0),
                            meta={"source": f"transcript_frames ({kind})", "license": lic,
                                  "copyright_free": cfree, "kind": kind, "channel": channel,
                                  "description": r.get("summary") or r.get("caption") or "",
                                  "shot_caption": r.get("caption") or "", "asset_type": r.get("asset_type") or "",
                                  "content_kind": r.get("content_kind") or "", "objects": r.get("objects") or [],
                                  "source_url": str(url), "clip_start": start, "clip_dur": dur,
                                  "similarity": round(float(r.get("score") or 0), 3)}))
                    return out

                _ts_prev = ctx.search_clips

                def _search_transcript_all(need, n, _p=_ts_prev):
                    """Segment hits and frame hits INTERLEAVED, not concatenated.

                    Their scores are on different scales (measured on two diamond-v2 beats: frames
                    0.62-0.71, segments 0.67-0.74), so a single sorted list would be meaningless — and
                    plain concatenation is just as wrong, because `c.rank` is assigned by position and
                    feeds the score, so whichever tier came second would be systematically demoted. Both
                    are ranked internally already; interleaving preserves each order and gives neither
                    tier a positional advantage. (The retrieval score itself is not load-bearing for video:
                    the engine RECOMPUTES relevance with CLIP on the downloaded frames.)"""
                    prev = (_p(need, n) if _p else [])
                    frames = _search_transcript_frames(need, n) if want_transcript_frames else []
                    if not frames:
                        return prev
                    segs = _search_transcript_lib(need, n) if want_transcript_lib else []
                    # CROSS-TIER RANGE DEDUP. Two indexes over one corpus find the same shot from both
                    # sides, and neither tier can see the other's picks: each dedups only within itself,
                    # and the claim ledger is read at SEARCH time but written at DOWNLOAD time (which the
                    # engine runs concurrently), so it cannot catch an overlap inside one need. Measured
                    # live on a diamond beat: the segment tier returned SouthDak1940 @537.2s+5.0s while
                    # the frame tier returned the same film @534.9s+12.0s — the second CONTAINS the first.
                    # That is two downloads of one shot, and two near-identical clips in the author's menu.
                    # The FRAME wins the overlap: its range is the real shot (keyframe → next cut) whereas
                    # the segment's is a flat ≤5s guess from an arbitrary point in a 45s window.
                    fr_ranges = [(str(c.meta.get("source_url") or ""), float(c.meta.get("clip_start", 0)),
                                  float(c.meta.get("clip_dur", 0))) for c in frames]

                    def _overlaps_a_frame(c):
                        u = str(c.meta.get("source_url") or "")
                        s = float(c.meta.get("clip_start", 0))
                        e = s + float(c.meta.get("clip_dur", 0))
                        return any(fu == u and s < fs + fd and fs < e for fu, fs, fd in fr_ranges)

                    kept_segs, dropped = [], 0
                    for c in segs:
                        if _overlaps_a_frame(c):
                            dropped += 1
                            continue
                        kept_segs.append(c)
                    if dropped:                      # no silent cap: say what the dedup removed
                        print(f"  [acquire] {dropped} segment hit(s) dropped — the frame tier already "
                              f"holds that shot with its true boundaries", flush=True)
                    woven, i = [], 0
                    while i < max(len(kept_segs), len(frames)):
                        if i < len(kept_segs):
                            woven.append(kept_segs[i])
                        if i < len(frames):
                            woven.append(frames[i])
                        i += 1
                    return prev + woven

                ctx.search_clips = (_search_transcript_all if want_transcript_frames else
                                    (lambda need, n, _p=_ts_prev:
                                     (_p(need, n) if _p else []) + _search_transcript_lib(need, n)))

                # materialise: download JUST the range from the source URL (archive → high-def h.264 derivative
                # + ffmpeg range; youtube → yt_dlp range). The feedback-2 download-the-range, headless.
                _td_prev = ctx.download

                def _download_transcript(c: Candidate, dest: Path):
                    # ONE materialisation path for both transcript tiers — same range pull, same
                    # broadcast-watermark cleanup, same claim. They differ in how the range was FOUND,
                    # never in how it is fetched, so there is no second dialect to drift.
                    if c.source not in ("transcript_lib", "transcript_frames"):
                        return _td_prev(c, dest) if _td_prev else False
                    from nolan import clipper
                    url = c.meta.get("source_url")
                    start = float(c.meta.get("clip_start", 0))
                    dur = float(c.meta.get("clip_dur", clip_seconds))
                    if not url:
                        return False
                    (dest / "videos").mkdir(parents=True, exist_ok=True)
                    out = dest / "videos" / (hashlib.md5(c.ref.encode()).hexdigest()[:12] + ".mp4")
                    src_url = url
                    dl_kind = "youtube" if ("youtube" in url or "youtu.be" in url) else "direct"
                    try:
                        if "archive.org" in url:
                            src_url = clipper.resolve_media_url(url, "archive", purpose="clip")
                            dl_kind = "direct"
                        saved = clipper.clip(src_url, start, start + dur, out, kind=dl_kind)
                    except Exception:
                        return False
                    if saved and out.exists() and out.stat().st_size > 20000:
                        # CLEANUP: these are BROADCAST sources — a Bloomberg/PBS clip carries a burned-in
                        # watermark + a caption band, and pooling that raw puts another channel's brand in
                        # the essay. Crop them out (same aspect, replaced in place) before the asset is
                        # scored/captioned. Soft: a cleanup failure never loses the clip.
                        if clean_transcript_clips:
                            rep = clean_media_inplace(out, cfg) or {}
                            c.meta["cleanup"] = rep
                            if rep.get("changed"):
                                bits = [k for k in ("logo", "caption", "trimmed") if rep.get(k)]
                                print(f"  [acquire] cleaned {out.name}: removed {', '.join(bits) or 'strays'}",
                                      flush=True)
                            elif rep.get("error"):
                                print(f"  ⚠ [acquire] cleanup failed on {out.name} ({rep['error']}) — "
                                      f"clip kept as-is", flush=True)
                        if project_dir:               # claim it so a later pass doesn't pull the same shot
                            record_claim(project_dir, url=url, start=start, dur=dur,
                                         owner="pool", file=out.name)
                        c.path = out
                        return True
                    return False
                ctx.download = _download_transcript
                print("[acquire] transcript_lib: downloadable b-roll from the transcript library "
                      "(youtube · youtube_cc · archive), copyright-marked"
                      + (", watermark/caption-cleaned" if clean_transcript_clips else ""), flush=True)
                if want_transcript_frames:
                    # NO SILENT CAP: the SHOWN tier can only reach rows that have been captioned, so say
                    # what fraction of the corpus that is — otherwise a thin frame tier reads as "the
                    # library had nothing" when it means "the library hasn't been captioned yet".
                    _cap = sum(1 for v in _tcat.values() if int(v.get("frames", 0) or 0) > 0)
                    print(f"[acquire] transcript_frames: the SHOWN tier — {_cap}/{len(_tcat)} library rows "
                          f"are captioned and reachable; shot-accurate ranges, content_kind=broll only",
                          flush=True)
            except Exception as e:
                print(f"⚠ [acquire] transcript_lib source unavailable — skipped ({type(e).__name__}: {e})", flush=True)

    # --- relevance: CLIP cosine (need text ↔ candidate image) ------------------------------------
    if want_clip:
        try:
            from nolan.imagelib.embeddings import ClipEmbedder
            emb = ClipEmbedder()
            tcache = {}

            def _cos(a, b):
                import math
                dot = sum(x * y for x, y in zip(a, b))
                na = math.sqrt(sum(x * x for x in a)) or 1.0
                nb = math.sqrt(sum(y * y for y in b)) or 1.0
                return max(0.0, dot / (na * nb))

            def relevance(text, path):
                t = tcache.get(text) or tcache.setdefault(text, emb.embed_text(text))
                iv = emb.embed_image(path)
                return _cos(t, iv) if (t and iv) else 0.0
            ctx.relevance = relevance

            def video_relevance(text, video_path):
                """Cheap frame-relevance for a video: score ONE mid-frame with the same CLIP cosine as
                images. The discriminating signal the segment text-embedding lacks (compressed band), so
                off-topic library clips are dropped BEFORE the expensive VLM filmstrip (cull cascade)."""
                fr = _extract_midframe(video_path)
                if not fr:
                    return 0.0
                try:
                    return relevance(text, fr)
                except Exception:
                    return 0.0
                finally:
                    fr.unlink(missing_ok=True)
            ctx.video_relevance = video_relevance
        except Exception:
            pass

    # --- generation: krea2 / ComfyUI (first-class, engine decides WHEN) --------------------------
    if want_gen:
        try:
            from nolan.workflow_registry import get_registry
            gclient, _ = get_registry().build_client("krea2-style-select", cfg, style=f",{gen_style}")

            def generate(prompt, out: Path, negative=None):
                out = Path(out)
                out.parent.mkdir(parents=True, exist_ok=True)
                try:                                    # prompt is art-directed (self-sufficient) → no generic suffix
                    asyncio.run(gclient.generate(prompt, out, timeout=200, negative=negative))
                except Exception:
                    return False
                return out.exists() and _valid_image(out)
            ctx.generate = generate
        except Exception:
            pass

    return ctx
