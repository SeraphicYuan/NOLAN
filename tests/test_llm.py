"""Tests for LLM client."""

import pytest
from unittest.mock import Mock, patch

from nolan.llm import GeminiClient


def test_gemini_client_initialization():
    """Client initializes with API key."""
    client = GeminiClient(api_key="test-key", model="gemini-3-flash-preview")

    assert client.api_key == "test-key"
    assert client.model == "gemini-3-flash-preview"


@pytest.mark.asyncio
async def test_generate_text_returns_response():
    """Client returns generated text from API."""
    client = GeminiClient(api_key="test-key", model="gemini-3-flash-preview")

    with patch.object(client, '_call_api') as mock_call:
        mock_call.return_value = "Generated response"

        result = await client.generate("Test prompt")

        assert result == "Generated response"
        mock_call.assert_called_once()
