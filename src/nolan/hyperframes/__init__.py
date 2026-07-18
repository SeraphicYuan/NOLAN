"""NOLAN-side HyperFrames composer edit mode — the "editing bridge".

A parallel composer-native scene-edit engine that MIRRORS the iterate pattern (load -> find scene ->
patch -> gate -> re-render only what's affected) over the composer artifact
(compositions/frames/<id>.spec.json), instead of scene_plan.json. Edit per scene, re-render per frame.
See render-service/_lab_hyperframes/kb/edit-mode-plan.md.
"""
from .edit import (
    discover_compositions, list_frames, load_frame_spec, save_frame_spec, frame_layers, frame_transcripts,
    apply_scene_edit, add_scene, remove_scene, retime_scene,
    recompose_frame, snapshot_frame, render_frame, beat_boundary_planner, catalog,
    revise_frame_note, build_note_prompt, list_assets, asset_pool_meta, resolve_asset, save_upload, comp_dir,
    new_essay, derive_asset_needs, run_pool, attach_voiceover, frame_video_path,
    add_scene_asset, remove_scene_asset, add_pool_asset, quickedit_asset, treat_preview, revert_asset,
    quick_edit_ops, fit_ground_to_scene, ensure_grounds_fit, cleanup_analyze, cleanup_asset,
    list_themes, suggest_theme, theme_exists,
    stage_comment, list_changeset, resolve_comment, log_activity, list_activity, resolve_mentions,
    propose_scene_edit, list_proposals, accept_proposal, reject_proposal, proposal_preview,
)

__all__ = [
    "discover_compositions", "list_frames", "load_frame_spec", "save_frame_spec", "frame_layers", "frame_transcripts",
    "apply_scene_edit", "add_scene", "remove_scene", "retime_scene",
    "recompose_frame", "snapshot_frame", "render_frame", "beat_boundary_planner", "catalog",
    "revise_frame_note", "build_note_prompt", "list_assets", "asset_pool_meta", "resolve_asset", "save_upload", "comp_dir",
    "new_essay", "derive_asset_needs", "run_pool", "attach_voiceover", "frame_video_path",
    "add_scene_asset", "remove_scene_asset", "add_pool_asset", "quickedit_asset", "treat_preview", "revert_asset",
    "quick_edit_ops", "fit_ground_to_scene", "ensure_grounds_fit", "cleanup_analyze", "cleanup_asset",
    "list_themes", "suggest_theme", "theme_exists",
    "stage_comment", "list_changeset", "resolve_comment", "log_activity", "list_activity", "resolve_mentions",
    "propose_scene_edit", "list_proposals", "accept_proposal", "reject_proposal", "proposal_preview",
]
