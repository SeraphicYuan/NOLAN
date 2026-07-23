"""Unit tests for the Key-Assets P1 (decompose + consolidate) — pure prompt/parse/registry, no LLM.

Covers the parts that must never regress: kind/asset normalization, entity parsing (dedup, id
assignment, default-asset backfill, collage defaults), direction parsing (id filtering, orphan
sweep = no entity lost), and schema round-trip.
"""
import json

from nolan.keyassets import registry
from nolan.keyassets.consolidate import parse_directions
from nolan.keyassets.decompose import parse_entities
from nolan.keyassets.enrich import merge_entities
from nolan.keyassets.schema import KeyAssetsProposal


# --- registry -------------------------------------------------------------------------------------
def test_normalize_kind_synonyms_and_default():
    assert registry.normalize_kind("Company") == "organization"
    assert registry.normalize_kind("PERSON") == "person"
    assert registry.normalize_kind("ad") == "work"
    assert registry.normalize_kind("nonsense") == "concept"


def test_normalize_asset_type_and_collage_default():
    assert registry.normalize_asset_type("wordmark") == "logo"
    assert registry.normalize_asset_type("advertisement") == "document"
    assert registry.normalize_asset_type("clip") == "footage"
    assert registry.normalize_asset_type("???") == "photo"
    assert registry.collage_default("logo") is True        # logos want a cutout
    assert registry.collage_default("photo") is False


# --- decompose.parse_entities --------------------------------------------------------------------
def test_parse_entities_normalizes_dedups_and_ids():
    raw = json.dumps([
        {"name": "De Beers", "kind": "company", "priority": "hero",
         "narrative_role": "the cartel", "mentions": ["a man named Cecil Rhodes"],
         "desired_assets": [{"type": "wordmark", "note": "mono logo"}]},
        {"name": "De Beers", "kind": "organization"},       # dup name → dropped
        {"name": "Cecil Rhodes", "kind": "person"},         # no desired_assets → default portrait
        {"name": "", "kind": "person"},                     # empty name → skipped
    ])
    ents = parse_entities(raw)
    assert [e.name for e in ents] == ["De Beers", "Cecil Rhodes"]
    de = ents[0]
    assert de.kind == "organization" and de.priority == "hero"
    assert de.id == "ka_de_beers" and de.desired_assets[0].type == "logo"
    assert de.desired_assets[0].collage_ready is True       # logo → collage even though not set
    rhodes = ents[1]
    assert rhodes.desired_assets[0].type == "portrait"      # default for person
    assert rhodes.priority == "supporting"                  # default


def test_collage_flag_only_on_cutout_types():
    raw = json.dumps([
        {"name": "A Diamond Is Forever", "kind": "work",
         "desired_assets": [{"type": "artwork", "collage_ready": True}]},   # artwork → cutout meaningless
        {"name": "De Beers", "kind": "organization",
         "desired_assets": [{"type": "logo", "collage_ready": True}]},       # logo → keep
        {"name": "Cecil Rhodes", "kind": "person",
         "desired_assets": [{"type": "portrait", "collage_ready": True}]},   # portrait → keep
    ])
    ents = parse_entities(raw)
    assert ents[0].desired_assets[0].collage_ready is False    # artwork stripped
    assert ents[1].desired_assets[0].collage_ready is True
    assert ents[2].desired_assets[0].collage_ready is True


def test_parse_entities_relevance_exact_and_related():
    raw = json.dumps([
        {"name": "1947 campaign film", "kind": "work",
         "desired_assets": [{"type": "footage", "relevance": "exact"}]},
        {"name": "1950s wedding b-roll", "kind": "concept",
         "desired_assets": [{"type": "video", "relevance": "evocative"}]},  # synonym → related
    ])
    ents = parse_entities(raw)
    assert ents[0].desired_assets[0].relevance == "exact"
    assert ents[1].desired_assets[0].type == "footage"          # 'video' → footage
    assert ents[1].desired_assets[0].relevance == "related"     # 'evocative' → related
    # default when absent is 'exact'
    d = parse_entities(json.dumps([{"name": "X", "kind": "work",
                                    "desired_assets": [{"type": "photo"}]}]))
    assert d[0].desired_assets[0].relevance == "exact"


