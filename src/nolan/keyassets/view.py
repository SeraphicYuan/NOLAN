"""build_view — the /keyassets page payload: the hero pull-list (plan) + any collected assets.

Reads the canonical `key_assets.json` (P2 output, with resolved files) if present, else the
`key_assets.proposal.json` (P1 plan). Groups entities by research direction (hero-first) and attaches
any collected media found under `capture/keyassets/` (matched to an entity by id-prefix in the
filename). Pure read — the route serves it as JSON, the page renders it client-side (mirrors
asset_pool.build_pool feeding /pool)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from .schema import KeyAssetsProposal


def _resolved_records(project_dir: Path) -> Dict[str, List[dict]]:
    """entity_id -> collected-asset records from canonical key_assets.json (file/variant/verified/
    `selected`/source/type), only for files that still exist. `selected` = in the FINAL pool (default
    True for older data without the flag)."""
    p = project_dir / "key_assets.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out: Dict[str, List[dict]] = {}
    for e in data.get("entities", []):
        recs = []
        for a in e.get("resolved", []) or []:
            f = a.get("file")
            if not f or not (project_dir / f).exists():
                continue
            recs.append({"file": f, "variant": a.get("variant", "original"), "type": a.get("type", ""),
                         "verified": bool(a.get("verified")), "selected": bool(a.get("selected", True)),
                         "source": a.get("source", "")})
        if recs and e.get("id"):
            out[e["id"]] = recs
    return out


def build_view(project_dir: Path) -> dict:
    project_dir = Path(project_dir)
    canonical = project_dir / "key_assets.json"
    proposal = project_dir / "key_assets.proposal.json"
    src = canonical if canonical.exists() else proposal
    prop = KeyAssetsProposal.load(src) if src.exists() else None
    if prop is None:
        return {"has_proposal": False, "project": project_dir.name}

    resolved = _resolved_records(project_dir)
    by_id = {e.id: e for e in prop.entities}
    directions = []
    for d in prop.directions:
        ents = [by_id[i] for i in d.entity_ids if i in by_id]
        ents.sort(key=lambda e: (e.priority != "hero", e.name.lower()))
        directions.append({
            "id": d.id, "title": d.title, "rationale": d.rationale, "queries": d.queries,
            "entities": [{
                "id": e.id, "name": e.name, "kind": e.kind, "priority": e.priority,
                "narrative_role": e.narrative_role, "mentions": e.mentions,
                "identifiers": e.identifiers, "queries_locked": e.queries_locked,
                "assets": [a.to_dict() for a in e.desired_assets],   # a.to_dict() carries `queries`
                "collected": resolved.get(e.id, []),                 # objects: file/variant/verified/selected
            } for e in ents],
        })
    all_recs = [r for v in resolved.values() for r in v]
    from .inventory import hero_coverage
    coverage = hero_coverage(project_dir)              # soft: which selected heroes the author actually placed
    stats = {
        "entities": len(prop.entities),
        "hero": sum(1 for e in prop.entities if e.priority == "hero"),
        "directions": len(prop.directions),
        "footage": sum(1 for e in prop.entities for a in e.desired_assets if a.type == "footage"),
        "related": sum(1 for e in prop.entities for a in e.desired_assets if a.relevance == "related"),
        "collected": len(all_recs),
        "selected": sum(1 for r in all_recs if r["selected"]),
    }
    return {"has_proposal": True, "project": project_dir.name, "canonical": canonical.exists(),
            "generated": prop.generated, "stats": stats, "directions": directions, "coverage": coverage}
