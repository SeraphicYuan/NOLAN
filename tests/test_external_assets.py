"""Tests for the shared external-asset finder (P2)."""

from types import SimpleNamespace
from unittest.mock import patch

import nolan.external_assets as ea
from nolan.scenes import Scene


def test_build_query_variants_broadens():
    s = Scene(id="x", search_query="Berlin Wall 1989 protest",
              visual_description="crowds at a concrete wall at night")
    v = ea.build_query_variants(s)
    assert v[0] == "Berlin Wall 1989 protest"          # original first
    assert any("1989" not in x and "Berlin" not in x for x in v[1:])  # a broadened variant
    assert all(isinstance(x, str) and x for x in v)


def _scorer(score):
    sc = SimpleNamespace()
    sc.calculate_quality_score = lambda c: (5.0, "ok")
    def score_results(cands, q, context=None):
        for c in cands:
            c.score = score
        return cands
    sc.score_results = score_results
    return sc


def _cand(media_type, url="http://x/a", source="wikimedia"):
    return SimpleNamespace(media_type=media_type, url=url, source=source, quality_score=None,
                           score=None, thumbnail_url=None, preview_image_url=None,
                           source_url="http://x/page", title="t", license="CC0", duration=6.0)


def test_external_video_attaches_matched_clip(tmp_path):
    scene = Scene(id="v1", visual_type="b-roll", search_query="trench")
    client = SimpleNamespace()
    client.search_assets = lambda q, **k: [_cand("video")] if k.get("media_type") == "video" else []
    client.resolve_video = lambda best: SimpleNamespace(
        url="http://x/clip.mp4", source="pexels_video", source_url="p", title="t",
        license="CC0", duration=6.0, preview_image_url="th", thumbnail_url="th")

    kind = ea.external_match_for_scene(
        scene, client=client, scorer=_scorer(8.0), vid_sources=["pexels_video"],
        out_dir=tmp_path, project_root=tmp_path, prefer_video=True, gate=4)
    assert kind.startswith("video:") and scene.matched_clip["external"] and not scene.matched_asset


def test_external_image_downloads_and_sets_matched_asset(tmp_path):
    scene = Scene(id="i1", visual_type="b-roll", search_query="map")
    client = SimpleNamespace()
    client.search_assets = lambda q, **k: [] if k.get("media_type") == "video" else [_cand("image")]
    client.resolve_video = lambda b: None

    with patch("httpx.get", return_value=SimpleNamespace(content=b"\x89PNG\r\n\x1a\n")):
        kind = ea.external_match_for_scene(
            scene, client=client, scorer=_scorer(7.0), vid_sources=[],
            out_dir=tmp_path / "broll", project_root=tmp_path, prefer_video=True, gate=4)
    assert kind.startswith("image:")
    assert scene.matched_asset == "broll/i1.jpg" and (tmp_path / "broll" / "i1.jpg").exists()
    assert not scene.matched_clip


def test_external_below_gate_returns_none(tmp_path):
    scene = Scene(id="x", visual_type="b-roll", search_query="q")
    client = SimpleNamespace()
    client.search_assets = lambda q, **k: [_cand("image")]
    client.resolve_video = lambda b: None
    kind = ea.external_match_for_scene(
        scene, client=client, scorer=_scorer(2.0), vid_sources=[],   # below gate 4
        out_dir=tmp_path, project_root=tmp_path, gate=4)
    assert kind is None and not scene.matched_asset and not scene.matched_clip


def test_external_no_candidates_returns_none(tmp_path):
    scene = Scene(id="x", visual_type="b-roll", search_query="q")
    client = SimpleNamespace(search_assets=lambda q, **k: [], resolve_video=lambda b: None)
    assert ea.external_match_for_scene(scene, client=client, scorer=_scorer(9.0),
                                       vid_sources=[], out_dir=tmp_path,
                                       project_root=tmp_path, gate=4) is None
