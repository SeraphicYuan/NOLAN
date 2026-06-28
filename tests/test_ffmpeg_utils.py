"""Tests for shared ffmpeg helpers (pipeline consolidation P1)."""

from types import SimpleNamespace
from unittest.mock import patch

import nolan.ffmpeg_utils as fu


def _ok(*a, **k):
    return SimpleNamespace(returncode=0, stderr="", stdout="")


def test_uses_bundled_ffmpeg():
    assert "ffmpeg" in fu.FFMPEG.lower()
    # bundled imageio_ffmpeg binary is an absolute path, not bare "ffmpeg"
    assert fu.FFMPEG not in ("ffmpeg", "ffmpeg.exe")


def test_normalize_vf():
    vf = fu.normalize_vf(1920, 1080, 30)
    assert "scale=1920:1080:force_original_aspect_ratio=decrease" in vf
    assert "pad=1920:1080" in vf and "fps=30" in vf
    assert "fade" not in vf
    vf2 = fu.normalize_vf(1280, 720, 25, fade=0.4, duration=6.0)
    assert "fade=t=in:st=0:d=0.4" in vf2 and "fade=t=out:st=5.600:d=0.4" in vf2


def test_extract_subclip_builds_bundled_normalized_cmd(tmp_path):
    captured = {}

    def cap(cmd, **kw):
        captured["cmd"] = cmd
        return _ok()

    with patch.object(fu.subprocess, "run", side_effect=cap):
        out = fu.extract_subclip("src.mp4", 12.5, 6.0, tmp_path / "o.mp4", fade=0.4)
    cmd = captured["cmd"]
    assert cmd[0] == fu.FFMPEG                  # bundled binary, not bare "ffmpeg"
    assert "-ss" in cmd and "12.5" in cmd
    assert "-t" in cmd and "6.000" in cmd
    assert any("scale=1920:1080" in str(c) for c in cmd)   # normalized for assemble
    assert "-an" in cmd                          # audio dropped
    assert str(out).endswith("o.mp4")


def test_silent_audio_builds_bundled_cmd(tmp_path):
    captured = {}

    def cap(cmd, **kw):
        captured["cmd"] = cmd
        return _ok()

    with patch.object(fu.subprocess, "run", side_effect=cap):
        fu.silent_audio(3.0, tmp_path / "s.wav")
    cmd = captured["cmd"]
    assert cmd[0] == fu.FFMPEG
    assert "anullsrc=channel_layout=stereo:sample_rate=48000" in cmd
    assert "3.000" in cmd and "pcm_s16le" in cmd


def test_failure_raises():
    bad = SimpleNamespace(returncode=1, stderr="boom", stdout="")
    with patch.object(fu.subprocess, "run", return_value=bad):
        try:
            fu.silent_audio(1.0, "x.wav")
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "boom" in str(e)


def test_callers_delegate_to_shared_helpers():
    # segment + orchestrator both route b-roll/silent-audio through ffmpeg_utils now
    import nolan.segment.render as seg
    from nolan.orchestrator import render as orch
    captured = []

    def cap(cmd, **kw):
        captured.append(cmd)
        return _ok()

    with patch.object(fu.subprocess, "run", side_effect=cap):
        orch.generate_silent_audio(2.0, "s.wav")
    assert captured and captured[0][0] == fu.FFMPEG   # orchestrator now uses bundled ffmpeg
