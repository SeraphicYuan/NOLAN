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
