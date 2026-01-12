"""Tests for scene design."""

import pytest
import json
from unittest.mock import Mock, AsyncMock

from nolan.scenes import SceneDesigner, Scene, ScenePlan, Beat, BeatPlan
from nolan.script import ScriptSection


def create_mock_llm():
    """Create a mock LLM that responds appropriately to different prompts."""
    client = Mock()

    async def smart_generate(prompt):
        # Pass 1: Beat detection (returns array of beats)
        if "Break this narration into BEATS" in prompt:
            return json.dumps([
                {
                    "id": "beat_001",
                    "narration": "Venezuela was once the richest country.",
                    "category": "b-roll",
                    "mode": "see-say",
                    "visual_intent": "Aerial shot of Caracas skyline",
                    "has_visual_hole": False,
                    "sync_word": "Venezuela"
                },
                {
                    "id": "beat_002",
                    "narration": "Oil revenues funded massive social programs.",
                    "category": "graphics",
                    "mode": "see-say",
                    "visual_intent": "Chart showing oil revenue growth",
                    "has_visual_hole": False,
                    "sync_word": "revenues"
                },
                {
                    "id": "beat_003",
                    "narration": "But when oil prices crashed, everything changed.",
                    "category": "graphics",
                    "mode": "see-say",
                    "visual_intent": "Chart showing price crash",
                    "has_visual_hole": False,
                    "sync_word": "crashed"
                }
            ])

        # Pass 2: Flexible beat → scene mapping (returns array of scenes)
        if "Convert these beats into SCENES" in prompt:
            return json.dumps([
                {
                    "id": "scene_001",
                    "covers_beats": ["beat_001"],
                    "visual_type": "b-roll",
                    "visual_description": "Aerial shot of Caracas skyline with modern buildings",
                    "narration_excerpt": "Venezuela was once the richest country.",
                    "duration": "5s",
                    "search_queries": ["caracas aerial", "venezuela cityscape"],
                    "mood": "hopeful",
                    "transition": "fade"
                },
                {
                    "id": "scene_002",
                    "covers_beats": ["beat_002", "beat_003"],  # Multiple beats → 1 scene
                    "visual_type": "graphics",
                    "visual_description": "Oil price chart with two phases: growth and crash",
                    "narration_excerpt": "Oil revenues funded massive social programs. But when oil prices crashed",
                    "duration": "12s",
                    "infographic": {
                        "template": "comparison",
                        "theme": "default",
                        "data": {
                            "title": "Oil Revenue",
                            "items": [
                                {"label": "Peak", "desc": "$100B"},
                                {"label": "Crash", "desc": "$20B"}
                            ]
                        }
                    },
                    "sync_points": [
                        {"trigger": "revenues", "action": "reveal_item", "target": 0},
                        {"trigger": "crashed", "action": "highlight", "target": 1}
                    ],
                    "transition": "cut"
                }
            ])

        # Default fallback
        return json.dumps([])

    client.generate = AsyncMock(side_effect=smart_generate)
    return client


@pytest.fixture
def mock_llm():
    """Create a mock LLM client that responds to two-pass prompts."""
    return create_mock_llm()


def test_scene_has_required_fields():
    """Scene object contains all required fields."""
    scene = Scene(
        id="scene_001",
        covers_beats=["beat_001"],
        start="0:00",
        duration="10s",
        narration_excerpt="Test narration",
        visual_type="b-roll",
        visual_description="Test description",
        search_query="test query",
        comfyui_prompt="test prompt",
        library_match=True
    )

    assert scene.id == "scene_001"
    assert scene.covers_beats == ["beat_001"]
    assert scene.visual_type == "b-roll"


def test_beat_dataclass():
    """Beat dataclass works correctly."""
    beat = Beat(
        id="beat_001",
        narration="Test narration",
        category="b-roll",
        mode="see-say",
        visual_intent="Test visual",
        has_visual_hole=False,
        sync_word="test"
    )

    assert beat.id == "beat_001"
    assert beat.category == "b-roll"
    assert beat.sync_word == "test"


def test_beat_plan_to_av_script():
    """BeatPlan exports to A/V script format."""
    beats = [
        Beat(id="beat_001", narration="First sentence.", category="b-roll",
             mode="see-say", visual_intent="Aerial shot"),
        Beat(id="beat_002", narration="Second sentence.", category="graphics",
             mode="counterpoint", visual_intent="Chart showing data", has_visual_hole=True),
    ]
    plan = BeatPlan(section_title="Test Section", beats=beats)

    av_script = plan.to_av_script()

    assert "Test Section" in av_script
    assert "VISUAL" in av_script
    assert "AUDIO" in av_script
    assert "B-ROLL" in av_script
    assert "GRAPHICS" in av_script
    assert "Visual holes: 1" in av_script


