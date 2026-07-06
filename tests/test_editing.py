"""Editing umbrella — registry honesty + authoring validation + wiring.

The module contract's enforcement arm: the registry, the skill doc, the
skills index, and the executors must agree — a catalog that can drift from
the code is worse than none.
"""

import json
import re
from pathlib import Path

from nolan.editing import (BY_ID, REGISTRY, TRANSITIONS,
                           validate_plan_editing, validate_scene_editing)

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills" / "common" / "editing-craft.md"


# --- registry sanity -----------------------------------------------------------

def test_registry_entries_are_complete():
    assert len(REGISTRY) >= 3
    for t in REGISTRY:
        assert t.purpose and t.when_to_use, f"{t.id} lacks craft guidance"
        assert t.authored_by, f"{t.id} must name its authored field"
        assert t.executor, f"{t.id} must name its executor"
        assert t.scope in ("boundary", "scene", "project")
        # the umbrella's legality gate: everything offered preserves duration
        assert t.duration_preserving, f"{t.id} would break narration-owns-duration"


def test_transitions_mirror_tempo_plan():
    from nolan.tempo_plan import _TRANSITIONS
    assert TRANSITIONS == _TRANSITIONS


# --- the honesty test: skill doc <-> registry <-> index -------------------------

def test_skill_doc_covers_every_technique():
    text = SKILL.read_text(encoding="utf-8")
    doc_headings = set(re.findall(r"^## ([a-z][a-z0-9-]+)$", text, re.M))
    registry_ids = set(BY_ID)
    missing = registry_ids - doc_headings
    orphans = doc_headings - registry_ids
    assert not missing, f"skill doc missing technique section(s): {missing}"
    assert not orphans, f"skill doc documents unregistered technique(s): {orphans}"


def test_skill_registered_in_index():
    idx = json.loads((REPO / "skills" / "index.json").read_text(encoding="utf-8"))
    entry = next((s for s in idx["skills"] if s["id"] == "common.editing-craft"), None)
    assert entry is not None
    assert (REPO / entry["path"]).exists()
    assert idx["count"] == len(idx["skills"])


# --- authoring validation --------------------------------------------------------

def test_validate_accepts_wellformed_scene():
    assert validate_scene_editing({
        "id": "s1", "transition": "dissolve",
        "shots": [{"src": "a.png", "place": [0.5, 0.5], "weight": 2},
                  {"src": "b.png"}]}) == []


def test_validate_names_malformed_shots():
    probs = validate_scene_editing({
        "id": "s1",
        "shots": [{"place": [0.5, 0.5]},              # no src
                  {"src": "b.png", "place": [1.5, 0]},  # out of range
                  {"src": "c.png", "weight": 0}]})      # weight <= 0
    assert len(probs) == 3
    assert all("s1" in p for p in probs)


def test_validate_rejects_unknown_transition():
    probs = validate_scene_editing({"id": "s2", "transition": "whip-pan"})
    assert probs and "whip-pan" in probs[0]


def test_validate_plan_walks_sections():
    plan = {"sections": {"A": [{"id": "s1", "transition": "cut"}],
                         "B": [{"id": "s2", "shots": "nope"}]}}
    probs = validate_plan_editing(plan)
    assert len(probs) == 1 and "s2" in probs[0]


# --- executor wiring (transition-in -> Chapter step) -----------------------------

def test_chapter_supports_transition_in():
    tsx = (REPO / "render-service" / "remotion-lib" / "src" / "Chapter.tsx"
           ).read_text(encoding="utf-8")
    assert "transitionIn" in tsx, "Chapter.tsx lost the transitionIn executor"
