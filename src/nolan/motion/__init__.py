"""NOLAN motion-spec system.

Translate a natural-language scene design into a precise, validated render spec and
render it on the right backend (Python renderer or Remotion). The registry
(`registry.py`) is the single source of truth — add effects/params there over time.

    from nolan.motion import author
    spec, errors = await author("circle the 88% stat, scribble, top-left", "out.mp4")
"""
from .registry import REGISTRY, BY_ID, get_effect, normalize_position, MotionEffect, Param, SHARED, ANCHORS, THEMES
from .manifest import build_manifest, build_guide
from .spec import validate
from .compiler import compile_spec, compile_many
from .executor import chapter_step_for_spec, render


async def author(scene_design: str, out_path, client=None):
    """Compile a scene design and render it. Returns (spec, errors)."""
    if client is None:
        from nolan.config import load_config
        from nolan.llm import create_text_llm
        client = create_text_llm(load_config())
    spec, errors = await compile_spec(scene_design, client)
    render(spec, out_path)
    return spec, errors


__all__ = [
    "REGISTRY", "BY_ID", "get_effect", "normalize_position", "MotionEffect", "Param",
    "SHARED", "ANCHORS", "THEMES", "build_manifest", "build_guide", "validate",
    "compile_spec", "compile_many", "render", "chapter_step_for_spec", "author",
]
