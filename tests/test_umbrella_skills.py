"""Umbrella catalogs can't rot — skills, registries and the map must agree.

The module contract's enforcement for motion + pairing (editing has its own
in test_editing.py): every registry capability appears in its umbrella skill
doc, nothing undocumented hides in the doc, the public pairing catalog
mirrors the internal prompt table, and /api/map serves it all.
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _doc_headings(path: Path) -> set:
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r"^## ([a-z][a-z0-9-]+)$", text, re.M))


# --- motion ---------------------------------------------------------------------

def test_motion_skill_covers_every_builtin_effect():
    from nolan.motion.registry import REGISTRY
    builtin = {e.id for e in REGISTRY if not e.provenance}
    headings = _doc_headings(REPO / "skills" / "common" / "motion-craft.md")
    assert builtin - headings == set(), "skill doc missing effects"
    assert headings - builtin == set(), "skill doc lists unregistered effects"


def test_every_builtin_effect_has_when_to_use():
    from nolan.motion.registry import REGISTRY
    missing = [e.id for e in REGISTRY if not e.provenance and not e.when_to_use]
    assert missing == [], f"effects without craft guidance: {missing}"


# --- effects (visual treatments umbrella) --------------------------------------

def test_effects_skill_covers_every_treatment():
    from nolan.effects.registry import REGISTRY
    ids = {e.id for e in REGISTRY if not getattr(e, "provenance", None)}
    headings = _doc_headings(REPO / "skills" / "common" / "effects-craft.md")
    assert ids - headings == set(), f"effects skill missing treatments: {ids - headings}"
    assert headings - ids == set(), f"effects skill lists unregistered treatments: {headings - ids}"


def test_every_treatment_has_when_to_use():
    from nolan.effects.registry import REGISTRY
    missing = [e.id for e in REGISTRY if not getattr(e, "provenance", None) and not e.when_to_use]
    assert missing == [], f"treatments without craft guidance: {missing}"


# --- pairing --------------------------------------------------------------------

def test_pairing_catalog_mirrors_prompt_table():
    from nolan.evoke_broll import OPERATORS, _OP
    assert set(OPERATORS) == set(_OP), (
        "public OPERATORS catalog drifted from the internal _OP prompt table")
    for k, v in OPERATORS.items():
        assert v.get("purpose") and v.get("when_to_use"), f"{k} lacks guidance"
        assert isinstance(v.get("automated_bridge"), bool)


def test_composition_skill_covers_every_archetype():
    from nolan import composition as comp
    headings = _doc_headings(REPO / "skills" / "common" / "composition-craft.md")
    ids = set(comp.ids())
    assert ids - headings == set(), f"composition skill missing archetypes: {ids - headings}"
    assert headings - ids == set(), f"composition skill lists unregistered archetypes: {headings - ids}"


def test_pairing_skill_covers_every_operator():
    from nolan.evoke_broll import OPERATORS
    headings = _doc_headings(REPO / "skills" / "common" / "pairing-craft.md")
    assert set(OPERATORS) - headings == set()
    assert headings - set(OPERATORS) == set()


def test_automated_bridge_flags_match_bridge_queries_default():
    # bridge_queries' unattended default must only use judgment-safe operators
    from nolan.evoke_broll import OPERATORS
    import inspect
    from nolan.evoke_broll import bridge_queries
    default = inspect.signature(bridge_queries).parameters["operators"].default
    assert set(default) == {k for k, v in OPERATORS.items()
                            if v["automated_bridge"]}


# --- index + map ----------------------------------------------------------------

def test_umbrella_skills_registered_in_index():
    idx = json.loads((REPO / "skills" / "index.json").read_text(encoding="utf-8"))
    ids = {s["id"]: s for s in idx["skills"]}
    for sid in ("common.editing-craft", "common.motion-craft",
                "common.pairing-craft", "common.composition-craft"):
        assert sid in ids, f"{sid} not in skills/index.json"
        assert (REPO / ids[sid]["path"]).exists()
    assert idx["count"] == len(idx["skills"])


def test_map_serves_the_umbrella_catalog():
    from nolan.system_map import _umbrellas
    um = _umbrellas()
    for name in ("editing", "motion", "pairing", "blocks", "themes"):
        assert isinstance(um.get(name), list) and um[name], f"{name} missing/empty"
    for entry in um["editing"] + um["motion"] + um["pairing"]:
        assert entry.get("when_to_use") or entry.get("purpose")
