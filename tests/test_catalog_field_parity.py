"""Field-level catalog honesty test (audit gap 5 + the "docs claim, tests enforce" meta-rule).

`check_catalog.py` enforces parity of block TYPES (every BLOCKS fn has a catalog entry and vice-versa)
but NOT of the per-block `data_schema` FIELDS. So a knob the composer reads but the catalog never
advertises (the `timeline.solo` / `spine` class of bug) is invisible to an authoring agent — it can't
invoke a capability it can't see. This test closes that: for every catalog block, every TOP-LEVEL data
key the compose.py executor actually reads (`d.get("x")` / `d["x"]`, plus one level of `_helper(sid, sc)`
delegation) must be advertised in that block's `data_schema`.

Direction enforced: consumed ⊆ advertised (no HIDDEN knob). The reverse (advertised-but-dead) is noisier
— a field can be consumed in shared CSS, the caption track, or the variant resolver — so it is reported
as an informational warning, not a hard failure.
"""
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge"
CATALOG = json.loads((BRIDGE / "catalog.json").read_text(encoding="utf-8"))


def _all_source() -> str:
    src = (BRIDGE / "compose.py").read_text(encoding="utf-8")
    ext = BRIDGE / "compose_extension.py"
    return src + "\n\n" + (ext.read_text(encoding="utf-8") if ext.exists() else "")


def _bodies(allsrc: str):
    defs = [(m.group(1), m.start()) for m in re.finditer(r"^def ([a-zA-Z_][a-zA-Z0-9_]*)\(", allsrc, re.M)]
    out = {}
    for i, (name, pos) in enumerate(defs):
        end = defs[i + 1][1] if i + 1 < len(defs) else len(allsrc)
        out[name] = allsrc[pos:end]
    return out


def _reads(body: str):
    return (set(re.findall(r'\bd\.get\(["\']([a-zA-Z_]\w*)["\']', body))
            | set(re.findall(r'\bd\[["\']([a-zA-Z_]\w*)["\']\]', body)))


def _consumed(fn: str, bodies) -> set:
    body = bodies.get(fn, "")
    keys = _reads(body)
    for helper in set(re.findall(r"\b(_[a-zA-Z0-9_]+)\(sid,\s*sc", body)):  # one-level delegation
        keys |= _reads(bodies.get(helper, ""))
    return keys


# keys a block reads that are legitimately NOT author-facing catalog fields, with justification:
IGNORE = {
    "parchment",   # a media_ground passthrough default (stat/others forward d.get("parchment") into ground)
}

BODIES = _bodies(_all_source())
BLOCKS = sorted(CATALOG["scene_templates"].items())


@pytest.mark.parametrize("block,spec", BLOCKS, ids=[b for b, _ in BLOCKS])
def test_no_hidden_knob(block, spec):
    """Every data key the executor reads is advertised in the catalog data_schema."""
    advertised = set(spec.get("data_schema", {}).keys())
    consumed = _consumed(spec.get("fn"), BODIES)
    hidden = consumed - advertised - IGNORE
    assert not hidden, (
        f"{block}: compose.py reads {sorted(hidden)} but catalog.json advertises none of them "
        f"— an authoring agent can't discover these knobs. Add them to the '{block}' data_schema "
        f"(or, if truly internal, to IGNORE with a justification)."
    )
