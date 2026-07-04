"""File-backed store for video deconstructions.

One directory per deconstructed video under ``video_deconstructions/``:

    video_deconstructions/<slug>/
    ├── meta.json            # video_path, slug, title, created_at, status
    ├── extract.json         # facts + beats + operators + tempo (Tier 2 output)
    ├── recovered_plan.json  # draft scene_plan (deterministic; agent refines)
    ├── synthesis_task.md    # agent brief
    ├── breakdown.md         # agent-written editorial breakdown
    └── frames/beat_NN.jpg   # one representative frame per beat (agent evidence)

Same file-first philosophy as ScriptStyleStore / VideoStyleStore: everything
human- and agent-readable.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from nolan.video_style.store import slugify

DEFAULT_ROOT = Path("video_deconstructions")


class DeconstructionStore:
    def __init__(self, root: Path = DEFAULT_ROOT):
        self.root = Path(root)

    # --- paths ---------------------------------------------------------
    def dir(self, slug: str) -> Path:
        return self.root / slug

    def meta_path(self, slug: str) -> Path:
        return self.dir(slug) / "meta.json"

    def extract_path(self, slug: str) -> Path:
        return self.dir(slug) / "extract.json"

    def plan_path(self, slug: str) -> Path:
        return self.dir(slug) / "recovered_plan.json"

    def task_path(self, slug: str) -> Path:
        return self.dir(slug) / "synthesis_task.md"

    def breakdown_path(self, slug: str) -> Path:
        return self.dir(slug) / "breakdown.md"

    def frames_dir(self, slug: str) -> Path:
        return self.dir(slug) / "frames"

    # --- lifecycle -----------------------------------------------------
    def slug_for(self, video_path: str) -> str:
        return slugify(Path(video_path).stem)

    def create(self, video_path: str, title: str = "") -> str:
        slug = self.slug_for(video_path)
        d = self.dir(slug)
        d.mkdir(parents=True, exist_ok=True)
        self.frames_dir(slug).mkdir(exist_ok=True)
        meta = self.get(slug) or {}
        meta.update({
            "slug": slug,
            "video_path": str(video_path),
            "title": title or Path(video_path).stem,
            "created_at": meta.get("created_at") or datetime.now().isoformat(),
            "status": "new",
        })
        self._save_meta(slug, meta)
        return slug

    def exists(self, slug: str) -> bool:
        return self.meta_path(slug).exists()

    def get(self, slug: str) -> Optional[Dict[str, Any]]:
        p = self.meta_path(slug)
        if not p.exists():
            return None
        meta = json.loads(p.read_text(encoding="utf-8"))
        meta["has_extract"] = self.extract_path(slug).exists()
        meta["has_plan"] = self.plan_path(slug).exists()
        meta["has_breakdown"] = self.breakdown_path(slug).exists()
        return meta

    def list(self) -> List[Dict[str, Any]]:
        out = []
        if not self.root.exists():
            return out
        for d in sorted(self.root.iterdir()):
            if (d / "meta.json").exists():
                m = self.get(d.name)
                if m:
                    out.append(m)
        out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return out

    def delete(self, slug: str) -> bool:
        import shutil
        d = self.dir(slug)
        if not d.exists():
            return False
        shutil.rmtree(d, ignore_errors=True)
        return True

    def set_status(self, slug: str, status: str) -> None:
        meta = self.get(slug)
        if meta:
            meta["status"] = status
            self._save_meta(slug, meta)

    def _save_meta(self, slug: str, meta: Dict[str, Any]) -> None:
        clean = {k: v for k, v in meta.items()
                 if k not in ("has_extract", "has_plan", "has_breakdown")}
        self.meta_path(slug).write_text(
            json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- artifacts -----------------------------------------------------
    def write_extract(self, slug: str, extract: Dict[str, Any]) -> None:
        self.extract_path(slug).write_text(
            json.dumps(extract, indent=2, ensure_ascii=False), encoding="utf-8")

    def read_extract(self, slug: str) -> Optional[Dict[str, Any]]:
        p = self.extract_path(slug)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def write_plan(self, slug: str, plan: Dict[str, Any]) -> None:
        self.plan_path(slug).write_text(
            json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")

    def read_text(self, slug: str, name: str) -> Optional[str]:
        p = {"breakdown": self.breakdown_path(slug),
             "task": self.task_path(slug),
             "plan": self.plan_path(slug),
             "extract": self.extract_path(slug)}.get(name)
        if p is None or not p.exists():
            return None
        return p.read_text(encoding="utf-8")
