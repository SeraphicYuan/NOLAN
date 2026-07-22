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


def ranged_keyframes(url: str, timestamps: List[float], out_dir: Path,
                     is_youtube: bool = True) -> List[Tuple[float, Path]]:
    """Grab ONE full-res frame at each timestamp via ffmpeg input-seek over the remote stream (reuses the
    clipper -ss-before-i pattern; bundled ffmpeg; no ffprobe). For a YouTube watch URL, resolves a direct
    stream once + reuses it. Returns [(timestamp, jpg_path)] for frames produced (misses are skipped)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    src = _resolve_stream(url) if is_youtube else url
    if not src:
        return []
    ff = _ffmpeg()
    out: List[Tuple[float, Path]] = []
    for t in timestamps:
        fp = out_dir / f"kf_{int(float(t))}.jpg"
        subprocess.run([ff, "-y", "-ss", f"{float(t):.3f}", "-i", src, "-frames:v", "1",
                        "-q:v", "3", "-vf", "scale=640:-2", str(fp)], capture_output=True)
        if fp.exists() and fp.stat().st_size > 0:
            out.append((float(t), fp))
    return out


def storyboard_tiles(watch_url: str, out_dir: Path, every_s: float = 12.0,
                     max_tiles: int = 60) -> List[Tuple[float, Path]]:
    """Fetch YouTube storyboard spritesheets (NO video download) and split into (timestamp, tile jpg),
    sampled to ~every_s apart and capped at max_tiles. Low-res but free. Returns [] when a video has no
    storyboards. Gotchas handled: tile size derived from the SHEET, t0 accumulated across fragments,
    all-black trailing tiles dropped."""
    import urllib.request

    from PIL import Image
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(watch_url, download=False)
    sbs = [f for f in (info.get("formats") or []) if (f.get("format_id") or "").startswith("sb")]
    if not sbs:
        return []
    sb = max(sbs, key=lambda f: (f.get("width", 0) or 0) * (f.get("height", 0) or 0)
             * (f.get("rows", 1) or 1) * (f.get("columns", 1) or 1))
    rows, cols = int(sb.get("rows", 0) or 0), int(sb.get("columns", 0) or 0)
    frags = sb.get("fragments") or []
    if not (rows and cols and frags):
        return []
    out: List[Tuple[float, Path]] = []
    t0 = 0.0
    last_kept = -1e9
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
            if ts - last_kept < every_s:
                continue
            r, c = divmod(idx, cols)
            if (c + 1) * tw > sheet.width or (r + 1) * th > sheet.height:
                continue
            tile = sheet.crop((c * tw, r * th, (c + 1) * tw, (r + 1) * th))
            if tile.getbbox() is None:                        # all-black trailing tile
                continue
            fp = out_dir / f"sb_{int(ts)}.jpg"
            tile.save(fp, quality=85)
            out.append((round(ts, 1), fp))
            last_kept = ts
            if len(out) >= max_tiles:
                return out
        t0 += dur
    return out


def embed_frames(frames: List[Tuple[float, Path]], video_id: str, watch_url: str,
                 kind: str = "keyframe", title: str = "", embedder=None, base_dir=None) -> int:
    """CLIP-embed frames into the transcript-frame library, each tagged with {video_id, t, kind} so a
    search hit resolves back to a video + timestamp. Returns the number embedded."""
    lib = frame_lib(embedder=embedder, base_dir=base_dir)
    n = 0
    for ts, fp in frames:
        try:
            lib.add_file(str(fp), source=f"youtube-{kind}", source_url=watch_url,
                         title=title or video_id,
                         tags=f"video_id={video_id};t={float(ts):.1f};kind={kind}",
                         query=f"{float(ts):.1f}")
            n += 1
        except Exception:
            continue
    return n


def _parse_tags(tags: str) -> Dict[str, str]:
    return dict(kv.split("=", 1) for kv in (tags or "").split(";") if "=" in kv)


def visual_search(query: str, n: int = 24, embedder=None, base_dir=None) -> List[Dict[str, Any]]:
    """CLIP text→image over the transcript-frame library → [{video_id, start, watch_url, kind, title,
    score, thumb}] — the visual counterpart of the transcript TEXT search."""
    lib = frame_lib(embedder=embedder, base_dir=base_dir)
    out: List[Dict[str, Any]] = []
    for h in lib.search(query, k=int(n)):
        a = h.asset
        tg = _parse_tags(getattr(a, "tags", "") or "")
        ts = float(tg.get("t", 0) or 0)
        url = getattr(a, "source_url", "") or ""
        out.append({
            "video_id": tg.get("video_id", ""), "start": round(ts, 1),
            "watch_url": (f"{url}&t={int(ts)}s" if "watch?v=" in url else url),
            "kind": tg.get("kind", ""), "title": getattr(a, "title", "") or "",
            "score": round(float(h.score), 3), "thumb": str(lib.abs_path(a)),
        })
    return out
