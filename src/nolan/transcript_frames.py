"""Visual tier for the transcript library — grab FRAMES for a transcript video and CLIP-embed them so a
text query can retrieve by APPEARANCE (not just words), and picks can be eyeballed / confirmed.

Two frame sources (a tiered ladder, cheap → sharp):
  • storyboard tiles — yt-dlp fetches YouTube's storyboard spritesheets (a thumbnail every few seconds)
    WITHOUT downloading the video. Free + near-instant, but low-res — coarse candidate/verify.
  • ranged keyframes — ffmpeg input-seeks the remote stream (the clipper's -ss-before-i pattern) to grab a
    FULL-RES frame at chosen timestamps. Targeted byte cost; the sharp frames for confirming a pick.

Frames live in a dedicated ImageLibrary scope (projects/_library/transcript-frames) — CLIP image vectors
+ a catalog row per frame tagged with its {video_id, timestamp, kind}. visual_search = CLIP text→image
over them; each hit resolves back to a video + timestamp (a YouTube &t= deep-link).
"""
from __future__ import annotations

import io
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]                    # src/nolan/transcript_frames.py -> repo
FRAMES_DIR = REPO / "projects" / "_library" / "transcript-frames"
CAPTION_MODEL = "google/gemma-4-26b-a4b-it"                    # cheap, fast, conservative VLM (benchmarked winner)


def frame_lib(embedder=None, base_dir=None):
    """The dedicated transcript-frame ImageLibrary (CLIP image store), isolated from _library/images.
    base_dir overrides the default scope (tests/verifies pass a temp dir)."""
    from nolan.imagelib.store import ImageLibrary
    return ImageLibrary(base_dir=(Path(base_dir) if base_dir else FRAMES_DIR),
                        scope="transcript-frames", embedder=embedder)


def _ffmpeg() -> str:
    from nolan.clipper import _ffmpeg as ff
    return ff()


def _resolve_stream(watch_url: str) -> Optional[str]:
    """A direct, ffmpeg-readable media URL for a YouTube watch URL (a progressive mp4). Watch pages are
    not ffmpeg-readable — resolve a signed stream first (time-limited; grab frames right after)."""
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True,
            "format": "18/best[ext=mp4][height<=480]/best[height<=480]/best"}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(watch_url, download=False)
    if info.get("url"):
        return info["url"]
    for f in (info.get("requested_formats") or []):
        if f.get("url"):
            return f["url"]
    for f in (info.get("formats") or []):
        if f.get("vcodec") not in (None, "none") and f.get("url"):
            return f["url"]
    return None


def _extract_analysis(content: str) -> Dict[str, Any]:
    """Parse the VLM's JSON reply into the pieces the visual tier needs:
      • `caption` — ONE rich, searchable string: the summary PLUS the structured inferred_context
        (people / location / objects / story) folded in the SAME way the video library builds its embed
        text (`vector_search._build_segment_text`), so a query for a named person/place/object hits even
        when the summary omits it. BGE-embedded AND the raw material for the detail column.
      • `asset_type` (the rich 11-value shot type, SAME vocab as the video library's shots) + its coarse
        `content_kind` roll-up (broll / talking_head / graphics) — the shot classification an editor filters
        on; both stored as frame tags.
      • the split-out `people / location / objects / story` — for the structured detail column.
    Falls back to raw text (no structure) if the reply isn't valid JSON."""
    import json
    import re

    from nolan.visual_facts import content_kind_of
    try:
        m = re.search(r"\{.*\}", content, re.DOTALL)
        d = json.loads(m.group(0)) if m else {}
    except Exception:
        d = {}
    if not isinstance(d, dict):
        d = {}
    summary = (d.get("combined_summary") or d.get("frame_description") or "").strip()
    ctx = d.get("inferred_context") or {}
    ctx = ctx if isinstance(ctx, dict) else {}
    people = [str(p).strip() for p in (ctx.get("people") or []) if str(p).strip()]
    objects = [str(o).strip() for o in (ctx.get("objects") or []) if str(o).strip()]
    location = str(ctx.get("location") or "").strip()
    story = str(ctx.get("story_context") or "").strip()
    parts: List[str] = []
    if summary:
        parts.append(summary)
    if people:
        parts.append("People: " + ", ".join(people))
    if location:
        parts.append("Location: " + location)
    if objects:
        parts.append("Objects: " + ", ".join(objects))
    if story:
        parts.append("Context: " + story)
    caption = " | ".join(parts) if parts else (content or "").strip()[:400]
    at = (d.get("asset_type") or "").strip().lower()
    return {"caption": caption,
            "asset_type": at, "content_kind": content_kind_of(at),
            "people": people, "location": location, "objects": objects, "story": story}


