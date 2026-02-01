"""
Video generation backends for NOLAN.

Provides unified interface for video generation with two backends:
- ComfyUI: Local video models (LTX-Video, Wan, HunyuanVideo, etc.)
- Runway: Commercial API (Gen-3/Gen-4)

Usage:
    # ComfyUI (local)
    generator = ComfyUIVideoGenerator(workflow_file="workflows/ltx-video.json")
    video_path = await generator.generate(prompt="sunset over mountains", output_path=Path("out.mp4"))

    # Runway (commercial)
    generator = RunwayGenerator(api_key="...")
    video_path = await generator.generate(prompt="sunset over mountains", output_path=Path("out.mp4"))
"""

import json
import asyncio
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List, Literal

import httpx


@dataclass
class VideoGenerationResult:
    """Result of video generation."""
    success: bool
    video_path: Optional[Path] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None
    generation_time_seconds: Optional[float] = None
    cost_usd: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VideoGenerationConfig:
    """Configuration for video generation."""
    duration: float = 4.0  # seconds
    width: int = 1280
    height: int = 720
    fps: int = 24
    aspect_ratio: str = "16:9"
    style: Optional[str] = None  # style preset
    negative_prompt: Optional[str] = None
    seed: Optional[int] = None  # None = random


class VideoGenerator(ABC):
    """Abstract base for video generation backends."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        output_path: Path,
        config: Optional[VideoGenerationConfig] = None,
        timeout: float = 600.0
    ) -> VideoGenerationResult:
        """Generate a video clip from a text prompt.

        Args:
            prompt: Text description of the video to generate.
            output_path: Where to save the generated video.
            config: Generation configuration options.
            timeout: Maximum time to wait for generation (seconds).

        Returns:
            VideoGenerationResult with success status and video path.
        """
        pass

    @abstractmethod
    async def check_connection(self) -> bool:
        """Check if the backend is available.

        Returns:
            True if backend is reachable and ready.
        """
        pass

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Return the name of this backend."""
        pass


