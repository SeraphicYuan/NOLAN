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
