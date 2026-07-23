"""Internet Archive COLLECTION source for the transcript library.

A curated archive.org collection (e.g. ``prelinger``) as a copyright-free, transcript-bearing
discovery tier — the SAME row shape the YouTube channel source produces, so it reuses the whole
survey → dedup → topic-cluster → curate → ingest → search machinery in ``transcript_lib``. The
differences, all handled here:

* **Enumeration** is archive.org's scrape API (cursor-paginated, no 10k cap) — not yt-dlp. It returns
  RICH metadata for free: ``runtime`` (→duration), ``subject`` tag lists, ``description``, ``licenseurl``.
* **Copyright-free** is derived from ``licenseurl`` (public-domain / Creative Commons) — the signal behind
  the library's copyright-free filter.
* **Transcripts** are archive.org's Whisper ASR sidecar (``<id>.asr.srt``), fetched by direct HTTP (no
  rate-limit gymnastics) and normalized from 2-digit centisecond timestamps to 3-digit ms so the shared
  ``TranscriptLoader`` parses them. Items without an ``.asr.srt`` return ``(meta, None)`` — a soft miss the
  caller skips and REPORTS (no silent drop).

Metadata is deliberately kept DISTINCT from YouTube (subject tags + description + license), so the caller
clusters archive collections separately from channels.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

ADVSEARCH = "https://archive.org/advancedsearch.php"
META = "https://archive.org/metadata"
DOWNLOAD = "https://archive.org/download"
_UA = {"User-Agent": "NOLAN/1.0 (transcript library)"}

# advancedsearch (NOT the scrape API — scrape silently drops runtime/licenseurl) returns the rich fields.
# It has a ~10k deep-paging window; a collection larger than this is truncated (reported by the caller).
_FL = ["identifier", "title", "year", "runtime", "subject", "description", "licenseurl", "mediatype"]
_PAGE_ROWS = 1000
_ADV_CAP = 10000


def collection_ref(ref: str) -> str:
    """A collection id from a bare name, a ``/details/<id>`` URL, or a full archive.org URL."""
    m = re.search(r"/details/([^/?#]+)", ref or "")
    if m:
        return m.group(1)
    return (ref or "").strip().rstrip("/").split("/")[-1]


def parse_runtime(s: Any) -> Optional[int]:
    """archive.org ``runtime`` is a clock string ('9:29' or '1:02:03') — parse to seconds. None on junk."""
    if s is None or s == "":
        return None
    parts = str(s).strip().split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    sec = 0
    for p in nums:
        sec = sec * 60 + p
    return sec or None


def is_copyright_free(licenseurl: Optional[str], collection_free: bool = False) -> bool:
    """Copyright-free = an explicit PD/CC ``licenseurl`` OR the collection is curator-asserted copyright-free.
    In practice only ~18% of a collection like Prelinger carries a per-item ``licenseurl`` (though when present
    it's always PD/CC), yet the whole collection IS public domain — so the collection-level assertion made when
    the source is added is the primary signal, with the per-item license as confirmation."""
    if collection_free:
        return True
    l = (licenseurl or "").lower()
    return "publicdomain" in l or "creativecommons.org" in l


def _as_list(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x) for x in v if x]
    return [str(v)] if v else []


def survey_collection(ref: str, limit: Optional[int] = None, timeout: float = 45.0,
                      collection_free: bool = False) -> Tuple[List[Dict[str, Any]], int]:
    """Enumerate a collection's items via advancedsearch (paged, stable `identifier asc` sort). Returns
    ``(rows, total)`` where rows are shaped like the YouTube survey plus archive-only fields
    ``{video_id, url, title, duration, subject, description, license, copyright_free}`` and ``total`` is the
    collection's true size. ``collection_free`` (the curator's PD assertion for the whole collection) makes
    every row copyright-free. Bounded by advancedsearch's ~10k deep-paging window — if ``total`` exceeds what
    we fetched, the caller reports the truncation (no silent cap)."""
    coll = collection_ref(ref)
    out: List[Dict[str, Any]] = []
    total = 0
    with httpx.Client(headers=_UA, timeout=timeout) as c:
        page = 1
        while len(out) < _ADV_CAP:
            params: List[Tuple[str, Any]] = [
                ("q", f"collection:{coll}"), ("rows", _PAGE_ROWS), ("page", page),
                ("output", "json"), ("sort[]", "identifier asc")]
            params += [("fl[]", f) for f in _FL]
            r = c.get(ADVSEARCH, params=params)
            r.raise_for_status()
            resp = r.json().get("response", {}) or {}
            total = int(resp.get("numFound", 0) or 0)
            docs = resp.get("docs", []) or []
            if not docs:
                break
            for it in docs:
                ident = it.get("identifier")
                if not ident:
                    continue
                lic = it.get("licenseurl")
                out.append({
                    "video_id": ident,
                    "url": f"https://archive.org/details/{ident}",
                    "title": it.get("title") or ident,
                    "duration": parse_runtime(it.get("runtime")),
                    "subject": _as_list(it.get("subject")),
                    "description": it.get("description") or "",
                    "license": lic or "",
                    "copyright_free": is_copyright_free(lic, collection_free),
                })
                if limit and len(out) >= limit:
                    return out, total
            if len(out) >= total:
                break
            page += 1
    return out, total


def _normalize_srt(text: str) -> str:
    """archive.org's ``.asr.srt`` uses 2-digit centisecond fractions ('00:00:32,57'); standard SRT (and our
    TranscriptLoader) expects 3-digit ms ('00:00:32,570'). Pad any 2-fraction timestamp; leave 3-digit ones."""
    return re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{2})(?=\D)", r"\1,\g<2>0", text)


def _srt_name(files: List[Dict[str, Any]]) -> Optional[str]:
    """Prefer the ASR SubRip sidecar; fall back to any .srt (skip .vtt — TranscriptLoader takes .srt)."""
    asr = next((f.get("name") for f in files if str(f.get("name", "")).lower().endswith(".asr.srt")), None)
    if asr:
        return asr
    return next((f.get("name") for f in files if str(f.get("name", "")).lower().endswith(".srt")), None)


def fetch_transcript(identifier: str, collection: str = "", out_dir: Optional[Path] = None,
                     timeout: float = 45.0) -> Tuple[Dict[str, Any], Any]:
    """``(meta, transcript_cues)`` from archive.org's Whisper ASR ``.asr.srt``. ``(meta, None)`` when the item
    has no transcript sidecar (a soft miss the caller skips + reports). ``meta`` carries the rich item metadata
    (description, subject, license, runtime, year) so the ingest keeps it. Reuses ``TranscriptLoader`` by
    writing the normalized SRT to a temp file — so ``chunk_transcript`` works unchanged."""
    from nolan.transcript import TranscriptLoader
    ident = collection_ref(identifier) if "/" in (identifier or "") else identifier
    out = Path(out_dir) if out_dir else Path(tempfile.mkdtemp())
    out.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers=_UA, timeout=timeout, follow_redirects=True) as c:
        m = c.get(f"{META}/{ident}").json()
        md = m.get("metadata", {}) or {}
        files = m.get("files", []) or []
        lic = md.get("licenseurl") or ""
        coll_meta = md.get("collection")
        channel = collection or (coll_meta[0] if isinstance(coll_meta, list) and coll_meta else (coll_meta or ""))
        meta: Dict[str, Any] = {
            "video_id": ident,
            "title": md.get("title") or ident,
            "channel": channel,
            "url": f"https://archive.org/details/{ident}",
            "description": md.get("description") or "",
            "subject": _as_list(md.get("subject")),
            "license": lic,
            "copyright_free": is_copyright_free(lic),
            "runtime": md.get("runtime"),
            "duration": parse_runtime(md.get("runtime")),
            "upload_date": md.get("year") or (str(md.get("date") or "")[:4] or None),
            "shotlist": md.get("shotlist") or "",
        }
        srt = _srt_name(files)
        if not srt:
            return (meta, None)                                   # no transcript for this item — soft miss
        raw = c.get(f"{DOWNLOAD}/{ident}/{srt}").text
    srt_path = out / f"{ident}.srt"
    srt_path.write_text(_normalize_srt(raw), encoding="utf-8")
    transcript = TranscriptLoader.load(srt_path)
    return (meta, transcript)
