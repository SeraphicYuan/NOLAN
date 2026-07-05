"""Per-project asset shortlist — the curation pool that bridges the picture and
clip libraries to an essay's scenes.

Persisted as ``projects/<slug>/shortlist.json``. Each item is stored in the exact
shape the ``/scenes`` asset picker already consumes, so "send to essay" needs no
translation: every item carries a ready-to-POST ``payload`` for
``POST /api/scenes/scene/assets`` (``op:"add"``).

Item schema::

    {
      "key":    "img:123:global" | "clip:<video>@<start>",   # dedup identity
      "kind":   "image" | "clip",
      "label":  "…",
      "thumb":  "/api/images/raw?…" | "/api/scenes/frame-thumb?…",
      "payload": { "op": "add", "source": "library"|"clip", … },
      "added_at": <unix seconds>
    }

The store is deliberately tiny (a JSON list behind a project dir) — the pool is
per-project curation state, not indexed data, so it lives next to the project's
other plain-file artifacts (scene_plan.json, project.yaml).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Dict, Any

FILENAME = "shortlist.json"


def _path(project_dir: Path) -> Path:
    return Path(project_dir) / FILENAME


def load(project_dir: Path) -> List[Dict[str, Any]]:
    """Return the project's shortlist items (empty list if none / unreadable)."""
    p = _path(project_dir)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    items = data.get("items") if isinstance(data, dict) else data
    return items if isinstance(items, list) else []


def save(project_dir: Path, items: List[Dict[str, Any]]) -> None:
    _path(project_dir).write_text(
        json.dumps({"items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add(project_dir: Path, new_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Append items, de-duplicating on ``key``. Returns the full updated list."""
    items = load(project_dir)
    seen = {it.get("key") for it in items if it.get("key")}
    for it in new_items:
        if not isinstance(it, dict):
            continue
        key = it.get("key")
        if key and key in seen:
            continue
        it.setdefault("added_at", int(time.time()))
        items.append(it)
        if key:
            seen.add(key)
    save(project_dir, items)
    return items


def remove(project_dir: Path, keys: List[str]) -> List[Dict[str, Any]]:
    """Drop items whose ``key`` is in ``keys``. Returns the updated list."""
    drop = set(keys or [])
    items = [it for it in load(project_dir) if it.get("key") not in drop]
    save(project_dir, items)
    return items


def clear(project_dir: Path) -> None:
    save(project_dir, [])
