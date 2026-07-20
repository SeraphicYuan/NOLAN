"""Spine-structure registry — how a script's thesis is organised.

docs/SCRIPT_REVIEW_PROGRAM.md §5 (Phase 2). Real essays often carry more than one
thesis; forcing a single ``**[CHOSEN]**`` angle flattens them. A *composite spine* is
1..N threads bound by an explicit macro-structure. This registry names the structures a
spine may take, each with ``when_to_use`` and ``beat_guidance`` (how the threads map onto
the beat sequence). ``single`` reproduces today's behaviour, so this is additive.

A composite spine is stored on the project as::

    "composite_spine": {"structure": "chronological",
                        "threads": ["thread A", "thread B"],
                        "binding": "how they cohere into one felt through-line"}

Honesty: ``tests/test_spine_structures.py`` pins that every id resolves, the thread
counts validate, and ``single`` stays back-compatible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class SpineStructure:
    id: str
    title: str
    when_to_use: str
    beat_guidance: str          # how the threads should be arranged across beats
    min_threads: int = 1
    max_threads: int = 1


STRUCTURES: Dict[str, SpineStructure] = {
    "single": SpineStructure(
        id="single",
        title="Single spine",
        when_to_use="One through-line carries the whole piece. The default.",
        beat_guidance="One thread runs start to finish; every beat serves it directly.",
        min_threads=1, max_threads=1,
    ),
    "chronological": SpineStructure(
        id="chronological",
        title="Chronological",
        when_to_use="A story or argument whose force comes from time-order — rise/fall, "
                    "before/after, a sequence of escalating events.",
        beat_guidance="Order the threads as time phases; each beat advances the clock. Later "
                      "threads must build on (not merely follow) earlier ones — cause→effect, "
                      "not just next.",
        min_threads=1, max_threads=5,
    ),
    "hierarchical": SpineStructure(
        id="hierarchical",
        title="Hierarchical (general → specific)",
        when_to_use="A claim best understood by nesting — the big frame, then the layers "
                    "inside it, then the concrete instance.",
        beat_guidance="Open on the widest thread, then descend one level per movement; each "
                      "sub-thread is an instance of its parent. Return to the top level to close.",
        min_threads=2, max_threads=4,
    ),
    "braided": SpineStructure(
        id="braided",
        title="Braided (interleaved threads)",
        when_to_use="Two or three threads that gain meaning from each other and must be cut "
                    "together — a human story against a systemic one, say.",
        beat_guidance="Interleave the threads, returning to each on a rhythm; every hand-off must "
                      "carry a reason (a rhyme, a contrast, a consequence). They must MEET at the "
                      "close, not just end near each other.",
        min_threads=2, max_threads=3,
    ),
    "thesis-antithesis-synthesis": SpineStructure(
        id="thesis-antithesis-synthesis",
        title="Thesis · antithesis · synthesis",
        when_to_use="An argument that earns its verdict by fully staging the opposing view "
                    "before resolving it.",
        beat_guidance="Thread 1 = the case; thread 2 = the strongest counter-case at full "
                      "strength; thread 3 = the synthesis that resolves them. Do not resolve early.",
        min_threads=3, max_threads=3,
    ),
    "parallel-cases": SpineStructure(
        id="parallel-cases",
        title="Parallel cases",
        when_to_use="Several comparable instances that together prove one point (three "
                    "collapses, four inventions).",
        beat_guidance="Each thread is one case, told to the SAME shape so the pattern is felt; a "
                      "final beat names the shared conclusion the cases converge on.",
        min_threads=2, max_threads=5,
    ),
    "spatial-zoom": SpineStructure(
        id="spatial-zoom",
        title="Spatial zoom",
        when_to_use="A subject best traversed by scale or place — macro→micro, or a tour "
                    "across locations.",
        beat_guidance="Order threads by scale/place and move steadily in one direction; each beat "
                      "is a stop, and the move between stops is itself meaningful.",
        min_threads=1, max_threads=5,
    ),
}

DEFAULT_STRUCTURE = "single"


def get_structure(structure_id: str) -> SpineStructure:
    return STRUCTURES.get((structure_id or "").strip()) or STRUCTURES[DEFAULT_STRUCTURE]


def validate_composite_spine(spine: dict) -> Tuple[bool, str]:
    """Check a composite_spine dict against its structure's thread bounds. Empty/absent = valid
    (means 'single', the default)."""
    if not spine:
        return True, ""
    sid = (spine.get("structure") or "single").strip()
    if sid not in STRUCTURES:
        return False, f"unknown spine structure '{sid}' (choices: {', '.join(STRUCTURES)})"
    s = STRUCTURES[sid]
    threads = [t for t in (spine.get("threads") or []) if str(t).strip()]
    n = len(threads) or 1
    if not (s.min_threads <= n <= s.max_threads):
        return False, (f"structure '{sid}' takes {s.min_threads}–{s.max_threads} threads, got {n}")
    return True, ""


def render_structures_menu() -> str:
    """The menu offered to the angle step: pick single OR a composite structure."""
    lines = ["**Spine structures** — a spine may be a SINGLE thread or a COMPOSITE of a few "
             "threads bound by ONE of these macro-structures. Prefer `single` unless the material "
             "genuinely carries more than one thread that coheres better woven than merged:"]
    for s in STRUCTURES.values():
        rng = "1 thread" if s.max_threads == 1 else f"{s.min_threads}–{s.max_threads} threads"
        lines.append(f"- **{s.id}** ({rng}) — {s.when_to_use}")
    lines.append("If you choose a composite, record it as `**[SPINE]** structure:<id> · "
                 "threads:[t1; t2; …] · binding:<how they cohere into one felt through-line>`.")
    return "\n".join(lines)


def render_structure_guidance(spine: dict) -> str:
    """The beat-arrangement guidance for a chosen composite spine (empty for single)."""
    sid = (spine or {}).get("structure") or "single"
    if sid == "single":
        return ""
    s = get_structure(sid)
    threads = [t for t in (spine.get("threads") or []) if str(t).strip()]
    binding = (spine.get("binding") or "").strip()
    out = [f"### Composite spine — **{s.title}** (`{s.id}`)",
           f"_Arrangement:_ {s.beat_guidance}"]
    if threads:
        out.append("Threads to weave (arrange the beats so each is served AND they cohere):")
        out += [f"  {i}. {t}" for i, t in enumerate(threads, 1)]
    if binding:
        out.append(f"_Binding (the one felt through-line):_ {binding}")
    out.append("Do NOT let the threads become isolated chapters — the review's through-line "
               "dimension checks that they actually braid, not merely sit adjacent.")
    return "\n".join(out)
