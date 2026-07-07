"""Ingest a source into the KB raw store (markdown-first).

Routes url / youtube / file / pasted-text to clean text (reusing NOLAN's
publish.source + youtube modules), dedups by content hash, and writes
raw/<type>/<date>_<slug>.md with YAML frontmatter. Registers the source in the
catalog. Distillation (P2) reads status='raw' notes and writes parsed/ notes.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from . import paths
from .catalog import KBCatalog, Source


@dataclass
class IngestResult:
    id: str
    title: str
    source_type: str
    raw_path: Path
    deduped: bool


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()[:16]


def _slug(s: str, maxlen: int = 60) -> str:
    from nolan.publish.source import slugify
    return slugify(s or "untitled", maxlen=maxlen) or "untitled"


def _first_line(s: str, n: int = 70) -> str:
    line = next((ln.strip() for ln in s.splitlines() if ln.strip()), "untitled")
    return line[:n]


def _fm_str(v) -> str:
    """A YAML-safe double-quoted scalar."""
    s = str(v or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip()
    return f'"{s}"'


def _pdf_text(path: Path) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError(
            "PDF ingest needs PyMuPDF — install with: "
            r"D:\env\nolan\Scripts\pip.exe install pymupdf")
    doc = fitz.open(str(path))
    return "\n\n".join(page.get_text() for page in doc).strip()


def _load(src: str, source_type: Optional[str]):
    """Return (kind, text, meta) where meta = {title, url, author, published}."""
    from nolan.youtube import is_youtube_url

    s = src.strip()

    if source_type == "youtube" or (source_type is None and is_youtube_url(s)):
        from nolan.youtube import YouTubeClient
        info = YouTubeClient().fetch_transcript(s)
        return "youtube", info.get("text", ""), {
            "title": info.get("title", ""), "url": s,
            "author": info.get("channel", ""), "published": str(info.get("upload_date", ""))}

    if source_type == "text":
        return "text", s, {"title": _first_line(s), "url": ""}

    looks_url = s.startswith(("http://", "https://"))
    looks_file = (not looks_url) and len(s) < 400 and Path(s).exists()

    if looks_file and Path(s).suffix.lower() == ".pdf":
        # store the binary outside the vault; index only its text
        paths.BINARIES.mkdir(parents=True, exist_ok=True)
        text = _pdf_text(Path(s))
        return "file", text, {"title": Path(s).stem, "url": str(Path(s))}

    if looks_url or looks_file or source_type in ("url", "file", "article"):
        from nolan.publish.source import load_source
        doc = load_source(s)
        kind = "article" if looks_url else "file"
        return kind, doc.markdown, {"title": doc.title, "url": doc.url or (s if looks_url else ""),
                                    "author": "", "published": ""}

    # fallback: treat the argument as raw pasted text
    return "text", s, {"title": _first_line(s), "url": ""}


def _frontmatter(kind: str, title: str, meta: dict, h: str) -> str:
    lines = [
        "---",
        "kb: raw",
        f"id: {h}",
        f"source_type: {kind}",
        f"title: {_fm_str(title)}",
        f"url: {_fm_str(meta.get('url', ''))}",
        f"author: {_fm_str(meta.get('author', ''))}",
        f"published: {_fm_str(meta.get('published', ''))}",
        f"ingested: {date.today().isoformat()}",
        "status: raw",
        "---",
    ]
    return "\n".join(lines)


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suf, i = path.stem, path.suffix, 2
    while True:
        cand = path.with_name(f"{stem}-{i}{suf}")
        if not cand.exists():
            return cand
        i += 1


def ingest(src: str, *, source_type: Optional[str] = None,
           catalog: Optional[KBCatalog] = None) -> IngestResult:
    """Ingest one source into raw/. Idempotent by content hash."""
    paths.ensure_dirs()
    cat = catalog or KBCatalog()

    kind, text, meta = _load(src, source_type)
    text = (text or "").strip()
    if not text:
        raise ValueError(f"ingest produced no text for: {src[:80]}")

    h = _sha1(text)
    existing = cat.get(h)
    if existing:
        return IngestResult(h, existing.title, existing.source_type,
                            paths.VAULT / existing.raw_path, True)

    title = meta.get("title") or _first_line(text)
    fname = f"{date.today().isoformat()}_{_slug(title)}.md"
    raw_dir = paths.RAW / kind
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = _unique(raw_dir / fname)

    raw_path.write_text(_frontmatter(kind, title, meta, h) + "\n\n" + text, encoding="utf-8")
    rel = raw_path.relative_to(paths.VAULT).as_posix()

    cat.upsert(Source(
        id=h, source_type=kind, title=title, url=meta.get("url", ""),
        author=meta.get("author", ""), published=meta.get("published", ""),
        ingested_at=time.time(), raw_path=rel, char_count=len(text),
        status="raw", meta=meta))

    return IngestResult(h, title, kind, raw_path, False)
