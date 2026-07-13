"""Seamless boomerang freeze-heal (bridge/assemble_media.py) — holbein POST_MORTEM #7.

A video ground shorter than its scene window used to be slow-mo'd (looks sluggish for atmospheric
b-roll) or hard-looped (jump-cut). It now boomerang-loops (forward + reverse, seamless) to fill any
window. This locks the freeze contract: the healed clip is at least as long as the window.
"""
import importlib.util
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ASSEMBLE = REPO / "render-service" / "_lab_hyperframes" / "bridge" / "assemble_media.py"


def _ff():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _assemble_media():
    spec = importlib.util.spec_from_file_location("assemble_media", ASSEMBLE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_boomerang_heal_fills_the_window(tmp_path):
    ff = _ff()
    if not ff:
        pytest.skip("no ffmpeg")
    from nolan.hf_qa import probe
    comp = tmp_path / "comp"
    (comp / "assets").mkdir(parents=True)
    clip = comp / "assets" / "clouds.mp4"
    # a moving 3s clip (testsrc moves, so reverse/concat is meaningful) at a size that clears the
    # heal's 20KB sanity threshold
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=24", "-t", "3",
                    "-pix_fmt", "yuv420p", str(clip)], capture_output=True)
    if probe(clip).duration < 2.5:
        pytest.skip("test clip did not encode")

    am = _assemble_media()
    clips = [{"src": "assets/clouds.mp4", "duration": 7.0}]     # window 7s > clip 3s -> heal
    am.heal_video_freezes(comp, clips)

    healed = comp / clips[0]["src"]
    assert healed.name.endswith(".filled.mp4")                 # src was repointed at the healed clip
    assert probe(healed).duration + 0.15 >= 7.0                # fills the window (no freeze)
