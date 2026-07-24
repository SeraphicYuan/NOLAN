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
    clip_seconds: int = 30            # fetch only a SHORT segment of each video (via ffmpeg range-seek) — b-roll
                                      # needs 5-30s, not a full 21-minute archive.org film. 30 (was 20) gives a
                                      # contemplative atmospheric hold headroom so it fits the window without a
                                      # freeze-heal; longer windows still fall back to the seamless loop (#7)
    # sources (order tried; "generate" is conditional, handled by the engine)
    # clips_library = the LOCAL video library (VideoIndex + vector store). Rich per-clip
    # description/transcript/people/location drive SEMANTIC retrieval (the beat's meaning → the
    # footage that means the same), and matched clips rank just below the saved image library.
    # NOTE: the segment text-embedding compresses cosine into a narrow high band (~0.65-0.77 for
    # anything), so `clip_lib_min_sim` is only a cheap tail-trim, NOT a topic gate — cross-topic
    # discrimination is the job of the downstream VLM video cull (it judges real frames) + the
    # compose-first author selecting per beat. Set it opt-out via `sources` for a project where the
    # library is irrelevant and you don't want the trims/cull cost.
    sources: Tuple[str, ...] = ("clips_library", "transcript_lib", "library", "stock")
    # local clips-library depth (bounds the ffmpeg trims — video is expensive)
    clip_lib_max: int = 4             # keep at most this many local library clips per need
    clip_lib_min_sim: float = 0.55    # drop the weak tail below this similarity (a floor, not a topic gate)
    clip_lib_relevance_floor: float = 0.20  # CULL CASCADE: a cheap CLIP frame-relevance floor for library
                                      # clips, applied in the engine BEFORE the expensive VLM — the segment
                                      # text-embedding can't discriminate topic (compressed band), but CLIP
                                      # image-text on the actual frame can, so off-topic library clips are
                                      # dropped here instead of burning a VLM filmstrip call to reject them
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
    # VLM usability FLOOR (fused with the caption pass) — the semantic cull CLIP can't do: it kills the
    # 0.20–0.25 borderline junk (a sports car for "permit") + watermark/overlaid-text/stock-graphic stills.
    # A FLOOR, not a re-ranker. Contained: VLM down → neutral verdict → asset kept (cheap gates still apply).
    vlm_cull: bool = True             # run the score+caption judge and drop junk (set False to skip the VLM)
    vlm_floor: float = 4.0            # 0-10; drop non-generated images the editor scores below this as b-roll
    # diversity
    max_reuse: int = 3                # don't keep the same image for more than this many needs
    dedup_hamming: int = 6            # average-hash distance under which two images are near-duplicates
