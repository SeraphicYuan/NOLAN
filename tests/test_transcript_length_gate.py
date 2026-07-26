"""The length rule is enforced where the duration is actually KNOWN.

A topic search can only filter on a duration the crawl happened to cache. Measured on the live surveys:
youtube/youtube_cc rows carry one 100% of the time, archive rows 14.0% — and resolving the other 86% costs
an HTTP metadata round-trip each against a server that throttles per client (8 identical lookups: 88.8s
sequential vs 80.9s at 8-way, so concurrency buys nothing). So a sweep leaves archive rows unfiltered during
the search and enforces the rule after the download, where the runtime is exact and free.
"""
import asyncio
import contextlib
import json


class _Job:
    def __init__(self):
        self.logs = []

    def log(self, m):
        self.logs.append(m)

    def set_progress(self, *a, **k):
        pass


def _stub_capture(monkeypatch, tmp_path, duration):
    """Stand in for the download + cut detection so the test exercises the GATE, not ffmpeg."""
    from nolan import transcript_frames as tfr
    from nolan import transcript_lib as tl
    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"x")
    monkeypatch.setattr(tfr, "download_sem", lambda: contextlib.nullcontext())
    monkeypatch.setattr(tfr, "download_video", lambda url, out, **k: (vid, duration))
    monkeypatch.setattr(tfr, "detect_cuts", lambda *a, **k: ([], duration))
    monkeypatch.setattr(tfr, "storyboard_dir", lambda y, base_dir=None: tmp_path / "sb")
    monkeypatch.setattr(tfr, "storyboard_tiles", lambda *a, **k: [])
    monkeypatch.setattr(tl, "TRANSCRIPT_DIR", tmp_path)


def test_a_short_reel_is_rejected_on_its_real_runtime(monkeypatch, tmp_path):
    """The incident this exists for: a 4-minute reel with no crawled `runtime` sailed through the
    unknown-duration-is-KEPT rule and bought a caption run."""
    from nolan.webui import operations as ops
    _stub_capture(monkeypatch, tmp_path, 240.0)
    with __import__("pytest").raises(ops.LengthSkip) as e:
        asyncio.run(ops._capture_visual_tier("https://archive.org/details/x", [], "x", "A reel",
                                             kind="youtube", job=_Job(), min_sec=1200))
    assert e.value.dur == 240.0


def test_the_learned_duration_is_remembered_so_it_is_never_asked_for_again(monkeypatch, tmp_path):
    """The download yields an exact runtime for free — strictly better than the uploader-declared one the
    metadata API returns. Feeding it back means the length filter never pays for that item again."""
    from nolan import transcript_lib as tl
    from nolan.webui import operations as ops
    _stub_capture(monkeypatch, tmp_path, 240.0)
    tl._DUR_CACHE.clear()
    with __import__("pytest").raises(ops.LengthSkip):
        asyncio.run(ops._capture_visual_tier("https://archive.org/details/x", [], "x", "A reel",
                                             kind="youtube", job=_Job(), min_sec=1200))
    assert json.loads((tmp_path / "durations.json").read_text())["x"] == 240
    tl._DUR_CACHE.clear()


def test_no_filter_means_no_gate(monkeypatch, tmp_path):
    """With no length filter the gate must never fire — it is the caller's rule, not a policy of its own."""
    from nolan.webui import operations as ops
    _stub_capture(monkeypatch, tmp_path, 240.0)
    monkeypatch.setattr(ops, "_plan_and_caption", None, raising=False)
    try:
        asyncio.run(ops._capture_visual_tier("https://x/y", [], "x", "A reel", kind="youtube",
                                             job=_Job(), min_sec=0, max_sec=0))
    except ops.LengthSkip:
        raise AssertionError("the gate fired with no filter set")
    except Exception:
        pass                      # any LATER failure (no real media) is fine — the gate is what's tested
