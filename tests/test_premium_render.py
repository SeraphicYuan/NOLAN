"""Premium render mode — timing normalization + word-sync step building.

Pure-logic tests (no whisper/node): pin the wav-authoritative window
normalization and the words→step-frames mapping that drives block reveals.
"""

import subprocess
import wave

import pytest

from nolan.premium_render import _step_words, build_section_job


def _sine_wav(path, seconds):
    try:
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ff = "ffmpeg"
    subprocess.run([ff, "-y", "-v", "quiet", "-f", "lavfi",
                    "-i", f"sine=frequency=440:duration={seconds}",
                    "-ar", "44100", str(path)], check=True)
    return path


# --- _step_words -------------------------------------------------------------

WORDS = [
    {"t0": 0.2, "t1": 0.5, "text": "arma"},
    {"t0": 0.6, "t1": 1.0, "text": "virumque"},
    {"t0": 1.1, "t1": 1.4, "text": "cano"},
    {"t0": 4.2, "t1": 4.6, "text": "troiae"},
]


def test_step_words_window_and_relative_frames():
    words, reveals = _step_words(WORDS, 0.0, 4.0, fps=30, frames=120)
    assert [w["text"] for w in words] == ["arma", "virumque", "cano"]
    assert words[0]["startFrame"] == 6          # 0.2s * 30
    assert words[0]["endFrame"] == 15
    assert reveals[0] == 6                      # content lands on first word


def test_step_words_second_window_rebased():
    words, reveals = _step_words(WORDS, 4.0, 8.0, fps=30, frames=120)
    assert [w["text"] for w in words] == ["troiae"]
    assert words[0]["startFrame"] == 6          # (4.2 - 4.0) * 30
    assert reveals == [6, 6]


def test_step_words_empty():
    words, reveals = _step_words([], 0.0, 4.0, fps=30, frames=120)
    assert words == [] and reveals == []


def test_step_words_clamped_to_step():
    words, _ = _step_words([{"t0": -0.5, "t1": 0.2, "text": "early"},
                            {"t0": 3.9, "t1": 4.8, "text": "late"}],
                           0.0, 4.0, fps=30, frames=120)
    assert words[0]["startFrame"] == 0
    assert words[-1]["endFrame"] == 120


# --- build_section_job (wav is the timing authority) --------------------------

def test_section_job_normalizes_windows_to_wav(tmp_path):
    wav = _sine_wav(tmp_path / "sec.wav", 8.0)
    # plan windows claim 16s for this section — the 8s wav must win
    scenes = [
        {"id": "s1", "visual_type": "text-overlay", "start_seconds": 100.0,
         "end_seconds": 108.0,
         "layout_spec": {"template": "quote", "params": {"quote": "a"}}},
        {"id": "s2", "visual_type": "text-overlay", "start_seconds": 108.0,
         "end_seconds": 116.0,
         "layout_spec": {"template": "quote", "params": {"quote": "b"}}},
    ]
    job = build_section_job("t", scenes, project_path=tmp_path, section_wav=wav,
                            section_start=100.0, out_name="x.mp4",
                            work_dir=tmp_path / "w", fps=30)
    frames = [s["durationInFrames"] for s in job["props"]["steps"]]
    assert sum(frames) == 240                   # exactly 8s * 30fps
    assert frames == [120, 120]
    # audio slices tile the wav exactly
    for s, expected in zip(job["props"]["steps"], (4.0, 4.0)):
        with wave.open(s["audioSrc"], "rb") as w:
            assert abs(w.getnframes() / w.getframerate() - expected) < 0.06


def test_section_job_carries_words_and_reveals(tmp_path):
    wav = _sine_wav(tmp_path / "sec.wav", 4.0)
    scenes = [{"id": "s1", "visual_type": "text-overlay", "start_seconds": 0.0,
               "end_seconds": 4.0,
               "layout_spec": {"template": "quote", "params": {"quote": "a"}}}]
    words = [{"t0": 0.5, "t1": 0.9, "text": "hello"}]
    job = build_section_job("t", scenes, project_path=tmp_path, section_wav=wav,
                            section_start=0.0, out_name="x.mp4",
                            work_dir=tmp_path / "w", fps=30,
                            section_words=words)
    step = job["props"]["steps"][0]
    assert step["words"] == [{"text": "hello", "startFrame": 15, "endFrame": 27}]
    assert step["revealFrames"] == [15, 15]
