"""Block CAPABILITIES — what each composer template actually consumes.

The truth about a block lives in `bridge/compose.py` (ONE composer since the 2026-07-26 Tier-2
merge — the split was what let 14 blocks drift outside the gates): a block consumes a
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

# Blocks that paint `data.ground` through `_data_ground()` instead — the LAYER-3 ambient ground behind
# a data viz, with a legibility veil over it so thin marks still read. Same authored field, same real
# pixels on screen, different composer helper: 11 compose.py data blocks had it and the 14 Tier-2 ones
# gained it in the 2026-07-26 parity pass.
#
# It is a SEPARATE set from GROUND_BLOCKS on purpose. `coverage` must credit both (a photo behind a
# chart is media on screen — scoring it "none" is exactly the contradiction item 7 fixed one layer up,
# where grounding a pull_quote credited nothing while still tripping the long-hold advisory). But
# auto-ground places media only on GROUND_BLOCKS: an ambient ground behind data is an editorial choice
# the author makes, not one a pre-pass should make for them.
DATA_GROUND_BLOCKS: FrozenSet[str] = frozenset({
    "chart", "connection_board", "cycle", "funnel", "pie", "quadrant", "sankey", "scale", "spans",
    "spectrum", "venn",
    "bar_race", "data_table", "dumbbell", "gauge", "histogram", "isotype", "layout", "process",
    "slope", "small_multiples", "stream", "trajectory",
})

ANY_GROUND_BLOCKS: FrozenSet[str] = GROUND_BLOCKS | DATA_GROUND_BLOCKS


def consumes_ground(block: str) -> bool:
    """True iff `data.ground` renders for this block, by either mechanism."""
    return block in ANY_GROUND_BLOCKS


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


def visible_strings(data, _depth: int = 0) -> list:
    """Every piece of PROSE a scene paints, as SEPARATE strings, in document order.

    Key-agnostic by design: a flat top-level tuple silently missed `steps[]` (cycle/process),
    `events[]` (timeline), `items[]` (stat/bullet_list/ledger), `left`/`right` (comparison/
    juxtaposition) and `quote` — so those blocks could not corroborate their own placement.

    Kept SEPARATE (rather than pre-joined) because word ORDER is only meaningful WITHIN one displayed
    string. A bag-of-words matcher does not care, but a phrase matcher does: concatenating a title and
    a caption invents an adjacency that is on screen nowhere and is spoken nowhere.
    """
    if _depth > 6:
        return []
    out = []
    if isinstance(data, dict):
        for k, v in data.items():
            if k in NON_NARRATION_KEYS or str(k).startswith("_"):
                continue
            out.extend(visible_strings(v, _depth + 1))
    elif isinstance(data, (list, tuple)):
        for v in data:
            out.extend(visible_strings(v, _depth + 1))
    elif isinstance(data, str):
        if _is_prose(data):
            out.append(data.strip())
    return out


def visible_text(data, _depth: int = 0) -> str:
    """Everything a scene paints, as ONE string — the bag-of-words view. See `visible_strings`."""
    return " ".join(p for p in visible_strings(data, _depth) if p).strip()


# --- per-element reveal CUES ------------------------------------------------------------------------
# Blocks whose composer reads the author-supplied `at` (a per-element reveal time). The other 24 ignore
# it, and `author.py` accepted it anyway: a `timeline` authored with `events[].at` validates rc=0 "OK"
# and the cue does nothing. That is the phantom-field class from docs/WIRING_CHECKLIST.md — a
# gate-passing, INERT field, strictly worse than either supporting it or refusing it, because the author
# believes they timed the reveal and nothing on screen disagrees.
#
# Note `timeline`'s schema never declares `at` at all — so this is not "the schema promises what the
# block ignores", it is "the gate accepts what the schema never offered".
CUE_BLOCKS: FrozenSet[str] = frozenset({
    "annotate", "bullet_list", "chart", "collage", "connection_board", "cycle", "data_table", "document",
    "dumbbell", "funnel", "gauge", "geo", "histogram", "isotype", "layout", "ledger", "pie", "process",
    "quadrant", "sankey", "scale", "slope", "small_multiples", "spans", "spectrum", "stat", "trajectory",
    "venn",
})

CUE_KEY = "at"


def consumes_cues(block: str) -> bool:
    """True iff the block schedules its elements from an author-supplied `at`."""
    return block in CUE_BLOCKS


def find_cue_fields(data, _path: str = "data") -> list:
    """Every place an `at` cue is authored in a scene's data -> ["data.events[0].at", ...].

    Walks nested element lists (events/items/steps/rows/slices/...) because that is where a cue is
    actually written; a top-level check would miss all of them.
    """
    out = []
    if isinstance(data, dict):
        for k, v in data.items():
            if k == CUE_KEY and isinstance(v, (int, float)) and not isinstance(v, bool):
                out.append(f"{_path}.{k}")
            else:
                out.extend(find_cue_fields(v, f"{_path}.{k}"))
    elif isinstance(data, (list, tuple)):
        for i, v in enumerate(data):
            out.extend(find_cue_fields(v, f"{_path}[{i}]"))
    return out
