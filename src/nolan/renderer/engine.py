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
from .scenes.lower_third import LowerThirdRenderer
from .scenes.counter import CounterRenderer
from .scenes.comparison import ComparisonRenderer
from .scenes.timeline import TimelineRenderer, TimelineEvent
from .scenes.ken_burns import KenBurnsRenderer
from .scenes.flashback import FlashbackRenderer


# Scene types that can be rendered by Python engine
PYTHON_RENDERABLE_TYPES = {
    # Text-based
    "quote",
    "text-overlay",
    "title",
    "statistic",
    "year",
    "list",
    "chapter",
    # Overlay types
    "lower-third",
    "speaker-id",
    # Animated data
    "counter",
    "comparison",
    "timeline",
    # Image effects
    "ken-burns",
    "flashback",
    "historical",
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

        # Check for lower-third scenes
        if self._is_lower_third_scene(scene):
            return True

        # Check for comparison scenes
        if self._is_comparison_scene(scene):
            return True

        # Check for timeline scenes
        if self._is_timeline_scene(scene):
            return True

        # Check for image effect scenes (need image path)
        if self._is_ken_burns_scene(scene) and self._has_image(scene):
            return True

        if self._is_flashback_scene(scene) and self._has_image(scene):
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

    def _is_lower_third_scene(self, scene: Scene) -> bool:
        """Detect lower-third scenes from visual description."""
        desc = (scene.visual_description or "").lower()
        keywords = ["lower third", "lower-third", "speaker", "name card", "identification"]
        return any(kw in desc for kw in keywords)

    def _is_comparison_scene(self, scene: Scene) -> bool:
        """Detect comparison scenes from visual description."""
        desc = (scene.visual_description or "").lower()
        keywords = ["versus", " vs ", "comparison", "side by side", "split screen"]
        return any(kw in desc for kw in keywords)

    def _is_timeline_scene(self, scene: Scene) -> bool:
        """Detect timeline scenes from visual description."""
        desc = (scene.visual_description or "").lower()
        keywords = ["timeline", "chronolog", "sequence of dates", "key dates", "historical events"]
        return any(kw in desc for kw in keywords)

    def _is_ken_burns_scene(self, scene: Scene) -> bool:
        """Detect Ken Burns effect scenes."""
        desc = (scene.visual_description or "").lower()
        visual_type = (scene.visual_type or "").lower()
        keywords = ["ken burns", "slow zoom", "pan across", "documentary zoom", "photo zoom"]
        return visual_type == "ken-burns" or any(kw in desc for kw in keywords)

    def _is_flashback_scene(self, scene: Scene) -> bool:
        """Detect flashback/vintage effect scenes."""
        desc = (scene.visual_description or "").lower()
        visual_type = (scene.visual_type or "").lower()
        keywords = ["flashback", "sepia", "vintage", "historical photo", "black and white", "old photo"]
        return visual_type in ["flashback", "historical"] or any(kw in desc for kw in keywords)

    def _has_image(self, scene: Scene) -> bool:
        """Check if scene has an associated image."""
        # Check various asset paths
        return bool(
            getattr(scene, 'matched_asset', None) or
            getattr(scene, 'generated_asset', None) or
            getattr(scene, 'image_path', None)
        )

    def detect_scene_type(self, scene: Scene) -> str:
        """Detect the best renderer for a scene."""
        visual_type = (scene.visual_type or "").lower().strip()

        # Direct visual_type mappings
        if visual_type in ["quote"]:
            return "quote"
        if visual_type in ["title", "chapter"]:
            return "title"
        if visual_type in ["statistic", "year"]:
            return "statistic"
        if visual_type in ["list"]:
            return "list"
        if visual_type in ["lower-third", "speaker-id"]:
            return "lower-third"
        if visual_type in ["counter"]:
            return "counter"
        if visual_type in ["comparison"]:
            return "comparison"
        if visual_type in ["timeline"]:
            return "timeline"
        if visual_type in ["ken-burns"]:
            return "ken-burns"
        if visual_type in ["flashback", "historical"]:
            return "flashback"

        # Auto-detect from description
        if self._is_lower_third_scene(scene):
            return "lower-third"
        if self._is_comparison_scene(scene):
            return "comparison"
        if self._is_timeline_scene(scene):
            return "timeline"
        if self._is_ken_burns_scene(scene) and self._has_image(scene):
            return "ken-burns"
        if self._is_flashback_scene(scene) and self._has_image(scene):
            return "flashback"
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

    def extract_lower_third_content(self, scene: Scene) -> Dict[str, Any]:
        """Extract name and title for lower third."""
        desc = scene.visual_description or ""
        narration = scene.narration_excerpt or ""

        # Try to find name patterns
        name_match = re.search(r"([A-Z][a-z]+ [A-Z][a-z]+)", desc + narration)
        name = name_match.group(1) if name_match else "Speaker Name"

        # Try to find title/role
        title_match = re.search(r"(resident|expert|analyst|journalist|professor|director|ceo|founder)",
                                desc.lower())
        title = title_match.group(1).title() if title_match else None

        return {"name": name, "title": title}

    def extract_comparison_content(self, scene: Scene) -> Dict[str, Any]:
        """Extract left/right comparison content."""
        desc = scene.visual_description or ""

        # Try to find "X vs Y" pattern
        vs_match = re.search(r"([A-Za-z\s]+)\s+(?:vs\.?|versus)\s+([A-Za-z\s]+)", desc, re.IGNORECASE)
        if vs_match:
            left = vs_match.group(1).strip()
            right = vs_match.group(2).strip()
            return {"left_text": left, "right_text": right}

        return {"left_text": "Option A", "right_text": "Option B"}

    def extract_timeline_content(self, scene: Scene) -> Dict[str, Any]:
        """Extract timeline events from scene."""
        desc = scene.visual_description or ""
        narration = scene.narration_excerpt or ""
        combined = desc + " " + narration

        # Find year-label pairs
        events = []
        year_patterns = re.findall(r"\b(1[89]\d{2}|20[0-2]\d)\b[:\s-]*([^,.\d]{3,30})?", combined)
        for year, label in year_patterns:
            label = label.strip() if label else "Event"
            events.append({"year": year, "label": label})

        if not events:
            events = [
                {"year": "1821", "label": "Event 1"},
                {"year": "1900", "label": "Event 2"},
                {"year": "2000", "label": "Event 3"},
            ]

        return {"events": events, "title": "TIMELINE"}

    def extract_counter_content(self, scene: Scene) -> Dict[str, Any]:
        """Extract counter value and label."""
        desc = scene.visual_description or ""
        narration = scene.narration_excerpt or ""
        combined = desc + " " + narration

        # Look for number patterns
        num_match = re.search(r"(\d+(?:,\d{3})*)", combined)
        if num_match:
            # Remove commas for numeric value
            value = int(num_match.group(1).replace(",", ""))
        else:
            value = 100

        # Look for label
        label_match = re.search(r"(\d+(?:,\d{3})*)\s*(billion|million|thousand|percent|%|people|countries|years)?",
                                combined, re.IGNORECASE)
        suffix = ""
        if label_match and label_match.group(2):
            suffix = " " + label_match.group(2).upper()

        return {"value": value, "label": None, "suffix": suffix}

    def _get_image_path(self, scene: Scene) -> Optional[str]:
        """Get the image path from a scene."""
        if hasattr(scene, 'matched_asset') and scene.matched_asset:
            return scene.matched_asset
        if hasattr(scene, 'generated_asset') and scene.generated_asset:
            return scene.generated_asset
        if hasattr(scene, 'image_path') and scene.image_path:
            return scene.image_path
        return None

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

            elif scene_type == "lower-third":
                content = self.extract_lower_third_content(scene)
                renderer = LowerThirdRenderer(
                    name=content["name"],
                    title=content.get("title"),
                    width=self.width,
                    height=self.height,
                    fps=self.fps,
                )
                renderer.render(str(output_path), duration=duration)

            elif scene_type == "counter":
                content = self.extract_counter_content(scene)
                renderer = CounterRenderer(
                    value=content["value"],
                    label=content.get("label"),
                    suffix=content.get("suffix", ""),
                    width=self.width,
                    height=self.height,
                    fps=self.fps,
                )
                renderer.render(str(output_path), duration=duration)

            elif scene_type == "comparison":
                content = self.extract_comparison_content(scene)
                renderer = ComparisonRenderer(
                    left_text=content["left_text"],
                    right_text=content["right_text"],
                    width=self.width,
                    height=self.height,
                    fps=self.fps,
                )
                renderer.render(str(output_path), duration=duration)

            elif scene_type == "timeline":
                content = self.extract_timeline_content(scene)
                events = [
                    TimelineEvent(year=e["year"], label=e["label"])
                    for e in content["events"]
                ]
                renderer = TimelineRenderer(
                    events=events,
                    title=content.get("title"),
                    width=self.width,
                    height=self.height,
                    fps=self.fps,
                )
                renderer.render(str(output_path), duration=duration)

            elif scene_type == "ken-burns":
                image_path = self._get_image_path(scene)
                if not image_path:
                    return RenderResult(
                        success=False,
                        error="Ken Burns effect requires an image path"
                    )
                renderer = KenBurnsRenderer(
                    image_path=image_path,
                    zoom_start=1.0,
                    zoom_end=1.2,
                    width=self.width,
                    height=self.height,
                    fps=self.fps,
                )
                renderer.render(str(output_path), duration=duration)

            elif scene_type == "flashback":
                image_path = self._get_image_path(scene)
                if not image_path:
                    return RenderResult(
                        success=False,
                        error="Flashback effect requires an image path"
                    )
                # Check for year in description for overlay
                desc = (scene.visual_description or "") + (scene.narration_excerpt or "")
                year_match = re.search(r"\b(1[89]\d{2}|20[0-2]\d)\b", desc)
                year_text = year_match.group(1) if year_match else None

                renderer = FlashbackRenderer(
                    image_path=image_path,
                    style="sepia",
                    vignette=True,
                    grain=0.05,
                    year_text=year_text,
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
