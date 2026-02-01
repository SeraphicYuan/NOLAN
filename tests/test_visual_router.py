"""Tests for visual router."""

import pytest
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any

from nolan.visual_router import (
    VisualRouter,
    RouteDecision,
    TEMPLATE_VISUAL_TYPES,
    LIBRARY_VISUAL_TYPES,
    GENERATION_VISUAL_TYPES,
    INFOGRAPHIC_VISUAL_TYPES,
)


@dataclass
class MockScene:
    """Mock Scene for testing."""
    id: str
    visual_type: str = "b-roll"
    visual_description: str = ""
    narration_excerpt: str = ""
    lottie_template: Optional[str] = None
    lottie_config: Optional[Dict] = None
    rendered_clip: Optional[str] = None
    infographic: Optional[Dict] = None
    comfyui_prompt: str = ""


class TestVisualRouter:
    """Tests for VisualRouter class."""

    def test_route_b_roll_to_library(self):
        """B-roll scenes route to library."""
        router = VisualRouter()
        scene = MockScene("s1", "b-roll", "city skyline")

        decision = router.route(scene)

        assert decision.route == "library"

    def test_route_lower_third_to_template(self):
        """Lower-third scenes route to template."""
        router = VisualRouter()
        scene = MockScene("s1", "lower-third", "show speaker name")

        decision = router.route(scene)

        assert decision.route == "template"
        assert decision.template is not None

    def test_route_counter_to_template(self):
        """Counter scenes route to template."""
        router = VisualRouter()
        scene = MockScene("s1", "counter", "counting numbers")

        decision = router.route(scene)

        assert decision.route == "template"

    def test_route_infographic_with_spec(self):
        """Infographic with spec routes to infographic."""
        router = VisualRouter()
        scene = MockScene("s1", "infographic", "process", infographic={"template": "steps"})

        decision = router.route(scene)

        assert decision.route == "infographic"

    def test_route_generated_with_prompt(self):
        """Generated with comfyui_prompt routes to generation."""
        router = VisualRouter()
        scene = MockScene("s1", "generated", "futuristic", comfyui_prompt="futuristic city")

        decision = router.route(scene)

        assert decision.route == "generation"

    def test_route_generated_without_prompt(self):
        """Generated without comfyui_prompt falls back to library."""
        router = VisualRouter()
        scene = MockScene("s1", "generated", "something")

        decision = router.route(scene)

        assert decision.route == "library"

    def test_route_with_existing_rendered_clip(self):
        """Scenes with rendered_clip get passthrough."""
        router = VisualRouter()
        scene = MockScene("s1", "lower-third", "name", rendered_clip="clips/s1.mp4")

        decision = router.route(scene)

        assert decision.route == "passthrough"

    def test_route_with_explicit_lottie_template(self):
        """Scenes with lottie_template get template route."""
        router = VisualRouter()
        scene = MockScene("s1", "b-roll", "something", lottie_template="lower-thirds/simple.json")

        decision = router.route(scene)

        assert decision.route == "template"

    def test_route_all(self):
        """route_all processes multiple scenes."""
        router = VisualRouter()
        scenes = [
            MockScene("s1", "b-roll"),
            MockScene("s2", "lower-third", "name"),
            MockScene("s3", "counter", "stats"),
        ]

        decisions = router.route_all(scenes)

        assert len(decisions) == 3
        assert "s1" in decisions
        assert "s2" in decisions
        assert "s3" in decisions

    def test_summary(self):
        """summary returns correct counts."""
        router = VisualRouter()
        scenes = [
            MockScene("s1", "b-roll"),
            MockScene("s2", "b-roll"),
            MockScene("s3", "lower-third", "name"),
        ]

        decisions = router.route_all(scenes)
        summary = router.summary(decisions)

        assert summary["total"] == 3
        assert "library" in summary["by_route"]
        assert "template" in summary["by_route"]

    def test_threshold_affects_routing(self):
        """High threshold prevents template matches."""
        # With very high threshold, even good matches fail
        router = VisualRouter(template_score_threshold=0.99)
        scene = MockScene("s1", "lower-third", "something vague")

        decision = router.route(scene)

        # Should fall back to library since no match above 99%
        assert decision.route == "library"

    def test_template_visual_types_defined(self):
        """Template visual types are defined."""
        assert "lower-third" in TEMPLATE_VISUAL_TYPES
        assert "counter" in TEMPLATE_VISUAL_TYPES
        assert "title" in TEMPLATE_VISUAL_TYPES
        assert "lottie" in TEMPLATE_VISUAL_TYPES

    def test_library_visual_types_defined(self):
        """Library visual types are defined."""
        assert "b-roll" in LIBRARY_VISUAL_TYPES
        assert "a-roll" in LIBRARY_VISUAL_TYPES

    def test_generation_visual_types_defined(self):
        """Generation visual types are defined."""
        assert "generated" in GENERATION_VISUAL_TYPES
        assert "generated-image" in GENERATION_VISUAL_TYPES

    def test_infographic_visual_types_defined(self):
        """Infographic visual types are defined."""
        assert "infographic" in INFOGRAPHIC_VISUAL_TYPES
        assert "chart" in INFOGRAPHIC_VISUAL_TYPES
