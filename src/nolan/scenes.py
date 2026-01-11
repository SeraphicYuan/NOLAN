"""Scene design for NOLAN."""

import json
import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any

from nolan.script import ScriptSection


@dataclass
class SyncPoint:
    """Word-to-action synchronization point.

    Connects a trigger word/phrase in the narration to a visual action.
    The `time` field is None in Step 1 (design), populated in Step 4 (timing alignment).
    """
    trigger: str                    # Word/phrase to match in SRT
    action: str                     # reveal, highlight, zoom, show_lower_third, animate
    target: Optional[Any] = None    # Item index, element id, coordinates, etc.
    time: Optional[float] = None    # None in Step 1, populated in Step 4


@dataclass
class Layer:
    """A visual layer within a scene.

    Used for complex scenes with multiple visual elements stacked together.
    """
    type: str                       # background, overlay, caption, lower_third
    asset: Optional[str] = None     # Path to asset
    style: Optional[Dict] = None    # Position, opacity, animation params
    sync_point: Optional[SyncPoint] = None  # When to show/animate this layer


SCENE_DESIGN_PROMPT = """You are designing visual scenes for a YouTube video essay.

SECTION: {title}
TIMESTAMP: {timestamp}
NARRATION:
{narration}

Design a sequence of visual scenes to accompany this narration. For each scene, specify:
- When it starts and how long it lasts (estimate)
- What type of visual (b-roll, graphic, text-overlay, generated-image, infographic, layered)
- What should appear on screen
- Search terms for finding stock footage
- A prompt for AI image generation (if applicable)
- For infographics, provide an infographic spec with template/theme/data
- For animations, specify animation_type and params
- For sync points, specify trigger words that should trigger visual actions
- For layered scenes, define multiple layers (background, overlay, caption)

Return a JSON array of scenes with this structure:
[
  {{
    "id": "scene_XXX",
    "start": "M:SS",
    "duration": "Xs",
    "narration_excerpt": "the specific words being spoken",
    "visual_type": "b-roll|graphic|text-overlay|generated-image|infographic|layered",
    "visual_description": "detailed description of what appears on screen",
    "asset_suggestions": {{
      "search_query": "keywords for stock footage search",
      "comfyui_prompt": "detailed prompt for AI image generation",
      "library_match": true
    }},
    "animation": {{
      "type": "static|zoom|pan|reveal|kinetic",
      "params": {{"zoom_from": 1.0, "zoom_to": 1.2, "direction": "left-to-right"}},
      "transition": "cut|fade|dissolve|wipe"
    }},
    "sync_points": [
      {{"trigger": "word or phrase", "action": "reveal|highlight|zoom|animate", "target": 0}}
    ],
    "layers": [
      {{"type": "background|overlay|caption|lower_third", "style": {{}}}},
    ],
    "infographic": {{
      "template": "steps|list|comparison",
      "theme": "default|dark|warm|cool",
      "data": {{
        "title": "infographic title",
        "items": [
          {{"label": "Step 1", "desc": "Short detail"}},
          {{"label": "Step 2", "desc": "Short detail"}}
        ]
      }}
    }},
    "text_style": {{
      "position": "center|bottom|top",
      "font_size": 32,
      "color": "#ffffff",
      "animation": "fade|typewriter|none"
    }}
  }}
]

IMPORTANT: Return ONLY the JSON array, no other text.
NOTE: animation, sync_points, layers, infographic, and text_style are optional - include only when relevant."""


