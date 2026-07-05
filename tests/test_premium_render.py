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
    assert step["revealFrames"] == [12, 15]     # primary capped at 0.4s


# --- still-motion vocabulary ---------------------------------------------------

from nolan.premium_render import _still_motion_props


def test_still_motion_energy_sets_tightness():
    calm = _still_motion_props({"energy": 0.1})["focuses"][0]
    tense = _still_motion_props({"energy": 0.9})["focuses"][0]
    assert tense["w"] < calm["w"]               # higher energy -> tighter push


def test_still_motion_speed_sets_pacing():
    slow = _still_motion_props({"motion_speed": "slow"})
    fast = _still_motion_props({"motion_speed": "fast"})
    assert slow["glide"] > fast["glide"]
    assert slow["introHold"] > fast["introHold"]


def test_still_motion_honors_stamped_direction():
    left = _still_motion_props({"motion_spec": {"content": {"direction": "left"}}})["focuses"][0]
    right = _still_motion_props({"motion_spec": {"direction": "right"}})["focuses"][0]
    left_center = left["x"] + left["w"] / 2
    right_center = right["x"] + right["w"] / 2
    assert left_center < 0.5 < right_center
    assert right["x"] + right["w"] > 0.9        # hugs the right edge


def test_still_motion_alternates_lanes_by_ordinal():
    xs = [_still_motion_props({}, ordinal=i)["focuses"][0]["x"] for i in range(3)]
    assert len(set(xs)) == 3                    # center / left / right


def test_primary_reveal_capped_for_late_first_word():
    # narration starts 2s into the step (pause at the boundary) — the card
    # must not hold empty: primary reveal capped at 0.4s, secondary stays
    # on the spoken word.
    words = [{"t0": 2.0, "t1": 2.4, "text": "late"}]
    ws, reveals = _step_words(words, 0.0, 4.0, fps=30, frames=120)
    assert ws[0]["startFrame"] == 60
    assert reveals == [12, 60]


# --- nine-dot tray placements drive the composition ---------------------------

from nolan.premium_render import _scene_step


def _tray_scene(tmp_path, places):
    import cv2, numpy as np
    assets = []
    for i, place in enumerate(places):
        p = tmp_path / f"tray{i}.jpg"
        cv2.imwrite(str(p), (np.random.default_rng(i).random((90, 160, 3)) * 255).astype("uint8"))
        a = {"id": f"a{i+1}", "kind": "image", "src": str(p)}
        if place:
            a["place"] = list(place)
        assets.append(a)
    return {"id": "s1", "visual_type": "archival-art", "assets": assets,
            "energy": 0.5}


def test_two_placed_tray_images_become_a_montage(tmp_path):
    scene = _tray_scene(tmp_path, [(0.2, 0.25), (0.8, 0.78)])
    block, props = _scene_step(scene, tmp_path, 30, 4.0)
    assert block == "PhotoMontage"
    assert [(c["x"], c["y"]) for c in props["cards"]] == [(0.2, 0.25), (0.8, 0.78)]


def test_one_placed_tray_image_targets_the_camera(tmp_path):
    scene = _tray_scene(tmp_path, [(0.8, 0.25)])
    block, props = _scene_step(scene, tmp_path, 30, 4.0)
    assert block == "ArtworkStage"
    f = props["focuses"][0]
    # focus region centered on the chosen dot (clamped to frame)
    assert abs((f["x"] + f["w"] / 2) - 0.8) < 0.15
    assert abs((f["y"] + f["h"] / 2) - 0.25) < 0.15


def test_unplaced_tray_stays_comment_only(tmp_path):
    scene = _tray_scene(tmp_path, [None, None])
    scene["matched_asset"] = str(tmp_path / "tray0.jpg")
    block, props = _scene_step(scene, tmp_path, 30, 4.0)
    assert block == "ArtworkStage"
    assert props["src"].endswith("tray0.jpg")   # normal still path, no montage


def test_layout_spec_outranks_tray(tmp_path):
    scene = _tray_scene(tmp_path, [(0.5, 0.5), (0.2, 0.2)])
    scene["layout_spec"] = {"template": "quote", "params": {"quote": "arma"}}
    block, _ = _scene_step(scene, tmp_path, 30, 4.0)
    assert block == "PullQuote"