def test_merge_entities_dedups_names_and_fixes_id_collision():
    base = parse_entities(json.dumps([{"name": "De Beers", "kind": "organization"}]))
    extra = parse_entities(json.dumps([
        {"name": "De Beers", "kind": "organization"},           # dup name → dropped
        {"name": "De  Beers", "kind": "place"},                 # distinct name+kind, SAME slug → id suffixed
        {"name": "Kimberley Big Hole", "kind": "place"},
    ]))
    merged = merge_entities(base, extra)
    names = [e.name for e in merged]
    assert names == ["De Beers", "De  Beers", "Kimberley Big Hole"]
    ids = [e.id for e in merged]
    assert len(ids) == len(set(ids))                            # no id collision after merge
    assert ids[0] == "ka_de_beers" and ids[1] == "ka_de_beers_2"


def test_merge_entities_folds_near_dup_and_keeps_its_assets():
    base = parse_entities(json.dumps([
        {"name": "Edward Epstein", "kind": "person",
         "desired_assets": [{"type": "portrait"}]}]))
    extra = parse_entities(json.dumps([
        {"name": "Edward Epstein Interview", "kind": "person",    # same subject reframed → folded
         "desired_assets": [{"type": "footage", "relevance": "related"}]},
        {"name": "General Electric", "kind": "organization"}]))   # distinct → added
    merged = merge_entities(base, extra)
    assert [e.name for e in merged] == ["Edward Epstein", "General Electric"]   # interview NOT added
    epstein = merged[0]
    assert {a.type for a in epstein.desired_assets} == {"portrait", "footage"}  # its clip absorbed


def test_merge_entities_does_not_collapse_different_kinds():
    # 'De Beers' (org) must NOT swallow 'De Beers v. US' (event) — different kind
    base = parse_entities(json.dumps([{"name": "De Beers", "kind": "organization"}]))
    extra = parse_entities(json.dumps([{"name": "De Beers v. US case", "kind": "event"}]))
    merged = merge_entities(base, extra)
    assert [e.name for e in merged] == ["De Beers", "De Beers v. US case"]


def test_parse_entities_id_collision_suffix():
    raw = json.dumps([{"name": "The Ring", "kind": "work"}, {"name": "the ring!", "kind": "work"}])
    # different names (dedup is by exact lowercased name), same slug base → suffixed id
    ents = parse_entities(raw)
    assert len(ents) == 2 and ents[0].id == "ka_the_ring" and ents[1].id == "ka_the_ring_2"


# --- consolidate.parse_directions ----------------------------------------------------------------
def _ents(*names_kinds):
    raw = json.dumps([{"name": n, "kind": k} for n, k in names_kinds])
    return parse_entities(raw)


def test_parse_directions_assigns_and_filters_bad_ids():
    ents = _ents(("De Beers", "organization"), ("Cecil Rhodes", "person"), ("Lightbox", "organization"))
    raw = json.dumps([
        {"id": "de-beers-cartel", "title": "De Beers cartel",
         "entity_ids": ["ka_de_beers", "ka_cecil_rhodes", "ka_bogus"],  # bogus id filtered out
         "queries": ["De Beers history"]},
    ])
    directions, out = parse_directions(raw, ents)
    d0 = directions[0]
    assert d0.entity_ids == ["ka_de_beers", "ka_cecil_rhodes"]
    assert {e.id: e.direction for e in out}["ka_de_beers"] == "de-beers-cartel"


def test_parse_directions_sweeps_orphans_no_entity_lost():
    ents = _ents(("De Beers", "organization"), ("Jack Ogden", "person"))
    raw = json.dumps([{"id": "de-beers", "title": "De Beers", "entity_ids": ["ka_de_beers"]}])
    directions, out = parse_directions(raw, ents)
    # Jack Ogden was not claimed → gets a solo fallback direction; every entity has a direction
    assert all(e.direction for e in out)
    assert any(d.entity_ids == ["ka_jack_ogden"] for d in directions)


