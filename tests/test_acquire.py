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


def test_source_rank_tiers():
    from nolan.acquire.engine import source_rank
    assert source_rank("art", "stock:artvee") < source_rank("art", "stock:ddgs")        # art: artvee beats web
    assert source_rank("general", "library") == 0                                        # library ranks first
    assert source_rank("archival", "stock:archive") < source_rank("archival", "stock:pexels_video")


def test_evocative_ranks_by_tier_concrete_by_relevance(tmp_path):
    paths = _write(tmp_path, _patterns())

    def search_stock(need, n):
        return [Candidate(ref="lit", source="stock:ddgs", modality="image", path=paths["left"]),
                Candidate(ref="art", source="stock:artvee", modality="image", path=paths["top"])]
    # ddgs image scores HIGH on literal relevance, artvee LOW
    ctx = Context(search_stock=search_stock, relevance=lambda t, p: 0.5 if "left" in str(p) else 0.1)
    cfg = AcquireConfig(per_need=1, over_fetch=1, generate_evocative=False)

    ev = acquire_need({"id": "n", "query": "consent", "queries": ["consent"], "evocative": True,
                       "category": "art"}, ctx, cfg, tmp_path, [])
    assert ev[0].source == "stock:artvee"        # evocative → curated tier wins DESPITE lower CLIP

    co = acquire_need({"id": "n2", "query": "server", "queries": ["server"], "evocative": False,
                       "category": "general"}, ctx, cfg, tmp_path, [])
    assert co[0].source == "stock:ddgs"          # concrete → literal relevance wins


def test_library_gate_drops_offdomain(tmp_path):
    paths = _write(tmp_path, _patterns())
    # library returns a hit, but CLIP says it's off-domain (below library_min_relevance) — must be culled,
    # else a global cross-project store (e.g. medieval woodcuts) floods every beat at tier-0.
    ctx = Context(search_library=lambda q, n: [Candidate(ref="lib", source="library", path=paths["left"])],
                  relevance=lambda t, p: 0.10)
    cfg = AcquireConfig(per_need=3, over_fetch=1, library_min_relevance=0.24, generate_evocative=False)
    got = acquire_need({"id": "n", "query": "x", "queries": ["x"], "evocative": True, "category": "general"},
                       ctx, cfg, tmp_path, [])
    assert all(c.source != "library" for c in got)


def test_stock_floor_but_curated_exempt(tmp_path):
    paths = _write(tmp_path, _patterns())

    def search_stock(need, n):
        return [Candidate(ref="junk", source="stock:pexels", path=paths["left"]),   # generic web stock
                Candidate(ref="art", source="stock:artvee", path=paths["top"])]      # curated art
    ctx = Context(search_stock=search_stock, relevance=lambda t, p: 0.10)            # BOTH low relevance
    cfg = AcquireConfig(per_need=3, over_fetch=1, stock_relevance_floor=0.20, generate_evocative=False)
    got = acquire_need({"id": "n", "query": "x", "queries": ["x"], "evocative": True, "category": "art"},
                       ctx, cfg, tmp_path, [])
    srcs = {c.source for c in got}
    assert "stock:pexels" not in srcs        # generic stock below floor → dropped (literal-keyword junk)
    assert "stock:artvee" in srcs            # curated art exempt → kept despite low literal relevance (ART beat)

    # …but on a GENERAL beat, a museum piece is as off-topic as anything — the exemption must NOT apply
    gen = acquire_need({"id": "n2", "query": "x", "queries": ["x"], "evocative": True, "category": "general"},
                       ctx, cfg, tmp_path, [])
    assert "stock:artvee" not in {c.source for c in gen}   # museum art floored on a general-category beat


def test_acquire_pool_dedups_across_needs(tmp_path):
    paths = _write(tmp_path, _patterns())
    # both needs return the SAME 'left' image → the second must dedup it (shared taken_hashes)
    ctx = Context(search_stock=lambda need, n: [Candidate(ref="left", source="stock:x", path=paths["left"])],
                  relevance=lambda t, p: 0.5)
    cfg = AcquireConfig(per_need=3, over_fetch=1, generate_evocative=False)
    got = acquire_pool([{"id": "n1", "query": "a", "queries": ["a"]},
                        {"id": "n2", "query": "b", "queries": ["b"]}], ctx, cfg, tmp_path, log=lambda *_: None)
    assert len(got) == 1                                          # the near-dup was not kept twice
