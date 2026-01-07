"""Integration tests for the full pipeline."""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

from nolan.parser import parse_essay
from nolan.script import ScriptConverter
from nolan.scenes import SceneDesigner


@pytest.fixture
def mock_llm():
    """Create a mock LLM that returns realistic responses."""
    client = Mock()

    # Script conversion response
    script_response = """Venezuela. A land of stunning beauty – from cascading waterfalls to vibrant rainforests.

Yet, these beautiful images hide a stark reality. Widespread poverty, political unrest, and a nation constantly struggling.

Consider what Maria Rodriguez from Caracas told the Associated Press: "We are tired. Tired of the empty promises."

And this, in a nation sitting on one of the world's largest oil reserves. How did this happen? That's what we're going to explore."""

    # Scene design response
    scene_response = json.dumps([
        {
            "id": "scene_001",
            "start": "0:00",
            "duration": "8s",
            "narration_excerpt": "Venezuela. A land of stunning beauty",
            "visual_type": "b-roll",
            "visual_description": "Aerial drone shot of Venezuelan landscape with Angel Falls",
            "asset_suggestions": {
                "search_query": "venezuela aerial angel falls landscape",
                "comfyui_prompt": "aerial photography, angel falls venezuela, lush green rainforest, dramatic waterfall, golden hour lighting, 4k cinematic",
                "library_match": True
            }
        },
        {
            "id": "scene_002",
            "start": "0:08",
            "duration": "7s",
            "narration_excerpt": "cascading waterfalls to vibrant rainforests",
            "visual_type": "b-roll",
            "visual_description": "Close-up of tropical rainforest with colorful birds",
            "asset_suggestions": {
                "search_query": "tropical rainforest birds venezuela",
                "comfyui_prompt": "tropical rainforest, exotic birds, lush vegetation, morning mist, nature documentary style",
                "library_match": True
            }
        }
    ])

    client.generate = AsyncMock(side_effect=[script_response, scene_response])
    return client


@pytest.mark.asyncio
async def test_full_pipeline_with_sample_essay(sample_essay, mock_llm, temp_output_dir):
    """Test the full pipeline with the Venezuela essay."""
    # Parse essay
    sections = parse_essay(sample_essay)
    assert len(sections) == 7

    # Convert first section to script
    converter = ScriptConverter(mock_llm, words_per_minute=150)
    script_section = await converter.convert_section(sections[0], start_time=0.0)

    assert script_section.title == "Hook"
    assert len(script_section.narration) > 0
    assert script_section.end_time > 0

    # Design scenes for the script section
    designer = SceneDesigner(mock_llm)
    scenes = await designer.design_section(script_section)

    assert len(scenes) == 2
    assert scenes[0].id == "scene_001"
    assert scenes[0].visual_type == "b-roll"
    assert "venezuela" in scenes[0].visual_description.lower()


@pytest.mark.asyncio
async def test_pipeline_outputs_correct_files(sample_essay, mock_llm, temp_output_dir):
    """Test that pipeline creates expected output files."""
    from nolan.script import Script
    from nolan.scenes import ScenePlan

    # Parse and convert
    sections = parse_essay(sample_essay)
    converter = ScriptConverter(mock_llm, words_per_minute=150)

    # Just process first section for speed
    script_section = await converter.convert_section(sections[0], start_time=0.0)
    script = Script(sections=[script_section])

    # Save script
    script_path = temp_output_dir / "script.md"
    script_path.write_text(script.to_markdown())

    assert script_path.exists()
    assert "Hook" in script_path.read_text()

    # Design and save scenes
    designer = SceneDesigner(mock_llm)
    scenes = await designer.design_section(script_section)
    plan = ScenePlan(sections={"Hook": scenes})

    plan_path = temp_output_dir / "scene_plan.json"
    plan.save(str(plan_path))

    assert plan_path.exists()
    loaded = json.loads(plan_path.read_text())
    assert "sections" in loaded
    assert "Hook" in loaded["sections"]
