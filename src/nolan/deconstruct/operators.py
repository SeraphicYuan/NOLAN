"""Pairing-operator classification — WHY does this asset sit under this line?

Classifies each beat's script↔asset relationship using the SAME operator
vocabulary the forward pairing engine (``nolan.evoke_broll``) selects with,
so a deconstruction reads as a recipe the forward pipeline could replay.

The BGE said↔shown cosine (``video_style.pairing``) supplies a cheap
*directness prior*; the text LLM refines it into an operator + rationale.
Deterministic fallback maps the prior's band straight to an operator.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

# One-line semantics per operator — names identical to evoke_broll._OP.
OPERATOR_RUBRIC = {
    "literal": "the footage plainly SHOWS what the line names (keyword match)",
    "knowledge": "the SPECIFIC real, era-correct named asset (a titled artwork, artifact, place)",
    "tonal": "mood/atmosphere footage that EVOKES the line's emotion, not its subject",
    "conceptual": "a visual METAPHOR whose mechanic mirrors the idea (collapse→dominoes)",
    "ironic": "footage that CONTRADICTS or undercuts the line for pointed effect",
    "trait": "a person's quality embodied by an ACTIVITY (patience→fly-fishing)",
    "relational": "two shots/sides colliding to make a third meaning (split-screen, A-vs-B)",
    "scale": "a big NUMBER made tangible over a countable/graphic referent",
    "text-graphic": "the asset IS typography or an information graphic carrying the words/data",
}
OPERATORS = tuple(OPERATOR_RUBRIC) + ("unclear",)

_BAND_FALLBACK = {"literal": "literal", "associative": "conceptual",
                  "tonal/abstract": "tonal"}

_SYS = """You are a film editor analyzing WHY a finished video pairs each asset with its
narration. Use the operator vocabulary exactly as defined. Judge from evidence given;
if genuinely ambiguous, say "unclear". Reply with STRICT JSON only."""


def _beat_block(i: int, b: Dict[str, Any]) -> str:
    lines = [f"BEAT {i} — \"{b.get('title')}\" ({b.get('function')}), "
             f"{b.get('t0', 0):.0f}-{b.get('t1', 0):.0f}s"]
    if b.get("said"):
        lines.append(f'  narration: "{b["said"][:400]}"')
    if b.get("shown"):
        lines.append(f'  on screen: {b["shown"][:400]}')
    if b.get("asset_types"):
        lines.append(f"  asset types: {b['asset_types']}")
    if b.get("directness") is not None:
        lines.append(f"  said-shown similarity: {b['directness']:.2f} ({b.get('band')})")
    return "\n".join(lines)


def _prompt(beats: List[Dict[str, Any]]) -> str:
    rubric = "\n".join(f"- {k}: {v}" for k, v in OPERATOR_RUBRIC.items())
    blocks = "\n\n".join(_beat_block(i, b) for i, b in enumerate(beats))
    return f"""Pairing operators:
{rubric}
- unclear: cannot tell from the evidence

For EACH beat below, classify the script-to-asset pairing:

{blocks}

Return STRICT JSON: {{"classifications": [{{"beat": 0, "operator": "...",
"why": "<one sentence quoting the evidence>", "confidence": "high|medium|low"}}, ...]}}
One entry per beat, in order."""


def _parse_json(raw: str) -> Dict[str, Any]:
    raw = (raw or "").strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {}


def _fallback(b: Dict[str, Any]) -> Dict[str, Any]:
    at = (b.get("asset_types") or "")
    if "text-card" in at or "chart-graphic" in at or "map" in at:
        op = "text-graphic"
    else:
        op = _BAND_FALLBACK.get(b.get("band") or "", "unclear")
    return {"operator": op, "why": "derived from said-shown similarity band (no LLM)",
            "confidence": "low"}


async def classify_operators(beats: List[Dict[str, Any]], llm=None) -> Dict[str, Any]:
    """Annotate beats in place with operator/operator_why/operator_confidence.

    One batched LLM call for all beats (the model sees the whole arc);
    per-beat fallback from the directness band when the call fails or a
    beat's entry is missing/invalid. Returns {"source": "llm"|"fallback"}.
    """
    if not beats:
        return {"source": "fallback"}
    by_idx: Dict[int, Dict[str, Any]] = {}
    source = "fallback"
    if llm is not None:
        try:
            raw = await llm.generate(_prompt(beats), system_prompt=_SYS)
            for c in (_parse_json(raw) or {}).get("classifications") or []:
                try:
                    idx = int(c.get("beat"))
                except (TypeError, ValueError):
                    continue
                op = str(c.get("operator") or "").strip().lower()
                if op in OPERATORS:
                    by_idx[idx] = {
                        "operator": op,
                        "why": str(c.get("why") or "").strip()[:300],
                        "confidence": (str(c.get("confidence") or "medium").lower()
                                       if str(c.get("confidence") or "").lower()
                                       in ("high", "medium", "low") else "medium"),
                    }
            if by_idx:
                source = "llm"
        except Exception:
            pass
    for i, b in enumerate(beats):
        c = by_idx.get(i) or _fallback(b)
        b["operator"] = c["operator"]
        b["operator_why"] = c["why"]
        b["operator_confidence"] = c["confidence"]
    return {"source": source}
