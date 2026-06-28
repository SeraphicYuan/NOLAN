"""Source ingestion for the publisher: URL / HTML / file -> clean Markdown.

NOLAN's `extractors` return images, not article text, so the publisher does its
own HTML->Markdown (BeautifulSoup). The agent still cleans/de-dupes during the
plan phase; this just gets a faithful first draft into `source/source.md`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

_BLOCK = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "pre"}
_DROP = {"script", "style", "nav", "header", "footer", "form", "aside", "noscript", "svg", "button"}


@dataclass
class SourceDoc:
    title: str
    markdown: str
    url: str | None = None
    notes: list[str] = field(default_factory=list)


def fetch_html(url: str, timeout: float = 30.0) -> str:
    import httpx

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NOLAN-publish"}
    r = httpx.get(url, headers=headers, follow_redirects=True, timeout=timeout)
    r.raise_for_status()
    return r.text


def html_to_markdown(html: str, url: str | None = None) -> SourceDoc:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.get_text(strip=True) if soup.title else "") or "Untitled"
    for tag in soup.find_all(_DROP):
        tag.decompose()
    # pick the densest main-content container
    root = soup.find("article") or soup.find("main") or soup.body or soup
    lines: list[str] = []
    for el in root.find_all(_BLOCK):
        name = el.name
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        if name.startswith("h") and len(name) == 2 and name[1].isdigit():
            lines.append("#" * int(name[1]) + " " + text)
        elif name == "li":
            lines.append("- " + text)
        elif name == "blockquote":
            lines.append("> " + text)
        elif name == "pre":
            lines.append("```\n" + el.get_text("\n", strip=False).strip() + "\n```")
        else:
            lines.append(text)
    md = "\n\n".join(lines)
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    notes = []
    if len(md) < 400:
        notes.append("Extraction is short — the page may be JS-rendered; agent should verify.")
    return SourceDoc(title=title, markdown=md, url=url, notes=notes)


def load_source(src: str) -> SourceDoc:
    """`src` is a URL, an .html/.md/.txt file path, or raw text."""
    p = Path(src)
    if src.startswith("http://") or src.startswith("https://"):
        doc = html_to_markdown(fetch_html(src), url=src)
    elif p.exists() and p.suffix.lower() in {".html", ".htm"}:
        doc = html_to_markdown(p.read_text(encoding="utf-8", errors="replace"))
    elif p.exists() and p.suffix.lower() in {".md", ".markdown", ".txt"}:
        doc = SourceDoc(title=p.stem, markdown=p.read_text(encoding="utf-8", errors="replace"))
    else:
        # Anything else is treated as raw pasted text — but don't silently turn a
        # mistyped or unsupported *path* into the article body (a silent degrade).
        if p.exists():
            raise ValueError(f"unsupported source type {p.suffix!r}; pre-convert to .md/.html/.txt: {src}")
        looks_like_path = "\n" not in src and len(src) < 260 and (
            p.suffix.lower() in {".md", ".markdown", ".txt", ".html", ".htm", ".pdf", ".docx"}
            or src.startswith(("./", "../", "/", "~"))
            or (len(src) > 1 and src[1] == ":")  # Windows drive, e.g. D:\...
        )
        if looks_like_path:
            raise FileNotFoundError(f"source path not found: {src}")
        doc = SourceDoc(title="Untitled", markdown=src)
    return doc


def slugify(s: str, maxlen: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return (s[:maxlen].rstrip("-")) or "article"
