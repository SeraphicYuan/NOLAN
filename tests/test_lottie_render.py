"""Tests for Lottie rendering reintroduced into the unified core."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import nolan.lottie_render as lr
from nolan.scenes import Scene


def _mock_service(video_path):
    """Patched httpx.Client for the async job API: health/status/result GETs + /render POST."""
    client = MagicMock()
    c = client.__enter__.return_value

    def get(url, **k):
        if url.endswith("/health"):
            return SimpleNamespace(status_code=200)
        if "/render/status/" in url:
            return SimpleNamespace(json=lambda: {"status": "done"})
        if "/render/result/" in url:
            return SimpleNamespace(json=lambda: {"video_path": str(video_path)})
        return SimpleNamespace(status_code=404, json=lambda: {})

    c.get.side_effect = get
    post = MagicMock()
    post.raise_for_status = lambda: None
    post.json = lambda: {"job_id": "j1", "status": "queued"}
    c.post.return_value = post
    return client, c


def test_render_lottie_to_mp4_posts_correct_body(tmp_path):
    rendered = tmp_path / "svc_out.mp4"; rendered.write_bytes(b"video")
    client, c = _mock_service(rendered)
    with patch("httpx.Client", return_value=client):
        out = lr.render_lottie_to_mp4(tmp_path / "anim.json", tmp_path / "out.mp4",
                                      duration=6.0, width=1280, height=720, fps=25)
    body = c.post.call_args.kwargs["json"]
    assert body["engine"] == "remotion"                       # current API shape
    assert body["data"]["lottie_path"].endswith("anim.json")  # data.lottie_path, not spec.type
    assert body["width"] == 1280 and body["duration"] == 6.0
    assert out.exists() and out.read_bytes() == b"video"      # copied from job result


def test_render_lottie_to_mp4_raises_when_service_unhealthy(tmp_path):
    client = MagicMock()
    client.__enter__.return_value.get.return_value = SimpleNamespace(status_code=503)
    with patch("httpx.Client", return_value=client):
        try:
            lr.render_lottie_to_mp4(tmp_path / "a.json", tmp_path / "o.mp4", duration=5)
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "unhealthy" in str(e)


def test_prepare_lottie_passes_config(tmp_path):
    with patch("nolan.lottie.customize_lottie") as cust:
        lr.prepare_lottie(tmp_path / "t.json", tmp_path / "out.json",
                          {"text": {"A": "B"}, "colors": {"#fff": "#000"}, "duration": 4, "fps": 30})
    kw = cust.call_args.kwargs
    assert kw["text_replacements"] == {"A": "B"} and kw["color_map"] == {"#fff": "#000"}
    assert kw["duration_seconds"] == 4 and kw["fps"] == 30


def test_for_scene_uses_lottie_asset(tmp_path):
    asset = tmp_path / "a.json"; asset.write_text("{}")
    s = Scene(id="g1", visual_type="text-overlay", lottie_asset=str(asset))
    with patch("nolan.lottie_render.render_lottie_to_mp4") as r:
        ok = lr.render_lottie_for_scene(s, tmp_path / "o.mp4", duration=5.0)
    assert ok and r.called


def test_for_scene_customizes_template(tmp_path):
    tmpl = tmp_path / "tmpl.json"; tmpl.write_text("{}")
    s = Scene(id="g2", visual_type="text-overlay", lottie_template=str(tmpl),
              lottie_config={"text": {"x": "y"}})
    with patch("nolan.lottie_render.prepare_lottie", return_value=tmp_path / "p.json") as prep, \
         patch("nolan.lottie_render.render_lottie_to_mp4") as r:
        ok = lr.render_lottie_for_scene(s, tmp_path / "o.mp4", duration=5.0, work_dir=tmp_path)
    assert ok and prep.called and r.called


def test_for_scene_returns_false_when_service_down(tmp_path):
    asset = tmp_path / "a.json"; asset.write_text("{}")
    s = Scene(id="g3", visual_type="text-overlay", lottie_asset=str(asset))
    with patch("nolan.lottie_render.render_lottie_to_mp4", side_effect=RuntimeError("down")):
        assert lr.render_lottie_for_scene(s, tmp_path / "o.mp4", duration=5.0) is False


def test_for_scene_none_when_no_lottie(tmp_path):
    s = Scene(id="g4", visual_type="text-overlay")
    assert lr.render_lottie_for_scene(s, tmp_path / "o.mp4", duration=5.0) is False


# render_one routes lottie scenes through the lottie branch
def test_render_one_routes_lottie(tmp_path):
    import nolan.render_dispatch as rd
    s = {"id": "g1", "lottie_asset": str(tmp_path / "a.json")}
    with patch("nolan.lottie_render.render_lottie_for_scene", return_value=True) as f:
        kind = rd.render_one(s, tmp_path / "o.mp4", duration=5.0)
    assert kind == "lottie" and f.called


def test_render_one_lottie_falls_through_when_down(tmp_path):
    import nolan.render_dispatch as rd
    s = {"id": "g1", "lottie_asset": str(tmp_path / "a.json")}  # no other asset
    with patch("nolan.lottie_render.render_lottie_for_scene", return_value=False):
        kind = rd.render_one(s, tmp_path / "o.mp4", duration=5.0)
    assert kind is None   # lottie failed, nothing else to render -> caller handles
