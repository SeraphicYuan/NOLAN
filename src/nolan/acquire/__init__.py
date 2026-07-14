"""Multi-source asset acquisition — beat-driven, over-provisioned, relevance-ranked, fitness-gated.

The pool is the ceiling on essay quality, so it's built like a pro sources b-roll: for every need,
fan out to EVERY source (the saved library + stock/archival/museum providers), over-fetch, score
each for CLIP RELEVANCE and overlay FITNESS, de-dup semantically, keep the best, and GENERATE
originals where stock/library is thin or off-topic. Tune it all from `config.AcquireConfig`.
"""
from .config import AcquireConfig
from .engine import (Candidate, Context, acquire_need, acquire_pool,
                     avg_hash, hamming, fitness_score)
from .context import build_context, gen_style_for
from .judge import judge_prompt, extract_json, parse_verdict, is_junk, UNUSABLE_FLAGS

__all__ = [
    "AcquireConfig", "Candidate", "Context", "acquire_need", "acquire_pool",
    "avg_hash", "hamming", "fitness_score", "build_context", "gen_style_for",
    "judge_prompt", "extract_json", "parse_verdict", "is_junk", "UNUSABLE_FLAGS",
]
