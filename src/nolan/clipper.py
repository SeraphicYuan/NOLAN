"""Clip a time range out of any video SOURCE — a YouTube link, a direct `.mp4`, an `.m3u8`/HLS stream, or a
local file — with yt_dlp + ffmpeg, WITHOUT downloading the whole thing or going through the ingestion library.

Powers the `/clipper` page: paste a link, scrub, mark [in, out], and pull just that range into a folder (and
optionally straight into a HyperFrames project's pool). Two mechanisms, picked by source kind:

  - youtube / other extractor sites → yt_dlp with `download_ranges` (fetches only the marked range).
  - direct .mp4 / .m3u8 / local file → ffmpeg `-ss/-t` (input-seek + re-encode → frame-accurate cuts).

Playback (browser) is handled by the route/page, not here: YouTube uses the iframe API (robust vs SABR),
direct/HLS play a Range-proxied `<video>` / hls.js. This module only PROBES and CLIPS.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

_MEDIA_EXT = (".mp4", ".mov", ".webm", ".mkv", ".m4v", ".ts")


def _ffmpeg() -> str:
    from nolan.hf_qa import _ffmpeg as ff
    return ff()


def _is_url(s: str) -> bool:
    return s.startswith(("http://", "https://"))


def kind_of(src: str, info: Optional[dict] = None) -> str:
    """Source kind → drives both playback and the clip mechanism. local | youtube | hls | direct | extractor."""
    if not _is_url(src):
        return "local"
    low = urlparse(src).path.lower()
    if info and str(info.get("extractor") or "").startswith("youtube"):
        return "youtube"
    if low.endswith(".m3u8") or (info and info.get("protocol") in ("m3u8", "m3u8_native")):
        return "hls"
    if low.endswith(_MEDIA_EXT):
        return "direct"
    if info is None and ("youtube.com" in src or "youtu.be" in src):
        return "youtube"
    return "extractor"


def _ff_duration(target: str) -> Optional[float]:
    """Container duration (seconds) via ffmpeg -i, for a local path OR a remote URL. None if unknown."""
    r = subprocess.run([_ffmpeg(), "-i", target], capture_output=True, text=True, errors="replace")
    for ln in (r.stdout + r.stderr).splitlines():
        if "Duration:" in ln:
            t = ln.split("Duration:")[1].split(",")[0].strip()
            try:
                h, m, s = t.split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)
            except Exception:
                return None
    return None


def probe(src: str) -> Dict:
    """Metadata for the source WITHOUT downloading it: {kind, title, duration, thumbnail, src/video_id}.
    Direct/HLS/local are probed with ffmpeg (skip yt_dlp's generic extractor, which 403s on bare media URLs);
    extractor sites (YouTube, …) go through yt_dlp. `src` is what playback/clip should use downstream."""
    src = src.strip()
    if not _is_url(src):
        p = Path(src)
        if not p.is_file():
            raise FileNotFoundError(f"not a URL and no local file at {src!r}")
        return {"kind": "local", "title": p.name, "duration": _ff_duration(str(p)),
                "thumbnail": "", "src": str(p)}

    low = urlparse(src).path.lower()
    if low.endswith(".m3u8") or low.endswith(_MEDIA_EXT):        # bare media URL → ffmpeg, not yt_dlp
        return {"kind": "hls" if low.endswith(".m3u8") else "direct",
                "title": Path(urlparse(src).path).name or src, "duration": _ff_duration(src),
                "thumbnail": "", "src": src}

    import yt_dlp
    with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "noplaylist": True}) as ydl:
        info = ydl.extract_info(src, download=False)
    k = kind_of(src, info)
    out = {"kind": k, "title": info.get("title") or src, "duration": info.get("duration"),
           "thumbnail": info.get("thumbnail") or "", "src": src}
    if k == "youtube":
        out["video_id"] = info.get("id")                        # the page plays this via the iframe API
    return out


def _newest_matching(stem_path: Path) -> Optional[Path]:
    """The file yt_dlp actually produced for outtmpl `<stem>.%(ext)s` (ext varies by chosen format)."""
    parent, stem = stem_path.parent, stem_path.stem
    cands = [p for p in parent.glob(stem + ".*") if p.is_file()]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def clip(src: str, start: float, end: float, out_path: Path, *, kind: Optional[str] = None) -> Optional[Path]:
    """Pull [start, end] seconds of `src` into `out_path` (mp4). Returns the path, or None on failure.

    youtube/extractor → yt_dlp `download_ranges` (only the range is fetched). direct/hls/local → ffmpeg
    input-seek + re-encode (frame-accurate, so the marked in/out are honoured exactly)."""
    start, end = float(start), float(end)
    if end <= start:
        raise ValueError("out point must be after the in point")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    kind = kind or kind_of(src)

    if kind in ("youtube", "extractor"):
        import yt_dlp
        from yt_dlp.utils import download_range_func
        tmpl = str(out_path.with_suffix("")) + ".%(ext)s"
        opts = {"quiet": True, "noplaylist": True, "outtmpl": tmpl,
                "download_ranges": download_range_func(None, [(start, end)]),
                "force_keyframes_at_cuts": True, "format": "bv*+ba/b"}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([src])
        except Exception as e:
            raise RuntimeError(f"yt_dlp clip failed: {type(e).__name__}: {e}")
        produced = _newest_matching(out_path)
        if produced is None:
            return None
        if produced.suffix.lower() != ".mp4" or produced != out_path:  # normalise to the requested .mp4
            subprocess.run([_ffmpeg(), "-y", "-i", str(produced), "-c:v", "libx264", "-preset", "veryfast",
                            "-crf", "20", "-c:a", "aac", "-movflags", "+faststart", str(out_path)],
                           capture_output=True)
            if produced != out_path:
                produced.unlink(missing_ok=True)
        return out_path if out_path.exists() else None

    # direct / hls / local → ffmpeg range (input-seek keeps it fast; re-encode makes the cut frame-accurate)
    dur = end - start
    r = subprocess.run([_ffmpeg(), "-y", "-ss", f"{start:.3f}", "-i", src, "-t", f"{dur:.3f}",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac",
                        "-movflags", "+faststart", str(out_path)], capture_output=True, text=True, errors="replace")
    if not (out_path.exists() and out_path.stat().st_size > 1000):
        raise RuntimeError(f"ffmpeg clip failed: {(r.stderr or '')[-240:]}")
    return out_path
