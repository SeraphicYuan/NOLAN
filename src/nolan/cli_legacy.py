"""Backwards-compatibility shim for the old monolithic CLI module.

The CLI now lives in the ``nolan.cli`` package, split into domain modules.
This module re-exports every previously importable name from its new home
so that existing ``from nolan.cli_legacy import ...`` imports keep working.
"""

from nolan.cli import main

from nolan.cli.process import (
    _get_project_output_path,
    process,
    _process_essay,
    script,
    _convert_script,
    design,
    _design_scenes,
)
from nolan.cli.index import (
    index,
    _index_videos,
    export,
    _export_single_video,
    _export_all_videos,
    cluster,
    _cluster_video,
    _cluster_all_videos,
)
from nolan.cli.generate import (
    generate,
    _generate_images,
    generate_test,
    _generate_test_image,
)
from nolan.cli.render import (
    infographic,
    _infographic,
    render_infographics,
    _render_infographics,
    _unified_render_clip,
    render_clips,
    render_lottie,
    assemble,
    render_flow_cmd,
)
from nolan.cli.assets import (
    _scoring_vision_config,
    image_search,
    extract_assets,
    match_broll,
    _match_broll,
    match_clips,
    _match_clips,
    cutout,
    broll,
    _broll_localize_img,
    _broll_render,
    acquire_review,
)
from nolan.cli.library import (
    images,
    _open_library,
    images_search,
    images_add,
    images_list,
    images_reject,
    images_promote,
    images_stats,
)
from nolan.cli.audio import (
    transcribe,
    _transcribe_audio,
    align,
)
from nolan.cli.youtube import (
    yt_download,
    yt_search,
    yt_info,
)
from nolan.cli.projects import (
    projects,
    projects_init,
    projects_create,
    projects_list,
    projects_status,
    projects_backfill,
    projects_info,
    projects_delete,
)
from nolan.cli.search import (
    sync_vectors,
    _sync_vectors_impl,
    semantic_search,
)
from nolan.cli.hub import hub
from nolan.cli.templates import (
    templates,
    templates_list,
    templates_info,
    templates_search,
    templates_categories,
    templates_auto_tag,
    templates_summary,
    templates_index,
    templates_semantic_search,
    templates_match_scene,
    route_scenes,
)
from nolan.cli.video_gen import (
    video_gen,
    video_gen_check,
    video_gen_generate,
    video_gen_scene,
    video_gen_batch,
)
from nolan.cli.orchestrate import (
    orchestrate,
    build_from_segment,
)
from nolan.cli.iterate import (
    _COMFY_WF,
    revise_scene_cmd,
    rerender_cmd,
)
from nolan.cli.publish import publish_cmd
