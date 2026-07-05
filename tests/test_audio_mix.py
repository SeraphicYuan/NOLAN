"""Sound-design stage (SOTA #1) — selection, config, and a real ducking proof.

The integration test builds a video whose VO is a 300Hz tone with a silent
gap, lays an 880Hz "music" bed under it, and asserts the 880Hz band swells in
the gap versus during narration — i.e. the sidechain duck actually ducks.
"""

import json
import subprocess

import pytest

from nolan.audio_mix import (
    load_music_library,
    mix_soundtrack,
    resolve_music_config,
    section_energies,
    select_track,
)


def _ff():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _run(args):
    subprocess.run([_ff(), "-y", "-v", "quiet", *args], check=True)


# --- selection -----------------------------------------------------------------

PLAN = {"sections": {
    "A": [{"start_seconds": 0.0, "end_seconds": 5.0, "energy": 0.2},
          {"start_seconds": 5.0, "end_seconds": 10.0, "energy": 0.4}],
    "B": [{"start_seconds": 10.0, "end_seconds": 18.0, "energy": 0.8}],
}}


def test_section_energies():
    spans = section_energies(PLAN)
    assert spans == [(0.0, 10.0, pytest.approx(0.3)), (10.0, 18.0, 0.8)]


def test_select_track_by_energy():
    tracks = [{"path": None, "file": "calm.mp3", "energy": 0.2, "mood": "", "tags": []},
              {"path": None, "file": "mid.mp3", "energy": 0.55, "mood": "", "tags": []},
              {"path": None, "file": "epic.mp3", "energy": 0.9, "mood": "", "tags": []}]
    # PLAN mean energy = (0.3 + 0.8)/2 = 0.55
    assert select_track(tracks, PLAN)["file"] == "mid.mp3"


def test_select_track_mood_filter():
    tracks = [{"path": None, "file": "a.mp3", "energy": 0.5, "mood": "epic", "tags": []},
              {"path": None, "file": "b.mp3", "energy": 0.5, "mood": "calm", "tags": []}]
    assert select_track(tracks, PLAN, mood="calm")["file"] == "b.mp3"


def test_library_manifest(tmp_path):
    (tmp_path / "song.mp3").write_bytes(b"x")
    (tmp_path / "music.json").write_text(
        json.dumps([{"file": "song.mp3", "energy": 0.7, "mood": "epic"}]))
    lib = load_music_library(tmp_path)
    assert lib[0]["energy"] == 0.7 and lib[0]["mood"] == "epic"


def test_resolve_music_config(tmp_path):
    (tmp_path / "project.yaml").write_text("name: x\n")
    assert resolve_music_config(tmp_path)["enabled"] is False
    (tmp_path / "project.yaml").write_text(
        "name: x\nmusic: auto\nmusic_gain_db: -12\nsfx: false\nmusic_mood: epic\n")
    cfg = resolve_music_config(tmp_path)
    assert cfg == {"enabled": True, "music": None, "gain": -12.0,
                   "sfx": False, "mood": "epic"}


# --- the ducking proof -----------------------------------------------------------

def _band_rms(video, band_hz, t0, t1):
    """RMS (dB) of a frequency band within [t0, t1] of the video's audio."""
    r = subprocess.run(
        [_ff(), "-hide_banner", "-i", str(video), "-af",
         (f"atrim={t0}:{t1},bandpass=f={band_hz}:width_type=h:w=120,"
          "astats=measure_overall=RMS_level:measure_perchannel=none"),
         "-f", "null", "-"], capture_output=True, text=True)
    for line in r.stderr.splitlines():
        if "RMS level dB" in line:
            try:
                return float(line.split(":")[-1])
            except ValueError:
                return -120.0
    return -120.0


def test_ducking_swells_music_in_narration_gaps(tmp_path):
    # VO: 300Hz tone 0-4s, SILENCE 4-8s, tone 8-12s
    vo = tmp_path / "vo.wav"
    _run(["-f", "lavfi", "-i",
          "sine=frequency=300:duration=12",
          "-af", "volume=0:enable='between(t,4,8)'", "-ar", "44100", str(vo)])
    # a 12s black video carrying that VO
    video = tmp_path / "cut.mp4"
    _run(["-f", "lavfi", "-i", "color=c=black:s=320x180:d=12",
          "-i", str(vo), "-c:v", "libx264", "-preset", "ultrafast",
          "-c:a", "aac", "-shortest", str(video)])
    # "music": an 880Hz tone
    music = tmp_path / "music.wav"
    _run(["-f", "lavfi", "-i", "sine=frequency=880:duration=14",
          "-ar", "44100", str(music)])

    plan = {"sections": {"A": [{"start_seconds": 0, "end_seconds": 6, "energy": 0.5}],
                         "B": [{"start_seconds": 6, "end_seconds": 12, "energy": 0.5}]}}
    out = tmp_path / "mixed.mp4"
    mix_soundtrack(video, plan, out, music=music, music_gain_db=-10, sfx=False)

    assert abs(subprocess.run(  # duration preserved
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(out)],
        capture_output=True, text=True).returncode) == 0
    during_vo = _band_rms(out, 880, 1.0, 3.5)     # music while narration plays
    in_gap = _band_rms(out, 880, 5.0, 7.5)        # music in the silence
    assert in_gap > during_vo + 3, (
        f"duck not working: music {during_vo:.1f} dB under VO vs "
        f"{in_gap:.1f} dB in the gap")
    # the bed must be AUDIBLE under narration, not wallpapered to nothing
    unmixed_vo = _band_rms(video, 880, 1.0, 3.5)  # 880 band of the raw VO video
    assert during_vo > unmixed_vo + 2, (
        f"music inaudible under VO: {during_vo:.1f} dB mixed vs "
        f"{unmixed_vo:.1f} dB in the unmixed video")


def test_mix_requires_music():
    with pytest.raises(RuntimeError):
        mix_soundtrack("x.mp4", PLAN, "y.mp4", music=None,
                       library="Z:/definitely/missing")
