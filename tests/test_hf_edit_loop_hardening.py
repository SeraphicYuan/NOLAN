"""Phase 1 hardening from the HF edit-loop program (docs/HF_EDIT_LOOP.md) — regression tests for the
render/pipeline bugs the-openai-debate cold-author surfaced. Pure where possible; one ffmpeg integration.
"""
import inspect
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "render-service" / "_lab_hyperframes" / "bridge"))

from nolan.hyperframes import edit as hfedit          # noqa: E402
from nolan.hyperframes import incremental as inc      # noqa: E402
from nolan.hyperframes import finish as hffinish      # noqa: E402
from nolan.hyperframes import sync as hfsync          # noqa: E402

VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"


# ---- #8 number-anchor lint --------------------------------------------------------------------------
def test_numberish_anchor():
    f = hfsync._numberish_anchor
    assert f("nine hundred million people use chat")      # spelled-out number at the head
    assert f("60 percent of traffic")                     # digits
    assert f("$13.1 billion in a year")
    assert f("negative one hundred percent")
    assert not f("operating margin was negative")         # number-word past the head → fine
    assert not f("the belief is the business")
    assert not f("")


# ---- #4 comparison sides positioned at the SCENE window (no late-scene freeze) ----------------------
def test_comparison_mount_uses_scene_window(tmp_path):
    import inject_comparison_videos as icv
    fdir = tmp_path / "compositions" / "frames"
    fdir.mkdir(parents=True)
    # a comparison hole carrying the scene-local window (data-cmp-sstart/sdur)
    (fdir / "f1.html").write_text(
        '<div class="cmp-panel framed cmp-vhole" data-cmp-video="assets/videos/x.mp4" '
        'data-cmp-rect="10,20,30,40" data-cmp-id="s1-r-vid" data-cmp-mstart="0" '
        'data-cmp-sstart="12.5" data-cmp-sdur="8.0" data-cmp-framed="1" data-cmp-gray="0"></div>', encoding="utf-8")
    (fdir / "f2.html").write_text(  # legacy hole (no sstart/sdur) → falls back to the frame window
        '<div class="cmp-panel cmp-vhole" data-cmp-video="assets/videos/y.mp4" '
        'data-cmp-rect="0,0,10,10" data-cmp-id="s2-l-vid"></div>', encoding="utf-8")
    index = ('<div data-composition-src="compositions/frames/f1.html" data-start="100.0" data-duration="50.0"></div>'
             '<div data-composition-src="compositions/frames/f2.html" data-start="200.0" data-duration="30.0"></div>')
    mounts = icv.collect_mounts(index, tmp_path)
    m1 = next(m for m in mounts if m["id"] == "s1-r-vid")
    assert float(m1["start"]) == pytest.approx(112.5)     # frame_start(100) + scene sstart(12.5), NOT 100
    assert float(m1["dur"]) == pytest.approx(8.0)         # scene sdur, NOT the 50s frame
    m2 = next(m for m in mounts if m["id"] == "s2-l-vid")
    assert float(m2["start"]) == pytest.approx(200.0) and float(m2["dur"]) == pytest.approx(30.0)  # legacy → frame window


def test_composer_emits_scene_window_on_comparison_hole():
    import compose
    sc = {"id": "s9", "type": "comparison", "start": 37.36, "dur": 14.94,
          "data": {"left": {"type": "text", "title": "A"}, "right": {"type": "video", "src": "assets/videos/z.mp4"}}}
    result = compose.comparison("s9", sc)
    frag = result[0] if isinstance(result, tuple) else result   # comparison() returns (html_frags, tl_lines)
    html = "".join(frag) if isinstance(frag, (list, tuple)) else str(frag)
    assert 'data-cmp-sstart="37.36"' in html and 'data-cmp-sdur="14.94"' in html