class ComfyUIVideoGenerator(VideoGenerator):
    """Video generation using ComfyUI with video models.

    Supports workflows for:
    - LTX-Video (Lightricks)
    - Wan (Alibaba)
    - HunyuanVideo (Tencent)
    - CogVideoX
    - AnimateDiff / AnimateLCM
    - Any other video model with ComfyUI workflow

    The workflow file should be in ComfyUI API format and contain:
    - A text prompt input node (auto-detected or specified)
    - A video output node (SaveAnimatedWEBP, VHS_VideoCombine, etc.)
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8188,
        workflow_file: Optional[Path] = None,
        workflow: Optional[Dict] = None,
        prompt_node: Optional[str] = None,
        negative_node: Optional[str] = None,
        duration_node: Optional[str] = None,
        node_overrides: Optional[List[str]] = None,
    ):
        """Initialize ComfyUI video generator.

        Args:
            host: ComfyUI server host.
            port: ComfyUI server port.
            workflow_file: Path to workflow JSON file.
            workflow: Workflow dict (alternative to file).
            prompt_node: Node ID for positive prompt (auto-detected if None).
            negative_node: Node ID for negative prompt (auto-detected if None).
            duration_node: Node ID for duration/frames input (auto-detected if None).
            node_overrides: List of "node_id:param=value" strings.
        """
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self._node_overrides = self._parse_overrides(node_overrides or [])

        # Load workflow
        if workflow_file:
            self.workflow = self._load_workflow_file(Path(workflow_file))
        elif workflow:
            self.workflow = workflow
        else:
            raise ValueError("Either workflow_file or workflow must be provided")

        # Store explicit node mappings
        self._prompt_node = prompt_node
        self._negative_node = negative_node
        self._duration_node = duration_node

        # Auto-detect nodes if not specified
        self._detected_nodes = self._detect_nodes()

    def _load_workflow_file(self, workflow_path: Path) -> Dict[str, Any]:
        """Load and convert workflow file."""
        with open(workflow_path, 'r', encoding='utf-8') as f:
            workflow = json.load(f)

        # Check if UI format (has "nodes" array) vs API format
        if "nodes" in workflow:
            return self._convert_ui_to_api_format(workflow)
        return workflow

    def _convert_ui_to_api_format(self, ui_workflow: Dict[str, Any]) -> Dict[str, Any]:
        """Convert ComfyUI UI format to API format."""
        api_workflow = {}

        for node in ui_workflow.get("nodes", []):
            node_id = str(node["id"])
            class_type = node.get("type", "")

            if not class_type or "Note" in class_type or "Markdown" in class_type:
                continue

            inputs = {}
            widget_values = node.get("widgets_values", [])

            # Process input links
            for input_def in node.get("inputs", []):
                link_id = input_def.get("link")
                if link_id is not None:
                    for link in ui_workflow.get("links", []):
                        if link[0] == link_id:
                            source_node_id = str(link[1])
                            source_slot = link[2]
                            input_name = input_def.get("name", "")
                            inputs[input_name] = [source_node_id, source_slot]
                            break

            # Add widget values as inputs
            # This varies by node type - video workflows have many custom nodes
            # We'll rely on explicit node_overrides for complex cases
            api_workflow[node_id] = {
                "class_type": class_type,
                "inputs": inputs,
                "_meta": {"title": node.get("title", "")},
                "_widget_values": widget_values  # Store for reference
            }

        return api_workflow

    def _parse_overrides(self, overrides: List[str]) -> Dict[str, Dict[str, Any]]:
        """Parse node override strings."""
        result = {}
        for override in overrides:
            try:
                node_part, value_part = override.split("=", 1)
                node_id, param = node_part.rsplit(":", 1)
                value = self._convert_value(value_part)
                if node_id not in result:
                    result[node_id] = {}
                result[node_id][param] = value
            except ValueError:
                raise ValueError(f"Invalid override format: '{override}'. Use 'node_id:param=value'")
        return result

    def _convert_value(self, value_str: str) -> Any:
        """Convert string value to appropriate Python type."""
        try:
            return int(value_str)
        except ValueError:
            pass
        try:
            return float(value_str)
        except ValueError:
            pass
        if value_str.lower() in ("true", "false"):
            return value_str.lower() == "true"
        return value_str

    def _detect_nodes(self) -> Dict[str, Optional[str]]:
        """Auto-detect prompt and duration nodes in workflow."""
        detected = {"prompt": None, "negative": None, "duration": None}

        # Common video workflow node types for text input
        text_input_types = {
            "CLIPTextEncode", "CLIPTextEncodeSDXL",
            "PrimitiveStringMultiline", "String Multiline",
            "LTXVPromptEncode", "CogVideoTextEncode",
        }

        # Common video output node types
        video_output_types = {
            "SaveAnimatedWEBP", "VHS_VideoCombine", "SaveVideo",
            "LTXVSaveVideo", "AnimateDiffCombine",
        }

        for node_id, node_data in self.workflow.items():
            class_type = node_data.get("class_type", "")
            inputs = node_data.get("inputs", {})
            meta = node_data.get("_meta", {})
            title = meta.get("title", "").lower()

            # Detect prompt nodes
            if class_type in text_input_types or "TextEncode" in class_type:
                text = inputs.get("text", inputs.get("value", ""))
                if isinstance(text, str):
                    # Check for negative prompt indicators
                    is_negative = (
                        "negative" in title or
                        "negative" in class_type.lower() or
                        "low quality" in text.lower() or
                        "blurry" in text.lower()
                    )
                    if is_negative:
                        detected["negative"] = node_id
                    elif "positive" in title or detected["prompt"] is None:
                        detected["prompt"] = node_id

            # Detect duration nodes (frames or seconds)
            if "duration" in title or "frames" in title or "length" in title:
                detected["duration"] = node_id

        return detected

    @property
    def backend_name(self) -> str:
        return "comfyui"

    async def check_connection(self) -> bool:
        """Check if ComfyUI server is running."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/system_stats", timeout=5.0)
                return response.status_code == 200
        except Exception:
            return False

    def _build_workflow(
        self,
        prompt: str,
        config: VideoGenerationConfig
    ) -> Dict[str, Any]:
        """Build workflow with prompt and config injected."""
        workflow = json.loads(json.dumps(self.workflow))  # Deep copy

        # Inject positive prompt
        prompt_node = self._prompt_node or self._detected_nodes.get("prompt")
        if prompt_node and prompt_node in workflow:
            node = workflow[prompt_node]
            inputs = node.get("inputs", {})
            if "text" in inputs:
                inputs["text"] = prompt
            elif "value" in inputs:
                inputs["value"] = prompt

        # Inject negative prompt
        negative_node = self._negative_node or self._detected_nodes.get("negative")
        if negative_node and negative_node in workflow and config.negative_prompt:
            node = workflow[negative_node]
            inputs = node.get("inputs", {})
            if "text" in inputs:
                inputs["text"] = config.negative_prompt
            elif "value" in inputs:
                inputs["value"] = config.negative_prompt

        # Randomize seed if not specified
        if config.seed is None:
            for node_id, node_data in workflow.items():
                if "seed" in node_data.get("inputs", {}):
                    node_data["inputs"]["seed"] = random.randint(0, 2**32)
        else:
            for node_id, node_data in workflow.items():
                if "seed" in node_data.get("inputs", {}):
                    node_data["inputs"]["seed"] = config.seed

        # Apply node overrides
        for node_id, params in self._node_overrides.items():
            if node_id in workflow:
                if "inputs" not in workflow[node_id]:
                    workflow[node_id]["inputs"] = {}
                for param, value in params.items():
                    workflow[node_id]["inputs"][param] = value

        # Remove internal metadata before sending
        for node_id, node_data in workflow.items():
            node_data.pop("_meta", None)
            node_data.pop("_widget_values", None)

        return workflow

    async def _queue_prompt(self, workflow: Dict) -> str:
        """Queue a prompt for execution."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow}
            )
            if response.status_code != 200:
                error_detail = response.text
                raise RuntimeError(f"ComfyUI error ({response.status_code}): {error_detail}")
            return response.json()["prompt_id"]

    async def _wait_for_completion(
        self,
        prompt_id: str,
        timeout: float = 600.0,
        poll_interval: float = 2.0
    ) -> Dict:
        """Wait for video generation to complete."""
        elapsed = 0.0

        async with httpx.AsyncClient() as client:
            while elapsed < timeout:
                response = await client.get(f"{self.base_url}/history/{prompt_id}")

                if response.status_code == 200:
                    history = response.json()
                    if prompt_id in history:
                        return history[prompt_id]

                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

        raise TimeoutError(f"Video generation timed out after {timeout}s")

    async def _download_output(
        self,
        filename: str,
        subfolder: str,
        output_path: Path,
        output_type: str = "output"
    ) -> Path:
        """Download generated video from ComfyUI."""
        async with httpx.AsyncClient() as client:
            params = {"filename": filename, "subfolder": subfolder, "type": output_type}
            response = await client.get(f"{self.base_url}/view", params=params, timeout=60.0)
            response.raise_for_status()

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(response.content)

            return output_path

    async def generate(
        self,
        prompt: str,
        output_path: Path,
        config: Optional[VideoGenerationConfig] = None,
        timeout: float = 600.0
    ) -> VideoGenerationResult:
        """Generate a video from a text prompt."""
        config = config or VideoGenerationConfig()
        start_time = time.time()

        try:
            # Build and queue workflow
            workflow = self._build_workflow(prompt, config)
            prompt_id = await self._queue_prompt(workflow)

            # Wait for completion
            result = await self._wait_for_completion(prompt_id, timeout=timeout)

            # Find and download video output
            outputs = result.get("outputs", {})
            for node_id, node_output in outputs.items():
                # Check for video outputs (different formats)
                for key in ["videos", "gifs", "images"]:
                    if key in node_output:
                        output_info = node_output[key][0]
                        filename = output_info["filename"]
                        subfolder = output_info.get("subfolder", "")
                        output_type = output_info.get("type", "output")

                        # Download with appropriate extension
                        final_path = output_path
                        if not final_path.suffix:
                            ext = Path(filename).suffix
                            final_path = output_path.with_suffix(ext)

                        await self._download_output(filename, subfolder, final_path, output_type)

                        generation_time = time.time() - start_time
                        return VideoGenerationResult(
                            success=True,
                            video_path=final_path,
                            duration_seconds=config.duration,
                            generation_time_seconds=generation_time,
                            metadata={"prompt_id": prompt_id, "backend": "comfyui"}
                        )

            return VideoGenerationResult(
                success=False,
                error="No video output found in ComfyUI result"
            )

        except Exception as e:
            return VideoGenerationResult(
                success=False,
                error=str(e),
                generation_time_seconds=time.time() - start_time
            )


class RunwayGenerator(VideoGenerator):
    """Video generation using Runway Gen-3/Gen-4 API.

    Runway provides high-quality video generation with:
    - Gen-3 Alpha Turbo (fast, lower cost)
    - Gen-3 Alpha (higher quality)
    - Gen-4 (latest, experimental)

    Requires RUNWAY_API_KEY environment variable or explicit api_key.
    """

    # Runway model tiers
    MODEL_GEN3_TURBO = "gen3a_turbo"
    MODEL_GEN3 = "gen3a"
    # MODEL_GEN4 = "gen4"  # Not yet available via API

    # Pricing per second of video (approximate, may change)
    PRICING = {
        MODEL_GEN3_TURBO: 0.05,  # $0.05/second
        MODEL_GEN3: 0.10,  # $0.10/second
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = MODEL_GEN3_TURBO,
        base_url: str = "https://api.runwayml.com/v1",
    ):
        """Initialize Runway generator.

        Args:
            api_key: Runway API key. Uses RUNWAY_API_KEY env var if not provided.
            model: Model to use (gen3a_turbo or gen3a).
            base_url: Runway API base URL.
        """
        import os
        self.api_key = api_key or os.environ.get("RUNWAY_API_KEY")
        if not self.api_key:
            raise ValueError("Runway API key required. Set RUNWAY_API_KEY or pass api_key.")

        self.model = model
        self.base_url = base_url

    @property
    def backend_name(self) -> str:
        return "runway"

    async def check_connection(self) -> bool:
        """Check if Runway API is accessible."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10.0
                )
                return response.status_code in (200, 401, 403)  # 401/403 = auth issue but API is up
        except Exception:
            return False

    async def generate(
        self,
        prompt: str,
        output_path: Path,
        config: Optional[VideoGenerationConfig] = None,
        timeout: float = 600.0
    ) -> VideoGenerationResult:
        """Generate a video using Runway API."""
        config = config or VideoGenerationConfig()
        start_time = time.time()

        try:
            async with httpx.AsyncClient() as client:
                # Create generation task
                # Note: Runway API format may vary - this is based on documented patterns
                create_response = await client.post(
                    f"{self.base_url}/generations",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "duration": int(config.duration),  # Runway uses integer seconds
                        "ratio": config.aspect_ratio.replace(":", ":"),  # "16:9"
                        "seed": config.seed,
                    },
                    timeout=30.0
                )

                if create_response.status_code != 200:
                    return VideoGenerationResult(
                        success=False,
                        error=f"Runway API error: {create_response.status_code} - {create_response.text}"
                    )

                task_data = create_response.json()
                task_id = task_data.get("id")

                if not task_id:
                    return VideoGenerationResult(
                        success=False,
                        error=f"No task ID in response: {task_data}"
                    )

                # Poll for completion
                elapsed = 0.0
                poll_interval = 5.0

                while elapsed < timeout:
                    status_response = await client.get(
                        f"{self.base_url}/generations/{task_id}",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        timeout=30.0
                    )

                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        status = status_data.get("status", "")

                        if status == "completed":
                            video_url = status_data.get("output", {}).get("url")
                            if video_url:
                                # Download video
                                video_response = await client.get(video_url, timeout=120.0)
                                video_response.raise_for_status()

                                output_path.parent.mkdir(parents=True, exist_ok=True)
                                output_path.write_bytes(video_response.content)

                                generation_time = time.time() - start_time
                                cost = config.duration * self.PRICING.get(self.model, 0.10)

                                return VideoGenerationResult(
                                    success=True,
                                    video_path=output_path,
                                    duration_seconds=config.duration,
                                    generation_time_seconds=generation_time,
                                    cost_usd=cost,
                                    metadata={
                                        "task_id": task_id,
                                        "backend": "runway",
                                        "model": self.model
                                    }
                                )
                            else:
                                return VideoGenerationResult(
                                    success=False,
                                    error="No video URL in completed response"
                                )

                        elif status == "failed":
                            error_msg = status_data.get("error", "Unknown error")
                            return VideoGenerationResult(
                                success=False,
                                error=f"Generation failed: {error_msg}"
                            )

                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval

                return VideoGenerationResult(
                    success=False,
                    error=f"Generation timed out after {timeout}s"
                )

        except Exception as e:
            return VideoGenerationResult(
                success=False,
                error=str(e),
                generation_time_seconds=time.time() - start_time
            )


