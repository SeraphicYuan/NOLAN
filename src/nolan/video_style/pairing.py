"""Script↔Visual pairing analysis — how the asset relates to the narration.

A good video's picture isn't always a literal illustration of the words under it;
the said↔shown *relationship* is itself a style choice (literal, conceptual/
metaphor, tonal, counterpoint, …). NOLAN can measure this directly because the
index stores, per time-aligned segment, BOTH the ``transcript`` (said) and the
``combined_summary``/``frame_description``/``inferred_context`` (shown).

Objective backbone here: the **directness** of each segment = cosine similarity
between the transcript embedding and the visual-description embedding (reusing the
same BGE model as ``vector_search``). Low directness ⇒ associative/tonal; high ⇒
literal. We aggregate into a literalness distribution and how it varies across the
arc, plus paired (said, shown) samples for the synthesis agent to characterize the
relationship types (metaphor / counterpoint / elaborative) it can't get from cosine
alone.

This dimension needs an **indexed** video (aligned transcript + descriptions).
"""

from __future__ import annotations

import json
from statistics import mean
from typing import Any, Callable, Dict, List, Optional

import numpy as np

# Heuristic directness bands (BGE cosine). Calibrated from a real indexed video
# (related said↔shown pairs cluster ~0.55–0.80 with bge-base-en), so the cut-points
# sit higher than naive intuition. Provisional — refine across more videos; the
# agent does the nuanced labelling, these only give an objective backbone.
LITERAL_MIN = 0.72
TONAL_MAX = 0.58

Embedder = Callable[[List[str]], List[List[float]]]


def make_bge_embedder() -> Embedder:
    """Lazy BGE embedder matching vector_search (BAAI/bge-base-en-v1.5)."""
    from chromadb.utils import embedding_functions
    from nolan.vector_search import EMBEDDING_MODEL
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
    return lambda texts: list(ef(list(texts)))


def _cos(a, b) -> float:
    a = np.asarray(a, dtype=float); b = np.asarray(b, dtype=float)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(np.dot(a, b) / (na * nb)) if na and nb else 0.0


def _band(score: float) -> str:
    if score >= LITERAL_MIN:
        return "literal"
    if score < TONAL_MAX:
        return "tonal/abstract"
    return "associative"


def compose_shown(seg: Dict[str, Any]) -> str:
    """Best textual representation of what's *shown* in a segment."""
    shown = (seg.get("combined_summary") or seg.get("frame_description") or "").strip()
    ctx = seg.get("inferred_context")
    if isinstance(ctx, str):
        try:
            ctx = json.loads(ctx)
        except Exception:
            ctx = None
    if isinstance(ctx, dict):
        extra = []
        if ctx.get("objects"):
            extra.append("objects: " + ", ".join(ctx["objects"][:6]))
        if ctx.get("location"):
            extra.append("location: " + str(ctx["location"]))
        if extra:
            shown = (shown + " (" + "; ".join(extra) + ")").strip()
    return shown


def _position_bucket(start: float, duration: float) -> str:
    if not duration:
        return "mid"
    r = start / duration
    return "open" if r < 1 / 3 else "close" if r >= 2 / 3 else "mid"


def analyze_pairing(segments: List[Dict[str, Any]], duration: float = 0.0,
                    embed: Optional[Embedder] = None, max_samples: int = 40,
                    snippet_chars: int = 140) -> Dict[str, Any]:
    """Compute the said↔shown coupling profile for one video.

    Returns a dict with the mean directness, the literal/associative/tonal
    distribution, how directness varies across the arc (open/mid/close), and
    paired (said, shown) samples for the synthesis agent.
    """
    # Keep only segments that have BOTH a spoken line and a visual description.
    pairs = []
    for s in segments or []:
        said = (s.get("transcript") or "").strip()
        shown = compose_shown(s)
        if said and shown:
            pairs.append((s, said, shown))
    if len(pairs) < 2:
        return {"available": False, "reason": "need >=2 segments with transcript + visual description"}

    if embed is None:
        embed = make_bge_embedder()
    # Embed said + shown in ONE batch so both live in the same vector space.
    m = len(pairs)
    all_vecs = embed([p[1] for p in pairs] + [p[2] for p in pairs])
    said_vecs, shown_vecs = all_vecs[:m], all_vecs[m:]

    rows = []
    for (seg, said, shown), sv, hv in zip(pairs, said_vecs, shown_vecs):
        d = round(_cos(sv, hv), 3)
        start = float(seg.get("timestamp_start") or 0.0)
        rows.append({
            "t": round(start, 1),
            "directness": d,
            "band": _band(d),
            "position": _position_bucket(start, duration),
            "said": said[:snippet_chars],
            "shown": shown[:snippet_chars],
        })

    n = len(rows)
    dist = {b: round(sum(1 for r in rows if r["band"] == b) / n, 3)
            for b in ("literal", "associative", "tonal/abstract")}
    by_pos = {}
    for pos in ("open", "mid", "close"):
        ds = [r["directness"] for r in rows if r["position"] == pos]
        if ds:
            by_pos[pos] = round(mean(ds), 3)

    # Sample for the agent: spread across the timeline, favouring the extremes
    # (most literal + most associative) which best illustrate the style.
    by_time = sorted(rows, key=lambda r: r["t"])
    if len(by_time) > max_samples:
        step = len(by_time) / max_samples
        by_time = [by_time[int(i * step)] for i in range(max_samples)]

    return {
        "available": True,
        "segment_count": n,
        "mean_directness": round(mean(r["directness"] for r in rows), 3),
        "distribution": dist,                       # fractions, sum≈1
        "directness_by_position": by_pos,           # arc variation
        "literalness": ("mostly-literal" if dist["literal"] >= 0.6
                        else "mostly-associative" if (dist["associative"] + dist["tonal/abstract"]) >= 0.6
                        else "mixed"),
        "samples": by_time,                         # paired said/shown for the agent
        "bands": {"literal_min": LITERAL_MIN, "tonal_max": TONAL_MAX},
    }
