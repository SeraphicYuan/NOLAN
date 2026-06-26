"""File-backed store for video-style projects (the visual twin of ScriptStyleStore).

On-disk layout (one directory per style, under ``video_styles/``):

    video_styles/<id>/
    ├── manifest.json          # id, name, created_at, sources[] (reference videos)
    ├── per_video/<slug>.json   # per-video visual extract (stats + vision read)
    ├── frames/<slug>/          # sampled frames used for analysis (optional cache)
    ├── synthesis_task.md       # agent brief
    └── video_style_guide.md    # the distilled guide
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_ROOT = Path("video_styles")


def slugify(text: str, fallback: str = "item") -> str:
    # ASCII-only: keeps frame/dir paths cv2- and filesystem-safe on Windows
    # (non-ASCII paths break cv2 image I/O). CJK/other titles fall back cleanly.
    s = (text or "").lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^\w\-]", "", s, flags=re.ASCII)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or fallback


class VideoStyleStore:
    """Manage video-style corpora (reference videos) and their style guides."""

    def __init__(self, root: Path = DEFAULT_ROOT):
        self.root = Path(root)

    # --- paths -----------------------------------------------------------------
    def _dir(self, style_id: str) -> Path:
        return self.root / style_id

    def _manifest_path(self, style_id: str) -> Path:
        return self._dir(style_id) / "manifest.json"

    def extracts_dir(self, style_id: str) -> Path:
        return self._dir(style_id) / "per_video"

    def frames_dir(self, style_id: str, slug: str) -> Path:
        return self._dir(style_id) / "frames" / slug

    def guide_path(self, style_id: str) -> Path:
        return self._dir(style_id) / "video_style_guide.md"

    def task_path(self, style_id: str) -> Path:
        return self._dir(style_id) / "synthesis_task.md"

    # --- manifest io -----------------------------------------------------------
    def _load_manifest(self, style_id: str) -> Dict[str, Any]:
        p = self._manifest_path(style_id)
        if not p.exists():
            raise FileNotFoundError(f"video style not found: {style_id}")
        return json.loads(p.read_text(encoding="utf-8"))

    def _save_manifest(self, manifest: Dict[str, Any]) -> None:
        p = self._manifest_path(manifest["id"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- crud ------------------------------------------------------------------
    def create(self, name: str) -> str:
        base = slugify(name, "style")
        style_id, n = base, 2
        while self._dir(style_id).exists():
            style_id = f"{base}-{n}"; n += 1
        manifest = {"id": style_id, "name": name,
                    "created_at": datetime.now().isoformat(),
                    "script_style_id": None,  # optional pairing with a Script Style
                    "sources": []}
        self.extracts_dir(style_id).mkdir(parents=True, exist_ok=True)
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
        out: List[Dict[str, Any]] = []
        if not self.root.exists():
            return out
        for d in sorted(self.root.iterdir()):
            if (d / "manifest.json").exists():
                try:
                    m = self._load_manifest(d.name)
                    out.append({"id": m["id"], "name": m.get("name", m["id"]),
                                "created_at": m.get("created_at"),
                                "source_count": len(m.get("sources", [])),
                                "script_style_id": m.get("script_style_id"),
                                "has_guide": self.guide_path(d.name).exists()})
                except Exception:
                    continue
        out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return out

    def delete(self, style_id: str) -> bool:
        d = self._dir(style_id)
        if not d.exists():
            return False
        shutil.rmtree(d, ignore_errors=True)
        return True

    def pair_script_style(self, style_id: str, script_style_id: Optional[str]) -> None:
        """Cross-link this video style to a Script Style (for a 'channel profile')."""
        m = self._load_manifest(style_id)
        m["script_style_id"] = script_style_id or None
        self._save_manifest(m)

    # --- sources (reference videos from the library) ---------------------------
    def has_video(self, style_id: str, video_path: str) -> bool:
        m = self._load_manifest(style_id)
        return any(s.get("video_path") == video_path for s in m.get("sources", []))

    def _unique_slug(self, style_id: str, base: str) -> str:
        existing = {s["slug"] for s in self._load_manifest(style_id).get("sources", [])}
        slug = slugify(base, "video")
        candidate, n = slug, 2
        while candidate in existing:
            candidate = f"{slug}-{n}"; n += 1
        return candidate

    def add_video(self, style_id: str, *, video_path: str, title: str = "",
                  fingerprint: Optional[str] = None, duration: Optional[float] = None,
                  indexed: bool = False) -> Dict[str, Any]:
        """Add a reference video. Dedups by ``video_path`` (returns skipped=True)."""
        manifest = self._load_manifest(style_id)
        for s in manifest.get("sources", []):
            if s.get("video_path") == video_path:
                return {**s, "skipped": True}
        title = title or Path(video_path).stem
        slug = self._unique_slug(style_id, title)
        entry = {"slug": slug, "video_path": video_path, "title": title,
                 "fingerprint": fingerprint, "duration": duration,
                 "indexed": bool(indexed), "analyzed": False,
                 "added_at": datetime.now().isoformat()}
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
        (self.extracts_dir(style_id) / f"{slug}.json").unlink(missing_ok=True)
        shutil.rmtree(self.frames_dir(style_id, slug), ignore_errors=True)
        return True

    def sources(self, style_id: str) -> List[Dict[str, Any]]:
        return self._load_manifest(style_id).get("sources", [])

    def mark_analyzed(self, style_id: str, slug: str) -> None:
        m = self._load_manifest(style_id)
        for s in m.get("sources", []):
            if s["slug"] == slug:
                s["analyzed"] = True
        self._save_manifest(m)

    # --- extracts / guide ------------------------------------------------------
    def write_extract(self, style_id: str, slug: str, data: Dict[str, Any]) -> None:
        d = self.extracts_dir(style_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{slug}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                        encoding="utf-8")

    def read_extract(self, style_id: str, slug: str) -> Optional[Dict[str, Any]]:
        p = self.extracts_dir(style_id) / f"{slug}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def read_guide(self, style_id: str) -> Optional[str]:
        p = self.guide_path(style_id)
        return p.read_text(encoding="utf-8") if p.exists() else None

    def write_guide(self, style_id: str, markdown: str) -> None:
        self.guide_path(style_id).write_text(markdown, encoding="utf-8")
