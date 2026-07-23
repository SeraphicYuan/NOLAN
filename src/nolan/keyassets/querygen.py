"""QUERYGEN (Tier B) — LLM image-search query generation, the SOTA replacement for mechanical templating.

Mechanical name+qualifier queries can't inject WORLD KNOWLEDGE + RELATIONSHIPS — the exact thing a human
adds ('Cecil Rhodes' → 'Cecil Rhodes De Beers founder'). This runs at proposal time, once per entity
(concurrent), and returns a HYBRID: the entity's reusable IDENTIFIERS (role/affiliation/era/place — fed
back into the verify subject + Tier-C reformulation) plus, per asset need, a small DIVERSE set of SHORT
queries (query expansion) ordered canonical→descriptive. A dead LLM leaves queries empty → resolve falls
back to templating (contained). A human-edited entity (`queries_locked`) is never regenerated.

Pure prompt/parse (unit-testable); `generate_queries` is the injected async LLM fan-out.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Dict, List

from .schema import KeyEntity

SYS = ("You are a senior photo/archive researcher sourcing images for a documentary. You know the "
       "real-world facts about public figures, companies, works, places, and events, and you write the "
       "exact SHORT queries a professional types into an image search to find a SPECIFIC asset. Reply "
       "with STRICT JSON only.")


def query_prompt(entity: KeyEntity, essay_context: str = "", per_need: int = 3) -> str:
    ctx = " ".join((essay_context or "").split())[:600]
    needs = "\n".join(
        f'  [{i}] type={a.type} relevance={a.relevance} note="{(a.note or "").strip()}"'
        for i, a in enumerate(entity.desired_assets))
    return (
        (f"ESSAY CONTEXT: {ctx}\n" if ctx else "") +
        f'SUBJECT: "{entity.name}"  ({entity.kind}) — {entity.narrative_role}\n\n'
        "First, list this subject's IDENTIFIERS: the real-world terms that disambiguate it — role, "
        "affiliation, era/dates, place, and any common name variants. Use the essay context to pick the "
        "identifiers that matter for THIS story.\n\n"
        "Then, for EACH asset need below, write image-search queries. RULES:\n"
        f"- exactly {per_need} queries per need; each SHORT: 3-7 words. Long queries retrieve nothing.\n"
        "- DIVERSE, not synonyms. Vary across: (a) the identifiers above (role/affiliation/era/place), "
        "(b) name variants, (c) the visual MEDIUM matching the need (portrait/photograph/engraving; "
        "logo/wordmark; vintage print ad; diagram/chart; archival footage/newsreel).\n"
        "- ORDER most-specific -> broadest. Make the FIRST query the clean canonical 'name + medium' "
        "(best for encyclopedic/museum sources); later ones richer/descriptive (for web search).\n"
        "- EXACT needs: anchor to the real specific subject. RELATED needs: describe the SCENE/MOOD/era "
        "instead — it need not be the exact thing.\n\n"
        f"ASSET NEEDS:\n{needs}\n\n"
        'Return ONLY JSON: {"identifiers": ["...","..."], "queries": {"0": ["...","..."]}}')


def _parse(raw: str) -> Dict:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {}
    try:
        d = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def apply_queries(entity: KeyEntity, parsed: Dict, per_need: int = 3) -> None:
    """Write the parsed identifiers + per-need queries onto the entity (pure; no I/O)."""
    ids = [str(x).strip() for x in (parsed.get("identifiers") or []) if str(x).strip()]
    entity.identifiers = ids[:6]
    qmap = parsed.get("queries") or {}
    if not isinstance(qmap, dict):
        qmap = {}
    for i, a in enumerate(entity.desired_assets):
        raw = qmap.get(str(i)) or qmap.get(i) or []
        seen, qs = set(), []
        for q in raw:
            q = str(q).strip()
            k = q.lower()
            if q and k not in seen:
                seen.add(k)
                qs.append(q)
        a.queries = qs[:per_need + 1]                       # a touch of slack over the target


async def generate_queries(entities: List[KeyEntity], essay_context: str, client, *, per_need: int = 3):
    """LLM fan-out: populate each entity's identifiers + each desired asset's queries. Concurrent per
    entity; a per-entity failure just leaves that entity on the templating fallback. Skips locked entities."""
    async def _one(e: KeyEntity):
        if e.queries_locked or not e.desired_assets:
            return
        try:
            raw = await client.generate(query_prompt(e, essay_context, per_need), system_prompt=SYS)
            apply_queries(e, _parse(raw), per_need)
        except Exception:
            return

    await asyncio.gather(*[_one(e) for e in entities])
    return entities
