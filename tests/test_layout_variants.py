"""Layout-variant registry honesty (composition-quality program P3).

The module contract: registry + authored field (data.variant) + executor (block branch) + honesty test.
A variant declared in themes/composition/layout_variants.json but never rendered by its block is a
phantom (the `transition` / note-edit lesson). These gates enforce parity + the selection contract:
  1. every registry block is a real compose.BLOCKS block;
  2. every variant id is CONSUMED (referenced) in compose.py — no phantom variants;
  3. every auto/default id is a real variant of that block;
  4. _resolve_variant's hybrid contract: override > auto-by-count > default, variety rotates, unknown->None.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge"
for _p in (str(REPO / "src"), str(BRIDGE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import compose  # noqa: E402

SRC = (BRIDGE / "compose.py").read_text(encoding="utf-8")
REG = json.loads((REPO / "themes" / "composition" / "layout_variants.json").read_text(encoding="utf-8"))["blocks"]


def test_every_registry_block_is_a_real_block():
    for b in REG:
        assert b in compose.BLOCKS, f"variant-registry block {b!r} is not in compose.BLOCKS"


def test_every_variant_is_consumed_by_its_block():
    """A variant id must appear in compose.py (a `.v-<id>`/`.sv-<id>` CSS class or a literal branch) —
    else nothing renders it (the phantom-field lesson: schema without a consumer is a bug)."""
    for b, reg in REG.items():
        for v in reg["variants"]:
            assert v in SRC, f"variant {b}/{v!r} is declared but never referenced in compose.py (phantom)"


def test_auto_and_default_ids_are_valid_variants():
    for b, reg in REG.items():
        vs = set(reg["variants"])
        assert reg.get("default") in vs, f"{b}: default {reg.get('default')!r} is not one of {vs}"
        for k, v in reg.get("auto", {}).items():
            assert v in vs, f"{b}: auto[{k!r}]={v!r} is not one of {vs}"


def test_resolve_variant_hybrid_contract():
    # explicit override wins
    assert compose._resolve_variant("stat", {"items": [1], "variant": "lead-rail"}) == "lead-rail"
    # auto by content count
    assert compose._resolve_variant("stat", {"items": [1]}) == "hero-single"
    assert compose._resolve_variant("stat", {"items": [1, 2]}) == "centered-row"
    # a block with no registry entry is untouched
    assert compose._resolve_variant("geo", {}) is None
    # variety: the same content twice in a row does not repeat the variant
    first = compose._resolve_variant("stat", {"items": [1, 2]})
    assert compose._resolve_variant("stat", {"items": [1, 2]}, prev=first) != first
