"""NOLAN-side HyperFrames composer edit mode — the "editing bridge".

A parallel composer-native scene-edit engine that MIRRORS the iterate pattern (load -> find scene ->
patch -> gate -> re-render only what's affected) over the composer artifact
(compositions/frames/<id>.spec.json), instead of scene_plan.json. Edit per scene, re-render per frame.
See render-service/_lab_hyperframes/kb/edit-mode-plan.md.
"""
from .edit import (
    discover_compositions, list_frames, load_frame_spec, save_frame_spec,
    apply_scene_edit, add_scene, remove_scene, retime_scene,
    recompose_frame, snapshot_frame, render_frame, beat_boundary_planner, catalog,
    revise_frame_note, build_note_prompt, list_assets, resolve_asset, save_upload, comp_dir,
)

__all__ = [
    "discover_compositions", "list_frames", "load_frame_spec", "save_frame_spec",
    "apply_scene_edit", "add_scene", "remove_scene", "retime_scene",
    "recompose_frame", "snapshot_frame", "render_frame", "beat_boundary_planner", "catalog",
    "revise_frame_note", "build_note_prompt", "list_assets", "resolve_asset", "save_upload", "comp_dir",
]
