"""Unified project model (C1).

A single slug-keyed view of NOLAN projects under ``projects/``, with capability
flags derived from marker files — replacing the per-page ad-hoc scans (scenes,
script-projects, agents, library) that each recognised a project by a different
marker and never linked the filesystem to the index DB.

See docs/PROJECT_MODEL_DESIGN.md. This module is additive: discovery here mirrors
the legacy ``hub.scan_projects`` naming (slug = path relative to the root, with the
root itself named by its dir) so it can back the existing endpoints unchanged.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

DEFAULT_ROOT = Path("projects")
MAX_DEPTH = 3

# Sub-dirs that belong TO a project — never their own project, never recursed
# into as project candidates. (scriptgen/meta.json marks the *parent* as a project.)
_SKIP_DIRS = {
    "assets", "clips", "work", "output", "source", "frames", "voiceover",
    "vectors", "scriptgen", "imagelib", ".orchestrator", ".nolan",
    "node_modules", "__pycache__", ".git",
}


def _find_scene_plan(d: Path) -> Optional[Path]:
    for cand in (d / "scene_plan.json", d / "output" / "scene_plan.json"):
        if cand.exists():
            return cand
    return None


@dataclass
class Project:
    """One NOLAN project, identified by ``slug`` (path relative to the root)."""

    slug: str
    path: Path
    name: str
    has_scene_plan: bool = False
    has_script: bool = False
    has_scriptgen: bool = False
    has_orchestrator: bool = False
    has_segment: bool = False
    has_imagelib: bool = False
    has_article: bool = False
    scene_count: int = 0
    library_project_id: Optional[str] = None

    @property
    def kinds(self) -> List[str]:
        """Which workflows this project participates in (for display/filtering)."""
        k: List[str] = []
        if self.has_scriptgen or self.has_script:
            k.append("script")
        if self.has_scene_plan:
            k.append("scenes")
        if self.has_orchestrator:
            k.append("orchestrator")
        if self.has_segment:
            k.append("segment")
        if self.has_article:
            k.append("article")
        return k

    def to_dict(self) -> dict:
        d = asdict(self)
        d["path"] = str(self.path)
        d["kinds"] = self.kinds
        return d


def _markers(d: Path) -> dict:
    sp = _find_scene_plan(d)
    return {
        "scene_plan": sp,
        "has_scene_plan": sp is not None,
        "has_script": (d / "script.md").exists() or (d / "script.json").exists(),
        "has_scriptgen": (d / "scriptgen" / "meta.json").exists(),
        "has_orchestrator": (d / ".orchestrator").is_dir(),
        "has_segment": (d / "segment_meta.json").exists(),
        "has_imagelib": (d / "imagelib").is_dir(),
        "has_article": (d / "article" / "article.html").exists(),
        "has_yaml": (d / "project.yaml").exists(),
    }


def _is_project(m: dict) -> bool:
    return bool(
        m["has_scene_plan"] or m["has_script"] or m["has_scriptgen"]
        or m["has_orchestrator"] or m["has_segment"] or m["has_yaml"]
        or m["has_article"]
    )


def _scene_count(sp: Optional[Path]) -> int:
    if not sp:
        return 0
    try:
        data = json.loads(sp.read_text(encoding="utf-8"))
        return sum(len(v) for v in (data.get("sections") or {}).values())
    except Exception:
        return 0


def _name_for(d: Path, m: dict, slug: str) -> str:
    if m["has_yaml"]:
        try:
            import yaml
            y = yaml.safe_load((d / "project.yaml").read_text(encoding="utf-8")) or {}
            if y.get("name"):
                return str(y["name"])
        except Exception:
            pass
    return slug


def _build(base: Path, root: Path, m: dict, index=None) -> Project:
    rel = base.relative_to(root)
    slug = root.name if rel == Path(".") else rel.as_posix()
    library_id = None
    if index is not None:
        try:
            library_id = index.get_project_id_by_slug(slug)
        except Exception:
            library_id = None
    return Project(
        slug=slug, path=base, name=_name_for(base, m, slug),
        has_scene_plan=m["has_scene_plan"], has_script=m["has_script"],
        has_scriptgen=m["has_scriptgen"], has_orchestrator=m["has_orchestrator"],
        has_segment=m["has_segment"], has_imagelib=m["has_imagelib"],
        has_article=m["has_article"],
        scene_count=_scene_count(m["scene_plan"]), library_project_id=library_id,
    )


def _walk(base: Path, root: Path, out: List[Project], depth: int, max_depth: int, index) -> None:
    m = _markers(base)
    if _is_project(m):
        out.append(_build(base, root, m, index))
    if depth >= max_depth:
        return
    try:
        children = sorted(base.iterdir())
    except OSError:
        return
    for item in children:
        if item.is_dir() and item.name not in _SKIP_DIRS and not item.name.startswith("."):
            _walk(item, root, out, depth + 1, max_depth, index)


def discover_projects(root=DEFAULT_ROOT, index=None, max_depth: int = MAX_DEPTH) -> List[Project]:
    """Discover all projects under ``root`` with capability flags.

    Args:
        root: projects directory.
        index: optional VideoIndex — sets ``library_project_id`` by slug match.
        max_depth: recursion depth (mirrors legacy scan_projects = 3).
    """
    root = Path(root)
    out: List[Project] = []
    if not root.exists():
        return out
    _walk(root, root, out, 0, max_depth, index)
    return out


def get_project(slug: str, root=DEFAULT_ROOT, index=None) -> Optional[Project]:
    """Return the project with ``slug`` (path relative to root), or None."""
    for p in discover_projects(root, index=index):
        if p.slug == slug:
            return p
    return None


def link_db_project(index, project: "Project") -> Optional[str]:
    """Ensure an index-DB project row exists for an FS project; return its id.

    Idempotent: reuses an existing row matched by slug. This is the FS↔DB link
    that was missing (script/orchestrator creation never registered a DB project).
    """
    if index is None:
        return None
    existing = None
    try:
        existing = index.get_project_id_by_slug(project.slug)
    except Exception:
        existing = None
    if existing:
        return existing
    try:
        row = index.create_project(name=project.name, slug=project.slug,
                                   path=str(project.path))
        return row.get("id")
    except Exception:
        return None