def test_parse_directions_dedupes_entity_across_directions():
    ents = _ents(("De Beers", "organization"))
    raw = json.dumps([
        {"id": "a", "title": "A", "entity_ids": ["ka_de_beers"]},
        {"id": "b", "title": "B", "entity_ids": ["ka_de_beers"]},   # already assigned → dropped here
    ])
    directions, _ = parse_directions(raw, ents)
    assert directions[0].entity_ids == ["ka_de_beers"]
    assert all("ka_de_beers" not in d.entity_ids for d in directions[1:])


# --- resolve / collect (pure parts) --------------------------------------------------------------
def test_queries_for_note_first_and_domain_weave():
    from types import SimpleNamespace
    from nolan.keyassets.resolve import queries_for
    org = SimpleNamespace(name="De Beers", kind="organization")
    d = SimpleNamespace(type="logo", note="official monochrome logo", relevance="exact")
    qs = queries_for(org, d, domain="diamond")
    assert qs[0] == "De Beers official monochrome logo"       # note-query is most specific → first
    assert "De Beers logo" in qs                              # name + qualifier
    assert not any("diamond" in q for q in qs)               # a specific ORG name isn't domain-woven
    # a CONCEPT with a terse name DOES get the domain woven in (the 'four Cs' → not 'four-stroke' fix)
    concept = SimpleNamespace(name="The Four Cs", kind="concept")
    dc = SimpleNamespace(type="document", note="", relevance="exact")
    assert any("diamond" in q for q in queries_for(concept, dc, domain="diamond"))
    # bare-name related clip still yields a single deduped query
    e2 = SimpleNamespace(name="1950s wedding b-roll", kind="concept")
    d2 = SimpleNamespace(type="footage", note="", relevance="related")
    assert queries_for(e2, d2) == ["1950s wedding b-roll"]


def test_verify_subject_weaves_domain_for_ambiguous_kinds():
    from types import SimpleNamespace
    from nolan.keyassets.resolve import _verify_subject
    concept = SimpleNamespace(name="The Four Cs", kind="concept")
    d = SimpleNamespace(type="document", note="GIA diamond grading chart", relevance="exact")
    s = _verify_subject(concept, d, domain="diamond")
    assert "The Four Cs" in s and "diamond" in s and "GIA diamond grading chart" in s
    person = SimpleNamespace(name="Ernest Oppenheimer", kind="person")
    dp = SimpleNamespace(type="portrait", note="", relevance="exact")
    assert _verify_subject(person, dp, domain="diamond") == "Ernest Oppenheimer"   # specific name, no weave


def test_boost_prefers_institutional_sources():
    from types import SimpleNamespace
    from nolan.keyassets.resolve import _boost
    res = [SimpleNamespace(source="ddgs"), SimpleNamespace(source="wikimedia"), SimpleNamespace(source="pexels")]
    ordered = [r.source for r in _boost(res, "logo")]          # logo prefers wikimedia
    assert ordered[0] == "wikimedia"


def test_write_manifest_attaches_resolved(tmp_path):
    from nolan.keyassets.collect import _write_manifest
    ents = _ents(("De Beers", "organization"))
    directions, ents = parse_directions(
        json.dumps([{"id": "d", "title": "D", "entity_ids": ["ka_de_beers"]}]), ents)
    prop = KeyAssetsProposal(comp="x", entities=ents, directions=directions)
    resolved = {"ka_de_beers": [{"file": "capture/keyassets/ka_de_beers_logo.jpg", "type": "logo",
                                 "variant": "original", "source": "wikimedia"}]}
    p = _write_manifest(tmp_path, prop, resolved)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["collected"] == 1
    ent = data["entities"][0]
    assert ent["resolved"][0]["file"].endswith("ka_de_beers_logo.jpg")


# --- Tier B querygen (hybrid identifiers + per-need queries) -------------------------------------
def test_querygen_apply_queries_dedups_and_caps():
    from nolan.keyassets.querygen import apply_queries
    from nolan.keyassets.schema import DesiredAsset, KeyEntity
    e = KeyEntity(id="ka_cecil_rhodes", name="Cecil Rhodes", kind="person",
                  desired_assets=[DesiredAsset(type="portrait"), DesiredAsset(type="photo")])
    parsed = {"identifiers": ["De Beers founder", "diamond magnate", "Cape Colony", "1888", "f", "g", "h"],
              "queries": {"0": ["Cecil Rhodes portrait", "Cecil Rhodes De Beers founder", "cecil rhodes portrait"],
                          "1": ["Cecil Rhodes photograph 1890s"]}}
    apply_queries(e, parsed, per_need=3)
    assert e.identifiers == ["De Beers founder", "diamond magnate", "Cape Colony", "1888", "f", "g"]  # cap 6
    assert e.desired_assets[0].queries == ["Cecil Rhodes portrait", "Cecil Rhodes De Beers founder"]  # deduped
    assert e.desired_assets[1].queries == ["Cecil Rhodes photograph 1890s"]


