"""Tests for the style-contract spine — metrics, the dimension registry (5 gates + advisory),
presets/dials, dual-compile, linter, adapter, block-family honesty vs the catalog, and the
reference-fingerprint round-trip.
"""
import json
from pathlib import Path

import pytest

from nolan.style_contract import (
    SceneView, StyleContract, DIMENSIONS, GATES, ADVISORY, BLOCK_FAMILY, measure, lint,
    scenes_from_hf, fingerprint, contract_from_fingerprint,
    palette_brief, authoring_brief, catalog_blocks,
)

REPO = Path(__file__).resolve().parents[1]
CATALOG = REPO / "render-service" / "_lab_hyperframes" / "bridge" / "catalog.json"


def _sv(frame, sid, block, dur, media="none", register="paper", first=False, nums=0):
    return SceneView(frame_id=frame, scene_id=sid, block=block, dur=dur, media=media,
                     register=register, first_in_frame=first, num_count=nums)


def _v1_like():
    """A statement-heavy, near-zero-asset, uniform-pacing essay — the v1 shape."""
    scenes = []
    plan = [("statement", 21), ("stat", 6), ("comparison", 5), ("geo", 2), ("newshead", 2), ("diagram", 1)]
    i = 0
    for block, n in plan:
        for _ in range(n):
            media = "image" if (block == "comparison" and i % 2 == 0) else "none"
            scenes.append(_sv(f"f{i//5}", f"s{i}", block, 13.0, media=media, first=(i % 5 == 0)))
            i += 1
    return scenes


def test_registry_is_lean():
    assert len(GATES) == 4                                        # few hard gates (pacing is now advisory)
    assert {g.key for g in GATES} == {"coverage", "video_share",
                                      "layout_max_share", "layout_max_run"}
    assert "layout_entropy" not in {d.metric for d in DIMENSIONS}  # the misleading metric was cut
    assert all(d.mode == "advisory" for d in ADVISORY)


def test_measure_core_metrics():
    m = measure(_v1_like())
    assert m["n_scenes"] == 37
    assert abs(m["layout_max_share"] - 21 / 37) < 0.01           # statement dominates
    assert m["pacing_cv"] == 0.0                                  # uniform durations
    assert m["coverage"] < 0.15
    assert "layout_entropy" not in m


def test_scene_media_by_block_rules():
    from nolan.style_contract import scene_media
    # comparison = union of the two sides
    assert scene_media("comparison", {"left": {"type": "video", "src": "a.mp4"}, "right": {"type": "text"}}) == "video"
    assert scene_media("comparison", {"left": {"type": "image", "src": "a.jpg"}, "right": {"type": "stat"}}) == "image"
    assert scene_media("comparison", {"left": {"type": "text"}, "right": {"type": "stat"}}) == "none"
    # ground-honoring blocks
    assert scene_media("statement", {"ground": {"kind": "image", "src": "a.jpg"}}) == "image"
    assert scene_media("statement", {"ground": {"kind": "video", "src": "a.mp4"}}) == "video"
    assert scene_media("statement", {"lines": ["hi"]}) == "none"
    # newshead ignores a video ground (renders blank) -> none; honors an explicit image
    assert scene_media("newshead", {"ground": {"kind": "video", "src": "a.mp4"}}) == "none"
    assert scene_media("newshead", {"image": "a.jpg"}) == "image"
    # always-image + pure-data blocks (the false-positive fix: a stat's number is NOT an asset)
    assert scene_media("gallery", {"images": ["a.jpg"]}) == "image"
    assert scene_media("chart", {"series": [1, 2]}) == "none"
    assert scene_media("stat", {"items": [{"value": 5}]}) == "none"


def test_media_diversity_and_reuse_metrics():
    from nolan.style_contract import scene_asset_srcs
    assert scene_asset_srcs("statement", {"ground": {"kind": "image", "src": "a.jpg"}}) == ["a.jpg"]
    assert scene_asset_srcs("comparison", {"left": {"type": "video", "src": "v.mp4"}, "right": {"type": "text"}}) == ["v.mp4"]
    assert scene_asset_srcs("chart", {"series": [1]}) == []
    # one asset reused across 3 of 4 grounded scenes
    scenes = [SceneView("f", f"s{i}", "statement", 5.0, media="image", srcs=["same.jpg"]) for i in range(3)]
    scenes.append(SceneView("f", "s3", "statement", 5.0, media="image", srcs=["other.jpg"]))
    m = measure(scenes)
    assert m["max_asset_reuse"] == 3 and m["distinct_assets"] == 2
    assert abs(m["media_diversity"] - 0.5) < 0.01                 # 2 distinct / 4 grounded


