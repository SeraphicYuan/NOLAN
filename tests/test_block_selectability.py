"""Every remotion-lib block is either authorable or a KNOWN reverse-orphan.

Pitfall #2 (capable-but-unauthored): a block that renders but no Director path
can select is dead capability. We can't wire all of them today, but the set is
PINNED here — wiring one removes it from the list; adding a new render-only
block without an authoring path fails this test. The set can only shrink.
"""
from pathlib import Path

from nolan.webui.showcase_catalog import library_orphans

REPO = Path(__file__).resolve().parents[1]

# Blocks that render but have no Director block-template authoring path (2026-07).
# Shrink this by wiring a layout_blocks template + adapter (or delete the block).
KNOWN_ORPHANS = {
    "ArchetypeCards", "Distribution", "Formula", "Heatmap",
    "LottieIcon", "UnlockGrid", "ValueLadder", "WebVsBoxes",
}


def test_no_new_unauthorable_blocks():
    current = set(library_orphans(REPO))
    new = current - KNOWN_ORPHANS
    assert not new, (
        f"new render-only block(s) with no authoring path: {sorted(new)} — "
        "wire a layout_blocks template + adapter, or add to KNOWN_ORPHANS with a reason")


def test_known_orphans_still_exist_or_shrink():
    # if a block was wired (removed from orphans) update KNOWN_ORPHANS so the
    # list reflects reality — it should never claim orphans that are gone.
    current = set(library_orphans(REPO))
    stale = KNOWN_ORPHANS - current
    assert not stale, f"KNOWN_ORPHANS lists blocks that are no longer orphaned (wire done?): {sorted(stale)}"
