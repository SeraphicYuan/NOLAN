"""Stock VIDEO must be relevance-scored like every other candidate.

The engine only called `ctx.video_relevance` for the LOCAL tiers (clips_library / transcript_lib /
transcript_frames). Stock video therefore stayed at `relevance = 0.0` and scored
`w_fitness * fitness_score({}) = 0.5 * 0.6 = 0.30` flat, while any library clip that cleared its floor
scored `relevance + 0.30`. So a barely-relevant 2-second local snippet outranked a well-matched
20-second stock shot every time, whatever the pixels showed — and it looked like a duration problem
("clips_library returns 2.0-2.5s snippets and fills per_need before stock gets a look"). It was a
scoring problem: the scorer is source-agnostic, and by this point every candidate has a local path.

Observed live during a batch edit as "every stock-video relevance score came back 0.00".
"""
from pathlib import Path

from nolan.acquire import AcquireConfig, Candidate, Context, acquire_need


def _clips(tmp_path):
    """Two 'videos' — a weakly-matching local library clip and a strongly-matching stock shot."""
    lib = tmp_path / "lib.mp4"
    stock = tmp_path / "stock.mp4"
    lib.write_bytes(b"L" * 4096)
    stock.write_bytes(b"S" * 4096)
    return lib, stock


def _ctx(lib, stock, scores):
    def search_clips(need, n):
        return [Candidate(ref="lib", source="clips_library", modality="video", path=lib)]

    def search_stock(need, n):
        return [Candidate(ref="stock", source="stock:pexels", modality="video", path=stock)]

    return Context(search_clips=search_clips, search_stock=search_stock,
                   relevance=lambda t, p: 0.0,
                   video_relevance=lambda t, p: scores[Path(p).name])


def test_stock_video_is_scored(tmp_path):
    lib, stock = _clips(tmp_path)
    ctx = _ctx(lib, stock, {"lib.mp4": 0.25, "stock.mp4": 0.80})
    cfg = AcquireConfig(per_need=2, sources=("clips_library", "stock"))
    kept = acquire_need({"id": "n1", "query": "a foundry pouring steel", "media_type": "video"},
                        ctx, cfg, tmp_path, [])
    by_src = {c.source: c for c in kept}
    assert by_src["stock:pexels"].relevance == 0.80, "stock video used to be left at 0.0"


def test_a_better_stock_shot_now_outranks_a_weak_library_clip(tmp_path):
    lib, stock = _clips(tmp_path)
    ctx = _ctx(lib, stock, {"lib.mp4": 0.25, "stock.mp4": 0.80})
    cfg = AcquireConfig(per_need=2, sources=("clips_library", "stock"))
    kept = acquire_need({"id": "n1", "query": "a foundry pouring steel", "media_type": "video"},
                        ctx, cfg, tmp_path, [])
    assert kept[0].source == "stock:pexels", \
        f"ranking still favours the local tier regardless of pixels: {[(c.source, c.score) for c in kept]}"


def test_a_better_library_clip_still_wins(tmp_path):
    """The fix is scoring, not a thumb on the scale for stock — the local tier must still win on merit."""
    lib, stock = _clips(tmp_path)
    ctx = _ctx(lib, stock, {"lib.mp4": 0.75, "stock.mp4": 0.20})
    cfg = AcquireConfig(per_need=2, sources=("clips_library", "stock"))
    kept = acquire_need({"id": "n1", "query": "a foundry pouring steel", "media_type": "video"},
                        ctx, cfg, tmp_path, [])
    assert kept[0].source == "clips_library"


def test_the_library_clip_floor_still_culls_and_stock_is_not_newly_culled(tmp_path):
    """`clip_lib_relevance_floor` gates the LOCAL tiers before the VLM. Scoring stock must not
    silently add a cull for it — an empty beat is worse than a mediocre one."""
    lib, stock = _clips(tmp_path)
    ctx = _ctx(lib, stock, {"lib.mp4": 0.05, "stock.mp4": 0.05})
    cfg = AcquireConfig(per_need=2, sources=("clips_library", "stock"), clip_lib_relevance_floor=0.20)
    kept = acquire_need({"id": "n1", "query": "q", "media_type": "video"}, ctx, cfg, tmp_path, [])
    srcs = {c.source for c in kept}
    assert "clips_library" not in srcs, "the local floor still applies"
    assert "stock:pexels" in srcs, "stock video must not gain a new cull from being scored"


def test_no_video_relevance_organ_degrades_cleanly(tmp_path):
    lib, stock = _clips(tmp_path)
    ctx = Context(search_stock=lambda need, n: [Candidate(ref="s", source="stock:pexels",
                                                          modality="video", path=stock)],
                  relevance=lambda t, p: 0.0)          # CLIP present for images, no video scorer
    cfg = AcquireConfig(per_need=2, sources=("stock",))
    kept = acquire_need({"id": "n1", "query": "q", "media_type": "video"}, ctx, cfg, tmp_path, [])
    assert len(kept) == 1 and kept[0].relevance == 0.0
