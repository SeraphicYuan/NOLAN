"""Template matcher for style and scene-plan template databases.

v1: deterministic file-based scoring. Reads `meta.json` from each template
directory and scores against a project context (genre, duration, free-text
description). ChromaDB upgrade deferred until library outgrows the simple
scorer.

See docs/plans/2026-04-26-two-layer-orchestrator.md §10 for the design.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


TemplateKind = Literal["style", "scene_plan"]


@dataclass
class TemplateCandidate:
    template_id: str
    version: int
    name: str
    kind: TemplateKind
    score: float
    score_breakdown: dict[str, float]
    template_dir: Path
    summary: str

    def template_md_path(self) -> Path:
        return self.template_dir / "template.md"

    def skeleton_path(self) -> Path | None:
        path = self.template_dir / "skeleton.json"
        return path if path.exists() else None


def _templates_root(kind: TemplateKind, repo_root: Path) -> Path:
    subdir = "styles" if kind == "style" else "scene_plans"
    return repo_root / "assets" / "templates" / subdir


def _load_meta(template_dir: Path) -> dict | None:
    meta_path = template_dir / "meta.json"
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _score_candidate(
    meta: dict,
    project_genre: str | None,
    duration_seconds: int | None,
    free_text: str,
) -> tuple[float, dict[str, float]]:
    breakdown: dict[str, float] = {}

    genres = [g.lower() for g in meta.get("genres", [])]
    if project_genre and project_genre.lower() in genres:
        breakdown["genre_exact"] = 0.4
    elif project_genre:
        breakdown["genre_miss"] = 0.0
    else:
        breakdown["genre_unknown"] = 0.15

    duration_range = meta.get("duration_range", [0, 0])
    if duration_seconds and len(duration_range) == 2:
        lo, hi = duration_range
        if lo <= duration_seconds <= hi:
            breakdown["duration_in_range"] = 0.2
        else:
            distance = min(abs(duration_seconds - lo), abs(duration_seconds - hi))
            penalty = max(0.0, 0.2 - 0.001 * distance)
            breakdown["duration_partial"] = penalty
    else:
        breakdown["duration_unknown"] = 0.1

    tags = [t.lower() for t in meta.get("tags", [])]
    summary = meta.get("summary", "").lower()
    free_lower = free_text.lower()
    free_tokens = set(re.findall(r"[a-z]{4,}", free_lower))
    tag_hits = sum(1 for t in tags if any(tok in t for tok in free_tokens))
    summary_hits = sum(1 for tok in free_tokens if tok in summary)
    text_score = min(0.4, 0.05 * tag_hits + 0.02 * summary_hits)
    breakdown["text_overlap"] = text_score

    return sum(breakdown.values()), breakdown


def match_templates(
    kind: TemplateKind,
    project_genre: str | None,
    duration_seconds: int | None,
    free_text: str,
    repo_root: Path,
    top_k: int = 3,
) -> list[TemplateCandidate]:
    """Score every template of `kind` against the project context.

    Returns top-K candidates sorted by score descending. Empty list if no
    templates exist on disk.
    """
    root = _templates_root(kind, repo_root)
    if not root.exists():
        return []

    candidates: list[TemplateCandidate] = []
    for template_dir in sorted(root.iterdir()):
        if not template_dir.is_dir():
            continue
        meta = _load_meta(template_dir)
        if not meta:
            continue
        if meta.get("kind") != kind:
            continue
        score, breakdown = _score_candidate(
            meta, project_genre, duration_seconds, free_text
        )
        candidates.append(
            TemplateCandidate(
                template_id=meta["id"],
                version=meta.get("version", 1),
                name=meta.get("name", meta["id"]),
                kind=kind,
                score=score,
                score_breakdown=breakdown,
                template_dir=template_dir,
                summary=meta.get("summary", ""),
            )
        )

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:top_k]


def match_style_template(
    project_genre: str | None,
    duration_seconds: int | None,
    free_text: str,
    repo_root: Path,
    top_k: int = 3,
) -> list[TemplateCandidate]:
    return match_templates(
        "style", project_genre, duration_seconds, free_text, repo_root, top_k
    )


def match_scene_plan_template(
    project_genre: str | None,
    duration_seconds: int | None,
    free_text: str,
    repo_root: Path,
    top_k: int = 3,
) -> list[TemplateCandidate]:
    return match_templates(
        "scene_plan", project_genre, duration_seconds, free_text, repo_root, top_k
    )
