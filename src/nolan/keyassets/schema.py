"""Typed artifacts for the Key-Assets Anchored Pool.

The PROPOSAL (`key_assets.proposal.json`) is what P1 emits and the human reviews: the hero
pull-list (`entities`) grouped into `directions` (correlated entities researched together). P2
resolves each entity's `desired_assets` into files and a gate promotes it to canonical
`key_assets.json`. Pure dataclasses — no I/O beyond save/load — so decompose/consolidate stay testable.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class DesiredAsset:
    """One representation an entity needs on screen. `type` ∈ registry.ASSET_TYPES; `collage_ready`
    requests a background-removed cutout (logos, product shots, people cut for a collage). `relevance`
    is 'exact' (a specific named thing — THE 1947 ad) or 'related' (a directionally-relevant clip/photo
    that fits the era/mood — 1950s wedding footage — where an exact match isn't needed)."""
    type: str                                   # portrait|logo|product|artwork|document|photo|map|footage
    note: str = ""                              # what specifically (e.g. "official company logo, mono")
    collage_ready: bool = False
    relevance: str = "exact"                    # exact | related
    queries: List[str] = field(default_factory=list)  # LLM-generated image-search queries (querygen); editable

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "note": self.note, "collage_ready": self.collage_ready,
                "relevance": self.relevance, "queries": list(self.queries)}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DesiredAsset":
        return cls(type=str(d.get("type", "")), note=str(d.get("note", "")),
                   collage_ready=bool(d.get("collage_ready", False)),
                   relevance=str(d.get("relevance", "exact")),
                   queries=[str(q) for q in (d.get("queries") or [])])


@dataclass
class KeyEntity:
    """A hero/supporting subject the video is ABOUT — named + irreplaceable, unlike beat b-roll."""
    id: str
    name: str
    kind: str                                   # registry.ENTITY_KINDS
    narrative_role: str = ""                    # why it matters to the story
    priority: str = "supporting"               # hero|supporting
    mentions: List[str] = field(default_factory=list)     # short spoken phrases → sync anchors later
    desired_assets: List[DesiredAsset] = field(default_factory=list)
    direction: str = ""                         # research-direction id (filled by consolidate)
    identifiers: List[str] = field(default_factory=list)  # disambiguating terms (role/affiliation/era) — querygen;
    #                                             reused for the verify subject + Tier-C reformulation
    queries_locked: bool = False                # a human edited the queries → never auto-regenerate

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["desired_assets"] = [a.to_dict() for a in self.desired_assets]
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "KeyEntity":
        return cls(id=str(d.get("id", "")), name=str(d.get("name", "")), kind=str(d.get("kind", "")),
                   narrative_role=str(d.get("narrative_role", "")),
                   priority=str(d.get("priority", "supporting")),
                   mentions=[str(m) for m in (d.get("mentions") or [])],
                   desired_assets=[DesiredAsset.from_dict(a) for a in (d.get("desired_assets") or [])],
                   direction=str(d.get("direction", "")),
                   identifiers=[str(x) for x in (d.get("identifiers") or [])],
                   queries_locked=bool(d.get("queries_locked", False)))


@dataclass
class ResearchDirection:
    """A cluster of correlated entities researched TOGETHER in one greedy pass (P2). `queries` seed
    the web search. The key efficiency idea: De Beers + Rhodes + Oppenheimer + the 1947 ad are ONE
    direction, not four researches."""
    id: str
    title: str
    entity_ids: List[str] = field(default_factory=list)
    rationale: str = ""
    queries: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ResearchDirection":
        return cls(id=str(d.get("id", "")), title=str(d.get("title", "")),
                   entity_ids=[str(e) for e in (d.get("entity_ids") or [])],
                   rationale=str(d.get("rationale", "")),
                   queries=[str(q) for q in (d.get("queries") or [])])


@dataclass
class KeyAssetsProposal:
    """The reviewable pull-list. Persisted to `key_assets.proposal.json`; a human edits it before P2."""
    comp: str = ""
    entities: List[KeyEntity] = field(default_factory=list)
    directions: List[ResearchDirection] = field(default_factory=list)
    generated: str = ""                         # date stamp (caller fills — Date.now is unavailable in workflows)

    def to_dict(self) -> Dict[str, Any]:
        return {"comp": self.comp, "generated": self.generated,
                "entities": [e.to_dict() for e in self.entities],
                "directions": [d.to_dict() for d in self.directions]}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "KeyAssetsProposal":
        return cls(comp=str(d.get("comp", "")), generated=str(d.get("generated", "")),
                   entities=[KeyEntity.from_dict(e) for e in (d.get("entities") or [])],
                   directions=[ResearchDirection.from_dict(x) for x in (d.get("directions") or [])])

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> Optional["KeyAssetsProposal"]:
        p = Path(path)
        if not p.exists():
            return None
        try:
            return cls.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return None
