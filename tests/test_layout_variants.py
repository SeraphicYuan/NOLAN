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


# --- glass belongs to a PANEL, and the registry says which arrangements are panels ------------------

def _wrap_of(block, variant, **data):
    import re
    sc = {"id": "x1", "type": block, "start": 0.0, "dur": 10.0, "_variant": variant,
          "data": dict({"register": "footage",
                        "ground": {"kind": "image", "src": "assets/nope.jpg"}}, **data)}
    out = str(compose.BLOCKS[block]("x1", sc))
    cls = {"pull_quote": "pq-wrap", "comparison_table": "ct-wrap"}[block]
    m = re.search(r'<div class="' + cls + r'[^"]*"[^>]*>', out)
    return m.group(0) if m else ""


_PANEL_CASES = {
    "pull_quote": dict(quote="a quoted sentence here", cite="someone, 1889"),
    "comparison_table": dict(columns=[{"label": "a"}], rows=[{"label": "r", "cells": ["yes"]}]),
}


def test_glass_lands_only_on_arrangements_the_registry_calls_panels():
    """A frosted plate over a FULL-BLEED wrapper is not a panel, it is a frosted windshield.

    `.pq-wrap` / `.ct-wrap` are `position:absolute;inset:0`, so 3 of pull_quote's 4 variants were
    laying a 26px blur and a ~54% tint over the ENTIRE picture — diamond-v3 at 3:40 is an Oppenheimer
    portrait washed to flat beige. `highlight_statement` had it right all along: it emits `.stmt-card`
    only for `framed-card`. The predicate is the registry's own `zone == "framed"`, not a second list.
    """
    for block, data in _PANEL_CASES.items():
        variants = REG[block]["variants"]
        panels = [v for v, m in variants.items() if m.get("zone") == "framed"]
        assert panels, f"{block}: expected at least one framed variant to carry the glass"
        for v in variants:
            wrap = _wrap_of(block, v, **data)
            assert wrap, f"{block}/{v} rendered no wrapper"
            has_glass = "glass" in wrap
            assert has_glass == (v in panels), (
                f"{block}/{v}: zone={variants[v].get('zone')!r} but glass={has_glass} — glass must "
                f"follow the registry's panel zones")


def test_a_panel_rule_never_repaints_the_glass_opaque():
    """CSS specificity, as a contract rather than a coincidence.

    `.glass` is (0,1,0). A variant rule like `.blk-pull_quote.sv-framed .pq-wrap` is (0,3,0), so an
    unguarded `background:var(--surface)` in it WINS and the frosted plate renders as a solid slab —
    tint solved, backdrop blurred, nothing visible (diamond-v3 3:16 shipped `--glass-tint:56` under an
    opaque card). Any rule that paints a glass-capable wrapper must exclude `.glass`.

    `.stmt-card` is the instructive near-miss: it paints `background:var(--surface)` at the SAME
    specificity as `.glass` and survives only because `.glass` happens to be declared later in the
    sheet. Source order is not a contract, so it is held to the same rule here.
    """
    import re
    src = compose.__dict__["__file__"]
    css = Path(src).read_text(encoding="utf-8")
    wrappers = ("pq-wrap", "ct-wrap", "stmt-card")
    offenders = []
    for rule in re.finditer(r"([^\n{}]*\.(?:" + "|".join(wrappers) + r")[^\n{}]*)\{([^}]*)\}", css):
        sel, body = rule.group(1).strip(), rule.group(2)
        if re.search(r"(?<!-)\bbackground\s*:", body) and ":not(.glass)" not in sel:
            offenders.append(sel[:96])
    assert not offenders, ("these rules repaint a glass-capable wrapper — add `:not(.glass)`:\n  "
                           + "\n  ".join(offenders))


def test_ink_on_a_plate_is_scoped_to_the_plate():
    """"A panel replaces the ground for everything inside it" — only where a panel exists.

    The footage register normally paints light text with a drop shadow so it survives a photograph; a
    panel overrides that with theme ink, because on a frosted plate ink is what reads. Those overrides
    were written when `.pq-wrap` was always a plate. It is not: on every non-framed variant it is now
    bare, and the unscoped rule painted dark ink straight onto a portrait — diamond-v3's 3:41 quote
    came back illegible the moment the plate was correctly removed. Each override must name `.glass`.
    """
    import re
    css = Path(compose.__file__).read_text(encoding="utf-8")
    bad = []
    for rule in re.finditer(r"([^\n{}]*\{[^}]*\})", css):
        sel, body = rule.group(1).split("{", 1)
        if "text-shadow:none" not in body:
            continue
        for part in sel.split(","):
            part = part.strip()
            if not part.startswith(".footage"):
                continue
            # a wrapper that is only SOMETIMES a panel must be qualified by .glass
            if any(w in part for w in ("pq-wrap", "ct-wrap")) and ".glass" not in part:
                bad.append(part[:80])
    assert not bad, ("these kill the footage register's legibility treatment on a wrapper that may have "
                     f"no plate behind it — qualify with `.glass`: {bad}")
