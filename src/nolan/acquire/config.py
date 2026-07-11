"""Acquisition tuning — the numeric tweak surface. Change how DEEP, how PICKY, and how GENERATIVE
the pool is from this one place; the engine reads it."""
from dataclasses import dataclass, field
from typing import Tuple


@dataclass
class AcquireConfig:
    # depth
    per_need: int = 8                 # keep this many assets per need
    over_fetch: int = 3               # images: fetch per_need × over_fetch candidates, then cull to the best
    over_fetch_video: int = 1         # video: DON'T over-fetch — clips are large + slow, and video is ranked
                                      # by search order (not by a per-file score), so download only what we keep
    clip_seconds: int = 20            # fetch only a SHORT segment of each video (via ffmpeg range-seek) — b-roll
                                      # needs 5-30s, not a full 21-minute archive.org film
    # sources (order tried; "generate" is conditional, handled by the engine)
    sources: Tuple[str, ...] = ("library", "stock")
    # relevance + fitness gating
    relevance_floor: float = 0.5      # (evocative beats only) generate originals unless stock relevance clears
                                      # this — set high on purpose so abstract beats get bespoke art, not thin stock
    min_usable: int = 4               # escalate/generate if fewer than this survive fitness+relevance
    w_relevance: float = 1.0          # combined score weights
    w_fitness: float = 0.5
    # generation (first-class, floor-gated — only where stock/library is thin or off-topic)
    generate_evocative: bool = True   # generate for evocative beats below the relevance floor
    generate_n: int = 3               # abstract beats lean on bespoke originals — stock/library are thin there
    # library quality gate — the library is a k-NEAREST store: it returns `k` hits for ANY query even when
    # the nearest is off-domain (a global cross-project library full of, e.g., medieval woodcuts will match
    # "power grid" at ~0.18). Tier-0 alone would let that flood a beat, so library must clear an ABSOLUTE
    # relevance bar to be trusted; below it, the beat leans on relevant stock + generation instead.
    library_min_relevance: float = 0.24
    # generic-stock quality floor — web/stock providers (pexels/pixabay/ddgs/unsplash) match keywords
    # LITERALLY, so an abstract query drags in junk ("fast track"→race car, "shell company"→seashell).
    # Generic stock must clear this to be kept; CURATED museum/art sources are EXEMPT (their low literal
    # relevance is intentional — evocative art is not supposed to be a literal photo of the subject).
    stock_relevance_floor: float = 0.20
    # diversity
    max_reuse: int = 3                # don't keep the same image for more than this many needs
    dedup_hamming: int = 6            # average-hash distance under which two images are near-duplicates
