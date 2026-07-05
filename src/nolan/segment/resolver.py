"""Stage 4 — per-scene asset source resolution.

The resolver was promoted to the project-wide asset engine
(``nolan.asset_engine``, Phase 2 of the architecture consolidation) — one
ladder for every pipeline. This module remains as a compatibility shim so
existing imports (`nolan.segment.AssetResolver` …) keep working.
"""
from __future__ import annotations

from nolan.asset_engine import (
    ART_TYPES,
    FOOTAGE_TYPES,
    GENERATED_TYPES,
    AssetEngine as AssetResolver,
    EngineConfig as ResolverConfig,
)

__all__ = [
    "AssetResolver", "ResolverConfig",
    "FOOTAGE_TYPES", "GENERATED_TYPES", "ART_TYPES",
]