@dataclass
class Scene:
    """A single visual scene - progressively enriched across workflow steps.

    Step 1 (Design): id, start/duration (estimates), narration_excerpt, visual_type,
                     visual_description, search_query, comfyui_prompt, animation hints,
                     sync_points (trigger/action only), layers hints, infographic spec
    Step 2 (Assets): matched_asset, generated_asset, infographic_asset, layer assets
    Step 4 (Timing): start_seconds, end_seconds, sync_points (time populated), subtitle_cues
    Step 5 (Render): final composition using all populated fields
    """
    # === Identity ===
    id: str

    # === Timing (estimated in Step 1, precise after Step 4) ===
    start: str                              # "0:15" - LLM estimate
    duration: str                           # "5s" - LLM estimate
    start_seconds: Optional[float] = None   # Precise, from SRT (Step 4)
    end_seconds: Optional[float] = None     # Precise, from SRT (Step 4)

    # === Content ===
    narration_excerpt: str = ""             # Key phrase for SRT matching
    visual_type: str = "b-roll"             # b-roll, graphic, text-overlay, generated-image, infographic, layered
    visual_description: str = ""            # What appears on screen

    # === Asset Sources (Step 1 hints) ===
    search_query: str = ""                  # Stock footage keywords
    comfyui_prompt: str = ""                # AI image generation prompt
    library_match: bool = True              # Try indexed library first

    # === Animation (Step 1 hints, refined in Step 4/5) ===
    animation_type: Optional[str] = None    # static, zoom, pan, reveal, kinetic
    animation_params: Optional[Dict] = None # {zoom_from, zoom_to, focus_x, focus_y, direction}
    transition: Optional[str] = None        # cut, fade, dissolve, wipe

    # === Sync Points (Step 1 hints trigger/action, Step 4 adds time) ===
    sync_points: List[SyncPoint] = field(default_factory=list)

    # === Layers for complex scenes ===
    layers: List[Layer] = field(default_factory=list)

    # === Infographic spec (if visual_type == "infographic") ===
    infographic: Optional[Dict[str, Any]] = None

    # === Text overlay style (if visual_type == "text-overlay") ===
    text_style: Optional[Dict] = None       # {position, font_size, color, animation}

    # === Asset Results (populated in Step 2) ===
    skip_generation: bool = False
    matched_asset: Optional[str] = None
    generated_asset: Optional[str] = None
    infographic_asset: Optional[str] = None

    # === SRT Cues (attached in Step 4) ===
    subtitle_cues: List[Any] = field(default_factory=list)  # SubtitleCue objects


@dataclass
class ScenePlan:
    """Complete scene plan for a video."""
    sections: Dict[str, List[Scene]] = field(default_factory=dict)

    def to_json(self, indent: int = 2) -> str:
        """Export to JSON string."""
        data = {
            "sections": {
                title: [asdict(scene) for scene in scenes]
                for title, scenes in self.sections.items()
            }
        }
        return json.dumps(data, indent=indent)

    def save(self, path: str) -> None:
        """Save to JSON file."""
        with open(path, 'w') as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> "ScenePlan":
        """Load from JSON file."""
        with open(path, 'r') as f:
            data = json.load(f)

        plan = cls()
        for title, scenes_data in data["sections"].items():
            plan.sections[title] = [
                cls._scene_from_dict(scene) for scene in scenes_data
            ]
        return plan

    @staticmethod
    def _scene_from_dict(data: Dict) -> "Scene":
        """Convert a dict to a Scene, handling nested dataclasses."""
        # Parse sync points
        sync_points = []
        for sp_data in data.get("sync_points", []):
            if isinstance(sp_data, dict):
                sync_points.append(SyncPoint(
                    trigger=sp_data.get("trigger", ""),
                    action=sp_data.get("action", "reveal"),
                    target=sp_data.get("target"),
                    time=sp_data.get("time"),
                ))
            elif isinstance(sp_data, SyncPoint):
                sync_points.append(sp_data)

        # Parse layers
        layers = []
        for layer_data in data.get("layers", []):
            if isinstance(layer_data, dict):
                layer_sync = None
                if layer_data.get("sync_point"):
                    sp = layer_data["sync_point"]
                    layer_sync = SyncPoint(
                        trigger=sp.get("trigger", ""),
                        action=sp.get("action", "fade_in"),
                        target=sp.get("target"),
                        time=sp.get("time"),
                    )
                layers.append(Layer(
                    type=layer_data.get("type", "overlay"),
                    asset=layer_data.get("asset"),
                    style=layer_data.get("style"),
                    sync_point=layer_sync,
                ))
            elif isinstance(layer_data, Layer):
                layers.append(layer_data)

        # Build scene with parsed nested objects
        return Scene(
            id=data["id"],
            start=data["start"],
            duration=data["duration"],
            start_seconds=data.get("start_seconds"),
            end_seconds=data.get("end_seconds"),
            narration_excerpt=data.get("narration_excerpt", ""),
            visual_type=data.get("visual_type", "b-roll"),
            visual_description=data.get("visual_description", ""),
            search_query=data.get("search_query", ""),
            comfyui_prompt=data.get("comfyui_prompt", ""),
            library_match=data.get("library_match", True),
            animation_type=data.get("animation_type"),
            animation_params=data.get("animation_params"),
            transition=data.get("transition"),
            sync_points=sync_points,
            layers=layers,
            infographic=data.get("infographic"),
            text_style=data.get("text_style"),
            skip_generation=data.get("skip_generation", False),
            matched_asset=data.get("matched_asset"),
            generated_asset=data.get("generated_asset"),
            infographic_asset=data.get("infographic_asset"),
            subtitle_cues=data.get("subtitle_cues", []),
        )

    @property
    def all_scenes(self) -> List[Scene]:
        """Get all scenes flattened."""
        scenes = []
        for section_scenes in self.sections.values():
            scenes.extend(section_scenes)
        return scenes


