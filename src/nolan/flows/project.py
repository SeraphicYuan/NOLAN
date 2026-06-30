"""Project-owned flow spec — the persistent, beat-addressable artifact (Phase 1).

A flow video lives in its project as `projects/<slug>/flow.spec.json`, which self-declares
its `flow` id and holds the per-beat plan (block/props/focuses/reveal anchors). This one
artifact is the shared object for BOTH human-in-the-loop stages — authoring mode (plan-time)
and the Scene page (render-time) — so an edit at either stage is an edit to the same file.
See web-video-lab/flows/EDITOR.md.
"""
from __future__ import annotations

import json
from pathlib import Path

SPEC_NAME = "flow.spec.json"


def flow_spec_path(project) -> Path:
    return Path(project) / SPEC_NAME


def is_flow_project(project) -> bool:
    return flow_spec_path(project).exists()


def load_flow_spec(project):
    """Resolve a project's flow + its project-owned spec.

    Returns (Flow, spec_path). Raises if the project isn't a flow project or the spec
    doesn't name a flow.
    """
    sp = flow_spec_path(project)
    if not sp.exists():
        raise FileNotFoundError(f"{Path(project).name} has no {SPEC_NAME} — not a flow project")
    spec = json.loads(sp.read_text(encoding="utf-8"))
    flow_id = spec.get("flow")
    if not flow_id:
        raise ValueError(f"{sp} is missing a 'flow' id")
    from . import get_flow
    return get_flow(flow_id), sp
