"""ONE resolution policy for POOL-ASSET downloads — `min(available, TARGET_HEIGHT)`.

Two different mechanisms kept getting conflated. They are not the same job:

* **Preview / captioning** wants the CHEAPEST legible encode — a 320x240 archive `_512kb.mp4`, a 360p
  progressive YouTube stream — because it range-seeks single frames and feeds a VLM. That policy lives
  in `clipper.preview_frames` / `archive_source.pick_derivative(purpose='caption')` and stays low-res
  ON PURPOSE.
* **The actual snippet we pool and render** wants the BEST encode we can practically use. It lands in a
  1920x1080 composition, often as a full-bleed ground, so anything under 1080p is quality we simply threw
  away — and every provider was throwing some away, each in its own way:
      pexels   — sorted ascending, took the FIRST >=720  → exactly 720p even when 1080p/4K existed
      pixabay  — `medium` (720) before `large` (1080)     → 720p by construction
      archive  — median file BY BYTE SIZE                 → arbitrary; ignores the real derivative policy
      nasa     — first `.mp4` in the manifest             → arbitrary
      youtube  — `bv*+ba/b` with no ffmpeg_location       → unbounded, and a failed merge falls back to
                                                            the 360p progressive without saying so

`min(available, 1080)` is the honest rule: take the tallest option that does not EXCEED the target, so we
never downgrade below what exists, and never haul a 4K master to render at 1080. When every option exceeds
the target, take the SHORTEST of those — closest to what we need, not the biggest file on the server.
"""
from __future__ import annotations

from typing import Callable, List, Optional, TypeVar

TARGET_HEIGHT = 1080          # the composition canvas — pulling above this buys nothing at render time

T = TypeVar("T")


def pick_by_height(items: List[T], height_of: Callable[[T], Optional[int]],
                   target: int = TARGET_HEIGHT) -> Optional[T]:
    """`min(available, target)`: the TALLEST item at or below `target`; if every known height exceeds it,
    the SHORTEST of those. Items with an unknown/zero height are used only when nothing else qualifies
    (order-preserving), so a provider that omits dimensions still yields a download rather than nothing."""
    if not items:
        return None
    known, unknown = [], []
    for it in items:
        try:
            h = int(height_of(it) or 0)
        except (TypeError, ValueError):
            h = 0
        (known if h > 0 else unknown).append((h, it))
    at_or_below = [(h, it) for h, it in known if h <= target]
    if at_or_below:
        return max(at_or_below, key=lambda p: p[0])[1]
    if known:
        return min(known, key=lambda p: p[0])[1]          # all above target → the closest one down
    return unknown[0][1]


def ytdlp_format(target: int = TARGET_HEIGHT, prefer_h264: bool = False) -> str:
    """The yt-dlp format selector for the same policy.

    Prefer the best split streams at or below `target` (merged), then the best progressive at or below it,
    then — only if nothing qualifies — the best available at all. NOTE: the merged branch needs ffmpeg, so
    always pass `ffmpeg_location` alongside this; without it yt-dlp silently drops to the progressive
    fallback, which on YouTube is format 18 (360p), and the pool quietly fills with 360p clips.

    `prefer_h264` puts avc1 first at the SAME resolution — for library ingest, where scene detection
    decodes the whole file and H.264 is ~5x faster than AV1. It is a CODEC preference, never a resolution
    one: the avc1 branches are bounded by the same `target` and fall through to any codec at that height.
    """
    h264 = (f"bv*[height<={target}][vcodec^=avc1]+ba/b[height<={target}][vcodec^=avc1]/"
            if prefer_h264 else "")
    return (f"{h264}"
            f"bv*[height<={target}]+ba/b[height<={target}]/"
            f"bv*+ba/b")
