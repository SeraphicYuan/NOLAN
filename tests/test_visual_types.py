"""visual_type canonical vocabulary — the loud normalization gate.

Caught live 2026-07-06: a from-scratch script_to_scenes run invented slugs
(stat_card, kinetic_text, chart_animated...) and every downstream consumer
silently saw 0 eligible scenes. These pin the normalizer that now prevents
the silent cascade.
"""

from nolan.scenes import (VISUAL_TYPES, normalize_plan_visual_types,
                          normalize_visual_type)


def test_canonical_values_pass_through():
    for t in VISUAL_TYPES:
        assert normalize_visual_type(t) == t


def test_the_live_incident_slugs_all_map():
    # the exact vocabulary the aidc-2beat-test run invented
    expected = {
        "broll_stock": "b-roll",
        "broll_generated": "generated-image",
        "kinetic_text": "text-overlay",
        "stat_card": "text-overlay",
        "quote_card": "text-overlay",
        "chart_animated": "graphic",
        "comparison_composite": "graphic",
        "map_highlight": "graphic",
    }
    for raw, canon in expected.items():
        assert normalize_visual_type(raw) == canon, raw


def test_unmappable_returns_none():
    assert normalize_visual_type("interpretive-dance") is None
    assert normalize_visual_type("") is None


def test_plan_normalization_reports_and_rewrites():
    plan = {"sections": {"A": [
        {"id": "s1", "visual_type": "stat_card"},
        {"id": "s2", "visual_type": "stat_card"},
        {"id": "s3", "visual_type": "b-roll"},
        {"id": "s4", "visual_type": "interpretive-dance"},
    ]}}
    mapped, unknown = normalize_plan_visual_types(plan)
    assert mapped == {"stat_card -> text-overlay": 2}
    assert unknown == ["s4 ('interpretive-dance')"]
    scenes = plan["sections"]["A"]
    assert scenes[0]["visual_type"] == "text-overlay"
    assert scenes[2]["visual_type"] == "b-roll"           # untouched
    assert scenes[3]["visual_type"] == "interpretive-dance"  # left for the error


def test_archival_art_requires_search_query():
    """aeneid-2beat-v2: the designer NAMED every work in visual_description
    but left search_query empty — exact-title never ran and CLIP matched a
    botanical plate to a manuscript scene. The gate must catch this."""
    from nolan.scenes import validate_art_queries
    plan = {"sections": {"a": [
        {"id": "s1", "visual_type": "archival-art",
         "visual_description": "The Augustus of Prima Porta"},
        {"id": "s2", "visual_type": "archival-art",
         "search_query": "Augustus Prima Porta statue"},
        {"id": "s3", "visual_type": "b-roll"},
    ]}}
    assert validate_art_queries(plan) == ["s1"]
    plan["sections"]["a"][0]["search_query"] = "Augustus of Prima Porta"
    assert validate_art_queries(plan) == []
