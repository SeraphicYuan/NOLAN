"""Vision-based descriptions for picture-library assets.

Reuses the same vision pipeline the video library uses to describe segments
(:mod:`nolan.vision`). A *describer* is a sync ``Callable[[Path], str]`` so it
plugs into :class:`nolan.imagelib.store.ImageLibrary` (which may run inside
worker-thread pools) without each caller wiring async/vision config.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

# Asks for the things that make b-roll matchable: subjects, setting, era, mood,
# action — not a caption. One concise paragraph keeps embeddings focused.
DESCRIBE_PROMPT = (
    "Describe this image for matching it to documentary b-roll. In one concise "
    "paragraph, state the main subjects, setting/location, time period or era, "
    "notable objects, action, and overall mood. Be concrete and factual; do not "
    "add commentary or guesses beyond what is visible."
)


def make_describer(config, *, provider: Optional[str] = None,
                   prompt: str = DESCRIBE_PROMPT) -> Callable[[Path], str]:
    """Build a sync ``describe(path) -> str`` from a NOLAN config.

    The vision provider is created once and reused across calls. Returns "" on
    any failure so ingestion never breaks on a bad image / offline model.
    """
    from nolan.vision import create_vision_provider
    from nolan.webui.operations import _select_vision

    prov_name = provider or getattr(config.vision, "provider", "ollama")
    vcfg = _select_vision(config, prov_name, None, None, None)
    vprovider = create_vision_provider(vcfg)

    def describe(path) -> str:
        from nolan.segment.render import _run_async
        try:
            text = _run_async(vprovider.describe_image(Path(path), prompt))
        except Exception:
            return ""
        return (text or "").strip()

    return describe
