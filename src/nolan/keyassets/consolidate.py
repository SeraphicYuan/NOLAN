"""CONSOLIDATE — cluster correlated entities into a few RESEARCH DIRECTIONS so one greedy research
pass fulfills many. The efficiency idea the director called for: De Beers + Rhodes + Oppenheimer +
the 1947 ad + Kimberley are ONE "De Beers cartel" direction, not five separate researches — and each
direction carries seed `queries` we harvest greedily in P2.

Pure prompt/parse (testable); `consolidate` is the injected async LLM call. Every entity is guaranteed
a direction — orphans the LLM drops are swept into a per-entity fallback direction (no entity lost).
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Tuple

from .schema import KeyEntity, ResearchDirection


def consolidate_prompt(entities: List[KeyEntity]) -> str:
    """Given the pull-list, group correlated entities into research directions with seed queries."""
    lines = [f'- {e.id} | {e.name} ({e.kind}, {e.priority}) — {e.narrative_role}' for e in entities]
    return (
        "You are the RESEARCH LEAD planning how to gather a documentary's hero assets EFFICIENTLY. "
        "Below is the pull-list. Group entities that share a real-world subject, era, or event into a "
        "few RESEARCH DIRECTIONS — each direction is ONE research session that will surface assets + "
        "facts for ALL its entities at once (e.g. a company, its founders, its famous campaign, and "
        "its mine all belong to one direction). Aim for a SMALL number of directions (roughly one per "
        "distinct real-world subject cluster), each with 1-6 entities. Every entity id must appear in "
        "exactly one direction.\n\n"
        "For EACH direction return an object:\n"
        '  "id": short kebab slug (e.g. "de-beers-cartel")\n'
        '  "title": short human title\n'
        '  "entity_ids": [ids from the list that belong here]\n'
        '  "rationale": <=15 words on why they research together\n'
        '  "queries": 2-5 web-search queries that would surface the whole cluster\'s assets + history\n\n'
        "Return ONLY a JSON array (no prose, no code fences).\n\n"
        "PULL-LIST:\n" + "\n".join(lines))


def _extract_json_list(raw: str) -> List:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    i, j = raw.find("["), raw.rfind("]")
    if not (0 <= i < j):
        return []
    try:
        data = json.loads(raw[i:j + 1])
    except (json.JSONDecodeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _slug(title: str, taken: set) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")[:40] or "direction"
    n, k = base, 2
    while n in taken:
        n = f"{base}-{k}"
        k += 1
    taken.add(n)
    return n


def parse_directions(raw: str, entities: List[KeyEntity]) -> Tuple[List[ResearchDirection], List[KeyEntity]]:
    """Normalize directions, keep only real entity ids, and GUARANTEE coverage: any entity the LLM
    left out gets a solo fallback direction. Stamps each entity's `.direction`. Returns
    (directions, entities) with entities mutated in place for convenience."""
    by_id: Dict[str, KeyEntity] = {e.id: e for e in entities}
    assigned: set = set()
    taken_slugs: set = set()
    directions: List[ResearchDirection] = []
    for it in _extract_json_list(raw):
        if not isinstance(it, dict):
            continue
        ids = [str(x) for x in (it.get("entity_ids") or []) if str(x) in by_id and str(x) not in assigned]
        if not ids:
            continue
        did = _slug(str(it.get("id") or it.get("title") or "direction"), taken_slugs)
        directions.append(ResearchDirection(
            id=did, title=str(it.get("title", "")).strip() or did,
            entity_ids=ids, rationale=str(it.get("rationale", "")).strip(),
            queries=[str(q).strip() for q in (it.get("queries") or []) if str(q).strip()][:5]))
        for eid in ids:
            assigned.add(eid)
            by_id[eid].direction = did
    # sweep orphans (entities no direction claimed) into solo fallback directions — never lose one
    orphans = [e for e in entities if e.id not in assigned]
    for e in orphans:
        did = _slug(e.name, taken_slugs)
        directions.append(ResearchDirection(
            id=did, title=e.name, entity_ids=[e.id],
            rationale="(auto) uncorrelated with other subjects",
            queries=[e.name] + [f"{e.name} {a.type}" for a in e.desired_assets[:2]]))
        e.direction = did
    return directions, entities


async def consolidate(entities: List[KeyEntity], client) -> Tuple[List[ResearchDirection], List[KeyEntity]]:
    """LLM: pull-list -> research directions (with orphan sweep). `client` is a create_text_llm."""
    if not entities:
        return [], entities
    raw = await client.generate(consolidate_prompt(entities),
                                system_prompt="You plan efficient documentary research. Reply STRICT JSON only.")
    return parse_directions(raw, entities)