# ---- #4b comparison track-index stays under the renderer's 14-track cap (incident: f11 panel was BLACK) --
def test_comparison_tracks_stay_below_renderer_cap():
    """The HyperFrames renderer schedules only tracks 0..13 — a clip on track >=14 is silently dropped and
    the panel renders BLACK. assign_tracks reuses low tracks for non-overlapping scenes (track-index is
    temporal, not z-order), so 7 comparison panels no longer march 8..14. The 6-panel/5-scene shape below
    mirrors the-openai-debate (only f02's two panels overlap)."""
    import inject_comparison_videos as icv
    mounts = [
        {"id": "f02-l", "start": "119.5", "dur": "6.2"}, {"id": "f02-r", "start": "119.5", "dur": "6.2"},
        {"id": "f06",   "start": "625.5", "dur": "11.7"}, {"id": "f09", "start": "974.5", "dur": "14.2"},
        {"id": "f10a",  "start": "1067.8", "dur": "18.3"}, {"id": "f10b", "start": "1099.1", "dur": "8.3"},
        {"id": "f11",   "start": "1158.3", "dur": "14.9"},
    ]
    tracks = icv.assign_tracks(mounts)
    assert max(tracks) < icv._TRACK_CAP                    # nothing reaches the black-panel track 14
    assert max(tracks) == 9 and min(tracks) == 8          # only the overlapping f02 pair needs a 2nd track
    # the two panels that overlap in time must NOT share a track (else one is dropped)
    assert tracks[0] != tracks[1]
    # a non-overlapping later scene REUSES the base track (proof low tracks are recycled)
    assert tracks[mounts.index(next(m for m in mounts if m["id"] == "f11"))] == 8
    # no two time-overlapping mounts land on the same track
    for i in range(len(mounts)):
        for j in range(i + 1, len(mounts)):
            si, di = float(mounts[i]["start"]), float(mounts[i]["dur"])
            sj, dj = float(mounts[j]["start"]), float(mounts[j]["dur"])
            if si < sj + dj and sj < si + di:
                assert tracks[i] != tracks[j], f"{mounts[i]['id']} & {mounts[j]['id']} overlap but share a track"


# ---- #5 per-frame video under either name ----------------------------------------------------------
def test_frame_video_path_either_name(tmp_path, monkeypatch):
    fdir = tmp_path / "compositions" / "frames"
    fdir.mkdir(parents=True)
    monkeypatch.setattr(hfedit, "_frames_dir", lambda comp: fdir)
    assert hfedit.frame_video_path("x", "01-a") is None                 # neither exists
    clip = fdir / "01-a.clip.mp4"; clip.write_bytes(b"clip")
    assert hfedit.frame_video_path("x", "01-a") == clip                 # .clip.mp4 alone is accepted
    prev = fdir / "01-a.preview.mp4"; prev.write_bytes(b"prev")
    import os, time
    os.utime(prev, (time.time() + 10, time.time() + 10))               # make preview newer
    assert hfedit.frame_video_path("x", "01-a") == prev                 # newest wins


# ---- #1 caption burn is OFF by default -------------------------------------------------------------
def test_finish_defaults_captions_off():
    assert inspect.signature(hffinish.finish).parameters["burn_captions"].default is False
    assert "captions" in inspect.signature(inc.render_incremental).parameters


