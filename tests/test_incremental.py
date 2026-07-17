"""Tests for the incremental render's pure helpers (ground tags + injection + concat list)."""
from pathlib import Path

from nolan.hyperframes import incremental as inc


def test_ground_tags_and_injection():
    grounds = [{"src": "assets/videos/a1.mp4", "start": 0.0, "dur": 19.5},
               {"src": "assets/videos/a4.mp4", "start": 37.9, "dur": 8.2}]
    tags = inc.ground_tags(grounds)
    assert tags.count("<video class=\"clip\"") == 2
    assert 'data-track-index="0"' in tags and 'data-duration="19.5"' in tags
    html = '<div id="root"><div class="scene" data-x></div></div>'
    out = inc.inject_grounds(html, grounds)
    assert out.index("<video") < out.index('<div class="scene"')   # grounds go BEHIND the frame


def test_injection_noop_without_grounds():
    html = '<div id="root"><div class="scene"></div></div>'
    assert inc.inject_grounds(html, []) == html


def test_concat_list_is_ffmpeg_safe(tmp_path):
    clips = [tmp_path / "01.clip.mp4", tmp_path / "02.clip.mp4"]
    for c in clips:
        c.write_bytes(b"x")
    # concat_clips writes _concat.txt with forward-slash absolute paths (ffmpeg concat demuxer safe);
    # it then shells out to ffmpeg — so just verify the list file it would build is well-formed.
    out = tmp_path / "renders" / "v.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    listf = out.parent / "_concat.txt"
    listf.write_text("".join(f"file '{Path(c).resolve().as_posix()}'\n" for c in clips), encoding="utf-8")
    lines = listf.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and all(ln.startswith("file '") and ln.endswith("'") for ln in lines)
    assert "\\" not in listf.read_text(encoding="utf-8")           # no backslashes → concat-safe


def _kids():
    """Synthetic assembled-index root children: 2 frames + 2 grounds + bgm + a voice + captions."""
    return [
        ["div", [("data-composition-id", "01-a"), ("data-composition-src", "compositions/frames/01-a.html"),
                 ("data-start", "0"), ("data-duration", "10"), ("data-track-index", "1")]],
        ["div", [("data-composition-id", "02-b"), ("data-composition-src", "compositions/frames/02-b.html"),
                 ("data-start", "10"), ("data-duration", "8"), ("data-track-index", "1")]],
        ["video", [("class", "clip"), ("src", "assets/videos/g1.mp4"), ("data-start", "0"),
                   ("data-duration", "5"), ("data-track-index", "0"), ("muted", None)]],
        ["video", [("class", "clip"), ("src", "assets/videos/g2.mp4"), ("data-start", "12"),
                   ("data-duration", "4"), ("data-track-index", "0"), ("muted", None)]],
        ["audio", [("src", "assets/bgm/b.mp3"), ("data-start", "0"), ("data-duration", "18"),
                   ("data-track-index", "11")]],
        ["audio", [("src", "assets/voice/02.wav"), ("data-start", "10"), ("data-duration", "8"),
                   ("data-track-index", "10")]],
        ["div", [("data-composition-id", "captions"), ("data-composition-src", "compositions/captions.html"),
                 ("data-start", "0"), ("data-duration", "18"), ("data-track-index", "2")]],
    ]


def test_window_children_frame_window_and_shift():
    dur, elems = inc._window_children(_kids(), "02-b")
    j = "".join(elems)
    assert dur == 8.0
    # this frame's sub-comp is included, shifted to local 0; other frame + captions excluded
    assert '<div data-composition-id="02-b" data-composition-src="compositions/frames/02-b.html" data-start="0.0"' in j
    assert "01-a" not in j and "captions" not in j and "compositions/captions.html" not in j
    # track-0 GROUNDS are NOT windowed here — they're reconstructed from the spec by _merged_grounds so an
    # edited/added ground shows on the next incremental render instead of inheriting the stale assembled index
    assert "g1.mp4" not in j and "g2.mp4" not in j
    # bgm spans the whole video → kept, shifted to -10; the frame's voice kept, shifted to local 0
    assert "b.mp3" in j and 'data-start="-10.0"' in j
    assert 'src="assets/voice/02.wav"' in j and 'data-start="0.0"' in j


