"""Honesty test: the showcase catalog is a faithful view of the registries.

The showcase page must show exactly what the pipeline can author. If a motion
effect or block template is added/removed, this test fails unless the catalog
reflects it — so the showcase can never drift back into a hand-listed catalog
(the "catalog-blind" pitfall).
"""
from pathlib import Path

from nolan.webui.showcase_catalog import build_showcase_catalog
from nolan.motion.registry import REGISTRY
from nolan.layout_blocks import TEMPLATES, ADAPTERS

REPO = Path(__file__).resolve().parents[1]


def _cat():
    return build_showcase_catalog(REPO)


def test_every_motion_effect_is_present():
    cat = _cat()
    ids = {e["id"] for e in cat["effects"] if e["kind"] == "motion"}
    missing = {e.id for e in REGISTRY} - ids
    assert not missing, f"motion effects missing from showcase: {missing}"
    assert cat["counts"]["motion"] == len(REGISTRY)


def test_every_block_template_is_present():
    cat = _cat()
    ids = {e["id"] for e in cat["effects"] if e["kind"] == "block"}
    missing = set(TEMPLATES) - ids
    assert not missing, f"block templates missing from showcase: {missing}"
    assert cat["counts"]["block"] == len(TEMPLATES)


def test_authorable_flag_matches_adapters():
    cat = _cat()
    for e in cat["effects"]:
        if e["kind"] == "block":
            assert e["authorable"] == (e["id"] in ADAPTERS)
        elif e["kind"] == "orphan":
            assert e["authorable"] is False
        else:
            assert e["authorable"] is True


def test_each_entry_carries_purpose_and_when_to_use():
    cat = _cat()
    for e in cat["effects"]:
        assert e["description"], f"{e['id']} has no purpose"
        assert e["when_to_use"], f"{e['id']} has no when_to_use"


def test_preview_is_basename_or_none():
    cat = _cat()
    for e in cat["effects"]:
        assert e["preview"] is None or "/" not in e["preview"]
