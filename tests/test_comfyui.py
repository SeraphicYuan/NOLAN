"""Tests for ComfyUI integration."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

from nolan.comfyui import ComfyUIClient


@pytest.fixture
def comfyui_config():
    """Default ComfyUI configuration."""
    return {
        'host': '127.0.0.1',
        'port': 8188,
        'width': 1920,
        'height': 1080,
        'steps': 20
    }


def test_client_initialization(comfyui_config):
    """Client initializes with configuration."""
    client = ComfyUIClient(**comfyui_config)

    assert client.host == '127.0.0.1'
    assert client.port == 8188
    assert client.base_url == 'http://127.0.0.1:8188'


@pytest.mark.asyncio
async def test_generate_image_returns_path(comfyui_config, tmp_path):
    """Client returns path to generated image."""
    client = ComfyUIClient(**comfyui_config)

    # Mock the HTTP calls
    with patch.object(client, '_queue_prompt') as mock_queue:
        with patch.object(client, '_wait_for_completion') as mock_wait:
            with patch.object(client, '_download_image') as mock_download:
                mock_queue.return_value = "prompt-id-123"
                mock_wait.return_value = {"outputs": {"9": {"images": [{"filename": "output.png", "subfolder": ""}]}}}

                output_path = tmp_path / "scene_001.png"
                mock_download.return_value = output_path

                result = await client.generate(
                    prompt="A beautiful sunset over mountains",
                    output_path=output_path
                )

                assert result == output_path


@pytest.mark.asyncio
async def test_check_connection(comfyui_config):
    """Client can check if ComfyUI is running."""
    client = ComfyUIClient(**comfyui_config)

    with patch('httpx.AsyncClient.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        is_connected = await client.check_connection()

        assert is_connected is True
