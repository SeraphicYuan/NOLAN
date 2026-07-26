"""Which move, when the author didn't say — deterministic first, model last.

Precedence (the first that answers wins), ported from `still_motion.select_still_treatment` and
extended to read the beat's ACTUAL aligned narration rather than a guess:

  1. an authored lock                      — a human or the authoring agent chose; honoured verbatim
  2. narrative cue                          — what the sentence DOES (moves / widens / names)
  3. source shape                           — a tall source pans down its long axis, never sideways
  4. duration band                          — a <3s beat has no room for a considered move
  5. no-repeat                              — never the same FAMILY twice in a row

The no-repeat rule is the one that matters most in a finished essay: the aeneid feedback was "every
image got the same push", and two identical consecutive moves read as a template, not a camera.
"""
from __future__ import annotations

import re
from typing import Optional, Sequence, Tuple

from . import registry

# What the sentence DOES. Word-boundary matched, so "buttress" cannot trip " but ".
_PAN_CUES = (r"from\b.*\bto\b", r"\bacross\b", r"\bthrough\b", r"\bjourney\b", r"\bspread\b",
             r"\bmarch\w*\b", r"\btravel\w*\b", r"\bflow\w*\b", r"\broute\b", r"\bmigrat\w*\b")
_OUT_CUES = (r"\bbut\b", r"\bturns out\b", r"\bwhole\b", r"\bentire\b", r"\ball of\b", r"\beverything\b",
             r"\bbigger\b", r"\blarger\b", r"\bactually\b", r"\bin fact\b", r"\bempire\b", r"\bworld\b",
             r"\bzoom out\b", r"\bstep back\b")
_IN_CUES = (r"\bthis\b", r"\bthese\b", r"\bhere\b", r"\bdetail\b", r"\bface\b", r"\bhands?\b",
            r"\bsignature\b", r"\bnamed?\b", r"\blook at\b", r"\bnotice\b", r"\bclose\w*\b")
_STILL_CUES = (r"\bsilence\b", r"\bstops?\b", r"\bstill\b", r"\bfrozen\b", r"\bnothing\b")


def _hits(text: str, pats) -> bool:
    t = f" {(text or '').lower()} "
    return any(re.search(p, t) for p in pats)


def select(*, narration: str = "", dur: float = 6.0, img: Optional[Tuple[int, int]] = None,
           prev_family: Optional[str] = None, authored: Optional[str] = None,
           available: Optional[set] = None, canvas=(1920, 1080),
           index: int = 0) -> Tuple[str, str]:
    """(move_id, why). `why` is recorded on the scene so a human can see the camera's reasoning."""
    avail = set(available or {"target"})

    if authored:
        mv, reason = registry.degrade(authored, avail)
        return mv, (reason or f"authored lock `{authored}`")

    # 3. source shape wins over sentiment on a genuinely tall source: a sideways pan there is wrong
    if img and img[0] > 0:
        cw, ch = canvas
        if (img[1] / img[0]) > (ch / cw) * 1.35:
            return ("pan-down", "tall source — pans down its long axis")

    # 4. a very short beat cannot hold a considered move
    if dur < 3.0:
        if _hits(narration, _IN_CUES):
            return ("punch-in", f"{dur:.1f}s beat — a step accent, not a glide")
        return ("hold", f"{dur:.1f}s beat — too short for a move to read")

    # 2. what the sentence does
    if _hits(narration, _STILL_CUES):
        pick, why = "hold", "narration goes still"
    elif _hits(narration, _PAN_CUES):
        pick, why = ("pan-right" if index % 2 == 0 else "pan-left"), "narration MOVES"
    elif _hits(narration, _OUT_CUES):
        pick, why = "pull-out", "narration WIDENS"
    elif _hits(narration, _IN_CUES):
        pick, why = "push-in", "narration NAMES/EXAMINES"
    else:
        # A long hold is where the amplitude law EARNS its keep — a slow, large push. `drift` is the
        # alternation partner (below), not a duration default: defaulting to it past 9s gave a 14s beat
        # 2% of travel while a 5s beat got 5.6%, which is the dead-long-hold bug wearing a new hat.
        pick, why = "push-in", "no cue — the default push"

    # 5. no-repeat on the FAMILY (a second push of a different name is still a second push)
    if prev_family and registry.family_of(pick) == prev_family:
        rotation = {"push": ("pan-right", "drift"), "lateral": ("push-in", "pull-out"),
                    "still": ("push-in",), "depth": ("push-in",), "focus": ("push-in",),
                    "document": ("push-in",)}.get(prev_family, ("push-in",))
        for alt in rotation:
            if registry.family_of(alt) != prev_family:
                pick, why = alt, f"{why}; alternated off `{prev_family}` (no two in a row)"
                break

    mv, reason = registry.degrade(pick, avail)
    return mv, (f"{why} — {reason}" if reason else why)


def alternate(moves: Sequence[str]) -> list:
    """Post-pass: break any surviving same-family run in an already-chosen sequence."""
    out = []
    for i, m in enumerate(moves):
        fam = registry.family_of(m)
        if i and fam and fam == registry.family_of(out[-1]):
            m = "drift" if fam == "push" else "push-in"
        out.append(m)
    return out
