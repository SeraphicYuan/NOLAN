"""KB distillation: JSON parsing, audit/normalization, taxonomy snapping (offline)."""
import pytest

from nolan.kb import taxonomy
from nolan.kb.distill import _extract_json, _normalize


def test_extract_json_handles_fences_and_trailing_commas():
    raw = '```json\n{"tldr":"x","insights":[{"title":"A","core_idea":"c",}],"source_quality":{}}\n```'
    d = _extract_json(raw)
    assert d["tldr"] == "x" and d["insights"][0]["title"] == "A"


def test_normalize_drops_empty_and_snaps_category():
    data = {"tldr": "t", "insights": [
        {"title": "Good cut", "category": "cuts", "core_idea": "a real idea"},
        {"title": "", "category": "editing", "core_idea": "x"},                 # no title -> dropped
        {"title": "NoCore", "category": "editing", "core_idea": "NOT_SPECIFIED"},  # no core -> dropped
    ], "source_quality": {"argument_quality": "strong"}}
    dist = _normalize(data)
    assert len(dist.insights) == 1
    assert dist.insights[0].category == "editing"        # 'cuts' snapped to 'editing'
    assert dist.argument_quality == "STRONG"


def test_normalize_raises_when_no_usable_insights():
    with pytest.raises(ValueError):
        _normalize({"insights": []})


def test_taxonomy_normalization():
    assert taxonomy.normalize_category("sfx") == "sound-design-sfx"
    assert taxonomy.normalize_category("Transitions") == "editing"
    assert taxonomy.normalize_category("unknown-bucket") == "editing"       # never invents
    assert taxonomy.normalize_enum("advanced", taxonomy.DIFFICULTY, "medium") == "advanced"
    assert taxonomy.normalize_enum("bogus", taxonomy.NOLAN_HOOKS, "none") == "none"
