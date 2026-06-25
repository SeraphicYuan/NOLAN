"""Script-style corpora + style-guide library for NOLAN.

A *script style* is a named project that collects reference transcripts (a
corpus) and distills them into a reusable script-writing **style guide**. This is
the writing-craft mirror of the visual asset/effects library: instead of
learning visual technique from clips, we learn narrative/voice technique from
transcripts.

On-disk layout (one directory per style, under ``script_styles/``):

    script_styles/<id>/
    ├── manifest.json        # id, name, created_at, sources[]
    ├── corpus/<slug>.txt     # one transcript per source (plain text)
    ├── per_transcript/<slug>.json  # Stage-B per-transcript feature extracts
    └── style_guide.md        # the distilled guide (Stage-B synthesis output)

Files (not a DB) keep the artifacts human-readable and easy to hand to an agent,
matching how the rest of NOLAN stores creative artifacts.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_ROOT = Path("script_styles")


def slugify(text: str, fallback: str = "item") -> str:
    """URL/file-safe slug from arbitrary text."""
    s = (text or "").lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^\w\-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or fallback


class ScriptStyleStore:
    """File-backed manager for script-style corpora and their style guides."""

    def __init__(self, root: Path = DEFAULT_ROOT):
        self.root = Path(root)

    # --- paths -----------------------------------------------------------------
    def _dir(self, style_id: str) -> Path:
        return self.root / style_id

    def _manifest_path(self, style_id: str) -> Path:
        return self._dir(style_id) / "manifest.json"

    def corpus_dir(self, style_id: str) -> Path:
        return self._dir(style_id) / "corpus"

    def extracts_dir(self, style_id: str) -> Path:
        return self._dir(style_id) / "per_transcript"

    def guide_path(self, style_id: str) -> Path:
        return self._dir(style_id) / "style_guide.md"

    # --- manifest io -----------------------------------------------------------
    def _load_manifest(self, style_id: str) -> Dict[str, Any]:
        p = self._manifest_path(style_id)
        if not p.exists():
            raise FileNotFoundError(f"script style not found: {style_id}")
        return json.loads(p.read_text(encoding="utf-8"))

    def _save_manifest(self, manifest: Dict[str, Any]) -> None:
        p = self._manifest_path(manifest["id"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- crud ------------------------------------------------------------------
    def create(self, name: str) -> str:
        """Create a new style project; returns its id (unique slug)."""
        base = slugify(name, "style")
        style_id = base
        n = 2
        while self._dir(style_id).exists():
            style_id = f"{base}-{n}"
            n += 1
        manifest = {
            "id": style_id,
            "name": name,
            "created_at": datetime.now().isoformat(),
            "sources": [],
        }
        self.corpus_dir(style_id).mkdir(parents=True, exist_ok=True)
        self._save_manifest(manifest)
        return style_id

    def exists(self, style_id: str) -> bool:
        return self._manifest_path(style_id).exists()

    def get(self, style_id: str) -> Dict[str, Any]:
        m = self._load_manifest(style_id)
        m["has_guide"] = self.guide_path(style_id).exists()
        m["source_count"] = len(m.get("sources", []))
        return m

    def list(self) -> List[Dict[str, Any]]:
        out = []
        if not self.root.exists():
            return out
        for d in sorted(self.root.iterdir()):
            if (d / "manifest.json").exists():
                try:
                    m = self._load_manifest(d.name)
                    out.append({
                        "id": m["id"],
                        "name": m.get("name", m["id"]),
                        "created_at": m.get("created_at"),
                        "source_count": len(m.get("sources", [])),
                        "has_guide": self.guide_path(d.name).exists(),
                    })
                except Exception:
                    continue
        out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return out

    def delete(self, style_id: str) -> bool:
        d = self._dir(style_id)
        if not d.exists():
            return False
        import shutil
        shutil.rmtree(d, ignore_errors=True)
        return True

    # --- sources / dedup -------------------------------------------------------
    def has_video(self, style_id: str, video_id: Optional[str]) -> bool:
        """True if a YouTube video_id is already in this style's corpus."""
        if not video_id:
            return False
        m = self._load_manifest(style_id)
        return any(s.get("video_id") == video_id for s in m.get("sources", []))

    def _unique_slug(self, style_id: str, base: str) -> str:
        existing = {s["slug"] for s in self._load_manifest(style_id).get("sources", [])}
        slug = slugify(base, "transcript")
        candidate, n = slug, 2
        while candidate in existing or (self.corpus_dir(style_id) / f"{candidate}.txt").exists():
            candidate = f"{slug}-{n}"
            n += 1
        return candidate

    def add_source(self, style_id: str, *, text: str, title: str,
                   source_type: str, video_id: Optional[str] = None,
                   url: Optional[str] = None, channel: Optional[str] = None,
                   published_at: Optional[str] = None,
                   language: Optional[str] = None) -> Dict[str, Any]:
        """Write a transcript into the corpus and record it in the manifest.

        Dedups YouTube sources by ``video_id`` (returns the existing entry with
        ``skipped=True`` rather than re-adding).
        """
        manifest = self._load_manifest(style_id)
        if video_id:
            for s in manifest.get("sources", []):
                if s.get("video_id") == video_id:
                    return {**s, "skipped": True}

        slug = self._unique_slug(style_id, title or video_id or "transcript")
        self.corpus_dir(style_id).mkdir(parents=True, exist_ok=True)
        text_path = self.corpus_dir(style_id) / f"{slug}.txt"
        text_path.write_text(text or "", encoding="utf-8")

        entry = {
            "slug": slug,
            "source_type": source_type,
            "video_id": video_id,
            "url": url,
            "title": title,
            "channel": channel,
            "published_at": published_at,
            "language": language,
            "text_path": str(Path("corpus") / f"{slug}.txt"),
            "word_count": len((text or "").split()),
            "fetched_at": datetime.now().isoformat(),
        }
        manifest.setdefault("sources", []).append(entry)
        self._save_manifest(manifest)
        return {**entry, "skipped": False}

    def remove_source(self, style_id: str, slug: str) -> bool:
        manifest = self._load_manifest(style_id)
        sources = manifest.get("sources", [])
        kept = [s for s in sources if s["slug"] != slug]
        if len(kept) == len(sources):
            return False
        manifest["sources"] = kept
        self._save_manifest(manifest)
        (self.corpus_dir(style_id) / f"{slug}.txt").unlink(missing_ok=True)
        (self.extracts_dir(style_id) / f"{slug}.json").unlink(missing_ok=True)
        return True

    # --- corpus / guide access -------------------------------------------------
    def corpus_texts(self, style_id: str) -> List[Dict[str, Any]]:
        """Return [{slug, title, text}] for every source in the corpus."""
        manifest = self._load_manifest(style_id)
        out = []
        for s in manifest.get("sources", []):
            p = self._dir(style_id) / s["text_path"]
            text = p.read_text(encoding="utf-8") if p.exists() else ""
            out.append({"slug": s["slug"], "title": s.get("title") or s["slug"], "text": text})
        return out

    def write_extract(self, style_id: str, slug: str, data: Dict[str, Any]) -> None:
        d = self.extracts_dir(style_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{slug}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                        encoding="utf-8")

    def read_guide(self, style_id: str) -> Optional[str]:
        p = self.guide_path(style_id)
        return p.read_text(encoding="utf-8") if p.exists() else None

    def write_guide(self, style_id: str, markdown: str) -> None:
        self.guide_path(style_id).write_text(markdown, encoding="utf-8")