def test_queries_for_prefers_llm_queries_else_falls_back():
    from nolan.keyassets.resolve import queries_for
    from nolan.keyassets.schema import DesiredAsset, KeyEntity
    d = DesiredAsset(type="portrait", queries=["Cecil Rhodes De Beers founder", "Cecil John Rhodes portrait"])
    e = KeyEntity(id="x", name="Cecil Rhodes", kind="person", desired_assets=[d])
    qs = queries_for(e, d, domain="diamond")
    assert qs[0] == "Cecil Rhodes De Beers founder"           # LLM queries used verbatim, in order
    assert "Cecil Rhodes" in qs                               # bare-name safety net appended
    d2 = DesiredAsset(type="logo", note="mono logo")          # no queries → mechanical fallback
    e2 = KeyEntity(id="y", name="De Beers", kind="organization", desired_assets=[d2])
    assert any("De Beers" in q for q in queries_for(e2, d2))


def test_verify_subject_uses_identifiers_over_domain():
    from nolan.keyassets.resolve import _verify_subject
    from nolan.keyassets.schema import DesiredAsset, KeyEntity
    e = KeyEntity(id="x", name="Cecil Rhodes", kind="person",
                  identifiers=["De Beers founder", "diamond magnate", "Cape Colony", "extra"])
    s = _verify_subject(e, DesiredAsset(type="portrait", note="formal"), domain="diamond")
    assert "Cecil Rhodes" in s and "De Beers founder" in s and "formal" in s
    assert "extra" not in s                                   # only the first 3 identifiers


# --- P3 hero inventory (staging + honesty) -------------------------------------------------------
def test_hero_inventory_stages_lists_and_is_honest(tmp_path):
    import re
    from nolan.keyassets.inventory import HERO_END, HERO_START, write_hero_section
    ka = tmp_path / "capture" / "keyassets"
    (ka / "videos").mkdir(parents=True)
    (ka / "ka_de_beers_logo.jpg").write_bytes(b"img")
    (ka / "videos" / "ka_kimberley_footage.mp4").write_bytes(b"vid")
    data = {"entities": [
        {"id": "ka_de_beers", "name": "De Beers", "kind": "organization", "narrative_role": "the cartel",
         "mentions": ["De Beers"],
         "resolved": [{"file": "capture/keyassets/ka_de_beers_logo.jpg", "type": "logo",
                       "variant": "original", "verified": True, "source": "ddgs", "relevance": "exact"}]},
        {"id": "ka_kimberley", "name": "Kimberley Mine", "kind": "place", "narrative_role": "the big hole",
         "resolved": [{"file": "capture/keyassets/videos/ka_kimberley_footage.mp4", "type": "footage",
                       "variant": "original", "relevance": "related", "source": "archive"}]},
        {"id": "ka_ghost", "name": "Ghost", "kind": "work",
         "resolved": [{"file": "capture/keyassets/missing.jpg", "type": "photo"}]},   # no file → not listed
    ]}
    (tmp_path / "key_assets.json").write_text(json.dumps(data), encoding="utf-8")
    # a prior (acquisition) inventory that must be preserved below the HERO block
    ex = tmp_path / "capture" / "extracted"
    ex.mkdir(parents=True)
    (ex / "asset-descriptions.md").write_text("# Asset descriptions\n- `assets/pool_00.jpg` — a pool item\n",
                                              encoding="utf-8")

    n = write_hero_section(tmp_path, log=lambda *a: None)
    assert n == 2                                              # ghost (no file) excluded
    inv = (ex / "asset-descriptions.md").read_text(encoding="utf-8")
    assert HERO_START in inv and HERO_END in inv
    assert "a pool item" in inv                               # prior acquisition inventory preserved
    # heroes staged where assets.mjs looks
    assert (tmp_path / "capture/assets/ka_de_beers_logo.jpg").exists()
    assert (tmp_path / "capture/assets/videos/ka_kimberley_footage.mp4").exists()
    # HONESTY: every referenced hero basename exists on disk (no phantom)
    for ref in re.findall(r"`(assets/[^`]+)`", inv):
        if ref == "assets/pool_00.jpg":
            continue
        assert (tmp_path / "capture" / ref).exists(), ref
    # idempotent: a second pass doesn't duplicate the block
    write_hero_section(tmp_path, log=lambda *a: None)
    inv2 = (ex / "asset-descriptions.md").read_text(encoding="utf-8")
    assert inv2.count(HERO_START) == 1