def _extract_caption(content: str) -> str:
    """Back-compat: just the fused searchable caption from `_extract_analysis`."""
    return _extract_analysis(content)["caption"]


_EMPTY_ANALYSIS = {"caption": "", "asset_type": "", "content_kind": "",
                   "people": [], "location": "", "objects": [], "story": ""}


def caption_frame(image_path, transcript: Optional[str] = None, timestamp: Optional[float] = None,
                  model: Optional[str] = None) -> Dict[str, Any]:
    """Analyze a full-res frame with a cheap VLM (gemma-4-26b default), thinking OFF, using the SAME
    visual+audio prompt as video ingest — so the transcript window fuses with the pixels into a rich,
    OCR-/entity-aware description AND a shot classification. Returns the `_extract_analysis` dict
    ({caption, asset_type, content_kind, people, location, objects, story}); an empty-caption dict on any
    failure (a caption-less frame is still CLIP-embedded, so this never blocks the visual tier)."""
    import base64

    import httpx

    from nolan.config import load_config
    from nolan.vision import build_frame_analysis_prompt
    key = load_config().vision.openrouter_api_key
    if not key:
        return dict(_EMPTY_ANALYSIS)
    prompt = build_frame_analysis_prompt(transcript, timestamp)
    b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
    body = {"model": model or CAPTION_MODEL, "reasoning": {"enabled": False},   # thinking OFF (production)
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]}
    try:
        r = httpx.post("https://openrouter.ai/api/v1/chat/completions",
                       headers={"Authorization": f"Bearer {key}"}, json=body, timeout=90)
        if r.status_code != 200:
            return dict(_EMPTY_ANALYSIS)
        return _extract_analysis(r.json()["choices"][0]["message"]["content"])
    except Exception:
        return dict(_EMPTY_ANALYSIS)


def ranged_keyframes(url: str, timestamps: List[float], out_dir: Path,
                     is_youtube: bool = True, concurrency: int = 6) -> List[Tuple[float, Path]]:
    """Grab ONE full-res frame at each timestamp via ffmpeg input-seek over the remote stream (reuses the
    clipper -ss-before-i pattern; bundled ffmpeg; no ffprobe). For a YouTube watch URL, resolves a direct
    stream once + reuses it. Seeks run in PARALLEL (bounded thread pool) — the stream URL is signed once and
    each grab is independent, so N frames cost ~one grab of wall-clock. Returns [(timestamp, jpg_path)]
    sorted by time, misses skipped."""
    from concurrent.futures import ThreadPoolExecutor
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    src = _resolve_stream(url) if is_youtube else url
    if not src:
        return []
    ff = _ffmpeg()

    def _grab(t: float) -> Optional[Tuple[float, Path]]:
        fp = out_dir / f"kf_{int(float(t))}.jpg"
        subprocess.run([ff, "-y", "-ss", f"{float(t):.3f}", "-i", src, "-frames:v", "1",
                        "-q:v", "3", "-vf", "scale=640:-2", str(fp)], capture_output=True)
        return (float(t), fp) if fp.exists() and fp.stat().st_size > 0 else None

    with ThreadPoolExecutor(max_workers=max(1, int(concurrency))) as ex:
        out = [r for r in ex.map(_grab, [float(t) for t in timestamps]) if r]
    out.sort(key=lambda x: x[0])
    return out


async def caption_frames_async(items: List[Tuple[Path, Optional[str], Optional[float]]],
                               model: Optional[str] = None, concurrency: int = 8) -> List[Dict[str, Any]]:
    """Analyze many frames CONCURRENTLY (bounded), preserving input order. `items` = [(image_path,
    transcript_window, timestamp)]. Each is an independent OpenRouter call, so a video's frames analyze in
    ~one call of wall-clock instead of N serial ones. Returns the `caption_frame` analysis dicts parallel
    to `items`."""
    import asyncio
    sem = asyncio.Semaphore(max(1, int(concurrency)))

    async def _one(fp, tr, ts):
        async with sem:
            return await asyncio.to_thread(caption_frame, fp, tr, ts, model)

    return list(await asyncio.gather(*(_one(fp, tr, ts) for fp, tr, ts in items)))


