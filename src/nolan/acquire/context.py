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


def build_context(cfg, *, clip_seconds=None, want_stock=True, want_library=True, want_clip=True, want_gen=True) -> Context:
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
