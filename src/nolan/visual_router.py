"""
Visual type router for NOLAN.

Routes scenes to appropriate asset pipelines based on visual_type:
- Templates (Lottie) for: lower-third, text-overlay, counter, title, icon, loading
- Library search for: b-roll, a-roll
- Image generation for: generated, generated-image
- Infographic engine for: infographic, chart
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Literal

from nolan.scenes import Scene
from nolan.template_catalog import (
    TemplateCatalog,
    TemplateSearch,
    TemplateInfo,
    find_templates_for_scene,
)


# Route types
RouteType = Literal["template", "python-template", "library", "generation", "infographic", "passthrough"]


# Visual types that should use templates (Lottie/render-service)
TEMPLATE_VISUAL_TYPES = {
    "lower-third",
    "text-overlay",
    "title",
    "counter",
    "icon",
    "loading",
    "lottie",
    "ui",
}

# Visual types that can use Python renderer as fallback
PYTHON_TEMPLATE_TYPES = {
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
    # Image effects (require image path)
    "ken-burns",
    "flashback",
    "historical",
}

# Visual types that should search library
LIBRARY_VISUAL_TYPES = {
    "b-roll",
    "a-roll",
    "footage",
    "cinematic",
}

# Visual types that should generate images
GENERATION_VISUAL_TYPES = {
    "generated",
    "generated-image",
}

# Visual types that use infographic engine
INFOGRAPHIC_VISUAL_TYPES = {
    "infographic",
    "chart",
    "graphics",
}


@dataclass
class RouteDecision:
    """Result of routing decision for a scene."""
    route: RouteType
    reason: str
    template: Optional[TemplateInfo] = None
    template_score: Optional[float] = None
    python_renderer: Optional[str] = None  # e.g., "quote", "title", "statistic"


class VisualRouter:
    """Routes scenes to appropriate asset pipelines."""

    def __init__(
        self,
        catalog: TemplateCatalog = None,
        search: TemplateSearch = None,
        template_score_threshold: float = 0.5,
    ):
        """Initialize router.

        Args:
            catalog: Template catalog (created if not provided)
            search: Template search (created if not provided)
            template_score_threshold: Minimum score to use a template match
        """
        self.catalog = catalog
        self.search = search
        self.template_score_threshold = template_score_threshold
        self._initialized = False

    def _ensure_initialized(self):
        """Lazy initialization of catalog and search."""
        if self._initialized:
            return

        if self.catalog is None:
            self.catalog = TemplateCatalog()
            self.catalog.load_tags()
            self.catalog.auto_tag_all()

        if self.search is None:
            self.search = TemplateSearch(self.catalog)
            # Ensure indexed
            try:
                if self.search._get_collection().count() == 0:
                    self.search.index_templates()
            except Exception:
                self.search.index_templates()

        self._initialized = True

    def route(self, scene: Scene) -> RouteDecision:
        """Determine the best pipeline for a scene.

        Args:
            scene: Scene to route

        Returns:
            RouteDecision with route type and optional template match
        """
        visual_type = (scene.visual_type or "").lower().strip()

        # Already has a lottie template specified
        if scene.lottie_template:
            return RouteDecision(
                route="template",
                reason="Scene has lottie_template specified"
            )

        # Already has rendered clip
        if scene.rendered_clip:
            return RouteDecision(
                route="passthrough",
                reason="Scene already has rendered_clip"
            )

        # Check infographic first (has specific spec)
        if visual_type in INFOGRAPHIC_VISUAL_TYPES:
            if scene.infographic:
                return RouteDecision(
                    route="infographic",
                    reason=f"Visual type '{visual_type}' with infographic spec"
                )

        # Check template types
        if visual_type in TEMPLATE_VISUAL_TYPES:
            self._ensure_initialized()
            results = find_templates_for_scene(
                scene, self.catalog, self.search, top_k=1, require_schema=False
            )

            if results and results[0].score >= self.template_score_threshold:
                return RouteDecision(
                    route="template",
                    reason=f"Template match for '{visual_type}'",
                    template=results[0].template,
                    template_score=results[0].score
                )
            else:
                # Fallback to Python template if supported
                if visual_type in PYTHON_TEMPLATE_TYPES:
                    return RouteDecision(
                        route="python-template",
                        reason=f"Python fallback for '{visual_type}' (no Lottie match)",
                        python_renderer=visual_type
                    )
                # Fallback to library if no good template match
                return RouteDecision(
                    route="library",
                    reason=f"No template match above threshold ({self.template_score_threshold})"
                )

        # Check Python template types (quote, statistic, list, etc.)
        if visual_type in PYTHON_TEMPLATE_TYPES:
            return RouteDecision(
                route="python-template",
                reason=f"Python renderer for '{visual_type}'",
                python_renderer=visual_type
            )

        # Check generation types
        if visual_type in GENERATION_VISUAL_TYPES:
            if scene.comfyui_prompt:
                return RouteDecision(
                    route="generation",
                    reason=f"Visual type '{visual_type}' with comfyui_prompt"
                )
            else:
                return RouteDecision(
                    route="library",
                    reason=f"Visual type '{visual_type}' but no comfyui_prompt"
                )

        # Default to library search
        return RouteDecision(
            route="library",
            reason=f"Default route for visual type '{visual_type}'"
        )

    def route_all(self, scenes: list[Scene]) -> dict[str, RouteDecision]:
        """Route all scenes and return decisions.

        Args:
            scenes: List of scenes to route

        Returns:
            Dict mapping scene.id to RouteDecision
        """
        decisions = {}
        for scene in scenes:
            decisions[scene.id] = self.route(scene)
        return decisions

    def summary(self, decisions: dict[str, RouteDecision]) -> dict:
        """Get summary of routing decisions.

        Args:
            decisions: Dict from route_all()

        Returns:
            Summary with counts by route type
        """
        by_route = {}
        for decision in decisions.values():
            by_route[decision.route] = by_route.get(decision.route, 0) + 1

        return {
            "total": len(decisions),
            "by_route": by_route,
        }
