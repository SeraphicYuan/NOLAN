"""Command-line interface for NOLAN.

This package provides the CLI organized into domain modules. The shared
``main`` click group is defined in ``_root``; importing each domain module
registers its commands on ``main`` as a side effect.

Structure:
- process.py: Essay processing pipeline (process, script, design)
- index.py: Video indexing and export (index, export, cluster)
- generate.py: ComfyUI image generation (generate, generate-test)
- render.py: Rendering and assembly (infographic, render-infographics,
  render-clips, render-lottie, assemble, render-flow)
- assets.py: Asset sourcing and matching (image-search, extract-assets,
  match-broll, match-clips, cutout, broll, acquire-review)
- library.py: Picture library (images group)
- audio.py: Transcription and alignment (transcribe, align)
- youtube.py: YouTube download utilities (yt-download, yt-search, yt-info)
- projects.py: Project management group
- search.py: Semantic search (sync-vectors, semantic-search)
- hub.py: Unified NOLAN Hub UI launcher
- templates.py: Lottie template management group + route-scenes
- video_gen.py: Video generation group
- orchestrate.py: Pipeline orchestration (orchestrate, build-from-segment)
- iterate.py: Scene iteration (revise-scene, rerender)
- publish.py: Article publishing (publish)
- capabilities.py: Umbrella capability catalog (capabilities)
"""

from nolan.cli._root import main

# Import domain modules for their side effect: registering commands on `main`.
from nolan.cli import (  # noqa: E402,F401
    process,
    index,
    generate,
    render,
    assets,
    library,
    audio,
    youtube,
    projects,
    search,
    hub,
    templates,
    video_gen,
    orchestrate,
    iterate,
    publish,
    capabilities,
    brief_cmd,
    music,
    lint_cmd,
    package_cmd,
    retro_cmd,
    kb,
)

# The main group is the entry point
__all__ = ['main']
