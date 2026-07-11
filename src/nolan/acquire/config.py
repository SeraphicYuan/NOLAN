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
    generate_n: int = 2
    # diversity
    max_reuse: int = 3                # don't keep the same image for more than this many needs
    dedup_hamming: int = 6            # average-hash distance under which two images are near-duplicates
