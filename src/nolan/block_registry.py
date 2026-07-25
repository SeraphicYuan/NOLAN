"""Block CAPABILITIES — what each composer template actually consumes.

The truth about a block lives in `bridge/compose.py` (+ `compose_extension.py`): a block consumes a
field iff its composer function reads it. Nothing else can know this, so anything that needs the answer
must ask HERE, not keep a private copy.

WHY THIS MODULE EXISTS (an incident, not a preference). `_GROUND_BLOCKS` was defined TWICE, with the
same name and different contents:

  * `hyperframes/autoground.py`      -> the 6 blocks whose composer calls `media_ground()`
  * `style_contract/metrics.py`      -> `{"statement", "stat"}`

So auto-ground would place a ground on a `pull_quote` / `ledger` / `bullet_list` / `comparison_table`,
the composer would faithfully RENDER it, and `scene_media()` would then score that scene `none` — the
ground credited nothing toward `coverage` AND the scene was still flagged by the long-ungrounded-hold
advisory. The author was being told to fix a thing the metric refused to see (11 scenes in the
diamond-v2 run). Two constants, one name, two truths: the drift class the honesty tests exist to catch.

Adding a capability here is cheap; the honesty test (`tests/test_block_registry.py`) re-derives every
set from the composer source and fails if this file drifts. That is what makes it safe to trust.
"""
from __future__ import annotations

from typing import FrozenSet

# Blocks whose composer calls `media_ground()` — i.e. `data.ground` is actually PAINTED for them.
# Every other template either carries its own dominant visual or ignores the field entirely, so
# writing `data.ground` there is a no-op (and, for auto-ground, silently consumes a pool asset).
GROUND_BLOCKS: FrozenSet[str] = frozenset({
    "statement", "stat", "bullet_list", "pull_quote", "comparison_table", "ledger",
})


def consumes_ground(block: str) -> bool:
    """True iff `data.ground` renders for this block."""
    return block in GROUND_BLOCKS


# --- what a block DISPLAYS, for narration matching -------------------------------------------------
# The sync matcher located scenes with hand-maintained key tuples that did not match what the composer
# actually paints. Live defect: `_content_time` read ("kicker","title","titleHi","center","headline"),
# so a `pull_quote`'s QUOTE — the only text on screen — was invisible to it. It corroborated against the
# KICKER instead, which echoed the narrator's lead-in at 0s, so a 14-second text-before-voice lead went
# undetected and shipped (the quote appeared at 12:23, was spoken at 12:34).
#
# Two different questions, kept separate on purpose:
#   * WHERE does this scene go?      -> the author's `anchor` (an instruction)
#   * Is what's on screen said NOW?  -> `visible_text` (what the viewer reads)
# Corroborating an anchor against itself is what made the gate blind whenever an anchor existed.

# Keys that are DESIGN or PLUMBING — never spoken, so never evidence of when a scene's topic surfaces.
# `kicker` is here because bridge/catalog.json declares it verbatim: "small eyebrow label (design intent,
# not narration)". It was ALSO driving placement, which forced authors to rewrite design copy to appease
# a timing matcher (FRANCES GERETY -> THE DETAIL THAT LANDS HARDEST).
NON_NARRATION_KEYS = frozenset({
    "kicker", "eyebrow", "variant", "register", "reveal", "reveal_char", "cue", "_line_cues", "at",
    "value_source", "grade", "treatments", "fit", "side", "position", "motion", "arrange", "layout",
    "ground", "src", "image", "images", "subject", "avatar", "source", "kb", "type", "kind", "id",
    "color", "palette", "icon", "track", "align", "anchor", "operative", "hi", "cite", "credit",
})

_NON_TEXT_PREFIXES = ("assets/", "capture/", "http://", "https://", "data:", "#")


def _is_prose(v: str) -> bool:
    """A displayed STRING, not a path / colour / enum token. Enum-ish single lowercase words are dropped
    (they are block config, e.g. 'left', 'cover'); anything with a space is prose."""
    v = v.strip()
    if not v or v.lower().startswith(_NON_TEXT_PREFIXES):
        return False
    if " " in v:
        return True
    return len(v) >= 5 and not v.islower()          # 'GERETY' / 'Kimberley' yes; 'cover' / 'left' no


def visible_text(data, _depth: int = 0) -> str:
    """Every piece of PROSE a scene paints, walking nested items/steps/events/rows/sides.

    Key-agnostic by design: a flat top-level tuple silently missed `steps[]` (cycle/process),
    `events[]` (timeline), `items[]` (stat/bullet_list/ledger), `left`/`right` (comparison/
    juxtaposition) and `quote` — so those blocks could not corroborate their own placement.
    """
    if _depth > 6:
        return ""
    out = []
    if isinstance(data, dict):
        for k, v in data.items():
            if k in NON_NARRATION_KEYS or str(k).startswith("_"):
                continue
            out.append(visible_text(v, _depth + 1))
    elif isinstance(data, (list, tuple)):
        for v in data:
            out.append(visible_text(v, _depth + 1))
    elif isinstance(data, str):
        if _is_prose(data):
            out.append(data.strip())
    return " ".join(p for p in out if p).strip()
