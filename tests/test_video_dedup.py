"""Clips de-dup like stills do.

The pool's semantic dedup read `avg_hash(c.path) if c.modality == "image" else None` — ONE condition
that skipped video entirely. So four pool ids could be the same shot (a1_05/a17_02/a20_05/a23_02 were
one macro-diamond clip; a17_04/a19_06/a1_07 one pink-velvet ring-box), ~9 grounded scenes ran on ~4
distinct looks, and `media_diversity` still reported a healthy 1.10 because it counts FILE PATHS.
Measured on the shipped v2 pool after the fix: 13 of 81 clips collapse, 68 distinct looks remain.

Fixed by feeding the EXISTING average-hash a keyframe, not by adding a pHash stack.
"""
import subprocess

import pytest

from nolan.acquire.engine import _near_dup, avg_hash, video_hash


def _ffmpeg():
    try:
        from nolan.hf_qa import _ffmpeg as ff
        return ff()
    except Exception:
        return None


def _clip(path, src="testsrc", secs=3, size="128x128"):
    """A PATTERNED source, never a flat colour: average-hash compares each pixel to the frame mean, so
    every uniform image hashes to all-ones and two different flat colours look identical. Real footage
    is never flat, but a fixture can be — that is a property of the hash, not of the dedup."""
    ff = _ffmpeg()
    if not ff:
        pytest.skip("no ffmpeg")
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", f"{src}=s={size}:d={secs}",
                    "-pix_fmt", "yuv420p", str(path)], capture_output=True)
    return path if path.exists() else pytest.skip("ffmpeg could not synthesise a clip")


def test_a_clip_hashes(tmp_path):
    assert video_hash(_clip(tmp_path / "a.mp4", "testsrc")) is not None


def test_two_encodes_of_the_same_shot_collapse(tmp_path):
    """Byte-different files, same picture — exactly the pexels-contributor duplicate case."""
    a = video_hash(_clip(tmp_path / "a.mp4", "testsrc", secs=3))
    b = video_hash(_clip(tmp_path / "b.mp4", "testsrc", secs=5))    # different length ⇒ different bytes
    assert a is not None and b is not None
    assert _near_dup(b, [a], 6), "the same shot must read as a duplicate"


def test_a_genuinely_different_clip_survives(tmp_path):
    a = video_hash(_clip(tmp_path / "a.mp4", "testsrc"))
    b = video_hash(_clip(tmp_path / "b.mp4", "smptebars"))
    assert not _near_dup(b, [a], 6), "distinct footage must not be collapsed"


def test_an_unreadable_clip_is_kept_not_dropped(tmp_path):
    """A hash failure must never lose an asset — None means 'no opinion', so the clip survives."""
    bogus = tmp_path / "nope.mp4"
    bogus.write_bytes(b"not a video")
    assert video_hash(bogus) is None
    assert not _near_dup(None, [123], 6)


def test_the_engine_hashes_video_instead_of_skipping_it():
    import inspect

    from nolan.acquire import engine
    src = inspect.getsource(engine.acquire_need)
    assert "video_hash(c.path)" in src
    assert 'if c.modality == "image" else None' not in src, "the skip-video condition is back"
