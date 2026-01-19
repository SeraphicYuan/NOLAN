"""ComfyUI integration for NOLAN."""

import json
import asyncio
import random
from pathlib import Path
from typing import Optional, Dict, Any, List

import httpx


def load_workflow_file(workflow_path: Path) -> Dict[str, Any]:
    """Load a ComfyUI workflow JSON file and convert to API format.

    Args:
        workflow_path: Path to the workflow JSON file.

    Returns:
        Workflow dict in API format (node_id -> node_data).
    """
    with open(workflow_path, 'r', encoding='utf-8') as f:
        workflow = json.load(f)

    # Check if this is UI format (has "nodes" array) or API format
    if "nodes" in workflow:
        return convert_ui_to_api_format(workflow)
    else:
        # Already in API format
        return workflow


def convert_ui_to_api_format(ui_workflow: Dict[str, Any]) -> Dict[str, Any]:
    """Convert ComfyUI UI workflow format to API format.

    UI format has "nodes" array with positions and visual data.
    API format is {node_id: {class_type, inputs}}.

    Args:
        ui_workflow: Workflow in UI format.

    Returns:
        Workflow in API format.
    """
    api_workflow = {}

    for node in ui_workflow.get("nodes", []):
        node_id = str(node["id"])
        class_type = node.get("type", "")

        # Skip note/markdown nodes
        if "Note" in class_type or "Markdown" in class_type:
            continue

        # Build inputs from widget values and links
        inputs = {}

        # Get widget values
        widget_values = node.get("widgets_values", [])

        # Map inputs based on class type
        if class_type == "CheckpointLoaderSimple":
            if widget_values:
                inputs["ckpt_name"] = widget_values[0]

        elif class_type == "EmptySD3LatentImage" or class_type == "EmptyLatentImage":
            if len(widget_values) >= 3:
                inputs["width"] = widget_values[0]
                inputs["height"] = widget_values[1]
                inputs["batch_size"] = widget_values[2]

        elif class_type == "KSampler":
            if len(widget_values) >= 7:
                inputs["seed"] = widget_values[0] if widget_values[0] != "randomize" else random.randint(0, 2**32)
                inputs["steps"] = widget_values[2]
                inputs["cfg"] = widget_values[3]
                inputs["sampler_name"] = widget_values[4]
                inputs["scheduler"] = widget_values[5]
                inputs["denoise"] = widget_values[6]

        elif class_type == "CLIPTextEncode":
            if widget_values:
                inputs["text"] = widget_values[0]

        elif class_type == "ModelSamplingAuraFlow":
            if widget_values:
                inputs["shift"] = widget_values[0]

        elif class_type == "SaveImage":
            if widget_values:
                inputs["filename_prefix"] = widget_values[0]

        elif class_type == "VAEDecode":
            pass  # No widget values, just links

        # Handle custom subgraph nodes (positive/negative prompt encoders)
        elif "-" in class_type and len(class_type) > 30:
            # This is a subgraph node (UUID), treat as CLIPTextEncode equivalent
            # These nodes typically use "value" as the input name
            if widget_values:
                inputs["value"] = widget_values[0]

        # Process input links
        for input_def in node.get("inputs", []):
            link_id = input_def.get("link")
            if link_id is not None:
                # Find the link in the workflow
                for link in ui_workflow.get("links", []):
                    if link[0] == link_id:
                        source_node_id = str(link[1])
                        source_slot = link[2]
                        input_name = input_def.get("name", "")
                        inputs[input_name] = [source_node_id, source_slot]
                        break

        if class_type and not class_type.startswith("Markdown"):
            api_workflow[node_id] = {
                "class_type": class_type,
                "inputs": inputs
            }

    return api_workflow


