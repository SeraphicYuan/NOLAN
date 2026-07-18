"""Effects umbrella — visual treatments (colour grades, grain, film damage, element overlays) applied
to any media asset. Declarative registry (registry.py) + backend-agnostic render-time executor
(render.py). See CLAUDE.md module contract; mirrors nolan.motion / nolan.editing."""
from .registry import (BLEND_MODES, FAMILIES, FFMPEG_VF, METHODS, REGISTRY, BY_ID, Effect, bakeable,
                       get_effect, normalize_treatments, validate_treatments)
from .render import filter_chain, has_overlays, overlay_layers
from .library import load_overlay_library, resolve_plate, stocked_effects

__all__ = ["REGISTRY", "BY_ID", "Effect", "FAMILIES", "METHODS", "BLEND_MODES", "FFMPEG_VF", "bakeable",
           "get_effect", "validate_treatments", "normalize_treatments", "filter_chain", "overlay_layers",
           "has_overlays", "load_overlay_library", "resolve_plate", "stocked_effects"]
