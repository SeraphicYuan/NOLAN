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
                      *, frames: int = 0, added: str = "", catalog_dir: Optional[Path] = None) -> None:
    """Upsert one transcript video's display metadata into the sidecar (keyed by the YouTube video id).
    `frames` = how many visual keyframes were captioned (drives the visual-coverage badge)."""
    cat = load_catalog(catalog_dir)
    cat[str(video_id)] = {
        "video_id": str(video_id), "title": meta.get("title"),
        "channel": channel or meta.get("channel"), "url": meta.get("url"),
        "upload_date": meta.get("upload_date"), "language": meta.get("language"),
        "windows": int(windows_n), "frames": int(frames), "added": added,
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
                  video_count: Optional[int] = None, added: str = "", catalog_dir: Optional[Path] = None) -> None:
    srcs = load_sources(catalog_dir)
    s = srcs.get(channel) or {"channel": channel, "added": added or last_crawled or ""}
    if label is not None:
        s["label"] = label
    if last_crawled is not None:
        s["last_crawled"] = last_crawled
    if video_count is not None:
        s["video_count"] = int(video_count)
    s.setdefault("label", channel)
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


def list_channel(channel: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Enumerate a channel's videos (newest first) without downloading — [{video_id, url, title, ...}]."""
    from nolan.youtube import YouTubeClient
    return YouTubeClient().list_channel_videos(channel, limit=limit)


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
