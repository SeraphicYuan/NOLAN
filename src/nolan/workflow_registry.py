"""Registry of named ComfyUI generation workflows.

Each model usually needs its own workflow JSON (different loaders/nodes). This
registry gives them names + metadata so generation, the webUI, and the sample
runner can select among many models instead of relying on a single hardcoded
workflow. Stored as workflows/registry.json.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Optional, Dict, Any

REGISTRY_PATH = Path("workflows") / "registry.json"


@dataclass
class WorkflowEntry:
    name: str
    description: str = ""
    builtin: Optional[str] = None      # "default" → use DEFAULT_WORKFLOW
    file: Optional[str] = None         # path to an API-format workflow JSON
    checkpoint: Optional[str] = None   # informational (model filename)
    prompt_node: Optional[str] = None  # explicit positive-prompt node id (None = auto-detect)
    width: int = 1920
    height: int = 1080
    steps: int = 20
    styles: List[str] = field(default_factory=list)  # display tags, e.g. ["photoreal","illustration"]
    # Optional in-workflow style selector (e.g. ComfyUI-Easy-Use "easy stylesSelector").
    style_node: Optional[str] = None       # node id of the style selector
    style_input: str = "select_styles"     # input key to override on that node
    style_group: Optional[str] = None      # style list file in workflows/styles/<group>.json
    default_style: Optional[str] = None    # default selection

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WorkflowRegistry:
    """Load/save and manage named workflow entries."""

    def __init__(self, path: Path = REGISTRY_PATH):
        self.path = Path(path)
        self.entries: Dict[str, WorkflowEntry] = {}
        self.load()

    def load(self) -> None:
        self.entries = {}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                for e in data.get("workflows", []):
                    self.entries[e["name"]] = WorkflowEntry(**{
                        k: v for k, v in e.items() if k in WorkflowEntry.__dataclass_fields__
                    })
            except Exception:
                pass
        if not self.entries:
            self.seed_defaults()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"workflows": [e.to_dict() for e in self.entries.values()]}, indent=2),
            encoding="utf-8",
        )

    def seed_defaults(self) -> None:
        """Seed with the built-in SDXL default + any bundled workflow files."""
        self.entries["sdxl-default"] = WorkflowEntry(
            name="sdxl-default", description="Built-in SDXL workflow (juggernautXL)",
            builtin="default", checkpoint="juggernautXL_ragnarokBy.safetensors",
            prompt_node="6", width=1920, height=1080, steps=20,
            styles=["photoreal", "cinematic"],
        )
        lumina = Path("workflows/image/nolan_api_image_netayume_lumina_t2i.json")
        if lumina.exists():
            self.entries["netayume-lumina"] = WorkflowEntry(
                name="netayume-lumina", description="NetaYume Lumina text-to-image",
                file=str(lumina).replace("\\", "/"), checkpoint="NetaYumev35_pretrained_all_in_one.safetensors",
                prompt_node=None, width=1024, height=1024, steps=30,
                styles=["illustration", "anime"],
            )
        self.save()

    def list(self) -> List[WorkflowEntry]:
        return list(self.entries.values())

    def get(self, name: str) -> Optional[WorkflowEntry]:
        return self.entries.get(name)

    def default_name(self) -> str:
        return "sdxl-default" if "sdxl-default" in self.entries else next(iter(self.entries), "")

    def add(self, entry: WorkflowEntry) -> WorkflowEntry:
        self.entries[entry.name] = entry
        self.save()
        return entry

    def remove(self, name: str) -> bool:
        if name in self.entries:
            del self.entries[name]
            self.save()
            return True
        return False

    def build_client(self, name: Optional[str], config, **overrides):
        """Construct a ComfyUIClient for a registered workflow (or the default)."""
        from nolan.comfyui import ComfyUIClient
        entry = self.get(name) if name else None
        if entry is None:
            entry = self.get(self.default_name())
        kwargs = dict(
            host=config.comfyui.host, port=config.comfyui.port,
            width=overrides.get("width", entry.width if entry else config.comfyui.width),
            height=overrides.get("height", entry.height if entry else config.comfyui.height),
            steps=overrides.get("steps", entry.steps if entry else config.comfyui.steps),
        )
        if entry and entry.file:
            kwargs["workflow_file"] = Path(entry.file)
            if entry.prompt_node:
                kwargs["prompt_node"] = entry.prompt_node
            # Apply a chosen style to the workflow's style-selector node.
            style = overrides.get("style")
            if entry.style_node and style:
                kwargs["node_overrides"] = [f"{entry.style_node}:{entry.style_input}={style}"]
        # builtin/default → leave workflow None (ComfyUIClient uses DEFAULT_WORKFLOW)
        return ComfyUIClient(**kwargs), entry


_registry: Optional[WorkflowRegistry] = None


def get_registry() -> WorkflowRegistry:
    global _registry
    if _registry is None:
        _registry = WorkflowRegistry()
    return _registry
