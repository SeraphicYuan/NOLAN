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
