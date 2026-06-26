"""File-backed store for grounded script-writing projects.

A script project IS a normal NOLAN project (``projects/<slug>/`` with
``project.yaml`` + ``script.md``, consumed by the orchestrator Director). This
store adds a ``scriptgen/`` workspace that holds the grounding artifacts the
Director ignores:

    projects/<slug>/
    ├── project.yaml          # Director-ready meta (name, slug, description, …)
    ├── script.md             # FINAL voiceover (## beat headings + Total Duration)
    ├── source/ assets/ output/ .orchestrator/…   # standard project scaffold
    └── scriptgen/            # writing workspace (Director never reads it)
        ├── meta.json         # authoritative: subject, style_id, brief, sources[]
        ├── brief.md          # human-readable brief
        ├── sources/
        │   ├── sources.md    # human-readable manifest
        │   └── raw/S1-*.md   # fetched/pasted source text
        ├── facts.md          # grounded fact sheet ([S1] / [model: needs-check])
        ├── factcheck.md      # claim → supporting source quote / flag
        └── citations.md

Files (not a DB) keep everything human- and agent-readable, matching
``script_style.ScriptStyleStore``.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

DEFAULT_ROOT = Path("projects")


def slugify(text: str, fallback: str = "project") -> str:
    """URL/file-safe slug from arbitrary text."""
    s = (text or "").lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^\w\-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or fallback


# Project subfolders mirrored from `nolan projects init` so the result is
# orchestrator-ready without depending on that CLI command.
_PROJECT_SUBDIRS = (
    "source", "assets", "output",
    ".orchestrator/instructions", ".orchestrator/feedback",
    ".orchestrator/history", ".orchestrator/modules",
)


class ScriptProjectStore:
    """Manage script-writing projects and their ``scriptgen/`` workspace."""

    def __init__(self, root: Path = DEFAULT_ROOT):
        self.root = Path(root)

    # --- paths -----------------------------------------------------------------
    def project_dir(self, slug: str) -> Path:
        return self.root / slug

    def scriptgen_dir(self, slug: str) -> Path:
        return self.project_dir(slug) / "scriptgen"

    def meta_path(self, slug: str) -> Path:
        return self.scriptgen_dir(slug) / "meta.json"

    def brief_path(self, slug: str) -> Path:
        return self.scriptgen_dir(slug) / "brief.md"

    def sources_dir(self, slug: str) -> Path:
        return self.scriptgen_dir(slug) / "sources"

    def sources_raw_dir(self, slug: str) -> Path:
        return self.sources_dir(slug) / "raw"

    def sources_manifest_path(self, slug: str) -> Path:
        return self.sources_dir(slug) / "sources.md"

    def facts_path(self, slug: str) -> Path:
        return self.scriptgen_dir(slug) / "facts.md"

    def factcheck_path(self, slug: str) -> Path:
        return self.scriptgen_dir(slug) / "factcheck.md"

    def citations_path(self, slug: str) -> Path:
        return self.scriptgen_dir(slug) / "citations.md"

    def script_path(self, slug: str) -> Path:
        return self.project_dir(slug) / "script.md"

    def project_yaml_path(self, slug: str) -> Path:
        return self.project_dir(slug) / "project.yaml"

    # --- meta io ---------------------------------------------------------------
    def exists(self, slug: str) -> bool:
        return self.meta_path(slug).exists()

    def _load_meta(self, slug: str) -> Dict[str, Any]:
        p = self.meta_path(slug)
        if not p.exists():
            raise FileNotFoundError(f"script project not found: {slug}")
        return json.loads(p.read_text(encoding="utf-8"))

    def _save_meta(self, meta: Dict[str, Any]) -> None:
        p = self.meta_path(meta["slug"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- crud ------------------------------------------------------------------
    def create(self, name: str, *, subject: str, style_id: str,
               angle: str = "", pivot: str = "", target_minutes: float = 8.0,
               description: str = "") -> str:
        """Scaffold a Director-ready project + scriptgen workspace; return slug."""
        base = slugify(name or subject, "script")
        slug, n = base, 2
        while self.project_dir(slug).exists():
            slug = f"{base}-{n}"
            n += 1

        pdir = self.project_dir(slug)
        for sub in _PROJECT_SUBDIRS:
            (pdir / sub).mkdir(parents=True, exist_ok=True)
        self.sources_raw_dir(slug).mkdir(parents=True, exist_ok=True)

        display_name = name or subject
        # Director-ready project.yaml (same shape as `nolan projects init`).
        self.project_yaml_path(slug).write_text(
            yaml.safe_dump({
                "name": display_name,
                "slug": slug,
                "description": description or subject,
                "source_videos": ["source/"],
                "output_dir": "output/",
                "assets_dir": "assets/",
            }, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

        meta = {
            "slug": slug,
            "name": display_name,
            "subject": subject,
            "style_id": style_id,
            "angle": angle,
            "pivot": pivot,
            "target_minutes": float(target_minutes),
            "description": description or subject,
            "created_at": datetime.now().isoformat(),
            "status": "new",
            "sources": [],
        }
        self._save_meta(meta)
        self._write_brief(meta)
        self._write_sources_manifest(meta)
        # Placeholder so the project is Director-shaped before the agent writes.
        if not self.script_path(slug).exists():
            self.script_path(slug).write_text(
                "# Video Script\n\n**Total Duration:** _pending_\n\n---\n\n"
                "_Script not written yet. Run the writer to generate it._\n",
                encoding="utf-8")
        return slug

    def get(self, slug: str) -> Dict[str, Any]:
        m = self._load_meta(slug)
        m["source_count"] = len(m.get("sources", []))
        m["has_facts"] = self.facts_path(slug).exists()
        m["has_factcheck"] = self.factcheck_path(slug).exists()
        m["has_script"] = self._script_written(slug)
        return m

    def list(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if not self.root.exists():
            return out
        for d in sorted(self.root.iterdir()):
            if (d / "scriptgen" / "meta.json").exists():
                try:
                    out.append(self.get(d.name))
                except Exception:
                    continue
        out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return out

    def delete(self, slug: str) -> bool:
        d = self.project_dir(slug)
        if not d.exists():
            return False
        shutil.rmtree(d, ignore_errors=True)
        return True

    # --- sources ---------------------------------------------------------------
    def _next_source_id(self, meta: Dict[str, Any]) -> str:
        existing = {s["id"] for s in meta.get("sources", [])}
        n = 1
        while f"S{n}" in existing:
            n += 1
        return f"S{n}"

    def add_source(self, slug: str, *, kind: str, title: str = "",
                   url: Optional[str] = None, text: Optional[str] = None) -> Dict[str, Any]:
        """Add a source. ``kind`` ∈ {url, paste, file, reference}.

        If ``text`` is supplied (paste/file), it's saved to raw/ and marked
        ``fetched``. A bare ``url`` is recorded ``pending`` for the agent to
        fetch via WebFetch during the write step.
        """
        meta = self._load_meta(slug)
        sid = self._next_source_id(meta)
        entry: Dict[str, Any] = {
            "id": sid, "kind": kind, "title": title or url or kind,
            "url": url, "added_at": datetime.now().isoformat(),
        }
        if text:
            self.sources_raw_dir(slug).mkdir(parents=True, exist_ok=True)
            fname = f"{sid}-{slugify(title or url or 'source')[:40]}.md"
            (self.sources_raw_dir(slug) / fname).write_text(text, encoding="utf-8")
            entry["text_path"] = str(Path("sources") / "raw" / fname)
            entry["word_count"] = len(text.split())
            entry["status"] = "fetched"
        else:
            entry["status"] = "pending"  # agent will fetch the URL
        meta.setdefault("sources", []).append(entry)
        self._save_meta(meta)
        self._write_sources_manifest(meta)
        return entry

    def remove_source(self, slug: str, sid: str) -> bool:
        meta = self._load_meta(slug)
        sources = meta.get("sources", [])
        kept = [s for s in sources if s["id"] != sid]
        if len(kept) == len(sources):
            return False
        for s in sources:
            if s["id"] == sid and s.get("text_path"):
                (self.scriptgen_dir(slug) / s["text_path"]).unlink(missing_ok=True)
        meta["sources"] = kept
        self._save_meta(meta)
        self._write_sources_manifest(meta)
        return True

    def sources(self, slug: str) -> List[Dict[str, Any]]:
        return self._load_meta(slug).get("sources", [])

    # --- artifact access -------------------------------------------------------
    def read_script(self, slug: str) -> Optional[str]:
        p = self.script_path(slug)
        return p.read_text(encoding="utf-8") if p.exists() else None

    def _script_written(self, slug: str) -> bool:
        """True once the placeholder has been replaced by a real script."""
        p = self.script_path(slug)
        if not p.exists():
            return False
        return "Script not written yet" not in p.read_text(encoding="utf-8")

    def target_words(self, slug: str) -> int:
        return int(self._load_meta(slug).get("target_minutes", 8.0) * 150)

    def artifact_path(self, slug: str, name: str) -> Optional[Path]:
        return {
            "brief": self.brief_path(slug),
            "facts": self.facts_path(slug),
            "factcheck": self.factcheck_path(slug),
            "citations": self.citations_path(slug),
            "sources": self.sources_manifest_path(slug),
        }.get(name)

    def read_artifact(self, slug: str, name: str) -> Optional[str]:
        """Read a named scriptgen artifact (brief/facts/factcheck/citations/sources)."""
        p = self.artifact_path(slug, name)
        if p is None or not p.exists():
            return None
        return p.read_text(encoding="utf-8")

    def read_source_text(self, slug: str, sid: str) -> Optional[str]:
        """Read the fetched/pasted raw text for one source, if present."""
        for s in self.sources(slug):
            if s["id"] == sid and s.get("text_path"):
                p = self.scriptgen_dir(slug) / s["text_path"]
                return p.read_text(encoding="utf-8") if p.exists() else None
        return None

    # --- human-readable views --------------------------------------------------
    def _write_brief(self, meta: Dict[str, Any]) -> None:
        slug = meta["slug"]
        lines = [
            f"# Script Brief — {meta['name']}", "",
            f"- **Subject:** {meta['subject']}",
            f"- **Style:** `{meta['style_id']}` (narrative voice guide)",
            f"- **Angle:** {meta.get('angle') or '_(none — writer chooses)_'}",
            f"- **Hidden-detail pivot:** {meta.get('pivot') or '_(none specified)_'}",
            f"- **Target length:** ~{meta.get('target_minutes', 8)} min "
            f"(~{int(meta.get('target_minutes', 8) * 150)} words)",
            "",
            "_Edit this brief freely before running the writer._",
        ]
        self.brief_path(slug).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_sources_manifest(self, meta: Dict[str, Any]) -> None:
        slug = meta["slug"]
        lines = [f"# Sources — {meta['name']}", ""]
        if not meta.get("sources"):
            lines.append("_No sources yet._")
        for s in meta.get("sources", []):
            loc = s.get("text_path") or s.get("url") or ""
            lines.append(
                f"- **[{s['id']}]** ({s['kind']}, {s['status']}) "
                f"{s.get('title') or ''} — {loc}".rstrip())
        self.sources_manifest_path(slug).parent.mkdir(parents=True, exist_ok=True)
        self.sources_manifest_path(slug).write_text("\n".join(lines) + "\n", encoding="utf-8")