# --- /keyassets page: expose + edit queries/identifiers ------------------------------------------
def test_build_view_exposes_identifiers_and_queries(tmp_path):
    from nolan.keyassets.view import build_view
    data = {"comp": "x", "entities": [{"id": "ka_x", "name": "X", "kind": "person", "narrative_role": "r",
            "identifiers": ["a", "b"], "queries_locked": False,
            "desired_assets": [{"type": "portrait", "queries": ["q1", "q2"]}]}],
            "directions": [{"id": "d", "title": "D", "entity_ids": ["ka_x"]}]}
    (tmp_path / "key_assets.json").write_text(json.dumps(data), encoding="utf-8")
    e = build_view(tmp_path)["directions"][0]["entities"][0]
    assert e["identifiers"] == ["a", "b"]
    assert e["assets"][0]["queries"] == ["q1", "q2"]


def test_patch_entity_updates_both_files_and_locks(tmp_path):
    from nolan.webui.routes.keyassets import _patch_entity
    data = {"entities": [{"id": "ka_x", "name": "X", "identifiers": ["old"], "queries_locked": False,
                          "desired_assets": [{"type": "portrait", "queries": ["old"]}]}]}
    for f in ("key_assets.proposal.json", "key_assets.json"):
        (tmp_path / f).write_text(json.dumps(data), encoding="utf-8")
    changed = _patch_entity(tmp_path, "ka_x", "queries", 0, ["new1", "new2"])
    assert set(changed) == {"key_assets.proposal.json", "key_assets.json"}
    d = json.loads((tmp_path / "key_assets.proposal.json").read_text(encoding="utf-8"))
    assert d["entities"][0]["desired_assets"][0]["queries"] == ["new1", "new2"]
    assert d["entities"][0]["queries_locked"] is True         # edit locks against auto-regen
    _patch_entity(tmp_path, "ka_x", "identifiers", None, ["i1", "i2"])
    d2 = json.loads((tmp_path / "key_assets.json").read_text(encoding="utf-8"))
    assert d2["entities"][0]["identifiers"] == ["i1", "i2"]


# --- refine-scope: select assets into the final pool ---------------------------------------------
def test_build_view_collected_carries_selected(tmp_path):
    from nolan.keyassets.view import build_view
    ka = tmp_path / "capture" / "keyassets"
    ka.mkdir(parents=True)
    (ka / "ka_x_portrait.jpg").write_bytes(b"i")
    (ka / "ka_x_portrait_2.jpg").write_bytes(b"i")
    data = {"entities": [{"id": "ka_x", "name": "X", "kind": "person", "narrative_role": "r", "resolved": [
        {"file": "capture/keyassets/ka_x_portrait.jpg", "variant": "original", "verified": True, "selected": True},
        {"file": "capture/keyassets/ka_x_portrait_2.jpg", "variant": "original", "verified": True, "selected": False},
    ]}], "directions": [{"id": "d", "title": "D", "entity_ids": ["ka_x"]}]}
    (tmp_path / "key_assets.json").write_text(json.dumps(data), encoding="utf-8")
    v = build_view(tmp_path)
    coll = v["directions"][0]["entities"][0]["collected"]
    assert len(coll) == 2 and coll[0]["selected"] is True and coll[1]["selected"] is False
    assert v["stats"]["collected"] == 2 and v["stats"]["selected"] == 1


