"""Tests for the acquisition engine — pure orchestration with mocked organs (no real CLIP/stock/gen)."""
from pathlib import Path

import numpy as np
from PIL import Image

from nolan.acquire import (AcquireConfig, Candidate, Context, acquire_need, acquire_pool,
                           avg_hash, hamming, fitness_score)


def _patterns():
    h, w = 64, 96
    left = np.zeros((h, w), "uint8"); left[:, : w // 2] = 255
    top = np.zeros((h, w), "uint8"); top[: h // 2, :] = 255
    grad = np.tile(np.linspace(0, 255, w, dtype="uint8"), (h, 1))
    return {"left": left, "top": top, "grad": grad}


def _write(tmp: Path, pats) -> dict:
    out = {}
    for name, arr in pats.items():
        p = tmp / f"{name}.jpg"
        Image.fromarray(arr).convert("RGB").save(p)
        out[name] = p
    return out


def test_avg_hash_and_hamming(tmp_path):
    paths = _write(tmp_path, _patterns())
    ha, hb = avg_hash(paths["left"]), avg_hash(paths["top"])
    assert hamming(ha, ha) == 0
    assert hamming(ha, hb) > 0                                    # distinct patterns → distinct hashes


def test_fitness_score():
    assert fitness_score({"overlay_safe": True, "orientation": "landscape", "has_burned_text": False}) == 1.0
    assert fitness_score({"overlay_safe": True, "orientation": "landscape", "has_burned_text": True}) == 0.0
    assert fitness_score({}) == 0.6                               # unknown (video) → neutral


def test_acquire_need_keeps_top_and_generates_when_thin(tmp_path):
    paths = _write(tmp_path, _patterns())

    def search_stock(need, n):
        return [Candidate(ref=k, source="stock:x", modality="image", path=paths[k]) for k in paths]

    gen_calls = []

    def generate(prompt, out):
        Image.fromarray(_patterns()["grad"]).convert("RGB").save(out)
        gen_calls.append(prompt)
        return True

    ctx = Context(search_stock=search_stock, relevance=lambda t, p: 0.0, generate=generate)  # all off-topic
    cfg = AcquireConfig(per_need=2, over_fetch=1, min_usable=4, generate_evocative=True, generate_n=1)
    got = acquire_need({"id": "n1", "query": "idea", "queries": ["idea"], "evocative": True,
                        "gen_prompt": "a candle"}, ctx, cfg, tmp_path, [])
    assert sum(1 for c in got if c.source != "generate") <= 2     # kept ≤ per_need from stock
    assert any(c.source == "generate" for c in got)              # thin + off-topic → generated
    assert gen_calls == ["a candle"]


def test_generate_skipped_for_non_evocative(tmp_path):
    paths = _write(tmp_path, _patterns())
    ctx = Context(search_stock=lambda need, n: [Candidate(ref=k, source="stock:x", path=paths[k]) for k in paths],
                  relevance=lambda t, p: 0.0, generate=lambda pr, o: (_ for _ in ()).throw(AssertionError("gen!")))
    cfg = AcquireConfig(per_need=2, over_fetch=1, generate_evocative=True)
    got = acquire_need({"id": "n1", "query": "x", "queries": ["x"], "evocative": False}, ctx, cfg, tmp_path, [])
    assert all(c.source != "generate" for c in got)              # not evocative → never generate


def test_acquire_pool_dedups_across_needs(tmp_path):
    paths = _write(tmp_path, _patterns())
    # both needs return the SAME 'left' image → the second must dedup it (shared taken_hashes)
    ctx = Context(search_stock=lambda need, n: [Candidate(ref="left", source="stock:x", path=paths["left"])],
                  relevance=lambda t, p: 0.5)
    cfg = AcquireConfig(per_need=3, over_fetch=1, generate_evocative=False)
    got = acquire_pool([{"id": "n1", "query": "a", "queries": ["a"]},
                        {"id": "n2", "query": "b", "queries": ["b"]}], ctx, cfg, tmp_path, log=lambda *_: None)
    assert len(got) == 1                                          # the near-dup was not kept twice
