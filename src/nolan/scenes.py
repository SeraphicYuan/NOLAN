"""Scene design for NOLAN."""

import json
import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any

from nolan.script import ScriptSection


SCENE_DESIGN_PROMPT = """You are designing visual scenes for a YouTube video essay.

SECTION: {title}
TIMESTAMP: {timestamp}
NARRATION:
{narration}

Design a sequence of visual scenes to accompany this narration. For each scene, specify:
- When it starts and how long it lasts
- What type of visual (b-roll, graphic, text-overlay, generated-image, infographic)
- What should appear on screen
- Search terms for finding stock footage
- A prompt for AI image generation (if applicable)
- For infographics, provide an infographic spec with template/theme/data

Return a JSON array of scenes with this structure:
[
  {{
    "id": "scene_XXX",
    "start": "M:SS",
    "duration": "Xs",
    "narration_excerpt": "the specific words being spoken",
    "visual_type": "b-roll|graphic|text-overlay|generated-image|infographic",
    "visual_description": "detailed description of what appears on screen",
    "asset_suggestions": {{
      "search_query": "keywords for stock footage search",
      "comfyui_prompt": "detailed prompt for AI image generation",
      "library_match": true
    }},
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
    }}
  }}
]

IMPORTANT: Return ONLY the JSON array, no other text."""


@dataclass
class Scene:
    """A single visual scene."""
    id: str
    start: str
    duration: str
    narration_excerpt: str
    visual_type: str  # b-roll, graphic, text-overlay, generated-image
    visual_description: str
    search_query: str
    comfyui_prompt: str
    library_match: bool
    skip_generation: bool = False
    matched_asset: Optional[str] = None
    generated_asset: Optional[str] = None
    infographic: Optional[Dict[str, Any]] = None
    infographic_asset: Optional[str] = None


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
                Scene(**scene) for scene in scenes_data
            ]
        return plan

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
            scene = Scene(
                id=scene_data["id"],
                start=scene_data["start"],
                duration=scene_data["duration"],
                narration_excerpt=scene_data["narration_excerpt"],
                visual_type=scene_data["visual_type"],
                visual_description=scene_data["visual_description"],
                search_query=asset_suggestions.get("search_query", ""),
                comfyui_prompt=asset_suggestions.get("comfyui_prompt", ""),
                library_match=asset_suggestions.get("library_match", True),
                infographic=scene_data.get("infographic"),
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
