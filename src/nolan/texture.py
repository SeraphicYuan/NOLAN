"""Texture grammar — the tactile layer of the meta-style program.

One authored, scene-level field:

    scene.texture = {"jitter": {"fps": 4..15, "amp": 0..12},   # stop-motion stutter
                     "edge": "rough" | "boil"}                  # torn-paper outlines

`build_section_job` copies it onto every Chapter step of the scene; the
Chapter driver (render-service/remotion-lib/src/Chapter.tsx) executes it —
audio and captions sit OUTSIDE the wrapper, so narration timing and word
sync are untouched. Style packs set per-style defaults later; a scene-level
value always wins.

Vocabulary + validation live here (one owner). Invalid input is refused
loudly at the premium gate, never silently dropped.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

TEXTURE_EDGES = ("rough", "boil")

_JITTER_FPS = (4, 15)      # simulated update rate ("animating on twos/threes")
_JITTER_AMP = (0, 12)      # px displacement per update


def validate_texture(t: Any) -> Tuple[Dict[str, Any], List[str]]:
    """Return (normalized texture dict, errors). Empty dict = no texture."""
    errors: List[str] = []
    if t in (None, {}, ""):
        return {}, []
    if not isinstance(t, dict):
        return {}, [f"texture must be an object, got {type(t).__name__}"]
    out: Dict[str, Any] = {}
    jit = t.get("jitter")
    if jit is not None:                    # {} = "defaults, please"
        if not isinstance(jit, dict):
            errors.append("texture.jitter must be an object {fps, amp}")
        else:
            try:
                fps = int(jit.get("fps", 12))
                amp = float(jit.get("amp", 4))
            except (TypeError, ValueError):
                errors.append("texture.jitter fps/amp must be numbers")
            else:
                if not (_JITTER_FPS[0] <= fps <= _JITTER_FPS[1]):
                    errors.append(f"texture.jitter.fps {fps} outside {_JITTER_FPS}")
                elif not (_JITTER_AMP[0] <= amp <= _JITTER_AMP[1]):
                    errors.append(f"texture.jitter.amp {amp} outside {_JITTER_AMP}")
                else:
                    out["jitter"] = {"fps": fps, "amp": amp}
    edge = t.get("edge")
    if edge not in (None, ""):
        if edge in TEXTURE_EDGES:
            out["edge"] = edge
        else:
            errors.append(f"texture.edge '{edge}' not in {TEXTURE_EDGES}")
    unknown = set(t) - {"jitter", "edge"}
    if unknown:
        errors.append(f"texture: unknown keys {sorted(unknown)}")
    return out, errors


def stamp_step(step: Dict[str, Any], scene: Dict[str, Any]) -> None:
    """Copy a scene's validated texture onto one Chapter step (in place)."""
    tex, errors = validate_texture(scene.get("texture"))
    if errors:
        raise ValueError(f"scene {scene.get('id')}: " + "; ".join(errors))
    if tex.get("jitter"):
        step["jitter"] = tex["jitter"]
    if tex.get("edge"):
        step["edge"] = tex["edge"]
