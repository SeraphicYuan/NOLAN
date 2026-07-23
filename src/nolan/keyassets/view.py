"""build_view — the /keyassets page payload: the hero pull-list (plan) + any collected assets.

Reads the canonical `key_assets.json` (P2 output, with resolved files) if present, else the
`key_assets.proposal.json` (P1 plan). Groups entities by research direction (hero-first) and attaches
any collected media found under `capture/keyassets/` (matched to an entity by id-prefix in the
filename). Pure read — the route serves it as JSON, the page renders it client-side (mirrors
asset_pool.build_pool feeding /pool)."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .schema import KeyAssetsProposal

_MEDIA_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".webm")


def _collected(project_dir: Path, entities) -> Dict[str, List[str]]:
    """entity_id -> [project-relative media paths] found under capture/keyassets/ (P2 fills this)."""
    ka_dir = project_dir / "capture" / "keyassets"
    out: Dict[str, List[str]] = {}
    if not ka_dir.exists():
        return out
    ids = sorted(((e.id or "").lower(), e.id) for e in entities if e.id)
    for p in sorted(ka_dir.rglob("*")):
        if not (p.is_file() and p.suffix.lower() in _MEDIA_EXT):
            continue
        rel = p.relative_to(project_dir).as_posix()
        stem = p.stem.lower()
        for low, real in ids:                        # longest id first so a prefix match is the tightest
            if low and stem.startswith(low):
                out.setdefault(real, []).append(rel)
                break
    return out


def build_view(project_dir: Path) -> dict:
    project_dir = Path(project_dir)
    canonical = project_dir / "key_assets.json"
    proposal = project_dir / "key_assets.proposal.json"
    src = canonical if canonical.exists() else proposal
    prop = KeyAssetsProposal.load(src) if src.exists() else None
    if prop is None:
        return {"has_proposal": False, "project": project_dir.name}

    collected = _collected(project_dir, prop.entities)
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
                "collected": collected.get(e.id, []),
            } for e in ents],
        })
    stats = {
        "entities": len(prop.entities),
        "hero": sum(1 for e in prop.entities if e.priority == "hero"),
        "directions": len(prop.directions),
        "footage": sum(1 for e in prop.entities for a in e.desired_assets if a.type == "footage"),
        "related": sum(1 for e in prop.entities for a in e.desired_assets if a.relevance == "related"),
        "collected": sum(len(v) for v in collected.values()),
    }
    return {"has_proposal": True, "project": project_dir.name, "canonical": canonical.exists(),
            "generated": prop.generated, "stats": stats, "directions": directions}
