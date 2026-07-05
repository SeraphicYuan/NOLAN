"""Shared voice-pipeline helpers (deferred #5 dedup) — schema + concat."""

import json
import subprocess

from nolan.voice_pipeline import build_tts_items, concat_wavs_to_mp3


def _ff():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def test_item_schema_matches_omnivoice_contract():
    items = build_tts_items(["one", "two"], ref_audio="v.wav", ref_text="hi",
                            speed=1.1, language_id="en")
    assert items[0]["id"] == "sec_0000" and items[1]["id"] == "sec_0001"
    assert items[0] == {"id": "sec_0000", "text": "one", "ref_audio": "v.wav",
                        "ref_text": "hi", "speed": 1.1, "language_id": "en"}


def test_item_schema_omits_absent_fields():
    items = build_tts_items(["x"], instruct="calm narrator")
    assert items == [{"id": "sec_0000", "text": "x", "instruct": "calm narrator"}]


def test_concat_wavs_to_mp3(tmp_path):
    wavs = []
    for i, secs in enumerate((2.0, 3.0)):
        p = tmp_path / f"sec_{i:04d}.wav"
        subprocess.run([_ff(), "-y", "-v", "quiet", "-f", "lavfi",
                        "-i", f"sine=frequency={300+i*100}:duration={secs}",
                        "-ar", "44100", str(p)], check=True)
        wavs.append(p)
    out = tmp_path / "voiceover.mp3"
    concat_wavs_to_mp3(wavs, tmp_path / "_concat.txt", out)
    assert out.exists()
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                        "-show_format", str(out)], capture_output=True, text=True)
    dur = float(json.loads(r.stdout)["format"]["duration"])
    assert abs(dur - 5.0) < 0.15


def test_concat_tempo(tmp_path):
    p = tmp_path / "sec_0000.wav"
    subprocess.run([_ff(), "-y", "-v", "quiet", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=4", "-ar", "44100",
                    str(p)], check=True)
    out = tmp_path / "fast.mp3"
    concat_wavs_to_mp3([p], tmp_path / "_c.txt", out, tempo=2.0)
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                        "-show_format", str(out)], capture_output=True, text=True)
    dur = float(json.loads(r.stdout)["format"]["duration"])
    assert abs(dur - 2.0) < 0.15                # 4s at 2x -> 2s
