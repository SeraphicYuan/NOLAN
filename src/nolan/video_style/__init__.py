"""Video-style analysis for NOLAN.

The visual twin of ``script_style``: distill the *production / visual* style of
reference videos (from the library) into a reusable ``video_style_guide.md`` so a
similar look can be cloned. Mirrors the Script Styles flow — corpus of reference
videos → per-video extract → agent synthesis → guide.

This package owns the file-backed store and the deterministic visual-stats
computation (color, motion, pacing, graphics density). The style-focused vision
pass and the synthesis agent dispatch live alongside the Script Styles ones.
"""

from .store import VideoStyleStore
from . import visual_stats
from . import pairing
from . import tempo

__all__ = ["VideoStyleStore", "visual_stats", "pairing", "tempo"]
