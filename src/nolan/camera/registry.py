"""The camera umbrella — the ONE vocabulary of moves a still can be given.

WHY THIS MODULE EXISTS. Two camera vocabularies already existed and neither could see the other: the
LEGACY Remotion path (`nolan/still_motion.py` + `StillMotion.tsx`) had ken-burns in/out/pan, parallax,
rack-focus, subject targeting from a rembg centroid, and narrative-cue selection with a no-repeat
rule — while the DOMINANT compose-first path had exactly one move, `scale kb[0] -> kb[1]`, linear,
about the centre, hardcoded in `media_ground`. Porting the vocabulary block-by-block would have
created WIRING_CHECKLIST pitfall #4 (two dialects for one decision) by construction, so it lands here
once and both paths import it.

A move is DATA. The executor (`camera.emit`) turns it into GSAP; the solver (`camera.solve`) decides
the geometry; the selector (`camera.select`) picks one when the author didn't. Adding a move means
adding an entry here plus its executor branch — `tests/test_camera.py` fails if a registered move has
no executor, or an executor has no entry.

`needs` is what makes a move degrade honestly rather than break:
  target    — a point to aim at (subject detection, or the centre as fallback)
  box       — a REGION (a face, a logo, a quoted line); strictly more than a point
  cutout    — an alpha matte of the subject (rembg), for real depth
  detection — a model call (VLM/OCR) rather than a deterministic derivation
A move whose need is unmet falls back along `degrades_to` and SAYS SO; it never silently no-ops.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class Move:
    id: str
    family: str                  # push | lateral | depth | focus | document | still
    purpose: str
    when_to_use: str
    needs: Tuple[str, ...] = ()
    degrades_to: Optional[str] = None
    constraints: Tuple[str, ...] = ("seek_safe", "duration_preserving", "transform_only")


def _m(id, family, purpose, when_to_use, needs=(), degrades_to=None, constraints=None) -> Move:
    return Move(id=id, family=family, purpose=purpose, when_to_use=when_to_use, needs=tuple(needs),
                degrades_to=degrades_to,
                constraints=tuple(constraints) if constraints else
                ("seek_safe", "duration_preserving", "transform_only"))


MOVES: Dict[str, Move] = {m.id: m for m in [
    # --- A. push / pull — the scale family ---------------------------------------------------------
    _m("push-in", "push",
       "Scale up about a target point over the beat.",
       "The default life-giver for any still held longer than ~3s. Motivated by narration that NAMES "
       "or EXAMINES a thing ('this', 'the man', 'the detail').",
       needs=("target",)),
    _m("pull-out", "push",
       "Start TIGHT on the target and widen to the full frame.",
       "The narrative widening — 'you weren't seeing the whole picture'. Motivated by reveal language "
       "('but', 'it turns out', 'the whole', 'everything'). Earns a turn instead of decorating one.",
       needs=("target",)),
    _m("punch-in", "push",
       "A fast step push (~0.35s) at a cue, then hold.",
       "Emphasis on ONE spoken word. Not ambience — at most one per beat, and never as a default.",
       needs=("target",)),
    _m("push-to-detail", "push",
       "Push into a BOX so it fills most of the frame.",
       "A named logo / face / object / signature the narration calls out. The box is what separates "
       "this from push-in: a point cannot tell you how tight to go.",
       needs=("box",), degrades_to="push-in"),
    _m("settle", "push",
       "Push that overshoots slightly and eases back.",
       "An opening shot — reads as an operator finding the frame. Sparingly; it draws attention to the "
       "camera itself.",
       needs=("target",)),

    # --- B. lateral — the translate family ---------------------------------------------------------
    _m("pan-right", "lateral",
       "Translate across the frame left→right.",
       "Wide horizontal sources, and narration that MOVES ('from', 'across', 'the journey'). Direction "
       "follows the subject's lead room, then reading order.",
       needs=("target",)),
    _m("pan-left", "lateral", "Translate across the frame right→left.",
       "As pan-right, when lead room or continuity wants the other direction.",
       needs=("target",)),
    _m("pan-down", "lateral",
       "Translate top→bottom, revealing a TALL source down its long axis.",
       "Posters, full newspaper pages, portraits, documents. Panning a portrait sideways is the classic "
       "amateur tell; on a tall source this is the move that exists.",
       needs=()),
    _m("pan-up", "lateral", "Translate bottom→top on a tall source.",
       "As pan-down, when the payoff is at the top (a headline, a face above a body of text).",
       needs=()),
    _m("pan-to-subject", "lateral",
       "Start off-subject and land ON it at the cue.",
       "'The camera finds it' — a person or object entering the argument mid-beat.",
       needs=("target",), degrades_to="push-in"),
    _m("drift", "lateral",
       "A sub-perceptual lateral + scale (≤2%).",
       "Long holds where a real push would be too much movement — ambience, not a statement.",
       needs=()),

    # --- C. depth — 2.5D -------------------------------------------------------------------------
    _m("parallax", "depth",
       "Sharp subject cutout pushes faster than a blurred background.",
       "The single biggest 'looks expensive' upgrade for a still-heavy stretch. Needs a clean subject.",
       needs=("cutout",), degrades_to="push-in"),
    _m("parallax-pan", "depth",
       "Subject and background translate at different rates.",
       "Landscapes, crowds, cityscapes — lateral travel with real depth.",
       needs=("cutout",), degrades_to="pan-right"),
    _m("depth-dolly", "depth",
       "Foreground scales while the background stays nearly still.",
       "Approach rather than sideways travel; good on a portrait.",
       needs=("cutout",), degrades_to="push-in"),

    # --- D. focus / atmosphere --------------------------------------------------------------------
    _m("rack-focus", "focus",
       "Blur → sharp on the subject at a cue.",
       "A revelation or a realisation. With a cutout it is a true rack; without, the whole frame.",
       needs=("cutout",), degrades_to="blur-in",
       constraints=("seek_safe", "duration_preserving")),          # filter, not transform
    _m("blur-in", "focus", "The whole frame resolves from blurred to sharp.",
       "Memory, dream, 'coming into focus'. Cheap and seek-safe.",
       constraints=("seek_safe", "duration_preserving")),
    _m("blur-out", "focus", "The whole frame dissolves into blur.",
       "An exit into a transition, or a thought trailing off.",
       constraints=("seek_safe", "duration_preserving")),
    _m("roll-drift", "focus",
       "A push with 0.3-0.8 degrees of rotation.",
       "Unease, archival, instability. NEVER a default — a visible rotation reads as a screensaver.",
       needs=("target",)),

    # --- E. document / text-aware -----------------------------------------------------------------
    _m("read-along", "document",
       "Arrive on a quoted LINE as it is spoken.",
       "The essay-specific move: a document, ad, patent or headline the narration quotes. Fuses the "
       "camera with word-level alignment.",
       needs=("box", "detection"), degrades_to="push-to-detail"),
    _m("scan-column", "document",
       "A slow vertical crawl down a column, paced to the reading.",
       "A long document or letter read aloud — the frame keeps pace with the reading so the viewer is always looking at the line being spoken.",
       needs=("box",), degrades_to="pan-down"),

    # --- F. stillness ------------------------------------------------------------------------------
    _m("hold", "still",
       "A locked frame. No move.",
       "An iconic image at a climax; a face at the emotional peak. A system that always moves is as "
       "monotonous as one that never does — this must be selectable AND selected.",
       constraints=("seek_safe", "duration_preserving")),
]}

FAMILIES = ("push", "lateral", "depth", "focus", "document", "still")


def get(move_id: str) -> Optional[Move]:
    return MOVES.get(str(move_id or "").strip())


def family_of(move_id: str) -> Optional[str]:
    m = get(move_id)
    return m.family if m else None


def degrade(move_id: str, available: set) -> Tuple[str, Optional[str]]:
    """(move_id_to_use, reason_if_degraded) given the capabilities actually available.

    Walks `degrades_to` until every `needs` is met, ending at `hold` rather than raising: a missing
    cutout must cost you the parallax, never the render.
    """
    seen, cur = set(), str(move_id or "")
    while cur and cur not in seen:
        seen.add(cur)
        m = get(cur)
        if m is None:
            return "push-in", f"unknown move {move_id!r} — fell back to push-in"
        missing = [n for n in m.needs if n not in available]
        if not missing:
            return cur, (None if cur == move_id else f"{move_id} needs {missing or ''} — degraded to {cur}")
        nxt = m.degrades_to
        if not nxt:
            return "hold", f"{move_id} needs {sorted(missing)} and has no fallback — holding"
        cur = nxt
    return "hold", f"{move_id} degrade chain looped — holding"
