"""Every Chapter-hostable step name is classified for the contact gate.

The Video-flagged-as-overflow incident: a new step type shipped without a
gate classification and the pre-flight refused a correct render. This makes
the omission impossible — a new block file or hosted comp fails here until
someone decides media (overflow skipped) or text (overflow applies).
"""

import re
from pathlib import Path

from nolan.flows.gate.contact import _MEDIA_BLOCKS, _TEXT_BLOCKS

REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "render-service" / "remotion-lib" / "src"


def _hostable_names() -> set:
    names = {p.stem for p in (LIB / "blocks" / "library").glob("*.tsx")}
    comps_src = (LIB / "comps.ts").read_text(encoding="utf-8")
    m = re.search(r"export const COMPS[^{]*\{(.*?)\n\};", comps_src, re.S)
    body = m.group(1)
    for line in body.splitlines():
        line = line.split("//")[0].strip().rstrip(",")
        if not line:
            continue
        key = line.split(":")[0].strip()
        if re.fullmatch(r"[A-Za-z0-9_]+", key):
            names.add(key)
    names.add("Video")                       # the raw-footage pseudo-block
    return names


def test_every_hostable_step_is_classified():
    names = _hostable_names()
    assert len(names) > 40, "hostable-name discovery looks broken"
    unclassified = names - _MEDIA_BLOCKS - _TEXT_BLOCKS
    assert unclassified == set(), (
        f"unclassified step type(s) {sorted(unclassified)} — add each to "
        "_MEDIA_BLOCKS (full-bleed imagery: overflow check skipped) or "
        "_TEXT_BLOCKS (typography/graphic: overflow check applies) in "
        "nolan/flows/gate/contact.py")


def test_no_step_is_both():
    both = _MEDIA_BLOCKS & _TEXT_BLOCKS
    assert both == set(), f"ambiguous classification: {sorted(both)}"


def test_no_phantom_classifications():
    """Classified names must exist — a rename can't leave a stale entry."""
    names = _hostable_names()
    # promoted comps register dynamically; only check the static universe
    phantom = (_MEDIA_BLOCKS | _TEXT_BLOCKS) - names - {"RouteMap"}
    phantom = {p for p in phantom
               if not (LIB / f"{p}.tsx").exists()
               and not (LIB / "promoted" / f"{p}.tsx").exists()}
    assert phantom == set(), f"classified but nonexistent: {sorted(phantom)}"
