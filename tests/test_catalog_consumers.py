"""Catalog→decision-point routing (WIRING_CHECKLIST pitfall #5, consumption).

An umbrella's catalog existing (and being registry-synced) is not enough —
it must REACH each decision point that chooses from it. CATALOG_CONSUMERS
declares where; these tests grep that the linkage is real, so a refactor
that silently orphans a catalog fails the suite.

Also pins the two incidents this rule came from:
- tempo_plan kept a private transition tuple that nolan.editing mirrored
  by comment (two dialects for one decision);
- the evoke planner's operator menu was hand-written prose duplicating
  OPERATORS' when_to_use (catalog-blind agent).
"""

from pathlib import Path

import pytest

from nolan.system_map import CATALOG_CONSUMERS, UMBRELLA_WIRING

REPO = Path(__file__).resolve().parents[1]


def _entries():
    for umbrella, consumers in CATALOG_CONSUMERS.items():
        for file, token, role in consumers:
            yield umbrella, file, token, role


@pytest.mark.parametrize("umbrella,file,token,role",
                         list(_entries()),
                         ids=[f"{u}:{Path(f).name}" for u, f, _t, _r in _entries()])
def test_catalog_reaches_consumer(umbrella, file, token, role):
    p = REPO / file
    assert p.exists(), f"{umbrella}: consumer file {file} missing"
    text = p.read_text(encoding="utf-8", errors="replace")
    assert token in text, (
        f"{umbrella}: {file} no longer contains {token!r} — the catalog is "
        f"orphaned from its decision point ({role})")


def test_every_umbrella_declares_consumption():
    missing = set(UMBRELLA_WIRING) - set(CATALOG_CONSUMERS)
    assert not missing, (
        f"umbrellas with no declared catalog consumer: {sorted(missing)} — "
        "add CATALOG_CONSUMERS entries (who reads this catalog when deciding?)")


# --- incident pins -----------------------------------------------------------

def test_tempo_has_no_private_transition_dialect():
    src = (REPO / "src/nolan/tempo_plan.py").read_text(encoding="utf-8")
    assert '_TRANSITIONS = ("cut"' not in src, (
        "tempo_plan regrew a private transition tuple — import TRANSITIONS "
        "from nolan.editing instead (one registry per decision)")


def test_evoke_planner_menu_is_generated():
    from nolan.evoke_broll import OPERATORS, operator_menu
    menu = operator_menu()
    for name, spec in OPERATORS.items():
        assert f"- {name}:" in menu
        # a distinctive fragment of when_to_use must appear — the menu is
        # built FROM the registry, not parallel prose
        fragment = spec["when_to_use"].split(";")[0].split(".")[0][:40]
        assert fragment in menu, f"{name}: menu does not carry when_to_use"


def test_planner_prompt_uses_the_generated_menu():
    src = (REPO / "src/nolan/evoke_broll.py").read_text(encoding="utf-8")
    body = src[src.find("async def _auto_plan"):src.find("async def _auto_judge")]
    assert "operator_menu()" in body, (
        "_auto_plan no longer injects operator_menu() — the planner is "
        "catalog-blind again")
    assert "- literal: the beat names" not in body, (
        "_auto_plan regrew a hand-written operator list")
