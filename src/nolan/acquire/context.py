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
    from nolan.image_search import ImageSearchClient
    s = cfg.image_sources
    return ImageSearchClient(pexels_api_key=s.pexels_api_key or None,
                             pixabay_api_key=s.pixabay_api_key or None,
                             smithsonian_api_key=getattr(s, "smithsonian_api_key", "") or None,
                             keys=s.provider_keys())


def _valid_image(path: Path) -> bool:
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.load()
        return True
    except Exception:
        return False


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


def _resolve_clips_db(cfg) -> Optional[Path]:
    """Resolve the video-library DB path robustly against CWD. `run_pool` runs `bridge/pool.py` with
    cwd=BRIDGE, where load_config() cannot see the repo-root nolan.yaml and so defaults indexing.database
    to the stale ~/.nolan db (the holbein POST_MORTEM #1 class of bug: a config/CWD mixup silently opens
    the WRONG library). Prefer the repo-root nolan.yaml's configured DB (the one whose vector store also
    exists), and fall back to whatever cfg carries — so the clips source finds the SAME rich library
    whether acquisition runs from the repo root or from the bridge dir."""
    cands = []
    try:
        import yaml
        repo_yaml = Path(__file__).resolve().parents[3] / "nolan.yaml"
        if repo_yaml.exists():
            y = yaml.safe_load(repo_yaml.read_text(encoding="utf-8")) or {}
            d = (y.get("indexing") or {}).get("database")
            if d:
                cands.append(Path(d).expanduser())
    except Exception:
        pass
    try:
        d = getattr(getattr(cfg, "indexing", None), "database", "") or ""
        if d:
            cands.append(Path(d).expanduser())
    except Exception:
        pass
    for db in cands:                                    # prefer a DB whose paired vector store exists
        if db and db.exists() and (db.parent / "vectors").exists():
            return db
    return cands[0] if cands else None


def build_context(cfg, *, clip_seconds=None, want_stock=True, want_library=True, want_clip=True, want_gen=True,
                  want_clips_library=True, clip_lib_max=4, clip_lib_min_sim=0.55) -> Context:
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
                _vstats = _vsearch.get_stats()
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
                            if not _resolve_src(getattr(r, "video_path", "")):
                                continue
                            key = (r.video_path, round(float(r.timestamp_start), 1))
                            if key not in best or r.score > best[key].score:
                                best[key] = r
                    ranked = sorted(best.values(), key=lambda r: r.score, reverse=True)[:clip_lib_max]
                    out = []
                    for r in ranked:
                        src = _resolve_src(r.video_path)
                        start = max(0.0, float(r.timestamp_start) - 0.4)
                        out.append(Candidate(
                            ref=f"{src}#{start:.1f}", source="clips_library", modality="video",
                            path=None,                       # materialised (trimmed) in download()
                            relevance=float(r.score),        # similarity feeds the engine score for video
                            meta={"source": "clips_library (local)", "license": "library",
                                  "description": r.description, "transcript": r.transcript,
                                  "people": r.people, "location": r.location,
                                  "source_video": str(src), "clip_start": round(start, 2),
                                  "clip_dur": float(clip_seconds), "similarity": round(float(r.score), 3)}))
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
        except Exception:
            pass

    # --- generation: krea2 / ComfyUI (first-class, engine decides WHEN) --------------------------
    if want_gen:
        try:
            from nolan.workflow_registry import get_registry
            gclient, _ = get_registry().build_client("krea2-style-select", cfg, style=",Cinematic")

            def generate(prompt, out: Path):
                out = Path(out)
                out.parent.mkdir(parents=True, exist_ok=True)
                try:
                    asyncio.run(gclient.generate(f"{prompt}, cinematic, highly detailed", out, timeout=200))
                except Exception:
                    return False
                return out.exists() and _valid_image(out)
            ctx.generate = generate
        except Exception:
            pass

    return ctx
