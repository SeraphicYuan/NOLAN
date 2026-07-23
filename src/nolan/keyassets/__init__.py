"""Key-Assets Anchored Pool — the GLOBAL, top-down pre-acquisition stage.

A senior archival producer reads the whole script, decomposes it into the HERO assets the video is
ABOUT (named people/orgs/logos/works/places/events/clips), consolidates correlated ones into a few
GREEDY research directions, then (P2) researches, resolves, conditions, and gates them into a typed,
provenance-carrying anchored pool that authoring consumes FIRST. This package holds P1 (decompose +
consolidate → reviewable proposal); see docs/KEY_ASSETS_ANCHORED_POOL.md.
"""
from __future__ import annotations

from typing import List

from . import registry
from .collect import collect
from .consolidate import consolidate, consolidate_prompt, parse_directions
from .decompose import decompose, decompose_prompt, parse_entities
from .enrich import enrich, enrich_prompt, merge_entities
from .inventory import stage_heroes, write_hero_section
from .querygen import apply_queries, generate_queries, query_prompt
from .resolve import build_client, queries_for, resolve_image, resolve_video
from .schema import DesiredAsset, KeyAssetsProposal, KeyEntity, ResearchDirection

__all__ = [
    "registry", "DesiredAsset", "KeyEntity", "ResearchDirection", "KeyAssetsProposal",
    "decompose", "decompose_prompt", "parse_entities",
    "enrich", "enrich_prompt", "merge_entities",
    "consolidate", "consolidate_prompt", "parse_directions", "build_proposal",
    "collect", "build_client", "queries_for", "resolve_image", "resolve_video",
    "stage_heroes", "write_hero_section", "generate_queries", "apply_queries", "query_prompt",
]


async def build_proposal(script: str, client, *, comp: str = "", k: int = 30,
                         enrich_pass: bool = True, querygen_pass: bool = True) -> KeyAssetsProposal:
    """P1 end-to-end: decompose → (archival/clip ENRICH) → consolidate → (Tier-B QUERYGEN: per-asset
    LLM image-search queries + entity identifiers). Returns the reviewable proposal (caller stamps
    `.generated` + saves). `enrich_pass`/`querygen_pass=False` skip those passes."""
    entities = await decompose(script, client, k=k)
    if enrich_pass:
        entities = await enrich(script, entities, client)
    directions, entities = await consolidate(entities, client)
    if querygen_pass:
        await generate_queries(entities, script, client)
    return KeyAssetsProposal(comp=comp, entities=entities, directions=directions)
