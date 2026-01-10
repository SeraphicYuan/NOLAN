"""Tests for vision provider module."""

import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

from nolan.vision import (
    VisionConfig,
    OllamaVision,
    GeminiVision,
    create_vision_provider,
)


class TestVisionConfig:
    """Tests for VisionConfig."""

    def test_defaults(self):
        """Test default configuration values."""
        config = VisionConfig()
        assert config.provider == "ollama"
        assert config.model == "qwen3-vl:8b"
        assert config.host == "127.0.0.1"
        assert config.port == 11434
        assert config.timeout == 60.0

    def test_custom_values(self):
        """Test custom configuration values."""
        config = VisionConfig(
            provider="gemini",
            model="gemini-2.0-flash",
            api_key="test-key"
        )
        assert config.provider == "gemini"
        assert config.model == "gemini-2.0-flash"
        assert config.api_key == "test-key"


class TestOllamaVision:
    """Tests for OllamaVision provider."""

    def test_init(self):
        """Test initialization."""
        config = VisionConfig(model="llava:7b", port=11435)
        vision = OllamaVision(config)
        assert vision.model == "llava:7b"
        assert vision.base_url == "http://127.0.0.1:11435"

    @pytest.mark.asyncio
    async def test_describe_image(self, tmp_path):
        """Test image description."""
        config = VisionConfig()
        vision = OllamaVision(config)

        # Create a test image
        test_image = tmp_path / "test.jpg"
        test_image.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # Minimal JPEG

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            # Chat API returns message.content instead of response
            mock_response.json.return_value = {
                "message": {"content": "A test image description"}
            }
            mock_response.raise_for_status = Mock()

            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value.post = AsyncMock(return_value=mock_response)

            result = await vision.describe_image(test_image, "Describe this image")
            assert result == "A test image description"

    @pytest.mark.asyncio
    async def test_check_connection_success(self):
        """Test connection check success."""
        config = VisionConfig()
        vision = OllamaVision(config)

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200

            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value.get = AsyncMock(return_value=mock_response)

            result = await vision.check_connection()
            assert result is True

    @pytest.mark.asyncio
    async def test_check_connection_failure(self):
        """Test connection check failure."""
        config = VisionConfig()
        vision = OllamaVision(config)

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value.get = AsyncMock(side_effect=Exception("Connection refused"))

            result = await vision.check_connection()
            assert result is False


class TestCreateVisionProvider:
    """Tests for vision provider factory."""

    def test_create_ollama(self):
        """Test creating Ollama provider."""
        config = VisionConfig(provider="ollama")
        provider = create_vision_provider(config)
        assert isinstance(provider, OllamaVision)

    def test_create_gemini(self):
        """Test creating Gemini provider."""
        config = VisionConfig(provider="gemini", api_key="test")
        provider = create_vision_provider(config)
        assert isinstance(provider, GeminiVision)

    def test_unknown_provider(self):
        """Test unknown provider raises error."""
        config = VisionConfig(provider="unknown")
        with pytest.raises(ValueError, match="Unknown vision provider"):
            create_vision_provider(config)