def _iter_storyboard(watch_url: str):
    """Yield (timestamp, PIL.RGB tile) for EVERY storyboard cell at native density (no video download).
    The one place the spritesheet fetch + split lives — shared by `storyboard_tiles` (thins + saves) and
    `storyboard_change_points` (diffs in memory). Gotchas handled: tile size from the SHEET, t0 accumulated
    across fragments, all-black trailing tiles dropped."""
    import urllib.request

    from PIL import Image
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(watch_url, download=False)
    sbs = [f for f in (info.get("formats") or []) if (f.get("format_id") or "").startswith("sb")]
    if not sbs:
        return
    sb = max(sbs, key=lambda f: (f.get("width", 0) or 0) * (f.get("height", 0) or 0)
             * (f.get("rows", 1) or 1) * (f.get("columns", 1) or 1))
    rows, cols = int(sb.get("rows", 0) or 0), int(sb.get("columns", 0) or 0)
    frags = sb.get("fragments") or []
    if not (rows and cols and frags):
        return
    t0 = 0.0
    for frag in frags:
        dur = float(frag.get("duration", 0) or 0)
        per = dur / (rows * cols) if dur else 0.0
        try:
            req = urllib.request.Request(frag["url"], headers={"User-Agent": "Mozilla/5.0"})
            sheet = Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=30).read())).convert("RGB")
        except Exception:
            t0 += dur
            continue
        tw, th = sheet.width // cols, sheet.height // rows
        for idx in range(rows * cols):
            ts = t0 + idx * per
            r, c = divmod(idx, cols)
            if (c + 1) * tw > sheet.width or (r + 1) * th > sheet.height:
                continue
            tile = sheet.crop((c * tw, r * th, (c + 1) * tw, (r + 1) * th))
            if tile.getbbox() is None:                        # all-black trailing tile
                continue
            yield round(ts, 1), tile
        t0 += dur


def storyboard_tiles(watch_url: str, out_dir: Path, every_s: float = 12.0,
                     max_tiles: int = 60) -> List[Tuple[float, Path]]:
    """Fetch YouTube storyboard spritesheets (NO video download) and split into (timestamp, tile jpg),
    sampled to ~every_s apart and capped at max_tiles. Low-res but free. Returns [] when a video has no
    storyboards."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out: List[Tuple[float, Path]] = []
    last_kept = -1e9
    for ts, tile in _iter_storyboard(watch_url):
        if ts - last_kept < every_s:
            continue
        fp = out_dir / f"sb_{int(ts)}.jpg"
        tile.save(fp, quality=85)
        out.append((round(ts, 1), fp))
        last_kept = ts
        if len(out) >= max_tiles:
            break
    return out


def storyboard_change_points(watch_url: str, sigma: float = 2.0, save_dir: Optional[Path] = None,
                             save_every_s: float = 12.0) -> Tuple[List[float], float, List[Tuple[float, Path]]]:
    """Detect visual CHANGE timestamps from the free storyboard tiles (no video download): consecutive-tile
    grayscale mean-abs diff, adaptive threshold (mean + sigma·std) so a fast-cut video and a static
    talking-head each get a sensible cut set. If `save_dir` is given, ALSO writes a thinned filmstrip of the
    tiles (~every save_every_s) there — the whole-video storyboard overview shown in a video's detail,
    reusing this single spritesheet fetch. Returns (change_timestamps, duration_estimate, [(t, sprite_jpg)]).
    duration_estimate = the last tile's timestamp (storyboards span the whole video) — used to fill the tail."""
    from PIL import ImageChops, ImageStat
    if save_dir is not None:
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
    prev = None
    diffs: List[Tuple[float, float]] = []
    sprites: List[Tuple[float, Path]] = []
    last_ts = 0.0
    last_saved = -1e9
    for ts, tile in _iter_storyboard(watch_url):
        g = tile.convert("L").resize((32, 18))
        if prev is not None:
            diffs.append((ts, ImageStat.Stat(ImageChops.difference(g, prev)).mean[0]))
        prev = g
        last_ts = ts
        if save_dir is not None and ts - last_saved >= save_every_s:
            fp = save_dir / f"sb_{int(ts)}.jpg"
            tile.save(fp, quality=85)
            sprites.append((round(ts, 1), fp))
            last_saved = ts
    if not diffs:
        return [], last_ts, sprites
    vals = [d for _, d in diffs]
    mean = sum(vals) / len(vals)
    std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
    thr = mean + float(sigma) * std
    return [ts for ts, d in diffs if d > thr], last_ts, sprites


def storyboard_dir(video_id: str, base_dir=None) -> Path:
    """Where a video's viewable storyboard filmstrip lives (kept on disk, NOT in the search index — the
    coarse overview shouldn't pollute visual search)."""
    root = Path(base_dir) if base_dir else FRAMES_DIR
    return root / "storyboards" / str(video_id)


