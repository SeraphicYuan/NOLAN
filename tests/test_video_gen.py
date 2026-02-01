"""Tests for video generation module."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import Optional, Dict

from nolan.video_gen import (
    VideoGenerator,
    VideoGenerationResult,
    VideoGenerationConfig,
    ComfyUIVideoGenerator,
    RunwayGenerator,
    VideoGeneratorFactory,
    generate_video_for_scene,
)


class TestVideoGenerationConfig:
    """Tests for VideoGenerationConfig dataclass."""

    def test_default_values(self):
        """Config has sensible defaults."""
        config = VideoGenerationConfig()

        assert config.duration == 4.0
        assert config.width == 1280
        assert config.height == 720
        assert config.fps == 24
        assert config.aspect_ratio == "16:9"
        assert config.style is None
        assert config.negative_prompt is None
        assert config.seed is None

    def test_custom_values(self):
        """Config accepts custom values."""
        config = VideoGenerationConfig(
            duration=8.0,
            width=1920,
            height=1080,
            fps=30,
            style="cinematic",
            negative_prompt="blurry, low quality",
            seed=42,
        )

        assert config.duration == 8.0
        assert config.width == 1920
        assert config.height == 1080
        assert config.fps == 30
        assert config.style == "cinematic"
        assert config.negative_prompt == "blurry, low quality"
        assert config.seed == 42


class TestVideoGenerationResult:
    """Tests for VideoGenerationResult dataclass."""

    def test_success_result(self):
        """Result captures success state."""
        result = VideoGenerationResult(
            success=True,
            video_path=Path("/output/video.mp4"),
            duration_seconds=4.0,
            generation_time_seconds=30.0,
            cost_usd=0.20,
        )

        assert result.success
        assert result.video_path == Path("/output/video.mp4")
        assert result.duration_seconds == 4.0
        assert result.generation_time_seconds == 30.0
        assert result.cost_usd == 0.20
        assert result.error is None

    def test_failure_result(self):
        """Result captures failure state."""
        result = VideoGenerationResult(
            success=False,
            error="Connection timeout",
            generation_time_seconds=60.0,
        )

        assert not result.success
        assert result.video_path is None
        assert result.error == "Connection timeout"
        assert result.generation_time_seconds == 60.0


class TestVideoGeneratorFactory:
    """Tests for VideoGeneratorFactory."""

    def test_create_comfyui_generator(self, tmp_path):
        """Factory creates ComfyUI generator."""
        # Create a minimal workflow file
        workflow_file = tmp_path / "workflow.json"
        workflow_file.write_text('{"1": {"class_type": "Test", "inputs": {}}}')

        generator = VideoGeneratorFactory.create(
            "comfyui",
            workflow_file=workflow_file
        )

        assert isinstance(generator, ComfyUIVideoGenerator)
        assert generator.backend_name == "comfyui"

    def test_create_runway_generator(self):
        """Factory creates Runway generator."""
        generator = VideoGeneratorFactory.create(
            "runway",
            api_key="test_key"
        )

        assert isinstance(generator, RunwayGenerator)
        assert generator.backend_name == "runway"

    def test_unknown_backend_raises(self):
        """Factory raises for unknown backend."""
        with pytest.raises(ValueError, match="Unknown backend"):
            VideoGeneratorFactory.create("unknown")


class TestComfyUIVideoGenerator:
    """Tests for ComfyUIVideoGenerator."""

    def test_init_with_workflow_file(self, tmp_path):
        """Generator loads workflow from file."""
        workflow_file = tmp_path / "workflow.json"
        workflow_file.write_text('{"1": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}}}')

        generator = ComfyUIVideoGenerator(workflow_file=workflow_file)

        assert generator.workflow is not None
        assert "1" in generator.workflow

    def test_init_with_workflow_dict(self):
        """Generator accepts workflow dict."""
        workflow = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}}
        }

        generator = ComfyUIVideoGenerator(workflow=workflow)

        assert generator.workflow == workflow

    def test_init_requires_workflow(self):
        """Generator requires workflow or workflow_file."""
        with pytest.raises(ValueError, match="Either workflow_file or workflow"):
            ComfyUIVideoGenerator()

    def test_backend_name(self, tmp_path):
        """Backend name is 'comfyui'."""
        workflow_file = tmp_path / "workflow.json"
        workflow_file.write_text('{"1": {"class_type": "Test", "inputs": {}}}')

        generator = ComfyUIVideoGenerator(workflow_file=workflow_file)

        assert generator.backend_name == "comfyui"

    def test_parse_overrides(self, tmp_path):
        """Generator parses node overrides."""
        workflow_file = tmp_path / "workflow.json"
        workflow_file.write_text('{"1": {"class_type": "Test", "inputs": {}}}')

        generator = ComfyUIVideoGenerator(
            workflow_file=workflow_file,
            node_overrides=["1:steps=30", "1:cfg=7.5", "2:text=test"]
        )

        assert generator._node_overrides == {
            "1": {"steps": 30, "cfg": 7.5},
            "2": {"text": "test"}
        }

    def test_convert_value_types(self, tmp_path):
        """Generator converts override values to correct types."""
        workflow_file = tmp_path / "workflow.json"
        workflow_file.write_text('{"1": {"class_type": "Test", "inputs": {}}}')

        generator = ComfyUIVideoGenerator(workflow_file=workflow_file)

        assert generator._convert_value("42") == 42
        assert generator._convert_value("3.14") == 3.14
        assert generator._convert_value("true") is True
        assert generator._convert_value("false") is False
        assert generator._convert_value("hello") == "hello"

    def test_detect_prompt_nodes(self, tmp_path):
        """Generator auto-detects prompt nodes."""
        workflow_file = tmp_path / "workflow.json"
        # Note: Detection checks text content for "low quality" to identify negative prompt
        workflow = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "a beautiful sunset"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "low quality, blurry, bad"}},
        }
        import json
        workflow_file.write_text(json.dumps(workflow))

        generator = ComfyUIVideoGenerator(workflow_file=workflow_file)

        # First node should be detected as positive (doesn't contain "low quality")
        assert generator._detected_nodes["prompt"] == "1"
        # Second node should be detected as negative (contains "low quality")
        assert generator._detected_nodes["negative"] == "2"

    @pytest.mark.asyncio
    async def test_check_connection_success(self, tmp_path):
        """check_connection returns True when server is up."""
        workflow_file = tmp_path / "workflow.json"
        workflow_file.write_text('{"1": {"class_type": "Test", "inputs": {}}}')

        generator = ComfyUIVideoGenerator(workflow_file=workflow_file)

        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            result = await generator.check_connection()

            assert result is True

    @pytest.mark.asyncio
    async def test_check_connection_failure(self, tmp_path):
        """check_connection returns False when server is down."""
        workflow_file = tmp_path / "workflow.json"
        workflow_file.write_text('{"1": {"class_type": "Test", "inputs": {}}}')

        generator = ComfyUIVideoGenerator(workflow_file=workflow_file)

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("Connection refused")
            )

            result = await generator.check_connection()

            assert result is False


class TestRunwayGenerator:
    """Tests for RunwayGenerator."""

    def test_init_with_api_key(self):
        """Generator initializes with API key."""
        generator = RunwayGenerator(api_key="test_key")

        assert generator.api_key == "test_key"
        assert generator.model == RunwayGenerator.MODEL_GEN3_TURBO

    def test_init_with_model(self):
        """Generator accepts model selection."""
        generator = RunwayGenerator(api_key="test_key", model=RunwayGenerator.MODEL_GEN3)

        assert generator.model == RunwayGenerator.MODEL_GEN3

    def test_init_requires_api_key(self):
        """Generator requires API key."""
        # Clear env var if set
        import os
        old_key = os.environ.pop('RUNWAY_API_KEY', None)

        try:
            with pytest.raises(ValueError, match="API key required"):
                RunwayGenerator()
        finally:
            if old_key:
                os.environ['RUNWAY_API_KEY'] = old_key

    def test_init_from_env_var(self):
        """Generator reads API key from environment."""
        import os
        os.environ['RUNWAY_API_KEY'] = 'env_test_key'

        try:
            generator = RunwayGenerator()
            assert generator.api_key == 'env_test_key'
        finally:
            del os.environ['RUNWAY_API_KEY']

    def test_backend_name(self):
        """Backend name is 'runway'."""
        generator = RunwayGenerator(api_key="test_key")

        assert generator.backend_name == "runway"

    def test_pricing_defined(self):
        """Pricing is defined for models."""
        assert RunwayGenerator.MODEL_GEN3_TURBO in RunwayGenerator.PRICING
        assert RunwayGenerator.MODEL_GEN3 in RunwayGenerator.PRICING

    @pytest.mark.asyncio
    async def test_check_connection(self):
        """check_connection tests API availability."""
        generator = RunwayGenerator(api_key="test_key")

        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            result = await generator.check_connection()

            assert result is True


class TestGenerateVideoForScene:
    """Tests for generate_video_for_scene utility function."""

    @pytest.mark.asyncio
    async def test_builds_optimized_prompt(self, tmp_path):
        """Function builds prompt from scene metadata."""
        # Create a mock generator
        mock_generator = MagicMock(spec=VideoGenerator)
        mock_generator.generate = AsyncMock(return_value=VideoGenerationResult(
            success=True,
            video_path=tmp_path / "output.mp4",
            duration_seconds=4.0,
            generation_time_seconds=10.0,
        ))

        output_path = tmp_path / "scene.mp4"

        result = await generate_video_for_scene(
            generator=mock_generator,
            visual_description="Aerial shot of city skyline at sunset",
            narration_excerpt="The city never sleeps",
            output_path=output_path,
            style_hint="cinematic",
        )

        # Check that generate was called
        mock_generator.generate.assert_called_once()

        # Check the prompt contains our content
        call_args = mock_generator.generate.call_args
        prompt = call_args[0][0]
        assert "cinematic" in prompt
        assert "Aerial shot of city skyline at sunset" in prompt
        assert "High quality" in prompt

    @pytest.mark.asyncio
    async def test_handles_empty_narration(self, tmp_path):
        """Function handles empty narration gracefully."""
        mock_generator = MagicMock(spec=VideoGenerator)
        mock_generator.generate = AsyncMock(return_value=VideoGenerationResult(
            success=True,
            video_path=tmp_path / "output.mp4",
        ))

        output_path = tmp_path / "scene.mp4"

        result = await generate_video_for_scene(
            generator=mock_generator,
            visual_description="Mountain landscape",
            narration_excerpt="",  # Empty narration
            output_path=output_path,
        )

        assert result.success

    @pytest.mark.asyncio
    async def test_passes_config(self, tmp_path):
        """Function passes config to generator."""
        mock_generator = MagicMock(spec=VideoGenerator)
        mock_generator.generate = AsyncMock(return_value=VideoGenerationResult(
            success=True,
            video_path=tmp_path / "output.mp4",
        ))

        output_path = tmp_path / "scene.mp4"
        config = VideoGenerationConfig(duration=8.0, width=1920, height=1080)

        await generate_video_for_scene(
            generator=mock_generator,
            visual_description="Test",
            narration_excerpt="Test",
            output_path=output_path,
            config=config,
        )

        call_args = mock_generator.generate.call_args
        passed_config = call_args[0][2]  # Third positional arg
        assert passed_config.duration == 8.0
        assert passed_config.width == 1920


class TestWorkflowConversion:
    """Tests for workflow format conversion."""

    def test_api_format_passthrough(self, tmp_path):
        """API format workflows pass through unchanged."""
        workflow = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 42}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "test"}},
        }
        import json
        workflow_file = tmp_path / "workflow.json"
        workflow_file.write_text(json.dumps(workflow))

        generator = ComfyUIVideoGenerator(workflow_file=workflow_file)

        assert generator.workflow["1"]["class_type"] == "KSampler"
        assert generator.workflow["2"]["class_type"] == "CLIPTextEncode"

    def test_ui_format_conversion(self, tmp_path):
        """UI format workflows are converted to API format."""
        ui_workflow = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CLIPTextEncode",
                    "widgets_values": ["test prompt"],
                    "inputs": [],
                },
                {
                    "id": 2,
                    "type": "KSampler",
                    "widgets_values": [],
                    "inputs": [{"name": "positive", "link": 100}],
                },
            ],
            "links": [
                [100, 1, 0, 2, 0, "CONDITIONING"]
            ],
        }
        import json
        workflow_file = tmp_path / "workflow.json"
        workflow_file.write_text(json.dumps(ui_workflow))

        generator = ComfyUIVideoGenerator(workflow_file=workflow_file)

        # Should have converted to API format
        assert "1" in generator.workflow
        assert "2" in generator.workflow
        assert generator.workflow["1"]["class_type"] == "CLIPTextEncode"
        # Check link was converted
        assert generator.workflow["2"]["inputs"]["positive"] == ["1", 0]
