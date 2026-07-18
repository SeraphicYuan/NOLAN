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
    assert comp.block_archetype("linedraw") == "focal-card"
    assert comp.block_archetype("nope") is None


def test_every_catalog_block_is_classified_by_an_archetype():
    # coverage (both directions): every composer scene_template + component maps to exactly one archetype,
    # except the archetype-agnostic escape hatch(es). No orphan block that block_archetype() returns None for.
    cat = json.loads((REPO / "render-service" / "_lab_hyperframes" / "bridge" / "catalog.json").read_text(encoding="utf-8"))
    blocks = set(cat.get("scene_templates", {})) | set(cat.get("components", {}))
    orphans = sorted(b for b in blocks if b not in comp.ARCHETYPE_EXEMPT_BLOCKS and comp.block_archetype(b) is None)
    assert not orphans, f"catalog blocks with no archetype (classify in archetypes.json blocks[]): {orphans}"
    # the exempt set is real (present in the catalog) — no stale exemptions
    assert comp.ARCHETYPE_EXEMPT_BLOCKS <= blocks, "ARCHETYPE_EXEMPT_BLOCKS names a block not in the catalog"


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


def test_scene_authoring_prompt_archetype_vocab_matches_registry():
    # the orchestrator's scene-authoring prompt lists an archetype vocabulary — it must match the registry
    # EXACTLY (docs claim, tests enforce: no drift between the prompt and the archetype ids)
    import re
    from nolan.scenes import PASS2_SCENES_PROMPT   # the beats->visual-scenes authoring prompt
    m = re.search(r'"archetype":\s*"([a-z0-9\-|]+)"', PASS2_SCENES_PROMPT)
    assert m, "no archetype field in the scene-authoring prompt schema"
    listed = set(m.group(1).split("|"))
    assert listed == set(comp.ids()), f"scene prompt archetypes {listed} != registry {set(comp.ids())}"


def test_render_gate_judge_prompt_is_archetype_aware():
    from nolan.hyperframes.render_gate import judge_prompt
    base = judge_prompt("a beat")
    assert '"composed"' not in base                      # no archetype -> no layout check (back-compat)
    with_a = judge_prompt("a beat", archetype="centered-hero")
    assert "centered-hero" in with_a and '"composed"' in with_a   # archetype -> the VLM checks the layout


def test_brief_section_renders_named_archetype_and_grid():
    s = comp.brief_section("centered-hero")
    assert "centered-hero" in s and "Intent:" in s and "rule-of-thirds" in s
    assert "Exemplar" in s          # centered-hero has a promoted exemplar
    assert "85%" in s               # the caption keep-out comes from the registry grid (one source)