def test_set_selected_toggles_and_reports_miss(tmp_path):
    from nolan.webui.routes.keyassets import _set_selected
    data = {"entities": [{"id": "ka_x", "resolved": [
        {"file": "capture/keyassets/ka_x_portrait.jpg", "selected": True}]}]}
    (tmp_path / "key_assets.json").write_text(json.dumps(data), encoding="utf-8")
    assert _set_selected(tmp_path, "capture/keyassets/ka_x_portrait.jpg", False) is True
    d = json.loads((tmp_path / "key_assets.json").read_text(encoding="utf-8"))
    assert d["entities"][0]["resolved"][0]["selected"] is False
    assert _set_selected(tmp_path, "nope.jpg", True) is False


def test_stage_heroes_only_stages_selected(tmp_path):
    from nolan.keyassets.inventory import stage_heroes
    ka = tmp_path / "capture" / "keyassets"
    ka.mkdir(parents=True)
    (ka / "ka_x_logo.jpg").write_bytes(b"i")
    (ka / "ka_x_logo_2.jpg").write_bytes(b"i")
    data = {"entities": [{"id": "ka_x", "name": "X", "kind": "organization", "resolved": [
        {"file": "capture/keyassets/ka_x_logo.jpg", "type": "logo", "variant": "original", "selected": True},
        {"file": "capture/keyassets/ka_x_logo_2.jpg", "type": "logo", "variant": "original", "selected": False}]}]}
    (tmp_path / "key_assets.json").write_text(json.dumps(data), encoding="utf-8")
    staged = stage_heroes(tmp_path)
    assert len(staged) == 1 and staged[0][0].endswith("ka_x_logo.jpg")   # only the selected one


def test_hero_coverage_reports_placed_and_unplaced(tmp_path):
    """Soft reliability: coverage counts a selected hero as USED only when its basename appears in a
    composed frame; unselected heroes are ignored; before authoring `composed` is False."""
    from nolan.keyassets.inventory import hero_coverage
    data = {"entities": [
        {"id": "e1", "name": "De Beers", "kind": "organization",
         "resolved": [{"file": "capture/keyassets/e1_logo.png", "type": "logo", "selected": True}]},
        {"id": "e2", "name": "Cecil Rhodes", "kind": "person",
         "resolved": [{"file": "capture/keyassets/e2_portrait.jpg", "type": "portrait", "selected": True}]},
        {"id": "e3", "name": "Skip", "kind": "organization",
         "resolved": [{"file": "capture/keyassets/e3.png", "type": "logo", "selected": False}]}]}
    (tmp_path / "key_assets.json").write_text(json.dumps(data), encoding="utf-8")

    pre = hero_coverage(tmp_path)
    assert pre["composed"] is False and pre["total"] == 2 and pre["used"] == 0   # nothing composed yet

    frames = tmp_path / "compositions" / "frames"
    frames.mkdir(parents=True)
    (frames / "01-intro.html").write_text('<img src="assets/e1_logo.png">', encoding="utf-8")
    post = hero_coverage(tmp_path)
    assert post["composed"] and post["total"] == 2                # unselected e3 excluded from the count
    assert post["used"] == 1 and post["unused"] == 1             # De Beers placed, Cecil Rhodes not
    used = {h["entity"]: h["used"] for h in post["heroes"]}
    assert used == {"De Beers": True, "Cecil Rhodes": False}


# --- schema round-trip ---------------------------------------------------------------------------
def test_proposal_round_trip(tmp_path):
    ents = _ents(("De Beers", "organization"), ("Cecil Rhodes", "person"))
    directions, ents = parse_directions(
        json.dumps([{"id": "d", "title": "D", "entity_ids": ["ka_de_beers", "ka_cecil_rhodes"]}]), ents)
    prop = KeyAssetsProposal(comp="x", entities=ents, directions=directions, generated="2026-07-22")
    p = prop.save(tmp_path / "key_assets.proposal.json")
    back = KeyAssetsProposal.load(p)
    assert back.comp == "x" and len(back.entities) == 2 and len(back.directions) == 1
    assert back.entities[0].desired_assets[0].type == "logo"
    assert back.directions[0].entity_ids == ["ka_de_beers", "ka_cecil_rhodes"]
