"""ComfyUI integration for NOLAN."""

import json
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any

import httpx


# Default workflow template for text-to-image
DEFAULT_WORKFLOW = {
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "cfg": 7,
            "denoise": 1,
            "latent_image": ["5", 0],
            "model": ["4", 0],
            "negative": ["7", 0],
            "positive": ["6", 0],
            "sampler_name": "euler",
            "scheduler": "normal",
            "seed": 42,
            "steps": 20
        }
    },
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {
            "ckpt_name": "sd_xl_base_1.0.safetensors"
        }
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {
            "batch_size": 1,
            "height": 1080,
            "width": 1920
        }
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["4", 1],
            "text": ""
        }
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["4", 1],
            "text": "blurry, low quality, distorted"
        }
    },
    "8": {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["3", 0],
            "vae": ["4", 2]
        }
    },
    "9": {
        "class_type": "SaveImage",
        "inputs": {
            "filename_prefix": "nolan",
            "images": ["8", 0]
        }
    }
}


class ComfyUIClient:
    """Client for ComfyUI image generation API."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8188,
        width: int = 1920,
        height: int = 1080,
        steps: int = 20,
        workflow: Optional[Dict] = None
    ):
        """Initialize the ComfyUI client.

        Args:
            host: ComfyUI server host.
            port: ComfyUI server port.
            width: Default image width.
            height: Default image height.
            steps: Default sampling steps.
            workflow: Custom workflow dict (uses default if None).
        """
        self.host = host
        self.port = port
        self.width = width
        self.height = height
        self.steps = steps
        self.workflow = workflow or DEFAULT_WORKFLOW.copy()
        self.base_url = f"http://{host}:{port}"

    async def check_connection(self) -> bool:
        """Check if ComfyUI server is running.

        Returns:
            True if connected, False otherwise.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/system_stats", timeout=5.0)
                return response.status_code == 200
        except Exception:
            return False

    def _build_workflow(self, prompt: str) -> Dict[str, Any]:
        """Build workflow with prompt inserted.

        Args:
            prompt: The text prompt for image generation.

        Returns:
            Complete workflow dict.
        """
        workflow = json.loads(json.dumps(self.workflow))  # Deep copy

        # Update prompt
        workflow["6"]["inputs"]["text"] = prompt

        # Update dimensions
        workflow["5"]["inputs"]["width"] = self.width
        workflow["5"]["inputs"]["height"] = self.height

        # Update steps
        workflow["3"]["inputs"]["steps"] = self.steps

        return workflow

    async def _queue_prompt(self, workflow: Dict) -> str:
        """Queue a prompt for execution.

        Args:
            workflow: The workflow to execute.

        Returns:
            Prompt ID for tracking.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow}
            )
            response.raise_for_status()
            return response.json()["prompt_id"]

    async def _wait_for_completion(
        self,
        prompt_id: str,
        timeout: float = 300.0,
        poll_interval: float = 1.0
    ) -> Dict:
        """Wait for prompt execution to complete.

        Args:
            prompt_id: The prompt ID to wait for.
            timeout: Maximum wait time in seconds.
            poll_interval: Time between status checks.

        Returns:
            Execution result with image info.
        """
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

        raise TimeoutError(f"Image generation timed out after {timeout}s")

    async def _download_image(
        self,
        filename: str,
        subfolder: str,
        output_path: Path
    ) -> Path:
        """Download generated image from ComfyUI.

        Args:
            filename: The image filename.
            subfolder: The subfolder in outputs.
            output_path: Local path to save to.

        Returns:
            Path to saved image.
        """
        async with httpx.AsyncClient() as client:
            params = {"filename": filename, "subfolder": subfolder, "type": "output"}
            response = await client.get(f"{self.base_url}/view", params=params)
            response.raise_for_status()

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(response.content)

            return output_path

    async def generate(
        self,
        prompt: str,
        output_path: Path,
        timeout: float = 300.0
    ) -> Path:
        """Generate an image from a text prompt.

        Args:
            prompt: The text prompt.
            output_path: Where to save the image.
            timeout: Maximum generation time.

        Returns:
            Path to the generated image.
        """
        workflow = self._build_workflow(prompt)
        prompt_id = await self._queue_prompt(workflow)
        result = await self._wait_for_completion(prompt_id, timeout=timeout)

        # Get the output image info
        outputs = result.get("outputs", {})
        for node_id, node_output in outputs.items():
            if "images" in node_output:
                image_info = node_output["images"][0]
                return await self._download_image(
                    image_info["filename"],
                    image_info.get("subfolder", ""),
                    output_path
                )

        raise RuntimeError("No image output found in ComfyUI result")
