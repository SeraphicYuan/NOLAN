"""Tests for nolan.pool_curation — orientation, overlay-safety (flat vs busy), thinness, routing."""
import numpy as np

from nolan import pool_curation as pc


def test_orientation():
    assert pc.orientation((1920, 1080)) == ("landscape", 1.78)
    assert pc.orientation((1080, 1920))[0] == "portrait"
    assert pc.orientation((1000, 1000))[0] == "square"


def test_overlay_safety_flat_vs_noisy():
    flat = np.full((400, 600), 0.5, dtype="float32")                 # a calm, flat ground
    noisy = np.random.default_rng(0).random((400, 600)).astype("float32")   # a busy wire-pile
    fs, ns = pc.overlay_safety(flat), pc.overlay_safety(noisy)
    assert fs["overlay_safe"] is True and ns["overlay_safe"] is False
    assert fs["overall_detail"] < ns["overall_detail"]
    assert len(fs["safe_rect"]) == 4


def test_thinness_flags_undersupply():
    pool = [{"media_type": "image", "overlay_safe": True, "orientation": "landscape"},
            {"media_type": "image", "overlay_safe": False, "orientation": "landscape"},
            {"media_type": "image", "overlay_safe": True, "orientation": "portrait"},
            {"media_type": "video"}]
    t = pc.thinness(pool, grounded_beats=5)
    assert t["n_images"] == 3 and t["overlay_safe_landscapes"] == 1
    assert t["thin"] is True                                          # 1 clean landscape < 5 grounded beats


def test_best_asset_prefers_clean_safe_landscape():
    cands = [
        {"id": "busy", "overlay_safe": False, "orientation": "landscape", "has_burned_text": False, "overall_detail": 0.3},
        {"id": "good", "overlay_safe": True, "orientation": "landscape", "has_burned_text": False, "overall_detail": 0.05},
        {"id": "burned", "overlay_safe": True, "orientation": "landscape", "has_burned_text": True, "overall_detail": 0.05},
    ]
    assert pc.best_asset(cands, "ground")["id"] == "good"             # burned text is disqualifying