def list_storyboard(video_id: str, base_dir=None) -> List[Dict[str, Any]]:
    """The saved storyboard filmstrip for a video → [{t, thumb}] sorted by time (for the detail overview)."""
    d = storyboard_dir(video_id, base_dir)
    if not d.exists():
        return []
    out: List[Dict[str, Any]] = []
    for fp in d.glob("sb_*.jpg"):
        try:
            t = float(fp.stem.split("_", 1)[1])
        except (IndexError, ValueError):
            t = 0.0
        out.append({"t": t, "thumb": str(fp)})
    out.sort(key=lambda x: x["t"])
    return out


def _fill_gap(prev: float, cur: float, min_gap: float, max_gap: float) -> List[float]:
    """Evenly-spaced interior points so no sub-gap exceeds max_gap — but never create a sub-gap below
    min_gap (min_gap WINS the tension: a 55s gap with min=30/max=50 stays un-filled rather than split into
    two 27.5s gaps)."""
    import math
    gap = cur - prev
    if gap <= max_gap:
        return []
    n = math.ceil(gap / max_gap)                 # enough intervals to keep each <= max_gap
    if gap / n < min_gap:                         # …unless that drops a sub-gap below the floor
        n = max(1, math.floor(gap / min_gap))
    step = gap / n
    return [prev + k * step for k in range(1, n)]


def plan_snapshot_times(changes: List[float], duration: float,
                        min_gap: float = 30.0, max_gap: float = 50.0, lag: float = 1.0) -> List[float]:
    """Turn scene-change points into the final snapshot schedule (the hybrid density rule):
      • anchor a snapshot just AFTER each change (`lag`s in — firmly into the new shot), so each distinct
        visual segment is sampled;
      • thin anchors closer than `min_gap` (don't over-sample rapid cuts);
      • fill any gap wider than `max_gap` (including head 0→first and tail last→duration) with evenly-spaced
        points, but never below `min_gap`.
    Result: snapshots land at real cuts, spaced within roughly [min_gap, max_gap]. A static video (no
    changes) still gets an even ~max_gap grid from the tail fill."""
    duration = float(duration or 0.0)
    anchors: List[float] = []
    for c in sorted({0.0} | {float(x) for x in changes}):        # always anchor the opening shot (t=0)
        t = c + lag
        if duration:
            t = min(t, duration - 0.5)
        t = max(t, 0.5)
        if not anchors or t - anchors[-1] >= min_gap:
            anchors.append(round(t, 1))
    times: List[float] = []
    prev = 0.0
    for a in anchors:
        times.extend(_fill_gap(prev, a, min_gap, max_gap))
        times.append(a)
        prev = a
    if duration:
        times.extend(_fill_gap(prev, duration, min_gap, max_gap))
    ceil = duration or (times[-1] if times else 0) + 1
    times = sorted({round(t, 1) for t in times if 0 <= t <= ceil})
    out: List[float] = []
    for t in times:                                # final min-gap guard
        if not out or t - out[-1] >= min_gap - 0.01:
            out.append(t)
    return out


def embed_frames(frames: List[Tuple[float, Path]], video_id: str, watch_url: str,
                 kind: str = "keyframe", title: str = "", embedder=None, base_dir=None,
                 captions: Optional[List[str]] = None, asset_types: Optional[List[str]] = None) -> int:
    """CLIP-embed frames into the transcript-frame library, each tagged with {video_id, t, kind} so a
    search hit resolves to a video + timestamp. If `captions` (parallel to `frames`) is given, each is
    stored as the frame's description → BGE-embedded too. If `asset_types` (parallel, gemma's 11-value shot
    type) is given, each frame carries an `at=<asset_type>` tag AND its derived `ck=<broll|talking_head|
    graphics>` roll-up so search can filter by either. Returns the number embedded."""
    from nolan.visual_facts import content_kind_of
    lib = frame_lib(embedder=embedder, base_dir=base_dir)
    n = 0
    for i, (ts, fp) in enumerate(frames):
        cap = (captions[i] if captions and i < len(captions) else None) or None
        at = (asset_types[i] if asset_types and i < len(asset_types) else "") or ""
        ck = content_kind_of(at)
        tags = f"video_id={video_id};t={float(ts):.1f};kind={kind}"
        if at:
            tags += f";at={at}"
        if ck:
            tags += f";ck={ck}"
        try:
            lib.add_file(str(fp), source=f"youtube-{kind}", source_url=watch_url,
                         title=title or video_id, description=cap, tags=tags, query=f"{float(ts):.1f}")
            n += 1
        except Exception:
            continue
    return n


def _parse_tags(tags: str) -> Dict[str, str]:
    return dict(kv.split("=", 1) for kv in (tags or "").split(";") if "=" in kv)