class SceneDesigner:
    """Designs visual scenes for script sections."""

    def __init__(self, llm_client):
        """Initialize the designer.

        Args:
            llm_client: The LLM client for scene generation.
        """
        self.llm = llm_client

    async def design_section(self, section: ScriptSection) -> List[Scene]:
        """Design scenes for a single script section.

        Args:
            section: The script section to design for.

        Returns:
            List of Scene objects.
        """
        prompt = SCENE_DESIGN_PROMPT.format(
            title=section.title,
            timestamp=section.timestamp,
            narration=section.narration
        )

        response = await self.llm.generate(prompt)

        # Parse JSON response
        try:
            scenes_data = json.loads(response.strip())
        except json.JSONDecodeError:
            # Try to extract JSON from response
            match = re.search(r'\[.*\]', response, re.DOTALL)
            if match:
                scenes_data = json.loads(match.group())
            else:
                raise ValueError(f"Could not parse scene JSON from response: {response[:200]}")

        scenes = []
        for scene_data in scenes_data:
            asset_suggestions = scene_data.get("asset_suggestions", {})
            animation = scene_data.get("animation", {})

            # Parse sync points
            sync_points = []
            for sp_data in scene_data.get("sync_points", []):
                sync_points.append(SyncPoint(
                    trigger=sp_data.get("trigger", ""),
                    action=sp_data.get("action", "reveal"),
                    target=sp_data.get("target"),
                    time=sp_data.get("time"),  # None in Step 1
                ))

            # Parse layers
            layers = []
            for layer_data in scene_data.get("layers", []):
                layer_sync = None
                if layer_data.get("sync_point"):
                    sp = layer_data["sync_point"]
                    layer_sync = SyncPoint(
                        trigger=sp.get("trigger", ""),
                        action=sp.get("action", "fade_in"),
                        target=sp.get("target"),
                        time=sp.get("time"),
                    )
                layers.append(Layer(
                    type=layer_data.get("type", "overlay"),
                    asset=layer_data.get("asset"),
                    style=layer_data.get("style"),
                    sync_point=layer_sync,
                ))

            scene = Scene(
                id=scene_data["id"],
                start=scene_data["start"],
                duration=scene_data["duration"],
                narration_excerpt=scene_data.get("narration_excerpt", ""),
                visual_type=scene_data.get("visual_type", "b-roll"),
                visual_description=scene_data.get("visual_description", ""),
                search_query=asset_suggestions.get("search_query", ""),
                comfyui_prompt=asset_suggestions.get("comfyui_prompt", ""),
                library_match=asset_suggestions.get("library_match", True),
                animation_type=animation.get("type"),
                animation_params=animation.get("params"),
                transition=animation.get("transition"),
                sync_points=sync_points,
                layers=layers,
                infographic=scene_data.get("infographic"),
                text_style=scene_data.get("text_style"),
            )
            scenes.append(scene)

        return scenes

    async def design_full_plan(self, sections: List[ScriptSection]) -> ScenePlan:
        """Design scenes for all script sections.

        Args:
            sections: List of script sections.

        Returns:
            Complete ScenePlan.
        """
        plan = ScenePlan()

        for section in sections:
            scenes = await self.design_section(section)
            plan.sections[section.title] = scenes

        return plan