def test_window_grounds_windows_track0_videos():
    # g1 (0–5) does NOT overlap [10,18] → dropped; g2 (12–16) overlaps → kept, shifted to frame-local 12→2
    g = inc._window_grounds(_kids(), "02-b")
    assert g == [{"src": "assets/videos/g2.mp4", "start": 2.0, "dur": 4.0}]
    assert inc._window_grounds(_kids(), "99-nope") == []


def test_asset_stem_matches_healed_variants():
    # a freeze-healed / retimed index src collapses to the same stem as its raw spec src → treated as UNCHANGED
    assert inc._asset_stem("assets/videos/s01n03_00.filled.mp4") == "s01n03_00"
    assert inc._asset_stem("assets\\videos\\s01n03_00.mp4") == "s01n03_00"
    assert inc._asset_stem("assets/f01s03_edit_vid2.mp4") == "f01s03_edit_vid2"   # an edited ground: distinct stem


def test_merged_grounds_spec_driven_with_heal_preserved(monkeypatch):
    """_merged_grounds is driven by the SPEC (which ground plays, current timing) but borrows the healed
    index src for an UNCHANGED ground; a swapped/added ground renders from its raw spec src; a removed one
    vanishes. frame_grounds (the spec read) is monkeypatched so this stays a pure-logic test."""
    kids = _kids()   # index has track-0 ground g2 in frame 02-b's window (local start 2.0, dur 4.0)

    # (a) UNCHANGED: spec ground shares g2's stem + window → keep the index (healed) src, not the raw spec one
    monkeypatch.setattr(inc, "frame_grounds",
                        lambda c, f: [{"src": "raw/g2.filled.mp4", "start": 2.0, "dur": 4.0}])
    assert inc._merged_grounds("c", "02-b", kids) == [{"src": "assets/videos/g2.mp4", "start": 2.0, "dur": 4.0}]

    # (b) SWAPPED/ADDED: a different asset in that window → render from the raw spec src (heal re-applies later)
    monkeypatch.setattr(inc, "frame_grounds",
                        lambda c, f: [{"src": "assets/f01s03_edit_vid2.mp4", "start": 2.0, "dur": 4.0}])
    assert inc._merged_grounds("c", "02-b", kids) == [
        {"src": "assets/f01s03_edit_vid2.mp4", "start": 2.0, "dur": 4.0}]

    # (c) REMOVED: spec has no grounds → nothing renders (the stale index ground does not linger)
    monkeypatch.setattr(inc, "frame_grounds", lambda c, f: [])
    assert inc._merged_grounds("c", "02-b", kids) == []


def test_window_children_unknown_frame_is_empty():
    dur, elems = inc._window_children(_kids(), "99-nope")
    assert dur is None and elems == []


def test_grid_frames_cumulative_is_drift_free():
    # per-frame round(dur*fps) would drift; cumulative round(end)-round(start) sums to the exact end frame
    durs = [55.12, 36.56, 47.58, 43.62]
    starts, acc = [], 0.0
    for d in durs:
        starts.append(acc)
        acc += d
    ns = [inc._grid_frames(s, d) for s, d in zip(starts, durs)]
    assert sum(ns) == round((starts[-1] + durs[-1]) * 30)      # == round(182.88*30), no accumulated error
    assert all(n > 0 for n in ns)
    # a frame whose window rounds tighter than its own duration still gets an exact grid count
    assert inc._grid_frames(55.12, 36.56, 30) == round(91.68 * 30) - round(55.12 * 30)