def split_caption(caption: str) -> Dict[str, Any]:
    """Reverse `_extract_analysis`'s fused caption back into {summary, people, location, objects, story}
    for the structured detail column (deterministic — we own the ' | Label: value' format)."""
    out: Dict[str, Any] = {"summary": "", "people": [], "location": "", "objects": [], "story": ""}
    labels = {"People": "people", "Location": "location", "Objects": "objects", "Context": "story"}
    for i, p in enumerate((caption or "").split(" | ")):
        p = p.strip()
        matched = False
        for lab, key in labels.items():
            if p.startswith(lab + ": "):
                val = p[len(lab) + 2:].strip()
                out[key] = [x.strip() for x in val.split(",") if x.strip()] if key in ("people", "objects") else val
                matched = True
                break
        if not matched and not out["summary"] and i == 0:
            out["summary"] = p
    return out


def frames_for_video(video_id: str, base_dir=None) -> List[Dict[str, Any]]:
    """All stored frames for a transcript video (matched on the video_id tag) → [{asset_id, t, kind,
    thumb, caption}] sorted by timestamp — the visual-tier detail for a video's drill-down."""
    lib = frame_lib(base_dir=base_dir)
    needle = f"video_id={video_id};"
    out: List[Dict[str, Any]] = []
    for a in lib.catalog.list(status="active"):
        tags = getattr(a, "tags", "") or ""
        if needle not in tags:
            continue
        tg = _parse_tags(tags)
        out.append({"asset_id": a.id, "t": float(tg.get("t", 0) or 0), "kind": tg.get("kind", ""),
                    "asset_type": tg.get("at", ""), "content_kind": tg.get("ck", ""),
                    "thumb": str(lib.abs_path(a)), "caption": getattr(a, "description", "") or ""})
    out.sort(key=lambda x: x["t"])
    return out


def delete_frames_for_video(video_id: str, base_dir=None) -> int:
    """Remove a transcript video's frames from the visual tier (status→deleted drops them from the CLIP +
    BGE collections and from search). Returns the count removed. Files stay (content-addressed, harmless)."""
    import shutil
    lib = frame_lib(base_dir=base_dir)
    needle = f"video_id={video_id};"
    ids = []
    for st in ("active", "deleted"):                       # purge BOTH so the sha256 is fully freed for re-embed
        try:
            rows = lib.catalog.list(status=st)
        except Exception:
            rows = []
        ids += [a.id for a in rows if needle in (getattr(a, "tags", "") or "")]
    n = 0
    for aid in set(ids):
        try:
            lib.hard_delete(aid)                          # vectors + row (not just status), so refresh truly replaces
            n += 1
        except Exception:
            continue
    shutil.rmtree(storyboard_dir(video_id, base_dir), ignore_errors=True)   # + the on-disk filmstrip
    return n


def visual_search(query: str, n: int = 24, embedder=None, base_dir=None,
                  content_kind: str = "") -> List[Dict[str, Any]]:
    """Search the transcript-frame library → [{video_id, start, watch_url, kind, content_kind, title,
    caption, score, thumb}]. HYBRID retrieval (CLIP appearance + the gemma caption's BGE text) so a query
    matches both what a frame LOOKS like and what the VLM described (OCR/entities); falls back to pure CLIP.
    `content_kind` (e.g. "broll") filters to that shot class — the "b-roll only" toggle; over-fetches so the
    filter still returns a full page."""
    lib = frame_lib(embedder=embedder, base_dir=base_dir)
    want = (content_kind or "").strip().lower()
    k = int(n) * 4 if want else int(n)
    try:
        hits = lib.search_hybrid(query, k=k)
    except Exception:
        hits = lib.search(query, k=k)
    out: List[Dict[str, Any]] = []
    for h in hits:
        a = h.asset
        tg = _parse_tags(getattr(a, "tags", "") or "")
        if want and tg.get("ck", "") != want:
            continue
        ts = float(tg.get("t", 0) or 0)
        url = getattr(a, "source_url", "") or ""
        out.append({
            "video_id": tg.get("video_id", ""), "start": round(ts, 1),
            "watch_url": (f"{url}&t={int(ts)}s" if "watch?v=" in url else url),
            "kind": tg.get("kind", ""), "content_kind": tg.get("ck", ""), "asset_type": tg.get("at", ""),
            "title": getattr(a, "title", "") or "",
            "caption": getattr(a, "description", "") or "",
            "score": round(float(h.score), 3), "thumb": str(lib.abs_path(a)),
        })
        if len(out) >= int(n):
            break
    return out
