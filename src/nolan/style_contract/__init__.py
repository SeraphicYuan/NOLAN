"""Style Contract — the reusable editorial-instruction layer for video-essay authoring.

Three separated layers: the block VOCABULARY (compose.py/catalog.json) stays as-is; a declarative
STYLE CONTRACT (a preset + a few dials) dual-compiles to the author's brief AND a deterministic
LINTER that scores a draft on measurable craft dimensions. Lean by design: 5 hard GATES, the rest
ADVISORY. Draft → lint → revise → accept. A reference video's fingerprint can seed a contract.

To tweak what's judged, edit ONE file: `dimensions.py` (the registry). The engine reads it.
"""
from .dimensions import (Dimension, DIMENSIONS, GATES, ADVISORY, BY_KEY,
                         DIAL_ALIASES, LEVELS, PRESETS, DEFAULT_PRESET, PRINCIPLES)
from .metrics import (SceneView, measure, block_family, BLOCK_FAMILY, MEDIA_CAPABLE,
                      scene_media, scene_words, scene_num_count, scene_asset_srcs)
from .contract import StyleContract, fmt_target
from .palette import (palette_brief, authoring_brief, load_catalog, catalog_blocks, BEAT_ROUTING)
from .linter import (lint, scenes_from_hf, fingerprint, contract_from_fingerprint, format_report)

__all__ = [
    "Dimension", "DIMENSIONS", "GATES", "ADVISORY", "BY_KEY",
    "DIAL_ALIASES", "LEVELS", "PRESETS", "DEFAULT_PRESET", "PRINCIPLES",
    "SceneView", "measure", "block_family", "BLOCK_FAMILY", "MEDIA_CAPABLE",
    "scene_media", "scene_words", "scene_num_count", "scene_asset_srcs",
    "StyleContract", "fmt_target",
    "palette_brief", "authoring_brief", "load_catalog", "catalog_blocks", "BEAT_ROUTING",
    "lint", "scenes_from_hf", "fingerprint", "contract_from_fingerprint", "format_report",
]
