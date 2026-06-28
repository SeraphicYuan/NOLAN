"""Scene-level iteration: edit/comment N scenes -> re-render only those -> reassemble.

Works on a `scene_plan.json` regardless of which pipeline produced it:

- **segment** (asset-first, `nolan build-from-segment`): clips in `clips/`, real VO,
  re-render via the skip-guarded `SegmentBuilder.build_from_plan`.
- **orchestrator** (linear, script->scenes->match): clips in `assets/rendered/`, silent
  audio, scenes carry `layout_spec` (so we operate on raw dicts, never the lossy
  `Scene` dataclass round-trip).

Public surface:
- `detect_pipeline(plan_path)` -> "segment" | "orchestrator"
- `revise_scene(scene, note, client, pipeline)` -> renderable field patch (async)
- `apply_edit(plan_path, scene_id, patch=?, note=?, client=?)` -> writes plan (async)
- `rerender_scenes(plan_path, scene_ids, ...)` -> reassembled final.mp4 path
"""
from .engine import (
    detect_pipeline,
    load_plan_raw,
    save_plan_raw,
    iter_scenes,
    find_scene,
    invalidate_scene,
    rerender_scenes,
)
from .revise import revise_scene, apply_patch, apply_edit, editable_fields
from .transcript import scene_words

__all__ = [
    "detect_pipeline",
    "load_plan_raw",
    "save_plan_raw",
    "iter_scenes",
    "find_scene",
    "invalidate_scene",
    "rerender_scenes",
    "revise_scene",
    "apply_patch",
    "apply_edit",
    "editable_fields",
    "scene_words",
]
