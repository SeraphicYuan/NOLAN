"""Vision provider abstraction for frame analysis."""

import base64
import json
import re
import httpx
from abc import ABC, abstractmethod
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class FrameAnalysisResult:
    """Result of combined frame analysis (vision + inference in one call)."""
    frame_description: str
    combined_summary: Optional[str] = None
    people: List[str] = field(default_factory=list)
    location: Optional[str] = None
    story_context: Optional[str] = None
    objects: List[str] = field(default_factory=list)
    confidence: str = "low"

    def to_inferred_context(self):
        """Convert to InferredContext object."""
        from nolan.indexer import InferredContext
        return InferredContext(
            people=self.people,
            location=self.location,
            story_context=self.story_context,
            objects=self.objects,
            confidence=self.confidence
        )


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

    async def analyze_frame(
        self,
        image_path: Path,
        transcript: Optional[str] = None,
        timestamp: Optional[float] = None
    ) -> FrameAnalysisResult:
        """Analyze a video frame with optional transcript in a single call.

        This combines frame description and context inference into one API call,
        reducing latency and cost by 50% compared to separate calls.

        Args:
            image_path: Path to frame image file.
            transcript: Optional transcript text for this segment.
            timestamp: Optional timestamp for context.

        Returns:
            FrameAnalysisResult with description and inferred context.
        """
        # Default implementation falls back to simple description
        description = await self.describe_image(
            image_path,
            "Describe this video frame in one sentence. Focus on the main subject, action, and setting."
        )
        return FrameAnalysisResult(frame_description=description)


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
        self.model = config.model or "gemini-3-flash-preview"
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

    async def analyze_frame(
        self,
        image_path: Path,
        transcript: Optional[str] = None,
        timestamp: Optional[float] = None
    ) -> FrameAnalysisResult:
        """Analyze a video frame with optional transcript in a single call.

        Combines frame description and context inference into one API call,
        reducing latency and cost by 50% compared to separate calls.

        Args:
            image_path: Path to frame image file.
            transcript: Optional transcript text for this segment.
            timestamp: Optional timestamp for context.

        Returns:
            FrameAnalysisResult with description and inferred context.
        """
        client = self._get_client()

        # Build time context
        time_context = ""
        if timestamp is not None:
            minutes = int(timestamp // 60)
            seconds = int(timestamp % 60)
            time_context = f" at {minutes}:{seconds:02d}"

        # Build prompt based on whether transcript is available
        if transcript and transcript.strip():
            prompt = f"""Analyze this video frame{time_context} along with its transcript.

TRANSCRIPT: {transcript}

Respond with a JSON object containing:

1. "frame_description": A single sentence describing what you SEE in the image (visual only).

2. "combined_summary": A 1-2 sentence description that captures BOTH what's seen AND what's being said. This should be useful for searching this video segment.

3. "inferred_context": An object with these fields (ONLY include fields where you have evidence from the image or transcript - omit fields without evidence):
   - "people": Array of identifiable people. Use names if you can identify them or they're mentioned. Otherwise use descriptions like "male speaker", "interviewer".
   - "location": Specific place if identifiable from visual cues or audio mentions.
   - "story_context": Brief narrative context - what's happening in the story/video at this moment.
   - "objects": Notable objects relevant to the content.
   - "confidence": "high" (explicit mention/clear visual), "medium" (strong implication), or "low" (educated guess).

IMPORTANT:
- For "people", try to identify who they are from visual appearance (face recognition) or name mentions in transcript.
- Only include inferred_context fields you have actual evidence for.
- The combined_summary should fuse visual and audio information.

Respond ONLY with valid JSON, no other text."""
        else:
            # No transcript - simpler prompt
            prompt = f"""Analyze this video frame{time_context}.

Respond with a JSON object containing:

1. "frame_description": A single sentence describing what you SEE in the image.

2. "inferred_context": An object with these fields (ONLY include fields where you have visual evidence - omit fields without evidence):
   - "people": Array of identifiable people from visual appearance.
   - "location": Specific place if identifiable from visual cues.
   - "story_context": Brief context of what's happening based on visuals.
   - "objects": Notable objects in the frame.
   - "confidence": "high", "medium", or "low" based on visual clarity.

IMPORTANT: Only include fields you have actual evidence for from the image.

Respond ONLY with valid JSON, no other text."""

        try:
            response = await client.generate_with_image(prompt, str(image_path))
            return self._parse_analysis_response(response, transcript)
        except Exception as e:
            # Fallback to simple description
            try:
                simple_desc = await self.describe_image(
                    image_path,
                    "Describe this video frame in one sentence."
                )
                return FrameAnalysisResult(frame_description=simple_desc)
            except Exception:
                return FrameAnalysisResult(
                    frame_description=f"Frame analysis failed: {str(e)}"
                )

    def _parse_analysis_response(
        self,
        response: str,
        transcript: Optional[str]
    ) -> FrameAnalysisResult:
        """Parse the JSON response from analyze_frame.

        Args:
            response: Raw response from LLM.
            transcript: Original transcript (for fallback).

        Returns:
            Parsed FrameAnalysisResult.
        """
        # Try to extract JSON from response
        try:
            # Find JSON in response
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]

            # Find JSON object boundaries
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = response[start:end]
                data = json.loads(json_str)

                # Extract fields
                frame_desc = data.get("frame_description", "")
                combined_summary = data.get("combined_summary")
                context = data.get("inferred_context", {})

                # If no combined_summary but we have transcript, create one
                if not combined_summary and transcript:
                    combined_summary = f"{frame_desc} | Audio: {transcript[:100]}..."

                return FrameAnalysisResult(
                    frame_description=frame_desc,
                    combined_summary=combined_summary,
                    people=context.get("people", []),
                    location=context.get("location"),
                    story_context=context.get("story_context"),
                    objects=context.get("objects", []),
                    confidence=context.get("confidence", "low")
                )
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

        # Fallback: use raw response as description
        return FrameAnalysisResult(
            frame_description=response[:500] if response else "No description available"
        )


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
