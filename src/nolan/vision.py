"""Vision provider abstraction for frame analysis."""

import base64
import httpx
from abc import ABC, abstractmethod
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class VisionConfig:
    """Configuration for vision providers."""
    provider: str = "ollama"  # ollama, gemini
    model: str = "qwen3-vl:8b"
    host: str = "127.0.0.1"  # Use IP, not hostname (Windows httpx issue)
    port: int = 11434
    timeout: float = 60.0
    # Gemini-specific
    api_key: Optional[str] = None


class VisionProvider(ABC):
    """Abstract base class for vision providers."""

    @abstractmethod
    async def describe_image(self, image_path: Path, prompt: str) -> str:
        """Describe an image using the vision model.

        Args:
            image_path: Path to image file.
            prompt: Prompt for the model.

        Returns:
            Model's description of the image.
        """
        pass

    @abstractmethod
    async def check_connection(self) -> bool:
        """Check if the provider is available.

        Returns:
            True if connection successful.
        """
        pass


class OllamaVision(VisionProvider):
    """Ollama-based vision provider."""

    def __init__(self, config: VisionConfig):
        """Initialize Ollama vision provider.

        Args:
            config: Vision configuration.
        """
        self.model = config.model
        self.base_url = f"http://{config.host}:{config.port}"
        self.timeout = config.timeout

    async def describe_image(self, image_path: Path, prompt: str) -> str:
        """Describe an image using Ollama vision model.

        Args:
            image_path: Path to image file.
            prompt: Prompt for the model.

        Returns:
            Model's description of the image.
        """
        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        # Use chat API for vision models
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_data]
                }
            ],
            "stream": False
        }

        timeout = httpx.Timeout(self.timeout, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            result = response.json()
            # Extract content from chat response
            message = result.get("message", {})
            return message.get("content", "").strip()

    async def check_connection(self) -> bool:
        """Check if Ollama is available.

        Returns:
            True if connection successful.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """List available models in Ollama.

        Returns:
            List of model names.
        """
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]


class GeminiVision(VisionProvider):
    """Gemini-based vision provider (uses existing LLM client)."""

    def __init__(self, config: VisionConfig):
        """Initialize Gemini vision provider.

        Args:
            config: Vision configuration.
        """
        self.api_key = config.api_key
        self.model = config.model or "gemini-2.0-flash"
        self._client = None

    def _get_client(self):
        """Lazy-load the Gemini client."""
        if self._client is None:
            from nolan.llm import GeminiClient
            self._client = GeminiClient(
                api_key=self.api_key,
                model=self.model
            )
        return self._client

    async def describe_image(self, image_path: Path, prompt: str) -> str:
        """Describe an image using Gemini.

        Args:
            image_path: Path to image file.
            prompt: Prompt for the model.

        Returns:
            Model's description of the image.
        """
        client = self._get_client()
        return await client.generate_with_image(prompt, str(image_path))

    async def check_connection(self) -> bool:
        """Check if Gemini API is available.

        Returns:
            True if connection successful.
        """
        try:
            client = self._get_client()
            # Simple test call
            await client.generate("Say 'ok'")
            return True
        except Exception:
            return False


def create_vision_provider(config: VisionConfig) -> VisionProvider:
    """Factory function to create vision provider.

    Args:
        config: Vision configuration.

    Returns:
        Configured VisionProvider instance.
    """
    providers = {
        "ollama": OllamaVision,
        "gemini": GeminiVision,
    }

    provider_class = providers.get(config.provider.lower())
    if provider_class is None:
        raise ValueError(f"Unknown vision provider: {config.provider}. "
                        f"Available: {list(providers.keys())}")

    return provider_class(config)
