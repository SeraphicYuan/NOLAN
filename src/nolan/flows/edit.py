"""Flow beat editing (Phase 3, Gate B) — apply a human edit to one beat, re-ingest.

Edits write to the project-owned `flow.spec.json` (the source of truth); the caller then
re-renders just that beat (`iterate.rerender_scenes(['beat_NN'])`). This backs the Scene
page's edit panel + asset tray for flow projects. See web-video-lab/flows/EDITOR.md.
"""
from __future__ import annotations

import json
from pathlib import Path


def _deep_merge(dst: dict, patch: dict) -> dict:
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def reingest_job(project) -> Path:
    """Regenerate flow.job.json from the (edited) flow.spec.json via the flow's ingest."""
    from .project import load_flow_spec
    flow, spec_path = load_flow_spec(project)
    job = Path(project) / "flow.job.json"
    flow.ingest(spec_path, job)
    return job


def patch_beat(project, i: int, patch: dict, *, reingest: bool = True) -> dict:
    """Deep-merge `patch` into beats[i] of flow.spec.json. Returns the updated beat.

    e.g. patch_beat(p, 0, {"label": {"title": "New title"}})
         patch_beat(p, 5, {"block": "ImageCompare"})        # swap the motion (palette-checked at the gate)
    """
    project = Path(project)
    sp = project / "flow.spec.json"
    spec = json.loads(sp.read_text(encoding="utf-8"))
    _deep_merge(spec["beats"][i], patch)
    sp.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    if reingest:
        reingest_job(project)
    return spec["beats"][i]


def set_beat_asset(project, i: int, src: str, *, key: str = "src") -> dict:
    """Tray bind — point a beat's image prop at an asset (ArtworkStage/DetailLoupe `src`)."""
    return patch_beat(project, i, {key: src})


def patch_focus(project, i: int, j: int, changes: dict, *, reingest: bool = True) -> dict:
    """Sub-beat edit (Phase 4) — update one focus within a beat (the 'segment within a beat').

    A focus is beats[i].focuses[j] = {word, x, y, w, h, caption} — one spotlight/callout in an
    ArtworkStage tour. Edits its region/caption independently of the rest of the beat.
    e.g. patch_focus(p, 4, 2, {"x": 0.30, "w": 0.30, "caption": "Death, closer"})
    """
    project = Path(project)
    sp = project / "flow.spec.json"
    spec = json.loads(sp.read_text(encoding="utf-8"))
    foc = spec["beats"][i].get("focuses") or []
    if j >= len(foc):
        raise IndexError(f"beat {i} has {len(foc)} focuses; no focus {j}")
    _deep_merge(foc[j], changes)
    sp.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    if reingest:
        reingest_job(project)
    return foc[j]
