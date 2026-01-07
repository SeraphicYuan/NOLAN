"""Tests for scene design."""

import pytest
import json
from unittest.mock import Mock, AsyncMock

from nolan.scenes import SceneDesigner, Scene, ScenePlan
from nolan.script import ScriptSection


@pytest.fixture
def mock_llm():
    """Create a mock LLM client that returns valid JSON."""
    client = Mock()
    client.generate = AsyncMock(return_value=json.dumps([
        {
            "id": "scene_001",
            "start": "0:00",
            "duration": "10s",
            "narration_excerpt": "Venezuela. A land of stunning beauty.",
            "visual_type": "b-roll",
            "visual_description": "Aerial shot of Venezuelan landscape with mountains and waterfalls",
            "asset_suggestions": {
                "search_query": "venezuela aerial landscape mountains",
                "comfyui_prompt": "aerial photography, venezuelan andes mountains, lush green valleys, dramatic clouds, 4k cinematic",
                "library_match": True
            }
        },
        {
            "id": "scene_002",
            "start": "0:10",
            "duration": "15s",
            "narration_excerpt": "cascading waterfalls, vibrant rainforests",
            "visual_type": "b-roll",
            "visual_description": "Angel Falls waterfall in Venezuela",
            "asset_suggestions": {
                "search_query": "angel falls venezuela waterfall",
                "comfyui_prompt": "angel falls, tallest waterfall, mist, tropical rainforest, dramatic lighting",
                "library_match": True
            }
        }
    ]))
    return client


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


@pytest.mark.asyncio
async def test_design_scenes_for_section(mock_llm):
    """Designer generates scenes for a script section."""
    designer = SceneDesigner(llm_client=mock_llm)
    section = ScriptSection(
        title="Hook",
        narration="Venezuela. A land of stunning beauty - cascading waterfalls.",
        start_time=0.0,
        end_time=45.0,
        word_count=8
    )

    scenes = await designer.design_section(section)

    assert len(scenes) == 2
    assert scenes[0].id == "scene_001"
    assert "venezuela" in scenes[0].visual_description.lower()


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
