"""ENRICH — the archival / clip completeness pass (an "archival supervisor" second look).

Decompose is entity-centric, so it under-produces VIDEO. This pass reads the script + the current
pull-list and adds what a documentary editor still wants:
  1. MISSED named subjects (a figure named once at the very end, a company mentioned in passing).
  2. ARCHIVAL CLIPS — vintage commercials, historical/process footage — as `footage` assets, marked
     relevance=`exact` (a specific known clip) OR `related` (directionally-relevant b-roll that fits
     the era/mood, where no exact match is needed — the "branch out" the director asked for).
  3. SUPPORTING period PICTURES beyond the hero stills.

New items are normalized through `parse_entities` (same validated shape) and merged into the list
(dedup by name, id-collision-safe). Pure `merge_entities` + a thin async `enrich`; a dead LLM just
adds nothing (contained).
"""
from __future__ import annotations

import re
from typing import List

from .decompose import parse_entities
from .schema import KeyEntity

_KINDS = "person | organization | place | event | work | concept"
_ATYPES = "portrait | logo | product | artwork | document | photo | map | footage"


def enrich_prompt(script: str, entities: List[KeyEntity]) -> str:
    """Second-look prompt: given what we already have, find missed subjects + the archival/clip tier."""
    have = ", ".join(sorted({e.name for e in entities})) or "(none yet)"
    return (
        "You are the ARCHIVAL SUPERVISOR reviewing a documentary's asset pull-list before research. "
        "The film NEEDS motion — archival footage and period clips, not only stills. Given the script "
        "and the subjects ALREADY on the list, add what's MISSING. Focus especially on VIDEO. Return "
        "THREE things, all as pull-list items:\n"
        "  1. any NAMED subjects the list missed (people/orgs/works/places/events named in the script);\n"
        "  2. ARCHIVAL CLIPS the story wants — vintage TV commercials, historical newsreel, on-location "
        "or PROCESS footage (e.g. a mine, a production line). For each clip use a `footage` desired_asset "
        "and set its \"relevance\": \"exact\" for a SPECIFIC known clip (e.g. the actual 1947 campaign film) "
        "or \"related\" for DIRECTIONALLY-relevant b-roll that only needs to fit the era/subject/mood "
        "(e.g. 1950s American wedding footage, 1980s jewelry-store b-roll) — branch out; it need NOT be "
        "an exact match, just genuinely on-theme;\n"
        "  3. a few SUPPORTING period PICTURES (photo/document/map) that ground scenes beyond the heroes.\n\n"
        "Each item: {\"name\": short specific name, \"kind\": one of [" + _KINDS + "], "
        "\"priority\": \"hero\"|\"supporting\", \"narrative_role\": <=15 words, "
        "\"mentions\": 1-2 short verbatim spoken phrases if applicable, "
        "\"desired_assets\": [{\"type\": one of [" + _ATYPES + "], \"note\": what specifically, "
        "\"collage_ready\": bool, \"relevance\": \"exact\"|\"related\"}]}. Do NOT repeat items already "
        "present. Return ONLY a JSON array (no prose, no code fences), up to 20 items.\n\n"
        "ALREADY ON THE LIST: " + have + "\n\nSCRIPT:\n" + (script or "")[:12000])


_STOP = {"the", "a", "an", "of", "and", "or", "for", "to", "in", "on", "de", "van", "von",
         "el", "la", "us", "usa"}


def _name_tokens(name: str) -> set:
    """Distinctive name tokens (lowercased, >2 chars, stopwords dropped) for near-dup detection."""
    return {t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if len(t) > 2 and t not in _STOP}


def _near_dup(a: KeyEntity, b: KeyEntity) -> bool:
    """Same subject in two framings? SAME kind + one name's distinctive tokens ⊆ the other's, with the
    smaller ≥2 tokens. Conservative on purpose: 'De Beers' ({beers}, 1 tok) never collapses into
    'De Beers v. US' (different kind anyway), but 'Edward Epstein' folds 'Edward Epstein Interview'."""
    if a.kind != b.kind:
        return False
    ta, tb = _name_tokens(a.name), _name_tokens(b.name)
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return len(small) >= 2 and small <= big


def _absorb_assets(dst: KeyEntity, src: KeyEntity) -> None:
    """Fold src's desired_assets into dst, deduped by (type, note); keeps the clip the near-dup found."""
    seen = {(x.type, x.note.strip().lower()) for x in dst.desired_assets}
    for x in src.desired_assets:
        key = (x.type, x.note.strip().lower())
        if key not in seen:
            seen.add(key)
            dst.desired_assets.append(x)


def merge_entities(entities: List[KeyEntity], extra: List[KeyEntity]) -> List[KeyEntity]:
    """Append `extra` to `entities`, dropping exact name-dups, FOLDING near-dups (same subject, another
    framing) into the existing entity's assets, and fixing id collisions. Pure + order-preserving."""
    have = {e.name.lower() for e in entities}
    taken = {e.id for e in entities}
    merged = list(entities)
    for e in extra:
        if not e.name or e.name.lower() in have:
            continue
        dup = next((x for x in merged if _near_dup(x, e)), None)
        if dup is not None:                          # same subject reframed → absorb its assets, don't add
            _absorb_assets(dup, e)
            have.add(e.name.lower())
            continue
        if e.id in taken:
            base, k = e.id, 2
            while f"{base}_{k}" in taken:
                k += 1
            e.id = f"{base}_{k}"
        have.add(e.name.lower())
        taken.add(e.id)
        merged.append(e)
    return merged


async def enrich(script: str, entities: List[KeyEntity], client, k: int = 20) -> List[KeyEntity]:
    """LLM second-look: add missed subjects + archival clips + supporting pictures. Returns the
    merged list (original order preserved, new items appended). A dead LLM adds nothing."""
    try:
        raw = await client.generate(enrich_prompt(script, entities),
                                    system_prompt="You complete a documentary asset list, prioritising "
                                                  "archival video. Reply STRICT JSON only.")
    except Exception:
        return entities
    return merge_entities(entities, parse_entities(raw, k=k))
