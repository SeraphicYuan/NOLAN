"""Client for the Infographic & Animation Render Service."""

import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum

import httpx


class Engine(str, Enum):
    """Rendering engine options."""
    INFOGRAPHIC = "infographic"
    MOTION_CANVAS = "motion-canvas"
    REMOTION = "remotion"


class JobStatus(str, Enum):
    """Status of a render job."""
    PENDING = "pending"
    RENDERING = "rendering"
    DONE = "done"
    ERROR = "error"


@dataclass
class RenderJob:
    """Represents a render job."""
    job_id: str
    status: JobStatus
    progress: float = 0.0
    video_path: Optional[str] = None
    error: Optional[str] = None


class InfographicClient:
    """Client for the Infographic & Animation Render Service."""

    def __init__(self, host: str = "127.0.0.1", port: int = 3010):
        """Initialize client.

        Args:
            host: Service host.
            port: Service port.
        """
        self.base_url = f"http://{host}:{port}"
        self.timeout = httpx.Timeout(30.0, connect=10.0)

    async def health_check(self) -> bool:
        """Check if service is running.

        Returns:
            True if service is healthy, False otherwise.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception:
            return False

    async def submit(
        self,
        engine: Engine,
        data: Dict[str, Any],
        template: Optional[str] = None,
        duration: Optional[float] = None,
        audio: Optional[str] = None,
        style_prompt: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        theme: Optional[str] = None,
        engine_mode: Optional[str] = None,
    ) -> RenderJob:
        """Submit a render job.

        Args:
            engine: Rendering engine to use.
            data: Data for the infographic.
            template: Template name (optional, LLM selects if not provided).
            duration: Duration in seconds.
            audio: Path to audio file for sync.
            style_prompt: Style customization prompt.
            width: Output width in pixels.
            height: Output height in pixels.
            theme: Color theme (default, dark, warm, cool).
            engine_mode: Force rendering engine mode (auto, antv, svg).

        Returns:
            RenderJob with job_id and initial status.
        """
        payload: Dict[str, Any] = {
            "engine": engine.value,
            "data": data,
        }
        if template:
            payload["template"] = template
        if duration:
            payload["duration"] = duration
        if audio:
            payload["audio"] = audio
        if style_prompt:
            payload["style_prompt"] = style_prompt
        if width:
            payload["width"] = width
        if height:
            payload["height"] = height
        if theme:
            payload["theme"] = theme
        if engine_mode:
            payload["engine_mode"] = engine_mode

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/render",
                json=payload
            )
            response.raise_for_status()
            result = response.json()

        return RenderJob(
            job_id=result["job_id"],
            status=JobStatus(result["status"])
        )

    async def get_status(self, job_id: str) -> RenderJob:
        """Get job status.

        Args:
            job_id: The job ID.

        Returns:
            RenderJob with current status.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/render/status/{job_id}")
            response.raise_for_status()
            result = response.json()

        return RenderJob(
            job_id=result["job_id"],
            status=JobStatus(result["status"]),
            progress=result.get("progress", 0.0),
            error=result.get("error")
        )

    async def get_result(self, job_id: str) -> RenderJob:
        """Get completed job result.

        Args:
            job_id: The job ID.

        Returns:
            RenderJob with video_path.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/render/result/{job_id}")
            response.raise_for_status()
            result = response.json()

        return RenderJob(
            job_id=result["job_id"],
            status=JobStatus.DONE,
            video_path=result.get("video_path")
        )

    async def wait_for_completion(
        self,
        job_id: str,
        poll_interval: float = 1.0,
        timeout: float = 300.0,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> RenderJob:
        """Wait for job to complete.

        Args:
            job_id: The job ID.
            poll_interval: Seconds between status checks.
            timeout: Maximum wait time in seconds.
            progress_callback: Optional callback(progress: float).

        Returns:
            Completed RenderJob.

        Raises:
            TimeoutError: If job doesn't complete in time.
            RuntimeError: If job fails.
        """
        elapsed = 0.0

        while elapsed < timeout:
            job = await self.get_status(job_id)

            if progress_callback:
                progress_callback(job.progress)

            if job.status == JobStatus.DONE:
                return await self.get_result(job_id)

            if job.status == JobStatus.ERROR:
                raise RuntimeError(f"Render failed: {job.error}")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")

    async def render(
        self,
        engine: Engine,
        data: Dict[str, Any],
        template: Optional[str] = None,
        duration: Optional[float] = None,
        audio: Optional[str] = None,
        style_prompt: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        theme: Optional[str] = None,
        engine_mode: Optional[str] = None,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> Path:
        """Submit job and wait for completion.

        Convenience method that combines submit + wait.

        Args:
            engine: Rendering engine to use.
            data: Data for the infographic.
            template: Template name (optional).
            duration: Duration in seconds.
            audio: Path to audio file for sync.
            style_prompt: Style customization prompt.
            width: Output width in pixels.
            height: Output height in pixels.
            theme: Color theme (default, dark, warm, cool).
            engine_mode: Force rendering engine mode (auto, antv, svg).
            progress_callback: Optional callback(progress: float).

        Returns:
            Path to the rendered video.
        """
        job = await self.submit(
            engine=engine,
            data=data,
            template=template,
            duration=duration,
            audio=audio,
            style_prompt=style_prompt,
            width=width,
            height=height,
            theme=theme,
            engine_mode=engine_mode
        )
        completed = await self.wait_for_completion(
            job.job_id,
            progress_callback=progress_callback
        )
        return Path(completed.video_path)
