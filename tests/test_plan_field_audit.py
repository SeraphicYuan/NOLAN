"""Plan-field consumer audit — authored fields must have real readers.

The `transition` field was authored for months while no renderer read it;
`bt.shots` was computed into the void. This audit makes the class structural:
every authored decision field names its consumer in PLAN_FIELD_CONSUMERS,
and the named consumer's source must actually reference the field.
"""

from pathlib import Path

from nolan.scenes import PLAN_FIELD_CONSUMERS

REPO = Path(__file__).resolve().parents[1]


def test_every_manifest_entry_is_true():
    for field, consumer in PLAN_FIELD_CONSUMERS.items():
        src_path = REPO / consumer
        assert src_path.exists(), f"{field}: consumer {consumer} does not exist"
        src = src_path.read_text(encoding="utf-8")
        assert field in src, (
            f"{field}: named consumer {consumer} never references it — "
            "the manifest is lying (or the wiring rotted)")


def test_the_incident_fields_are_covered():
    # the two fields that motivated this audit can never silently drop out
    for f in ("transition", "shots", "shots_wanted"):
        assert f in PLAN_FIELD_CONSUMERS


def test_authored_scene_fields_are_in_the_manifest():
    """Decision-carrying Scene fields (not bookkeeping) need an entry."""
    authored = {
        "narration_excerpt", "visual_type", "visual_description",
        "search_query", "comfyui_prompt", "energy", "motion_speed",
        "transition", "layout_spec", "motion_spec", "matched_asset",
        "matched_clip", "rendered_clip", "generated_asset",
    }
    missing = authored - set(PLAN_FIELD_CONSUMERS)
    assert missing == set(), f"authored fields without a named consumer: {missing}"