class VideoGeneratorFactory:
    """Factory for creating video generators."""

    @staticmethod
    def create(
        backend: Literal["comfyui", "runway"],
        **kwargs
    ) -> VideoGenerator:
        """Create a video generator for the specified backend.

        Args:
            backend: "comfyui" or "runway"
            **kwargs: Backend-specific configuration

        Returns:
            VideoGenerator instance
        """
        if backend == "comfyui":
            return ComfyUIVideoGenerator(**kwargs)
        elif backend == "runway":
            return RunwayGenerator(**kwargs)
        else:
            raise ValueError(f"Unknown backend: {backend}")


# Utility function for scene-to-video generation
async def generate_video_for_scene(
    generator: VideoGenerator,
    visual_description: str,
    narration_excerpt: str,
    output_path: Path,
    config: Optional[VideoGenerationConfig] = None,
    style_hint: Optional[str] = None,
) -> VideoGenerationResult:
    """Generate a video clip for a scene.

    Constructs an optimized prompt from scene metadata and generates video.

    Args:
        generator: Video generator to use.
        visual_description: Scene's visual description.
        narration_excerpt: What's being said during this scene.
        output_path: Where to save the video.
        config: Generation configuration.
        style_hint: Optional style guidance (e.g., "cinematic", "documentary").

    Returns:
        VideoGenerationResult with generated video path.
    """
    # Build an optimized video generation prompt
    prompt_parts = []

    # Add style hint first (guides overall aesthetic)
    if style_hint:
        prompt_parts.append(f"{style_hint} style.")

    # Add the visual description (main content)
    prompt_parts.append(visual_description)

    # Add context from narration if it helps
    # (Be selective - video gen prompts work better with visual descriptions)
    if narration_excerpt and len(narration_excerpt) < 100:
        # Short narration might contain useful context
        prompt_parts.append(f"Context: {narration_excerpt}")

    # Add quality boosters
    prompt_parts.append("High quality, professional videography, smooth motion.")

    prompt = " ".join(prompt_parts)

    return await generator.generate(prompt, output_path, config)