@pytest.mark.asyncio
async def test_detect_beats(mock_llm):
    """Pass 1: Designer detects beats from narration."""
    designer = SceneDesigner(llm_client=mock_llm)
    section = ScriptSection(
        title="Hook",
        narration="Venezuela was once the richest country. Oil revenues funded massive social programs.",
        start_time=0.0,
        end_time=45.0,
        word_count=12
    )

    beat_plan = await designer.detect_beats(section)

    assert beat_plan.section_title == "Hook"
    assert len(beat_plan.beats) == 3
    assert beat_plan.beats[0].category == "b-roll"
    assert beat_plan.beats[0].sync_word == "Venezuela"


@pytest.mark.asyncio
async def test_beats_to_scenes_flexible_mapping(mock_llm):
    """Pass 2: Flexible beat → scene mapping (N beats → 1 scene)."""
    designer = SceneDesigner(llm_client=mock_llm)

    # Create a beat plan
    beats = [
        Beat(id="beat_001", narration="Venezuela was once the richest country.",
             category="b-roll", mode="see-say", visual_intent="Aerial shot"),
        Beat(id="beat_002", narration="Oil revenues funded massive social programs.",
             category="graphics", mode="see-say", visual_intent="Chart"),
        Beat(id="beat_003", narration="But when oil prices crashed, everything changed.",
             category="graphics", mode="see-say", visual_intent="Chart"),
    ]
    beat_plan = BeatPlan(section_title="Test", beats=beats)

    scenes = await designer.beats_to_scenes(beat_plan)

    # Should have 2 scenes (3 beats mapped flexibly)
    assert len(scenes) == 2

    # First scene covers 1 beat
    assert scenes[0].id == "scene_001"
    assert scenes[0].covers_beats == ["beat_001"]
    assert scenes[0].visual_type == "b-roll"

    # Second scene covers 2 beats (sustained visual)
    assert scenes[1].id == "scene_002"
    assert scenes[1].covers_beats == ["beat_002", "beat_003"]
    assert scenes[1].visual_type == "graphics"
    assert len(scenes[1].sync_points) == 2


@pytest.mark.asyncio
async def test_design_section_full(mock_llm):
    """Full two-pass design produces scenes with flexible mapping."""
    designer = SceneDesigner(llm_client=mock_llm)
    section = ScriptSection(
        title="Hook",
        narration="Venezuela was once the richest country. Oil revenues funded massive social programs.",
        start_time=0.0,
        end_time=45.0,
        word_count=12
    )

    scenes = await designer.design_section(section, enrich=True)

    # Should have 2 scenes (from flexible mapping)
    assert len(scenes) == 2
    assert scenes[0].id == "scene_001"
    assert scenes[0].visual_type == "b-roll"
    assert scenes[1].covers_beats == ["beat_002", "beat_003"]


@pytest.mark.asyncio
async def test_design_section_beats_only(mock_llm):
    """Pass 1 only produces basic 1:1 scenes without enrichment."""
    designer = SceneDesigner(llm_client=mock_llm)
    section = ScriptSection(
        title="Hook",
        narration="Venezuela was once the richest country.",
        start_time=0.0,
        end_time=30.0,
        word_count=5
    )

    scenes = await designer.design_section(section, enrich=False)

    # Without enrichment, should be 1:1 mapping (3 beats → 3 scenes)
    assert len(scenes) == 3
    assert scenes[0].covers_beats == ["beat_001"]
    # Without enrichment, search_query should be empty
    assert scenes[0].search_query == ""


@pytest.mark.asyncio
async def test_scene_plan_exports_to_json(mock_llm):
    """Scene plan can be exported to JSON."""
    designer = SceneDesigner(llm_client=mock_llm)
    section = ScriptSection(
        title="Hook",
        narration="Test narration.",
        start_time=0.0,
        end_time=30.0,
        word_count=2
    )

    scenes = await designer.design_section(section)
    plan = ScenePlan(sections={"Hook": scenes})

    json_output = plan.to_json()
    parsed = json.loads(json_output)

    assert "Hook" in parsed["sections"]
    assert len(parsed["sections"]["Hook"]) == 2


def test_scene_with_covers_beats_serialization():
    """Scene with covers_beats serializes correctly."""
    scene = Scene(
        id="scene_001",
        covers_beats=["beat_001", "beat_002"],
        duration="10s",
        narration_excerpt="Test",
        visual_type="graphics",
        visual_description="Test chart",
    )

    plan = ScenePlan(sections={"Test": [scene]})
    json_output = plan.to_json()
    parsed = json.loads(json_output)

    assert parsed["sections"]["Test"][0]["covers_beats"] == ["beat_001", "beat_002"]