# ---- #1(bug) ensure_storyboard writes real src paths (not a stringified dict) -----------------------
def test_ensure_storyboard_src_resolves():
    comp = "_hf_hardening_pytest"
    dst = VIDEOS / comp
    if dst.exists():
        shutil.rmtree(dst)
    fdir = dst / "compositions" / "frames"
    fdir.mkdir(parents=True)
    try:
        for i, fid in enumerate(["01-a", "02-b"], start=1):
            (fdir / f"{fid}.spec.json").write_text(json.dumps(
                {"frames": [{"id": fid, "dur": 5.0, "format": "1920x1080", "scenes": []}]}), encoding="utf-8")
            (fdir / f"{fid}.html").write_text("<div id='root'></div>", encoding="utf-8")
        (dst / "audio_meta.json").write_text(json.dumps(
            {"voices": [{"frame": 1, "duration_s": 5.0, "path": "assets/voice/01.wav"},
                        {"frame": 2, "duration_s": 5.0, "path": "assets/voice/02.wav"}]}), encoding="utf-8")
        (dst / "SOURCE.md").write_text("# T\n## One [0:00]\nbody one.\n## Two [0:05]\nbody two.\n", encoding="utf-8")
        (dst / "hyperframes.json").write_text('{"theme":"highlighter-editorial"}', encoding="utf-8")
        sb = hfedit.ensure_storyboard(comp)
        text = Path(sb).read_text(encoding="utf-8")
        assert "{'id'" not in text and "'spec_file'" not in text      # the bug: a stringified frame dict
        for fid in ["01-a", "02-b"]:
            assert f"- src: compositions/frames/{fid}.html" in text
            assert (fdir / f"{fid}.html").exists()
    finally:
        shutil.rmtree(dst, ignore_errors=True)


# ---- #3 concat audio-integrity: _av_durations detects a dropped/short audio track ------------------
def _ffmpeg_or_skip():
    try:
        ff = inc._ffmpeg()
        subprocess.run([ff, "-version"], capture_output=True)
        return ff
    except Exception:
        pytest.skip("ffmpeg unavailable")


def test_av_durations_detects_short_audio(tmp_path):
    ff = _ffmpeg_or_skip()
    matched = tmp_path / "matched.mp4"
    short = tmp_path / "short.mp4"
    # 3s video + 3s audio → durations match
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=3", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=3", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(matched)],
                   capture_output=True)
    # 3s video + 1s audio → audio short (the "concat dropped the tail" signature)
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=3", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=1", "-c:v", "libx264", "-c:a", "aac", str(short)],
                   capture_output=True)
    if not (matched.exists() and short.exists()):
        pytest.skip("ffmpeg could not build test clips")
    vm, am = inc._av_durations(matched, ff)
    assert vm > 2.0 and abs(vm - am) < 1.0                # matched: audio spans the video
    vs, as_ = inc._av_durations(short, ff)
    assert vs - as_ > 1.0                                 # short: audio_dur << video_dur → guard fires


# ---- #4c black-panel gate: a DROPPED comparison root <video> is detected (last-frame audio-decode race) --
def test_comparison_panels_parse(tmp_path, monkeypatch):
    fdir = tmp_path / "compositions" / "frames"
    fdir.mkdir(parents=True)
    (fdir / "f1.html").write_text(
        '<div class="cmp-panel cmp-vhole" data-cmp-video="assets/videos/src.mp4" '
        'data-cmp-rect="100,0,200,240" data-cmp-id="s-r-vid" data-cmp-sstart="1.0" data-cmp-sdur="2.0"></div>',
        encoding="utf-8")
    monkeypatch.setattr(inc, "_frames_dir", lambda c: fdir)
    p = inc._comparison_panels("x", "f1")
    assert len(p) == 1
    assert (p[0]["x"], p[0]["y"], p[0]["w"], p[0]["h"]) == (100, 0, 200, 240)
    assert p[0]["sstart"] == 1.0 and p[0]["sdur"] == 2.0 and p[0]["src"] == "assets/videos/src.mp4"


