"""Command-line interface for NOLAN.

This package provides organized CLI commands. Currently re-exports from
the legacy cli module while migration is in progress.

Structure (target):
- process.py: Essay processing pipeline (process, script, design)
- index.py: Video indexing and export (index, export, cluster)
- search.py: Semantic and image search
- render.py: Video rendering and assembly
- youtube.py: YouTube download utilities
- projects.py: Project management group
- templates.py: Lottie template management group
- video_gen.py: Video generation group
- library.py: Library viewing utilities
"""

# Re-export from the legacy cli module for backwards compatibility
from nolan.cli_legacy import main

# The main group is the entry point
__all__ = ['main']
