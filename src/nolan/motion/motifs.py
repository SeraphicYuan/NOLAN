"""Motif layer — stateful infographics that ACCUMULATE across a video.

The reference-video "home base" device (quality program step 5): the Samurai-
in-Venice essay returns to ONE timeline six times, each return adding a
marker — the viewer watches understanding accumulate. NOLAN scenes are
designed independently, so nothing could build. Motifs fix that:

- ``scene_plan.json`` carries a top-level ``motifs`` list (lossless via
  ScenePlan.meta)::

      {"id": "greek-eras", "effect": "timeline",
       "base": {"title": "…", "start": -800, "end": 1950, "eras": [...]}}

- a scene references it with a DELTA::

      scene["motif"] = {"id": "greek-eras",
                        "delta": {"markers": [{"year": -750, "label": "…"}],
                                  "focus": {"from": -800, "to": -700}}}

- at render, :func:`resolve_plan_motifs` materializes each referencing scene's
  ``motion_spec``: base + every EARLIER delta (accumulated, rendered settled)
  + this scene's delta stamped ``isNew`` (only the delta animates). The plan
  on disk keeps the motif authoring — materialization is in-memory.

Only effects registered here may be motifs: they must render accumulated
items statically and animate ``isNew`` ones (the comp contract).
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

# effect id -> which content keys accumulate (list-append across deltas) and
# which are per-scene (taken from THIS delta only, else base).
STATEFUL_EFFECTS: Dict[str, Dict[str, Any]] = {
    "timeline": {"accumulate": ["markers"], "per_scene": ["focus", "title"]},
    "route-map": {"accumulate": ["pins"], "per_scene": ["title"]},
}


def _motif_index(plan: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for m in plan.get("motifs") or []:
        if isinstance(m, dict) and m.get("id"):
            out[str(m["id"])] = m
    return out


def _iter_scenes(plan: Dict[str, Any]):
    for scenes in (plan.get("sections") or {}).values():
        if isinstance(scenes, list):
            for s in scenes:
                if isinstance(s, dict):
                    yield s


def validate_plan_motifs(plan: Dict[str, Any]) -> List[str]:
    """Loud validation (the motion_design gate calls this): unknown motif ids,
    non-stateful effects, malformed deltas — each error names its scene."""
    from nolan.motion.registry import BY_ID

    errors: List[str] = []
    motifs = _motif_index(plan)
    for mid, m in motifs.items():
        eff = m.get("effect")
        if eff not in STATEFUL_EFFECTS:
            errors.append(f"motif {mid!r}: effect {eff!r} is not stateful "
                          f"(allowed: {sorted(STATEFUL_EFFECTS)})")
        elif eff not in BY_ID:
            errors.append(f"motif {mid!r}: effect {eff!r} not in the motion registry")
        if not isinstance(m.get("base"), dict):
            errors.append(f"motif {mid!r}: missing base content")
    for s in _iter_scenes(plan):
        ref = s.get("motif")
        if not ref:
            continue
        sid = s.get("id", "?")
        if not isinstance(ref, dict) or not ref.get("id"):
            errors.append(f"{sid}: motif reference must be {{id, delta}}")
            continue
        if str(ref["id"]) not in motifs:
            errors.append(f"{sid}: unknown motif id {ref['id']!r}")
            continue
        delta = ref.get("delta")
        if delta is not None and not isinstance(delta, dict):
            errors.append(f"{sid}: motif delta must be an object")
    return errors


def build_motif_content(motif: Dict[str, Any],
                        deltas_before: List[Dict[str, Any]],
                        delta_now: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Base + accumulated earlier deltas (settled) + this delta (isNew)."""
    rules = STATEFUL_EFFECTS[motif["effect"]]
    content = copy.deepcopy(motif.get("base") or {})
    for key in rules["accumulate"]:
        items = list(content.get(key) or [])
        for d in deltas_before:
            items.extend(copy.deepcopy(d.get(key) or []))
        for it in items:
            if isinstance(it, dict):
                it.pop("isNew", None)
        if delta_now:
            for it in copy.deepcopy(delta_now.get(key) or []):
                if isinstance(it, dict):
                    it["isNew"] = True
                items.append(it)
        content[key] = items
    for key in rules["per_scene"]:
        if delta_now and key in delta_now:
            content[key] = copy.deepcopy(delta_now[key])
    return content


def resolve_plan_motifs(plan: Dict[str, Any]) -> int:
    """Materialize motif references into per-scene motion_specs, IN MEMORY.

    Walks scenes in plan order (accumulation order = appearance order).
    A scene that already carries an explicit motion_spec keeps it (loudly
    unusual, but explicit beats derived). Returns the number of scenes
    materialized. Callers must NOT save the plan afterwards — the motif
    authoring, not the expansion, is the artifact.
    """
    from nolan.motion.registry import BY_ID

    motifs = _motif_index(plan)
    if not motifs:
        return 0
    seen: Dict[str, List[Dict[str, Any]]] = {mid: [] for mid in motifs}
    done = 0
    for s in _iter_scenes(plan):
        ref = s.get("motif")
        if not (isinstance(ref, dict) and str(ref.get("id")) in motifs):
            continue
        mid = str(ref["id"])
        motif = motifs[mid]
        delta = ref.get("delta") if isinstance(ref.get("delta"), dict) else None
        if s.get("motion_spec"):
            seen[mid].append(delta or {})
            continue
        content = build_motif_content(motif, seen[mid], delta)
        spec = BY_ID.get(motif["effect"])
        s["motion_spec"] = {
            "effect": motif["effect"],
            "backend": getattr(spec, "backend", "remotion"),
            "target": getattr(spec, "target", None),
            "content": content,
            "_from_motif": mid,          # provenance (in-memory only)
        }
        seen[mid].append(delta or {})
        done += 1
    return done
