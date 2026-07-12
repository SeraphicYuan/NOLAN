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
    provider: str = "ollama"  # ollama, gemini, openrouter
    model: str = "qwen3-vl:8b"
    host: str = "127.0.0.1"  # Use IP, not hostname (Windows httpx issue)
    port: int = 11434
    timeout: float = 60.0
    # Gemini / OpenRouter-specific
    api_key: Optional[str] = None
    # OpenRouter-specific (OpenAI-compatible endpoint)
    base_url: str = "https://openrouter.ai/api/v1"
    # Reasoning control for reasoning-capable OpenRouter models (e.g. qwen plus/max).
    # Disabled by default: cuts latency ~4-6x with negligible quality loss for
    # frame analysis. Set reasoning_enabled=True (optionally with a small
    # reasoning_max_tokens budget) to allow thinking on ambiguous frames.
    reasoning_enabled: bool = False
    reasoning_max_tokens: Optional[int] = None


def build_frame_analysis_prompt(
    transcript: Optional[str] = None,
    timestamp: Optional[float] = None,
) -> str:
    """Build the combined frame-analysis prompt shared by all providers.

    Keeping this in one place guarantees Gemini and OpenRouter (and any future
    provider) send identical instructions, which is required for fair
    cross-provider comparison.
    """
    time_context = ""
    if timestamp is not None:
        minutes = int(timestamp // 60)
        seconds = int(timestamp % 60)
        time_context = f" at {minutes}:{seconds:02d}"

    if transcript and transcript.strip():
        return f"""Analyze this video frame{time_context} along with its transcript.

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

    # No transcript - simpler prompt
    return f"""Analyze this video frame{time_context}.

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


def parse_frame_analysis_response(
    response: str,
    transcript: Optional[str] = None,
) -> FrameAnalysisResult:
    """Parse a model's JSON response into a FrameAnalysisResult.

    Shared across providers so parsing/fallback behaviour is identical.
    """
    try:
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]

        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            json_str = response[start:end]
            data = json.loads(json_str)

            frame_desc = data.get("frame_description", "")
            combined_summary = data.get("combined_summary")
            context = data.get("inferred_context", {}) or {}

            if not combined_summary and transcript:
                combined_summary = f"{frame_desc} | Audio: {transcript[:100]}..."

            return FrameAnalysisResult(
                frame_description=frame_desc,
                combined_summary=combined_summary,
                people=context.get("people", []),
                location=context.get("location"),
                story_context=context.get("story_context"),
                objects=context.get("objects", []),
                confidence=context.get("confidence", "low"),
            )
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    return FrameAnalysisResult(
        frame_description=response[:500] if response else "No description available"
    )


def _is_rate_limit_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(token in message for token in ("429", "rate limit", "resource_exhausted"))


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
        prompt = build_frame_analysis_prompt(transcript, timestamp)

        try:
            response = await client.generate_with_image(prompt, str(image_path))
            return parse_frame_analysis_response(response, transcript)
        except Exception as e:
            if _is_rate_limit_error(e):
                raise
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


class OpenRouterVision(VisionProvider):
    """OpenRouter-based vision provider (OpenAI-compatible chat completions).

    OpenRouter proxies many vision-capable models (e.g. qwen/qwen3.7-plus) behind
    a single OpenAI-style /chat/completions endpoint. Images are sent inline as
    base64 data URLs. Uses the same analysis prompt + parser as Gemini for fair
    cross-provider comparison.
    """

    def __init__(self, config: VisionConfig):
        """Initialize OpenRouter vision provider.

        Args:
            config: Vision configuration (api_key, model, base_url, timeout).
        """
        self.api_key = config.api_key
        self.model = config.model
        self.base_url = config.base_url.rstrip("/")
        self.timeout = config.timeout
        self.reasoning_enabled = config.reasoning_enabled
        self.reasoning_max_tokens = config.reasoning_max_tokens
        # Token usage accumulates across calls for cost reporting.
        self.last_usage: Optional[Dict[str, Any]] = None

    def _reasoning_param(self) -> Optional[Dict[str, Any]]:
        """OpenRouter `reasoning` field for reasoning-capable models.

        Returns None (omit) when reasoning is enabled without a budget, so the
        model uses its default thinking behaviour. Non-reasoning models ignore
        this field, so it is always safe to send.
        """
        if not self.reasoning_enabled:
            return {"enabled": False}
        if self.reasoning_max_tokens:
            return {"max_tokens": self.reasoning_max_tokens}
        return None

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # Optional attribution headers recommended by OpenRouter.
            "HTTP-Referer": "https://github.com/nolan",
            "X-Title": "NOLAN",
        }

    @staticmethod
    def _encode_image(image_path: Path) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    async def _chat(self, prompt: str, image_path: Path) -> str:
        """Send a single text+image chat completion and return the content."""
        image_b64 = self._encode_image(image_path)
        payload = {
            "model": self.model,
            "temperature": 0,   # vision here is JUDGING/describing (verdicts, captions, relevance) — determinism
                                # beats variety: the render gate gave different scores on unchanged scenes.
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            },
                        },
                    ],
                }
            ],
        }
        reasoning = self._reasoning_param()
        if reasoning is not None:
            payload["reasoning"] = reasoning

        timeout = httpx.Timeout(self.timeout, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
            )
            response.raise_for_status()
            result = response.json()

        self.last_usage = result.get("usage")
        choices = result.get("choices") or []
        if not choices:
            raise RuntimeError(f"OpenRouter returned no choices: {str(result)[:300]}")
        return (choices[0]["message"].get("content") or "").strip()

    async def describe_image(self, image_path: Path, prompt: str) -> str:
        """Describe an image using the configured OpenRouter model."""
        return await self._chat(prompt, image_path)

    async def check_connection(self) -> bool:
        """Check that the OpenRouter API key is valid and reachable."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return response.status_code == 200
        except Exception:
            return False

    async def analyze_frame(
        self,
        image_path: Path,
        transcript: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> FrameAnalysisResult:
        """Analyze a video frame with optional transcript in a single call.

        Uses the shared analysis prompt + parser so results are directly
        comparable to the Gemini provider.
        """
        prompt = build_frame_analysis_prompt(transcript, timestamp)
        try:
            response = await self._chat(prompt, image_path)
            return parse_frame_analysis_response(response, transcript)
        except Exception as e:
            if _is_rate_limit_error(e):
                raise
            # Fallback to simple description.
            try:
                simple_desc = await self._chat(
                    "Describe this video frame in one sentence.", image_path
                )
                return FrameAnalysisResult(frame_description=simple_desc)
            except Exception:
                return FrameAnalysisResult(
                    frame_description=f"Frame analysis failed: {str(e)}"
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
        "openrouter": OpenRouterVision,
    }

    provider_class = providers.get(config.provider.lower())
    if provider_class is None:
        raise ValueError(f"Unknown vision provider: {config.provider}. "
                        f"Available: {list(providers.keys())}")

    return provider_class(config)
