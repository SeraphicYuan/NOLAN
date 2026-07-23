"""Video flows — a flow is a DESCRIPTOR over one shared engine, not a second pipeline.

LEGACY (as of 2026-07): these art/explainer flows render via `remotion-lib` (Remotion) and are
SUPERSEDED by the dominant compose-first HyperFrames pipeline (GSAP) — see the `pipeline.hyperframes`
skill. The `explainer.*` / `art.*` / `flow.*` skill docs are deprecated. Kept for legacy projects.

art, explainer, … all share the job-JSON contract, the QA gate structure, the
`remotion-lib` render engine, and the 39-block library. A `Flow` carries only the parts
that genuinely differ: the ingest adapter (code), and the profile/palette/defaults (config
from web-video-lab/flows/registry.json). See web-video-lab/flows/INTEGRATION.md.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "web-video-lab" / "flows" / "registry.json"


@dataclass
class Flow:
    id: str
    ingest: Callable                          # (spec_path, job_path) -> None  (writes job.json)
    profile: str                              # pacing/palette/defaults key in registry.json
    palette: list = field(default_factory=list)
    defaults: dict = field(default_factory=dict)
    render_mechanism: str = "chapter-block"   # how a beat (re)renders — shared across flow types


def _registry_type(flow_id: str) -> dict | None:
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return next((t for t in reg.get("types", []) if t["id"] == flow_id), None)


def get_flow(flow_id: str) -> Flow:
    """Build a Flow from its tenant module (ingest adapter) + registry.json (config)."""
    from . import art, explainer
    tenants = {"art": art.INGEST, "explainer": explainer.INGEST}
    if flow_id not in tenants:
        raise ValueError(f"no flow tenant for '{flow_id}' (have: {sorted(tenants)})")
    t = _registry_type(flow_id) or {}
    return Flow(id=flow_id, ingest=tenants[flow_id], profile=flow_id,
                palette=t.get("palette", []), defaults=t.get("defaults", {}),
                render_mechanism=t.get("render_mechanism", "chapter-block"))
