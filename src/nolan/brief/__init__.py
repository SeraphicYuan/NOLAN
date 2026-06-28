"""NOLAN brief layer — agent-facing authoring for broll/motion scenes.

A *brief* is a compact, declarative description of a scene (which assets, what layout,
what motion, when — anchored to the voiceover). `resolve_brief` compiles it to a
validated `nolan.motion` spec; the LLM/agent only ever authors the brief.

    from nolan.brief import resolve_brief, SceneContext
    spec, msgs = resolve_brief({
        "kind": "photo-story", "layout": "grid", "grid": "2x3",
        "images": [...6 paths...], "fly_in": "one-by-one",
        "focus": {"image": 4, "at": {"cue": "keyword"}},
    }, SceneContext(duration=6.0, words=[...]))
    from nolan.motion import render; render(spec, "out.mp4")
"""
from .context import SceneContext
from .timeref import resolve_time
from .resolve import resolve_brief, resolve_for_scene, BRIEF_REGISTRY

__all__ = [
    "SceneContext", "resolve_time", "resolve_brief", "resolve_for_scene", "BRIEF_REGISTRY",
]
