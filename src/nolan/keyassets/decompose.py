"""DECOMPOSE — the global, top-down pass: a senior archival/research producer reads the WHOLE script
and lists the HERO assets the video is ABOUT (named people, orgs, logos, specific works/ads, places,
events, key clips) — NOT interchangeable beat b-roll (that's the acquisition engine's job).

Pure prompt/parse (unit-testable without an LLM); `decompose` is the injected async LLM call, same
shape as acquire.coverage.extract_entities / hyperframes.derive_asset_needs.
"""
from __future__ import annotations

import json
import re
from typing import List

from .registry import (DEFAULT_ASSET_BY_KIND, collage_default, normalize_asset_type,
                       normalize_kind, normalize_priority, normalize_relevance)
from .schema import DesiredAsset, KeyEntity

_KINDS = "person | organization | place | event | work | concept"
_ATYPES = "portrait | logo | product | artwork | document | photo | map | footage"


def decompose_prompt(script: str) -> str:
    """One senior-editor pass over the full script → the typed hero pull-list."""
    return (
        "You are a SENIOR ARCHIVAL / RESEARCH PRODUCER for a documentary video essay. Read the WHOLE "
        "script and build the ASSET PULL-LIST: the specific, NAMED, irreplaceable things the film is "
        "ABOUT and the viewer expects to SEE — real people, companies + their LOGOS, specific "
        "works/ads/documents/objects, named places, and key historical moments (which may need "
        "archival FOOTAGE). This is the GLOBAL view: think about the whole film at once, not line by "
        "line. EXCLUDE generic, interchangeable b-roll (a stock 'diamond ring', 'a city street') and "
        "pure abstractions — those are handled elsewhere. Prefer FEW, high-value HERO items over many.\n\n"
        "For EACH subject return an object:\n"
        '  "name": short specific name (e.g. "De Beers", "Ernest Oppenheimer", "A Diamond Is Forever ad")\n'
        f'  "kind": one of [{_KINDS}]\n'
        '  "priority": "hero" (load-bearing, recurs / anchors a section) or "supporting"\n'
        '  "narrative_role": <=15 words on why the film needs to SEE it\n'
        '  "mentions": 1-3 SHORT verbatim spoken phrases from the script near where it appears '
        "(for syncing the visual to the words later)\n"
        f'  "desired_assets": 1-3 of {{"type": one of [{_ATYPES}], "note": what specifically '
        '(e.g. "official monochrome logo", "portrait, older"), "collage_ready": true if it should be '
        "cut out (transparent) for a collage — logos, product shots, a person cut from a background}}\n\n"
        "Return ONLY a JSON array (no prose, no code fences), most important first, up to 30 items.\n\n"
        "SCRIPT:\n" + (script or "")[:12000])


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


def _slug(name: str, taken: set) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")[:32] or "entity"
    sid = f"ka_{base}"
    n = sid
    k = 2
    while n in taken:
        n = f"{sid}_{k}"
        k += 1
    taken.add(n)
    return n


def parse_entities(raw: str, k: int = 30) -> List[KeyEntity]:
    """Normalize the LLM array into validated KeyEntity objects: kinds/asset-types coerced to the
    registry, priorities normalized, deduped by lowercased name, a stable id assigned, and an entity
    with no desired_assets gets its kind's default representation (so nothing is un-resolvable)."""
    out: List[KeyEntity] = []
    seen_names: set = set()
    taken_ids: set = set()
    for it in _extract_json_list(raw)[:k]:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name", "")).strip()
        if not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())
        kind = normalize_kind(str(it.get("kind", "")))
        assets = []
        for a in (it.get("desired_assets") or []):
            if not isinstance(a, dict):
                continue
            at = normalize_asset_type(str(a.get("type", "")))
            cr = bool(a.get("collage_ready")) or collage_default(at)
            rel = normalize_relevance(str(a.get("relevance", "exact")))
            assets.append(DesiredAsset(type=at, note=str(a.get("note", "")).strip(),
                                       collage_ready=cr, relevance=rel))
        if not assets:                              # never leave an entity un-depictable
            at = DEFAULT_ASSET_BY_KIND.get(kind, "photo")
            assets.append(DesiredAsset(type=at, note="", collage_ready=collage_default(at)))
        out.append(KeyEntity(
            id=_slug(name, taken_ids), name=name, kind=kind,
            narrative_role=str(it.get("narrative_role", "")).strip(),
            priority=normalize_priority(str(it.get("priority", "supporting"))),
            mentions=[str(m).strip() for m in (it.get("mentions") or []) if str(m).strip()][:3],
            desired_assets=assets))
    return out


async def decompose(script: str, client, k: int = 30) -> List[KeyEntity]:
    """LLM: full script -> validated hero pull-list. `client` is a create_text_llm."""
    raw = await client.generate((script or "")[:12000], system_prompt=decompose_prompt(script))
    return parse_entities(raw, k=k)
