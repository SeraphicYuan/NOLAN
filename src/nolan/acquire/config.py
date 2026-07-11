"""Acquisition tuning — the numeric tweak surface. Change how DEEP, how PICKY, and how GENERATIVE
the pool is from this one place; the engine reads it."""
from dataclasses import dataclass, field
from typing import Tuple


@dataclass
class AcquireConfig:
    # depth
    per_need: int = 8                 # keep this many assets per need
    over_fetch: int = 3               # fetch per_need × over_fetch candidates, then cull to the best
    # sources (order tried; "generate" is conditional, handled by the engine)
    sources: Tuple[str, ...] = ("library", "stock")
    # relevance + fitness gating
    relevance_floor: float = 0.20     # CLIP sim below which stock is "not good enough" for a beat
    min_usable: int = 4               # escalate/generate if fewer than this survive fitness+relevance
    w_relevance: float = 1.0          # combined score weights
    w_fitness: float = 0.5
    # generation (first-class, floor-gated — only where stock/library is thin or off-topic)
    generate_evocative: bool = True   # generate for evocative beats below the relevance floor
    generate_n: int = 2
    # diversity
    max_reuse: int = 3                # don't keep the same image for more than this many needs
    dedup_hamming: int = 6            # average-hash distance under which two images are near-duplicates
