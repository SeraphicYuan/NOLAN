"""`hf-finish --render auto` — whole on a cold comp, incremental once a build exists.

The two modes are not rivals: they are FIRST build vs every build after. Defaulting to `whole` forever
meant the diamond-v2 run re-rendered all 9 frames three times (the last pass had 3 changed frames), and
left `compositions/frames/*.clip.mp4` never produced — so `/hyperframes` had no cached per-frame video
and re-rendered each frame on demand. Incremental emits those clips as a side effect, which is the
wiring that makes the edit loop cheap.
"""
import json

import pytest

from nolan.hyperframes.finish import resolve_render_mode


def _cold(tmp_path):
    (tmp_path / "renders").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _built(tmp_path):
    _cold(tmp_path)
    (tmp_path / "renders" / "video.mp4").write_bytes(b"x")
    cache = tmp_path / "compositions" / "_preview"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "clip_cache.json").write_text(json.dumps({"01-a": "sig"}), encoding="utf-8")
    return tmp_path


def test_auto_on_a_cold_comp_renders_whole(tmp_path):
    assert resolve_render_mode(_cold(tmp_path), "auto") == "whole"


def test_auto_after_a_build_goes_incremental(tmp_path):
    assert resolve_render_mode(_built(tmp_path), "auto") == "incremental"


def test_a_build_without_its_clip_cache_is_not_reusable(tmp_path):
    """renders/video.mp4 from a WHOLE render leaves no per-frame clips — nothing to reuse, so stay whole."""
    _cold(tmp_path)
    (tmp_path / "renders" / "video.mp4").write_bytes(b"x")
    assert resolve_render_mode(tmp_path, "auto") == "whole"


def test_a_clip_cache_without_a_build_is_not_enough(tmp_path):
    cache = tmp_path / "compositions" / "_preview"
    cache.mkdir(parents=True)
    (cache / "clip_cache.json").write_text("{}", encoding="utf-8")
    assert resolve_render_mode(tmp_path, "auto") == "whole"


@pytest.mark.parametrize("explicit", ["whole", "incremental"])
def test_an_explicit_mode_is_never_overridden(tmp_path, explicit):
    assert resolve_render_mode(_built(tmp_path), explicit) == explicit
    assert resolve_render_mode(_cold(tmp_path), explicit) == explicit


def test_auto_is_the_default_everywhere_it_is_declared():
    """Signature and CLI must agree — a default that differs between them is how modes drift."""
    import inspect

    from nolan.hyperframes import finish as F
    assert inspect.signature(F.finish).parameters["render_mode"].default == "auto"
    src = inspect.getsource(F.main)
    assert 'default="auto"' in src and '"auto", "whole", "incremental"' in src


def test_incremental_emits_the_clips_the_edit_loop_serves():
    """The wiring claim: what incremental writes is exactly what frame_video_path looks for."""
    import inspect

    from nolan.hyperframes import edit, incremental
    assert ".clip.mp4" in inspect.getsource(incremental.render_incremental)
    assert ".clip.mp4" in inspect.getsource(edit.frame_video_path)
