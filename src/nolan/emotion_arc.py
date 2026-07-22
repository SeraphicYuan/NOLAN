"""P6: tone / emotion arc — assign a delivery to the FEW pivot beats of a script.

The craft is restraint: emoting every beat sounds fake, so an LLM (taste) marks only the
beats that carry an emotional pivot (hook, reveal, turn, close), choosing from a small tone
registry. Output is `[delivery: <tone>]` markers written under those beat headings — the same
markers the A6 pipeline already parses (→ per-section CosyVoice `instruct`).

Propose → gate → apply: the LLM proposes {beat: tone}; a deterministic validator gates it
(registry-only, capped to the pivot budget); `apply_arc_to_script` writes the markers.
"""

from __future__ import annotations

import json
import re
from typing import Callable, List, Optional

# The sanctioned delivery tones. Kept small on purpose — a wide palette invites over-emoting.
TONE_REGISTRY = {
    "calm": "measured, unhurried, warm — the resting narration tone (rarely needs marking)",
    "grave": "somber, weighty — a dark turn or a sobering fact",
    "wry": "dry, knowing, lightly amused — an aside or a bit of irony",
    "urgent": "quicker, tense — rising stakes or a hinge moment",
    "warm": "gentle, intimate — a human, empathetic beat",
    "triumphant": "bright, resolved — a payoff or an uplift",
    "tense": "restrained, uneasy — suspense just before a reveal",
}


def pivot_budget(n_beats: int) -> int:
    """How many beats may carry a delivery — a hard restraint cap (~a third, 1–4)."""
    return max(1, min(4, n_beats // 3))


def build_arc_prompt(sections: List[dict], *, max_marked: int) -> str:
    beats = "\n".join(
        f"[{i}] {s.get('title') or 'beat'} — {((s.get('body') or '')[:200])}"
        for i, s in enumerate(sections))
    tones = "\n".join(f"  {k}: {v}" for k, v in TONE_REGISTRY.items())
    return (
        "You are a voice director shaping the emotional ARC of a narrated video essay.\n"
        f"Mark ONLY the {max_marked} (or fewer) beats that carry a real emotional pivot — the hook, "
        "a reveal, a turn, the close. Leave every other beat unmarked (it uses the calm baseline). "
        "Over-marking sounds fake; restraint is the whole point.\n\n"
        "Choose each tone from this registry ONLY:\n" + tones + "\n\n"
        "Beats:\n" + beats + "\n\n"
        f'Reply with ONLY a JSON object mapping beat index → tone, at most {max_marked} entries, '
        'e.g. {"0": "tense", "6": "grave"}. No prose.')


def parse_arc_response(text: str, n_beats: int, *, max_marked: int) -> List[Optional[str]]:
    """Validate the LLM proposal into deliveries aligned to beats (registry-only, capped)."""
    out: List[Optional[str]] = [None] * n_beats
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return out
    try:
        raw = json.loads(m.group(0))
    except ValueError:
        return out
    marked = 0
    for k, v in raw.items():
        try:
            idx = int(k)
        except (TypeError, ValueError):
            continue
        tone = str(v).strip().lower()
        if 0 <= idx < n_beats and tone in TONE_REGISTRY and out[idx] is None:
            out[idx] = tone
            marked += 1
            if marked >= max_marked:
                break
    return out


async def assign_arc(sections: List[dict], *, generate: Callable, max_marked: Optional[int] = None):
    """Ask the LLM to assign the emotion arc → validated deliveries (list aligned to sections)."""
    n = len(sections)
    cap = max_marked if max_marked is not None else pivot_budget(n)
    text = await generate(build_arc_prompt(sections, max_marked=cap))
    return parse_arc_response(text, n, max_marked=cap)


_DELIVERY_LINE = re.compile(r"^[ \t]*\[delivery:.*\][ \t]*\r?\n?", re.IGNORECASE | re.MULTILINE)
_HEADING = re.compile(r"^##\s+\S")


def apply_arc_to_script(md: str, deliveries: List[Optional[str]]) -> str:
    """Write `[delivery: <tone>]` markers under each assigned beat heading (idempotent: strips any
    existing delivery lines first, then re-inserts). Beats are counted by ``## `` heading order."""
    md = _DELIVERY_LINE.sub("", md or "")
    out, beat = [], -1
    for line in md.splitlines(keepends=True):
        out.append(line)
        if _HEADING.match(line):
            beat += 1
            dv = deliveries[beat] if beat < len(deliveries) else None
            if dv:
                nl = "\r\n" if line.endswith("\r\n") else "\n"
                out.append(f"[delivery: {dv}]{nl}")
    return "".join(out)
