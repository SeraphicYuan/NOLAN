"""Test: script<->visual pairing analysis (no embedding model needed).

Injects a deterministic bag-of-words embedder so we can assert the banding
without downloading BGE: a literal segment (said/shown share words) scores high,
a tonal segment (disjoint words) scores ~0.

Usage:
    D:/env/nolan/python.exe scripts/test_pairing.py
"""

import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.nolan.video_style import pairing


def fake_embedder(texts):
    """TF vectors over the shared vocab — cosine reflects word overlap."""
    toks = [re.findall(r"[a-z]+", t.lower()) for t in texts]
    vocab = sorted({w for ts in toks for w in ts})
    idx = {w: i for i, w in enumerate(vocab)}
    out = []
    for ts in toks:
        v = np.zeros(len(vocab))
        for w in ts:
            v[idx[w]] += 1
        out.append(v.tolist())
    return out


def main():
    segments = [
        # literal: said & shown share most words
        {"timestamp_start": 0.0, "timestamp_end": 3.0,
         "transcript": "a bridge collapsed into the river water",
         "combined_summary": "a bridge collapsing into the river water"},
        # associative: partial overlap
        {"timestamp_start": 30.0, "timestamp_end": 33.0,
         "transcript": "the city kept growing every year",
         "combined_summary": "an aerial shot of a sprawling city skyline at dusk"},
        # tonal/abstract: disjoint vocab
        {"timestamp_start": 58.0, "timestamp_end": 61.0,
         "transcript": "the economy market finance was declining",
         "combined_summary": "a wilting flower garden sunset calm",
         "inferred_context": {"objects": ["flower", "garden"], "location": "field"}},
    ]

    res = pairing.analyze_pairing(segments, duration=60.0, embed=fake_embedder)
    print("available:", res["available"], "| n:", res["segment_count"])
    print("mean_directness:", res["mean_directness"])
    print("distribution:", res["distribution"])
    print("by_position:", res["directness_by_position"], "| literalness:", res["literalness"])
    for s in res["samples"]:
        print(f"  t={s['t']:>4} {s['band']:<14} d={s['directness']:.2f}  said='{s['said'][:30]}' shown='{s['shown'][:30]}'")

    bands = {s["t"]: s["band"] for s in res["samples"]}
    assert bands[0.0] == "literal", bands
    assert bands[58.0] == "tonal/abstract", bands
    assert res["distribution"]["literal"] > 0 and res["distribution"]["tonal/abstract"] > 0
    assert res["directness_by_position"]["open"] > res["directness_by_position"]["close"], \
        "open (literal) should be more direct than close (tonal)"
    # inferred_context objects/location should enrich the 'shown' text
    assert "flower" in [s for s in res["samples"] if s["t"] == 58.0][0]["shown"]
    print("\nbanding + arc variation + context-enrichment OK")

    # too-few-pairs guard
    g = pairing.analyze_pairing([{"transcript": "x", "combined_summary": "y"}], embed=fake_embedder)
    assert g["available"] is False
    print("insufficient-data guard OK")
    print("\nOK - pairing analysis verified.")


if __name__ == "__main__":
    main()