def test_contract_resolve_dials_and_aliases():
    c = StyleContract.resolve("essay", asset_density="dense")
    assert c.targets["coverage"] == (0.6, 0.95)                   # dial alias -> coverage dense level
    c2 = StyleContract.resolve("essay", video_share=(0.1, 0.6))   # raw (lo,hi) override
    assert c2.targets["video_share"] == (0.1, 0.6)
    with pytest.raises(ValueError):
        StyleContract.resolve("essay", chart_density="high")     # dataviz is advisory -> not a dial
    with pytest.raises(ValueError):
        StyleContract.resolve("no-such-preset")


def test_compile_brief_gates_and_advisory():
    brief = StyleContract.resolve("essay", asset_density="dense").compile_brief()
    assert "MUST HIT" in brief and "ALSO WATCH" in brief
    assert "Evidence coverage" in brief and "Pacing variance" in brief
    assert "60%–95%" in brief                                     # dialed coverage range, formatted
    assert "Density is not monotonic" in brief


def test_linter_flags_the_v1_problems():
    rep = lint(_v1_like(), StyleContract.resolve("essay", asset_density="dense"))
    fails = {f["key"] for f in rep["failures"]}
    assert not rep["overall_pass"]
    assert fails == {"coverage", "video_share", "layout_max_share", "layout_max_run"}
    # advisory dimensions are reported but never counted as failures
    assert all(d["mode"] == "advisory" and d["ok"] for d in rep["dimensions"] if d["mode"] == "advisory")


def test_linter_passes_a_balanced_varied_essay():
    blocks = ["comparison", "statement", "stat", "collage", "geo", "newshead", "gallery", "chart",
              "comparison", "statement", "diagram", "collage"]
    durs = [4, 13, 6, 16, 3, 10, 5, 14, 7, 12, 4, 11]            # cv ~0.49
    scenes = []
    for i, (b, d) in enumerate(zip(blocks, durs)):
        media = "video" if b in ("gallery", "collage") and i % 3 == 0 else \
            ("image" if b in ("comparison", "collage", "newshead", "gallery") else "none")
        scenes.append(_sv(f"f{i//3}", f"s{i}", b, float(d), media=media,
                          register=("footage" if i % 2 else "paper"), first=(i % 3 == 0)))
    rep = lint(scenes, StyleContract.resolve("essay", asset_density="balanced"))
    assert rep["overall_pass"], rep["failures"]


def test_block_family_covers_the_catalog():
    """Every catalog block must have a family — else layout/data-viz metrics silently miss it."""
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    missing = set(cat.get("scene_templates", {})) - set(BLOCK_FAMILY)
    assert not missing, f"blocks in catalog with no style-contract family (stale): {missing}"


def test_scenes_from_hf_adapter(tmp_path):
    fdir = tmp_path / "compositions" / "frames"
    fdir.mkdir(parents=True)
    (fdir / "01-a.spec.json").write_text(json.dumps({"frames": [{"id": "01-a", "dur": 20, "scenes": [
        {"id": "s1", "type": "comparison", "start": 0, "dur": 10,
         "data": {"left": {"type": "image", "src": "assets/x.jpg"}, "right": {"type": "text"}}},
        {"id": "s2", "type": "statement", "start": 10, "dur": 10,
         "data": {"lines": ["hello world"], "register": "paper"}},
    ]}]}), encoding="utf-8")
    scenes = scenes_from_hf(tmp_path)
    assert len(scenes) == 2
    assert scenes[0].block == "comparison" and scenes[0].media == "image" and scenes[0].first_in_frame
    assert scenes[1].media == "none" and scenes[1].words >= 2


def test_palette_brief_covers_full_menu_and_routing():
    pb = palette_brief()
    blocks = catalog_blocks()
    assert len(blocks) >= 15
    for b in ("chart", "timeline", "gallery", "statement", "comparison"):
        assert f"- {b}:" in pb                                   # every block listed, incl. the long tail
    assert "BEAT → BLOCK routing" in pb and "TREND" in pb        # the shape→block discipline


def test_authoring_brief_combines_targets_and_palette():
    brief = authoring_brief(StyleContract.resolve("essay", asset_density="dense"))
    assert "MUST HIT" in brief and "FULL BLOCK PALETTE" in brief  # craft targets + the menu together


def test_distinct_blocks_metric_is_palette_coverage():
    assert measure(_v1_like())["distinct_blocks"] == 6           # v1 touched only 6 of the 17 blocks


def test_reference_fingerprint_roundtrips():
    scenes = _v1_like()
    fp = fingerprint(scenes)
    assert set(fp) == {d.key for d in DIMENSIONS}
    rep = lint(scenes, contract_from_fingerprint(scenes, "self"))
    assert rep["overall_pass"], rep["failures"]                  # a reference accepts itself
