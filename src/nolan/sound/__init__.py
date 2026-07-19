"""Sound umbrella — SFX cue-kinds as a declarative registry.

The taste/vocabulary layer for sound design (see docs/SOUND_DESIGN.md). The
registry names the *kinds* of cue (whoosh, impact, paper, data-punch, …) with
craft guidance for WHEN to fire each; the curated bank (projects/_library/sfx/
sfx.json) holds the *files*, each tagged with its `kind`. Cues are authored as
data on the plan (`scene.sfx` in the standard pipeline; `scene.data.sfx` in the
HyperFrames spec), validated here, and executed in the mix path
(nolan.audio_mix). Mirrors nolan/editing.py + nolan/motion/registry.py.
"""

from .registry import (
    SoundCue, REGISTRY, BY_ID, KINDS, FAMILIES,
    validate_scene_sound, validate_plan_sound,
)

__all__ = [
    "SoundCue", "REGISTRY", "BY_ID", "KINDS", "FAMILIES",
    "validate_scene_sound", "validate_plan_sound",
]