def find_prompt_nodes(workflow: Dict[str, Any]) -> Dict[str, str]:
    """Find nodes that accept text prompts in a workflow.

    Args:
        workflow: Workflow in API format.

    Returns:
        Dict with 'positive' and 'negative' node IDs.
    """
    result = {"positive": None, "negative": None}

    for node_id, node_data in workflow.items():
        class_type = node_data.get("class_type", "")
        inputs = node_data.get("inputs", {})
        meta = node_data.get("_meta", {})
        title = meta.get("title", "").lower()

        # Check for PrimitiveStringMultiline nodes with "Prompt" title (API format)
        if class_type == "PrimitiveStringMultiline":
            value = inputs.get("value", "")
            if isinstance(value, str):
                # Check title first for explicit labeling
                if title == "prompt":
                    result["positive"] = node_id
                elif "negative" in title or "low quality" in value.lower() or "blurry" in value.lower():
                    result["negative"] = node_id

        # Look for CLIPTextEncode or custom prompt nodes
        elif "CLIPTextEncode" in class_type or "Prompt" in class_type:
            text = inputs.get("text", "")
            if isinstance(text, str):
                if "negative" in class_type.lower() or "low quality" in text.lower():
                    result["negative"] = node_id
                elif "positive" in class_type.lower() or result["positive"] is None:
                    result["positive"] = node_id

        # Handle subgraph nodes (UUIDs)
        elif "-" in class_type and len(class_type) > 30:
            text = inputs.get("text", inputs.get("value", ""))
            if isinstance(text, str):
                if "low quality" in text.lower() or "blurry" in text.lower():
                    result["negative"] = node_id
                else:
                    result["positive"] = node_id

    return result


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
            "ckpt_name": "juggernautXL_ragnarokBy.safetensors"
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
        workflow: Optional[Dict] = None,
        workflow_file: Optional[Path] = None,
        prompt_node: Optional[str] = None,
        node_overrides: Optional[List[str]] = None
    ):
        """Initialize the ComfyUI client.

        Args:
            host: ComfyUI server host.
            port: ComfyUI server port.
            width: Default image width.
            height: Default image height.
            steps: Default sampling steps.
            workflow: Custom workflow dict (uses default if None).
            workflow_file: Path to workflow JSON file (overrides workflow param).
            prompt_node: Explicit node ID for prompt injection (overrides auto-detection).
            node_overrides: List of "node_id:param=value" strings to override workflow params.
        """
        self.host = host
        self.port = port
        self.width = width
        self.height = height
        self.steps = steps
        self.base_url = f"http://{host}:{port}"
        self._node_overrides = self._parse_overrides(node_overrides or [])

        # Load workflow from file if provided
        if workflow_file:
            self.workflow = load_workflow_file(Path(workflow_file))
            # Use explicit prompt_node if provided, otherwise auto-detect
            if prompt_node:
                self._prompt_nodes = {"positive": prompt_node, "negative": None}
            else:
                self._prompt_nodes = find_prompt_nodes(self.workflow)
            self._using_custom_workflow = True
        else:
            self.workflow = workflow or DEFAULT_WORKFLOW.copy()
            self._prompt_nodes = {"positive": "6", "negative": "7"}
            self._using_custom_workflow = False

    def _parse_overrides(self, overrides: List[str]) -> Dict[str, Dict[str, Any]]:
        """Parse node override strings into a structured dict.

        Args:
            overrides: List of "node_id:param=value" strings.

        Returns:
            Dict of {node_id: {param: value}}.
        """
        result = {}
        for override in overrides:
            try:
                # Parse "node_id:param=value"
                node_part, value_part = override.split("=", 1)
                node_id, param = node_part.rsplit(":", 1)

                # Try to convert value to appropriate type
                value = self._convert_value(value_part)

                if node_id not in result:
                    result[node_id] = {}
                result[node_id][param] = value
            except ValueError:
                raise ValueError(f"Invalid override format: '{override}'. Use 'node_id:param=value'")
        return result

    def _convert_value(self, value_str: str) -> Any:
        """Convert string value to appropriate Python type."""
        # Try int
        try:
            return int(value_str)
        except ValueError:
            pass
        # Try float
        try:
            return float(value_str)
        except ValueError:
            pass
        # Try bool
        if value_str.lower() in ("true", "false"):
            return value_str.lower() == "true"
        # Keep as string
        return value_str

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

        if self._using_custom_workflow:
            # Inject prompt into the positive prompt node
            positive_node_id = self._prompt_nodes.get("positive")
            if positive_node_id and positive_node_id in workflow:
                node = workflow[positive_node_id]
                inputs = node.get("inputs", {})

                # Find the prompt input (could be "text" or "value")
                prompt_key = "text" if "text" in inputs else "value" if "value" in inputs else None

                if prompt_key:
                    existing = inputs[prompt_key]
                    if isinstance(existing, str) and "<Prompt Start>" in existing:
                        # Keep system prefix, replace user prompt after the tag
                        prefix = existing.split("<Prompt Start>")[0] + "<Prompt Start> "
                        inputs[prompt_key] = prefix + prompt
                    else:
                        # No system prefix, just set the prompt directly
                        inputs[prompt_key] = prompt

            # Randomize seed in KSampler (unless overridden)
            if "3" not in self._node_overrides or "seed" not in self._node_overrides.get("3", {}):
                for node_id, node_data in workflow.items():
                    if node_data.get("class_type") == "KSampler":
                        if "seed" in node_data.get("inputs", {}):
                            node_data["inputs"]["seed"] = random.randint(0, 2**32)
        else:
            # Default workflow handling
            workflow["6"]["inputs"]["text"] = prompt
            workflow["5"]["inputs"]["width"] = self.width
            workflow["5"]["inputs"]["height"] = self.height
            workflow["3"]["inputs"]["steps"] = self.steps

        # Apply node overrides
        for node_id, params in self._node_overrides.items():
            if node_id in workflow:
                if "inputs" not in workflow[node_id]:
                    workflow[node_id]["inputs"] = {}
                for param, value in params.items():
                    workflow[node_id]["inputs"][param] = value

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
            if response.status_code != 200:
                error_detail = response.text
                raise RuntimeError(f"ComfyUI error ({response.status_code}): {error_detail}")
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
