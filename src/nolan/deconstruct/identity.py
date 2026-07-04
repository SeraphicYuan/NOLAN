"""Asset-identity cross-check — ground vision claims in the narration.

Vision identity hints confabulate (a model will confidently attribute a
painting to the most famous associated artist and invent supporting detail).
But essay narration frequently NAMES the works on screen. This pass links
each hinted/artwork shot to its narration window with one batched text-LLM
call and grades every identity:

- ``narration-confirmed`` — narration names the same work the vision claimed;
- ``narration-named``     — narration names a work; it wins over the hint
                            (the vision claim is preserved in ``identity_vision``);
- ``vision-claim``        — only the vision hint exists; treat as unverified.

Results are Tier-2 interpretation: they live in the extract (and beat
summaries), not in the library ``shots`` table. The synthesis agent is
instructed to web-verify surviving vision-claims where possible.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

IDENTITY_SOURCES = ("vision-claim", "narration-confirmed", "narration-named")

# asset types whose identity is worth checking even without a vision hint
_CHECK_TYPES = ("painting", "illustration", "photo", "map")

_SYS = """You verify artwork/asset identifications in a video. For each shot you get the
vision model's identity GUESS (may be wrong or empty) and the NARRATION spoken around
that shot. Decide ONLY from the narration text: does it name the artwork/asset shown?
Never invent names that are not in the narration. Reply with STRICT JSON only."""


def _prompt(items: List[Dict[str, Any]]) -> str:
    lines = []
    for it in items:
        lines.append(f"SHOT {it['idx']} — vision guess: {it['hint'] or '(none)'}\n"
                     f"  narration: \"{it['narration'][:400]}\"")
    return f"""{chr(10).join(lines)}

For EACH shot: if the narration explicitly names the artwork/asset on screen (title
and/or artist), report it; else null. Also say whether it matches the vision guess.
Return STRICT JSON: {{"checks": [{{"shot": <idx>, "named": "<title/artist or null>",
"matches_guess": true|false}}, ...]}} — one entry per shot, in order."""


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


def _window(shot_said: List[str], i: int) -> str:
    parts = [shot_said[j] for j in range(max(0, i - 1), min(len(shot_said), i + 2))
             if j < len(shot_said) and shot_said[j]]
    return " ".join(parts)


async def cross_check_identities(shots: List[Dict[str, Any]], shot_said: List[str],
                                 llm=None, batch_cap: int = 60) -> Dict[str, Any]:
    """Annotate shots in place with identity_source (and narration overrides).

    Candidates: shots carrying an ``identity_hint`` OR typed as artwork-like.
    Shots with a hint but no verification keep it, graded ``vision-claim``.
    Returns {"checked": n, "confirmed": n, "named": n, "source": "llm"|"none"}.
    """
    cands = []
    for s in shots:
        i = s.get("shot_index", 0)
        hint = (s.get("identity_hint") or "").strip()
        if not hint and (s.get("asset_type") not in _CHECK_TYPES):
            continue
        narration = _window(shot_said, i)
        if not narration:
            if hint:
                s["identity_source"] = "vision-claim"
            continue
        cands.append({"idx": i, "hint": hint, "narration": narration, "shot": s})

    confirmed = named = 0
    by_idx: Dict[int, Dict[str, Any]] = {}
    source = "none"
    if llm is not None and cands:
        try:
            batch = cands[:batch_cap]
            raw = await llm.generate(
                _prompt([{k: c[k] for k in ("idx", "hint", "narration")} for c in batch]),
                system_prompt=_SYS)
            for c in (_parse_json(raw) or {}).get("checks") or []:
                try:
                    by_idx[int(c.get("shot"))] = c
                except (TypeError, ValueError):
                    continue
            if by_idx:
                source = "llm"
        except Exception:
            pass

    for c in cands:
        s, hint = c["shot"], c["hint"]
        chk = by_idx.get(c["idx"]) or {}
        raw_named = chk.get("named")
        named_title = (str(raw_named).strip()
                       if raw_named and str(raw_named).lower() != "null" else "")
        if named_title and hint and chk.get("matches_guess"):
            s["identity_source"] = "narration-confirmed"
            confirmed += 1
        elif named_title:
            if hint:
                s["identity_vision"] = hint       # keep the overridden guess
            s["identity_hint"] = named_title[:120]
            s["identity_source"] = "narration-named"
            named += 1
        elif hint:
            s["identity_source"] = "vision-claim"

    return {"checked": len(cands), "confirmed": confirmed, "named": named,
            "source": source}
