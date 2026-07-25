"""The ONE pool-asset resolution policy: min(available, 1080).

Every video provider had its own conservative heuristic and each quietly threw quality away — measured
in the diamond v2 acquisition, which came back 1280x720 across the board even for 1080p-published clips.
Preview/captioning stays low-res on purpose; these tests pin the two policies apart.
"""
import inspect

from nolan.media_quality import TARGET_HEIGHT, pick_by_height, ytdlp_format


def _h(x):
    return x.get("height")


def test_picks_the_tallest_at_or_below_target():
    files = [{"height": 360}, {"height": 720}, {"height": 1080}, {"height": 480}]
    assert pick_by_height(files, _h) == {"height": 1080}


def test_never_hauls_a_4k_master_when_1080_exists():
    files = [{"height": 720}, {"height": 2160}, {"height": 1080}, {"height": 4320}]
    assert pick_by_height(files, _h) == {"height": 1080}


def test_when_everything_exceeds_target_takes_the_closest_down_not_the_biggest():
    files = [{"height": 2160}, {"height": 4320}]
    assert pick_by_height(files, _h) == {"height": 2160}


def test_never_downgrades_below_what_exists():
    """The old pexels rule ('first >=720' over an ascending sort) returned 720 here; 1080 was available."""
    files = [{"height": 640}, {"height": 720}, {"height": 1080}]
    assert pick_by_height(files, _h)["height"] == 1080
    # and when the best on offer is small, we still take the best on offer
    assert pick_by_height([{"height": 240}, {"height": 360}], _h)["height"] == 360


def test_unknown_heights_are_a_last_resort_not_a_dead_end():
    assert pick_by_height([{"url": "a"}, {"url": "b"}], _h) == {"url": "a"}   # no dims → still downloads
    mixed = [{"url": "x"}, {"height": 1080}]
    assert pick_by_height(mixed, _h) == {"height": 1080}                      # known beats unknown


def test_empty_is_none():
    assert pick_by_height([], _h) is None


def test_ytdlp_format_bounds_at_the_target_and_still_has_a_fallback():
    fmt = ytdlp_format()
    assert f"height<={TARGET_HEIGHT}" in fmt
    assert fmt.endswith("/bv*+ba/b")            # never return nothing just because all formats are big


# --- the two policies must stay distinct -----------------------------------------------------------

def test_resolve_media_url_honours_purpose_for_youtube():
    """REGRESSION: the youtube branch ignored `purpose` and hardcoded format 18 — always 360p — so a
    `purpose='clip'` caller silently got preview-grade video for an asset we pool and render."""
    from nolan import clipper
    src = inspect.getsource(clipper.resolve_media_url)
    clip_branch = src[src.index('if purpose == "clip"'):src.index("else:", src.index('if purpose == "clip"'))]
    assert "18/" not in clip_branch, "the clip branch must not fall back to format 18 (360p)"
    assert "height<=" in clip_branch
    assert "18/" in src, "the caption branch should still prefer the cheap 360p progressive"


def test_clip_download_pins_ffmpeg_so_the_merge_cannot_silently_degrade():
    """Without ffmpeg_location yt-dlp can't merge split streams and drops to the 360p progressive —
    a silent quality failure (you still get a file)."""
    from nolan import clipper
    src = inspect.getsource(clipper.clip)
    assert "ffmpeg_location" in src
    assert "ytdlp_format()" in src
