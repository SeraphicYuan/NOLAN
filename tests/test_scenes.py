"""Tests for scene design."""

import pytest
import json
from unittest.mock import Mock, AsyncMock

from nolan.scenes import SceneDesigner, Scene, ScenePlan, Beat, BeatPlan
from nolan.script import ScriptSection


def create_mock_llm():
    """Create a mock LLM that responds appropriately to different prompts."""
    client = Mock()

    # Track call count to return different responses
    call_count = [0]

    async def smart_generate(prompt):
        call_count[0] += 1

        # Pass 1: Beat detection (returns array of beats)
        if "Break this narration into BEATS" in prompt:
            return json.dumps([
                {
                    "id": "beat_001",
                    "narration": "Venezuela. A land of stunning beauty.",
                    "category": "b-roll",
                    "mode": "see-say",
                    "visual_intent": "Aerial shot of Venezuelan landscape",
                    "has_visual_hole": False,
                    "sync_word": "Venezuela"
                },
                {
                    "id": "beat_002",
                    "narration": "cascading waterfalls",
                    "category": "b-roll",
                    "mode": "see-say",
                    "visual_intent": "Angel Falls waterfall footage",
                    "has_visual_hole": False,
                    "sync_word": "waterfalls"
                }
            ])

        # Pass 2: B-roll enrichment (returns object)
        if "sourcing B-roll footage" in prompt:
            return json.dumps({
                "search_queries": ["venezuela landscape aerial", "south america mountains"],
                "visual_description": "Aerial shot of Venezuelan landscape with mountains",
                "mood": "energetic",
                "motion": "dynamic",
                "suggested_duration": "5s"
            })

        # Pass 2: Graphics enrichment
        if "designing a graphic" in prompt:
            return json.dumps({
                "graphic_type": "infographic",
                "spec": {
                    "template": "steps",
                    "theme": "default",
                    "title": "Test",
                    "items": [{"label": "Step 1", "desc": "Detail"}]
                },
                "suggested_duration": "10s"
            })

        # Pass 2: Generated image enrichment
        if "AI image generation prompt" in prompt:
            return json.dumps({
                "comfyui_prompt": "aerial photography, venezuela, mountains, cinematic",
                "negative_prompt": "blurry, low quality",
                "style": "photorealistic",
                "aspect_ratio": "16:9",
                "visual_description": "Stunning aerial view of Venezuela",
                "suggested_duration": "5s"
            })

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
        narration="Venezuela. A land of stunning beauty - cascading waterfalls.",
        start_time=0.0,
        end_time=45.0,
        word_count=8
    )

    beat_plan = await designer.detect_beats(section)

    assert beat_plan.section_title == "Hook"
    assert len(beat_plan.beats) == 2
    assert beat_plan.beats[0].category == "b-roll"
    assert beat_plan.beats[0].sync_word == "Venezuela"


@pytest.mark.asyncio
async def test_design_section_full(mock_llm):
    """Full two-pass design produces scenes."""
    designer = SceneDesigner(llm_client=mock_llm)
    section = ScriptSection(
        title="Hook",
        narration="Venezuela. A land of stunning beauty - cascading waterfalls.",
        start_time=0.0,
        end_time=45.0,
        word_count=8
    )

    scenes = await designer.design_section(section, enrich=True)

    assert len(scenes) == 2
    assert scenes[0].id == "scene_001"
    assert scenes[0].visual_type == "b-roll"
    # Check enrichment happened
    assert scenes[0].search_query != ""


@pytest.mark.asyncio
async def test_design_section_beats_only(mock_llm):
    """Pass 1 only produces basic scenes without enrichment."""
    designer = SceneDesigner(llm_client=mock_llm)
    section = ScriptSection(
        title="Hook",
        narration="Venezuela. A land of stunning beauty.",
        start_time=0.0,
        end_time=30.0,
        word_count=5
    )

    scenes = await designer.design_section(section, enrich=False)

    assert len(scenes) == 2
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
