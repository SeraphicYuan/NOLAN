"""Brief resolution — the authoring layer between broll design and the render engines.

`resolve_brief(brief, ctx)` turns a compact, agent-authored *brief* into a validated
motion spec (which `nolan.motion.render` then renders on python or remotion). Resolution
is deterministic and pure given a `SceneContext`; the only "magic" is TimeRef → seconds
against the scene transcript. New brief families register a resolver in BRIEF_REGISTRY.

Design boundary: resolution happens at DESIGN time (where the transcript lives) and the
resulting spec is persisted on the scene. Render stays context-free.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .context import SceneContext
from . import photo_story

# kind -> resolver(brief, ctx) -> motion spec (pre-validation)
BRIEF_REGISTRY: Dict[str, Any] = {}
BRIEF_REGISTRY.update(photo_story.RESOLVERS)


def resolve_brief(brief: Dict[str, Any], ctx: Optional[SceneContext] = None) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Resolve a brief into a *validated* motion spec.

    Returns (spec, messages). `messages` collects design-time warnings (missing cue,
    missing image, grid overflow) plus any spec-validation errors — surface these to the
    author; resolution still returns a best-effort spec so a render can proceed.
    """
    if not isinstance(brief, dict):
        return None, [f"brief must be an object, got {type(brief).__name__}"]
    if ctx is None:
        ctx = SceneContext(duration=float(brief.get("duration", 8.0)))

    kind = brief.get("kind", "photo-story")
    resolver = BRIEF_REGISTRY.get(kind)
    if resolver is None:
        return None, [f"unknown brief kind {kind!r}; known: {sorted(BRIEF_REGISTRY)}"]

    spec = resolver(brief, ctx)

    from nolan.motion import validate
    norm, errors = validate(spec)
    return norm, ctx.warnings + errors


def resolve_for_scene(brief: Dict[str, Any], scene, words: Optional[list] = None) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Convenience: build a SceneContext from a Scene-like object, then resolve.

    `words` is an optional transcript word list (abs seconds) for cue matching; pass the
    project transcript sliced to this scene. Without it, cue refs fall back to anchors.
    """
    ctx = SceneContext.from_scene(scene, words=words)
    if not ctx.words:
        ctx.warn("no narration word-timing available; cue-based timing falls back to anchors")
    return resolve_brief(brief, ctx)
