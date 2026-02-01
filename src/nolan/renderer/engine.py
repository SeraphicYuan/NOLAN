"""
Python Template Engine for NOLAN.

Provides a fallback rendering engine using pure Python (PIL + MoviePy).
Can be used when render-service is unavailable or for lightweight rendering.

Usage:
    from nolan.renderer.engine import PythonTemplateEngine

    engine = PythonTemplateEngine()

    # Check if a scene can be rendered
    if engine.can_render(scene):
        output_path = engine.render(scene, output_dir, duration=5.0)
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List
import re

from nolan.scenes import Scene

from .scenes.quote import QuoteRenderer
from .scenes.title import TitleRenderer
from .scenes.statistic import StatisticRenderer
from .scenes.list import ListRenderer


# Scene types that can be rendered by Python engine
PYTHON_RENDERABLE_TYPES = {
    "quote",
    "text-overlay",
    "title",
    "statistic",
    "year",
    "list",
    "chapter",
}


@dataclass
class RenderResult:
    """Result of a render operation."""
    success: bool
    output_path: Optional[str] = None
    error: Optional[str] = None
    renderer_used: Optional[str] = None


class PythonTemplateEngine:
    """
    Pure Python rendering engine for animated text scenes.

    Supports:
    - Quotes with attribution
    - Title cards with subtitles
    - Statistics and year reveals
    - Bullet point lists
    """

    def __init__(
        self,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
    ):
        self.width = width
        self.height = height
        self.fps = fps

    def can_render(self, scene: Scene) -> bool:
        """Check if this engine can render the given scene."""
        visual_type = (scene.visual_type or "").lower().strip()

        # Direct match
        if visual_type in PYTHON_RENDERABLE_TYPES:
            return True

        # Check for quote-like scenes
        if self._is_quote_scene(scene):
            return True

        # Check for title-like scenes
        if self._is_title_scene(scene):
            return True

        # Check for statistic-like scenes
        if self._is_statistic_scene(scene):
            return True

        return False

    def _is_quote_scene(self, scene: Scene) -> bool:
        """Detect quote scenes from visual description."""
        desc = (scene.visual_description or "").lower()
        keywords = ["quote", "typography", "text appears", "bold text", "says", "said"]
        return any(kw in desc for kw in keywords)

    def _is_title_scene(self, scene: Scene) -> bool:
        """Detect title scenes from visual description."""
        desc = (scene.visual_description or "").lower()
        keywords = ["title", "heading", "chapter", "fades in", "video title"]
        return any(kw in desc for kw in keywords)

    def _is_statistic_scene(self, scene: Scene) -> bool:
        """Detect statistic scenes from visual description."""
        desc = (scene.visual_description or "").lower()
        keywords = ["statistic", "number", "percent", "billion", "million", "year", "1821", "1976", "counter"]
        return any(kw in desc for kw in keywords)

    def detect_scene_type(self, scene: Scene) -> str:
        """Detect the best renderer for a scene."""
        visual_type = (scene.visual_type or "").lower().strip()

        if visual_type in ["quote"]:
            return "quote"
        if visual_type in ["title", "chapter"]:
            return "title"
        if visual_type in ["statistic", "year"]:
            return "statistic"
        if visual_type in ["list"]:
            return "list"

        # Auto-detect from description
        if self._is_quote_scene(scene):
            return "quote"
        if self._is_statistic_scene(scene):
            return "statistic"
        if self._is_title_scene(scene):
            return "title"

        return "title"  # Default fallback

    def extract_quote_content(self, scene: Scene) -> Dict[str, Any]:
        """Extract quote and attribution from scene."""
        desc = scene.visual_description or ""
        narration = scene.narration_excerpt or ""

        # Try to extract quoted text
        quote_match = re.search(r"['\"]([^'\"]+)['\"]", narration)
        if quote_match:
            quote = quote_match.group(1).upper()
        else:
            # Use first sentence of narration
            quote = narration.split('.')[0].upper()[:50]

        # Try to extract attribution
        attr_match = re.search(r"—\s*([^,]+)", desc) or re.search(r"[-–]\s*([^,]+)", desc)
        if attr_match:
            attribution = f"— {attr_match.group(1).strip()}"
        else:
            attribution = None

        return {"quote": quote, "attribution": attribution}

    def extract_title_content(self, scene: Scene) -> Dict[str, Any]:
        """Extract title and subtitle from scene."""
        desc = scene.visual_description or ""
        narration = scene.narration_excerpt or ""

        # Try to find quoted title in description
        title_match = re.search(r"['\"]([^'\"]+)['\"]", desc)
        if title_match:
            title = title_match.group(1).upper()
        else:
            # Use first part of narration
            title = narration.split('.')[0].upper()[:40]

        # Look for subtitle
        subtitle = None
        if "subtitle" in desc.lower():
            sub_match = re.search(r"subtitle[:\s]+([^.]+)", desc, re.IGNORECASE)
            if sub_match:
                subtitle = sub_match.group(1).strip()

        return {"title": title, "subtitle": subtitle}

    def extract_statistic_content(self, scene: Scene) -> Dict[str, Any]:
        """Extract value and label from scene."""
        desc = scene.visual_description or ""
        narration = scene.narration_excerpt or ""

        # Look for year patterns
        year_match = re.search(r"\b(1[89]\d{2}|20[0-2]\d)\b", desc + narration)
        if year_match:
            return {"value": year_match.group(1), "label": None, "is_year": True}

        # Look for number patterns
        num_match = re.search(r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(%|billion|million|thousand)?",
                              desc + narration, re.IGNORECASE)
        if num_match:
            value = num_match.group(1)
            suffix = num_match.group(2) or ""
            return {"value": value, "suffix": suffix.upper(), "label": None, "is_year": False}

        return {"value": "???", "label": None, "is_year": False}

    def extract_list_content(self, scene: Scene) -> Dict[str, Any]:
        """Extract title and items from scene."""
        desc = scene.visual_description or ""

        # Try to find title
        title_match = re.search(r"['\"]([^'\"]+)['\"]", desc)
        title = title_match.group(1).upper() if title_match else "KEY POINTS"

        # Try to find numbered items
        items = re.findall(r"(\d+)\.\s*([^,.\d]+)", desc)
        if items:
            return {"title": title, "items": [item[1].strip() for item in items]}

        # Fallback
        return {"title": title, "items": ["Point 1", "Point 2", "Point 3"]}

    def render(
        self,
        scene: Scene,
        output_dir: Path,
        duration: float = 5.0,
        style: str = "documentary",
    ) -> RenderResult:
        """
        Render a scene to MP4.

        Args:
            scene: Scene to render
            output_dir: Directory for output file
            duration: Video duration in seconds
            style: Visual style (documentary, modern, historical, danger)

        Returns:
            RenderResult with success status and output path
        """
        try:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            scene_type = self.detect_scene_type(scene)
            output_path = output_dir / f"{scene.id}_python.mp4"

            if scene_type == "quote":
                content = self.extract_quote_content(scene)
                renderer = QuoteRenderer(
                    quote=content["quote"],
                    attribution=content.get("attribution"),
                    width=self.width,
                    height=self.height,
                    fps=self.fps,
                )
                renderer.render(str(output_path), duration=duration)

            elif scene_type == "title":
                content = self.extract_title_content(scene)
                renderer = TitleRenderer(
                    title=content["title"],
                    subtitle=content.get("subtitle"),
                    width=self.width,
                    height=self.height,
                    fps=self.fps,
                )
                renderer.render(str(output_path), duration=duration)

            elif scene_type == "statistic":
                content = self.extract_statistic_content(scene)
                renderer = StatisticRenderer(
                    value=content["value"],
                    label=content.get("label"),
                    suffix=content.get("suffix", ""),
                    width=self.width,
                    height=self.height,
                    fps=self.fps,
                )
                if content.get("is_year"):
                    renderer.with_historical_style()
                elif style == "danger":
                    renderer.with_danger_style()
                else:
                    renderer.with_modern_style()
                renderer.render(str(output_path), duration=duration)

            elif scene_type == "list":
                content = self.extract_list_content(scene)
                renderer = ListRenderer(
                    title=content["title"],
                    items=content["items"],
                    width=self.width,
                    height=self.height,
                    fps=self.fps,
                )
                renderer.render(str(output_path), duration=duration)

            else:
                return RenderResult(
                    success=False,
                    error=f"Unknown scene type: {scene_type}"
                )

            return RenderResult(
                success=True,
                output_path=str(output_path),
                renderer_used=f"Python:{scene_type}"
            )

        except Exception as e:
            return RenderResult(
                success=False,
                error=str(e)
            )

    def render_batch(
        self,
        scenes: List[Scene],
        output_dir: Path,
        duration_map: Dict[str, float] = None,
    ) -> Dict[str, RenderResult]:
        """
        Render multiple scenes.

        Args:
            scenes: List of scenes to render
            output_dir: Directory for output files
            duration_map: Optional map of scene.id -> duration

        Returns:
            Dict mapping scene.id to RenderResult
        """
        results = {}
        duration_map = duration_map or {}

        for scene in scenes:
            if self.can_render(scene):
                duration = duration_map.get(scene.id, 5.0)
                results[scene.id] = self.render(scene, output_dir, duration)
            else:
                results[scene.id] = RenderResult(
                    success=False,
                    error=f"Cannot render visual_type: {scene.visual_type}"
                )

        return results
