"""`pool._probe_dims` must actually read dimensions — the LOW-RES menu tag depends on it.

REGRESSION: the first implementation derived an ffprobe path by name-swapping the bundled ffmpeg
(`ffmpeg-win-*.exe` -> `ffprobe-win-*.exe`). imageio_ffmpeg ships NO ffprobe, so every call raised
FileNotFoundError, the broad `except` swallowed it, and every clip stayed 0x0 — the tag silently never
fired. Exactly the silent cap the feature exists to remove, so it gets a test that runs a real file.
"""
import subprocess
import sys
from pathlib import Path

import pytest

BRIDGE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"


def _pool_module():
    sys.path.insert(0, str(BRIDGE))
    try:
        import pool
        return pool
    finally:
        sys.path.pop(0)


def _ffmpeg():
    try:
        from nolan.hf_qa import _ffmpeg as ff
        return ff()
    except Exception:
        return None


@pytest.mark.parametrize("w,h", [(320, 240), (1280, 720)])
def test_probe_reads_real_dimensions(tmp_path, w, h):
    ff = _ffmpeg()
    if not ff:
        pytest.skip("no ffmpeg available")
    clip = tmp_path / f"{w}x{h}.mp4"
    r = subprocess.run([ff, "-y", "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:d=1",
                        "-pix_fmt", "yuv420p", str(clip)], capture_output=True)
    if not clip.exists():
        pytest.skip(f"ffmpeg could not synthesize a test clip: {r.stderr[-200:]!r}")
    assert _pool_module()._probe_dims(clip) == (w, h)


def test_probe_returns_zeroes_for_a_non_video(tmp_path):
    bogus = tmp_path / "not-a-video.mp4"
    bogus.write_bytes(b"definitely not an mp4")
    assert _pool_module()._probe_dims(bogus) == (0, 0)


def test_probe_does_not_depend_on_a_separate_ffprobe_binary():
    """The bundled ffmpeg is the ONLY binary we can count on — guard the name-swap from coming back."""
    src = (BRIDGE / "pool.py").read_text(encoding="utf-8")
    fn = src[src.index("def _probe_dims"):src.index("def _video_still")]
    assert "ffprobe" not in fn.replace("NOT ffprobe", "")
