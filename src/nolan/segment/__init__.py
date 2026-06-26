"""Build a ~1-minute video essay from a segment (span / script / voiceover).

Wraps the validated asset-first pipeline: input -> design(+motion) -> timing ->
resolve sources -> [review gate] -> render -> assemble.

    from nolan.segment import SegmentBuilder, BuildConfig
    from nolan.segment.inputs import from_indexed_span
"""
from .inputs import (SegmentInput, from_indexed_span, from_script, from_vo,
                     assign_timing, parse_srt)
from .resolver import AssetResolver, ResolverConfig, FOOTAGE_TYPES, GENERATED_TYPES
from .render import RenderContext, render_scene_clip
from .builder import SegmentBuilder, BuildConfig, BuildResult, suggest_spans

__all__ = [
    "SegmentInput", "from_indexed_span", "from_script", "from_vo", "assign_timing", "parse_srt",
    "AssetResolver", "ResolverConfig", "FOOTAGE_TYPES", "GENERATED_TYPES",
    "RenderContext", "render_scene_clip",
    "SegmentBuilder", "BuildConfig", "BuildResult", "suggest_spans",
]