def test_black_panel_gate_flags_dropped_not_dark(tmp_path, monkeypatch):
    ff = _ffmpeg_or_skip()
    cdir = tmp_path / "x"
    (cdir / "assets" / "videos").mkdir(parents=True)
    monkeypatch.setattr(inc, "_comp_dir", lambda c: cdir)
    panel = {"src": "assets/videos/src.mp4", "x": 100, "y": 0, "w": 200, "h": 240, "sstart": 0.0, "sdur": 3.0}

    def _clip(path, color, dur=4):
        subprocess.run([ff, "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x240:d={dur}",
                        "-c:v", "libx264", "-t", str(dur), str(path)], capture_output=True)

    src = cdir / "assets" / "videos" / "src.mp4"
    dropped = tmp_path / "dropped.mp4"
    good = tmp_path / "good.mp4"
    _clip(src, "white"); _clip(dropped, "black"); _clip(good, "white")
    if not (src.exists() and dropped.exists() and good.exists()):
        pytest.skip("ffmpeg could not build test clips")
    assert inc._panel_dropped_black(dropped, "x", panel, ff) is True    # panel black + source bright → dropped
    assert inc._panel_dropped_black(good, "x", panel, ff) is False      # panel bright → fine
    _clip(src, "black")                                                 # source genuinely dark now
    assert inc._panel_dropped_black(dropped, "x", panel, ff) is False   # dark source → NOT a false drop-flag


# ---- voice-mux src is found regardless of attribute order (else the video-only clip is SILENT) -----------
def test_voice_track_src_order_agnostic():
    # src BEFORE data-track-index (the assembled-index order that broke the old regex → silent clips)
    before = ('<audio id="v" src="assets/voice/11.wav" data-start="0" data-duration="102" '
              'data-track-index="10" data-volume="1"></audio>')
    after = '<audio data-track-index="10" src="assets/voice/03.wav"></audio>'   # src AFTER data-track-index
    assert inc._voice_track_src(before) == "assets/voice/11.wav"
    assert inc._voice_track_src(after) == "assets/voice/03.wav"
    # a non-voice track (index != 10) is ignored; no voice track → None
    assert inc._voice_track_src('<audio data-track-index="11" src="sfx.wav"></audio>') is None
    assert inc._voice_track_src('<div>no audio here</div>') is None


# ---- audio-less clip handling: the renderer can write a VIDEO-ONLY clip (no crash) → must not ship silent --
def test_has_audio_and_ensure_audio(tmp_path):
    ff = _ffmpeg_or_skip()
    sil, aud = tmp_path / "sil.mp4", tmp_path / "aud.mp4"
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "color=c=black:s=160x120:d=2",
                    "-c:v", "libx264", "-t", "2", str(sil)], capture_output=True)
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "color=c=black:s=160x120:d=2", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(aud)],
                   capture_output=True)
    if not (sil.exists() and aud.exists()):
        pytest.skip("ffmpeg could not build test clips")
    assert inc._has_audio(aud) is True and inc._has_audio(sil) is False
    fixed = inc._ensure_audio(sil, ff)                       # silent → sibling gains a silent audio stream
    assert fixed != sil and inc._has_audio(fixed) is True
    assert inc._ensure_audio(aud, ff) == aud                # already has audio → returned untouched


def test_mux_voice_into_silent_clip(tmp_path):
    ff = _ffmpeg_or_skip()
    (tmp_path / "assets" / "voice").mkdir(parents=True)
    voice = tmp_path / "assets" / "voice" / "5.wav"
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3", str(voice)], capture_output=True)
    # voice tag with src BEFORE data-track-index (the order that broke the old regex)
    (tmp_path / "index.html").write_text(
        '<audio id="v" src="assets/voice/5.wav" data-start="0" data-track-index="10"></audio>', encoding="utf-8")
    clip = tmp_path / "f.clip.mp4"
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "color=c=black:s=160x120:d=3",
                    "-c:v", "libx264", "-t", "3", str(clip)], capture_output=True)
    if not (voice.exists() and clip.exists()):
        pytest.skip("ffmpeg could not build test clips")
    assert inc._has_audio(clip) is False
    assert inc._mux_voice(clip, tmp_path) is True            # voice muxed into the previously-silent clip
    assert inc._has_audio(clip) is True
    (tmp_path / "index.html").write_text("<div>no voice</div>", encoding="utf-8")
    assert inc._mux_voice(clip, tmp_path) is False           # no voice track → nothing to mux
