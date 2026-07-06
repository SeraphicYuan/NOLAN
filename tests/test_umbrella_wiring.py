"""Umbrella wiring manifest — every umbrella has an author AND an executor.

WIRING_CHECKLIST pitfall #2 (capable-but-unauthored), mechanized: the motion
library sat unreachable from the spine for weeks because nothing asserted
that an umbrella's catalog had an authoring surface. Now every umbrella in
the capability map must declare both wires, and each declaration must be
TRUE (the named file contains the named token).
"""

from pathlib import Path

from nolan.system_map import UMBRELLA_WIRING, _umbrellas

REPO = Path(__file__).resolve().parents[1]


def test_every_umbrella_declares_both_wires():
    live = {k for k, v in _umbrellas().items() if isinstance(v, list)}
    missing = live - set(UMBRELLA_WIRING)
    assert missing == set(), (
        f"umbrella(s) {sorted(missing)} appear in the capability map with no "
        "UMBRELLA_WIRING declaration — name the authoring surface and the "
        "executor (see docs/WIRING_CHECKLIST.md)")
    for name, wiring in UMBRELLA_WIRING.items():
        assert wiring.get("authored_by"), f"{name}: no authoring surface"
        assert wiring.get("executed_by"), f"{name}: no executor"


def test_every_declared_wire_is_true():
    for name, wiring in UMBRELLA_WIRING.items():
        for kind in ("authored_by", "executed_by"):
            for rel, token in wiring[kind]:
                p = REPO / rel
                assert p.exists(), f"{name}.{kind}: {rel} does not exist"
                src = p.read_text(encoding="utf-8", errors="replace")
                assert token in src, (
                    f"{name}.{kind}: {rel} never mentions {token!r} — the "
                    "manifest is lying (or a refactor moved the wire; update "
                    "the manifest to the new truth)")


def test_stale_wiring_entries_fail():
    live = {k for k, v in _umbrellas().items() if isinstance(v, list)}
    stale = set(UMBRELLA_WIRING) - live
    assert stale == set(), f"UMBRELLA_WIRING names unknown umbrella(s): {stale}"
