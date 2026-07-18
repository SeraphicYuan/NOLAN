"""Composition archetype registry (nolan.composition): the registry loads + is internally consistent
(exemplars exist, blocks parity with the composer catalog), and resolve() is content-first with the
theme's allowed set constraining and an explicit direction overriding (the A/B/C/D-proven lever)."""
import json
from pathlib import Path

from nolan import composition as comp

REPO = Path(__file__).resolve().parents[1]


def test_registry_loads_and_is_complete():
    a = comp.archetypes()
    assert len(a) >= 8
    req = {"intent", "when_to_use", "serves_beats", "anchor", "balance", "density", "blocks", "exemplar"}
    for aid, spec in a.items():
        assert req <= set(spec), f"{aid} missing {req - set(spec)}"
    g = comp.grid()
    assert g["columns"] == 12 and "caption_keep_out" in g["safe_areas"]


def test_every_exemplar_path_exists_on_disk():
    # the honesty test the audit flagged: a non-null exemplar must exist + load (no dangling paths)
    for aid, spec in comp.archetypes().items():
        rel = spec.get("exemplar")
        if rel:
            f = comp.REGISTRY_PATH.parent / rel
            assert f.exists(), f"{aid}: exemplar {rel} missing on disk"
            ex = comp.exemplar(aid)
            assert ex and ex.get("html"), f"{aid}: exemplar unreadable / no html"


def test_blocks_parity_with_composer_catalog():
    # every block an archetype claims must be a real composer block/component (no drift into a 2nd dialect)
    cat = json.loads((REPO / "render-service" / "_lab_hyperframes" / "bridge" / "catalog.json").read_text(encoding="utf-8"))
    known = set(cat.get("scene_templates", {})) | set(cat.get("components", {}))
    for aid, spec in comp.archetypes().items():
        for b in spec.get("blocks", []):
            assert b in known, f"{aid}: block {b!r} not in the composer catalog {sorted(known)}"


def test_block_archetype_derivation():
    assert comp.block_archetype("stat") == "centered-hero"
    assert comp.block_archetype("comparison") == "split-screen"
    assert comp.block_archetype("statement") == "editorial-column"
    assert comp.block_archetype("spotlight") == "focal-card"
    assert comp.block_archetype("nope") is None


def test_resolve_is_content_first_with_direction_override_and_allowed_constraint():
    # scene type -> archetype (content-first)
    assert comp.resolve(scene_type="stat") == "centered-hero"
    assert comp.resolve(scene_type="comparison") == "split-screen"
    # explicit direction OVERRIDES the scene type (the proven lever)
    assert comp.resolve(scene_type="statement", direction="centre it, use the full canvas") == "centered-hero"
    assert comp.resolve(scene_type="statement", direction="a split-screen comparison") == "split-screen"
    # beat label when no type
    assert comp.resolve(beat="a big question") == "centered-hero"
    # allowed CONSTRAINS: resolved candidate outside allowed -> first allowed
    assert comp.resolve(scene_type="stat", allowed=["editorial-column", "swiss-grid"]) == "editorial-column"
    # no signal -> the non-left default, and it's always a valid id
    assert comp.resolve() == "centered-hero"
    assert comp.resolve(scene_type="xyz", beat="") in comp.ids()


def test_brief_section_renders_named_archetype_and_grid():
    s = comp.brief_section("centered-hero")
    assert "centered-hero" in s and "Intent:" in s and "rule-of-thirds" in s
    assert "Exemplar" in s          # centered-hero has a promoted exemplar
    assert "83%" in s               # the caption keep-out comes from the registry grid (one source)
