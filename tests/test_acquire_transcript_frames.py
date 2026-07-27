"""The SHOWN tier — the transcript library's captioned keyframes as an acquisition source.

Acquisition used to reach the transcript library only through `search_level="segments"`, i.e. by what is
SAID. Measured on a real diamond-v2 beat ("diamond mine open pit excavation machinery"), that anchored the
super-pit documentary at 0.0s — its title card — because that is where the narrator says the topic, while
the captioned frames held the shovel bucket (62.0s), the operator's controls (66.2s) and the Komatsu truck
(97.4s). Same video, wrong seconds.

The registration tests below are the honesty tests the wiring checklist demands: a new source that is not
named in TIERS silently ranks BELOW every real provider, and one that is not named in the video-relevance
recompute keeps `relevance = 0.0` and is then culled by the CLIP floor — both fail as "the source found
nothing", which is indistinguishable from an empty library.
"""
import inspect


def test_the_new_source_is_ranked_not_silently_last():
    """`source_rank` falls through to `len(order) + 50` for an unknown source, so an unregistered tier
    gets a tier_bonus of ~0 and loses every evocative beat without ever erroring."""
    from nolan.acquire import engine as E
    for category in E.TIERS:
        assert "transcript_frames" in E.TIERS[category], f"unranked in {category}"
        # ranked immediately after the segment tier — same corpus, same provenance, better timing
        assert E.source_rank(category, "transcript_frames") == E.source_rank(category, "transcript_lib") + 1
        assert E.source_rank(category, "transcript_frames") < E.source_rank(category, "ddgs")


def test_video_relevance_is_recomputed_for_the_new_source():
    """Video candidates get their retrieval score REPLACED by CLIP on the downloaded frames. A source
    missing from that tuple keeps relevance 0.0 and is then dropped by `clip_lib_relevance_floor` — the
    source would look empty rather than broken."""
    src = inspect.getsource(__import__("nolan.acquire.engine", fromlist=["x"]))
    recompute = 'c.source in ("clips_library", "transcript_lib", "transcript_frames")'
    assert src.count(recompute) >= 2, "must be in BOTH the relevance recompute and the _keep CLIP floor"


def test_the_engine_gate_admits_the_new_source():
    """`acquire_need` only calls `ctx.search_clips` when a clip-ish source is in `cfg.sources`."""
    from nolan.acquire.config import AcquireConfig
    from nolan.acquire import engine as E
    assert "transcript_frames" in AcquireConfig().sources
    src = inspect.getsource(E.acquire_need)
    assert "transcript_frames" in src


def test_one_materialisation_path_for_both_transcript_tiers():
    """Both tiers pull a RANGE from the same URL, clean the same broadcast watermark and write the same
    claim. Two download paths would be two dialects for one decision."""
    from nolan.acquire import context as C
    src = inspect.getsource(C.build_context)
    assert 'c.source not in ("transcript_lib", "transcript_frames")' in src
    assert src.count("clean_media_inplace") == 1


def test_build_context_exposes_the_switch():
    from nolan.acquire.context import build_context
    p = inspect.signature(build_context).parameters
    assert "want_transcript_frames" in p and p["want_transcript_frames"].default is True


# --- behaviour -------------------------------------------------------------------------------------

def _wire(monkeypatch, tmp_path, frames, hits, catalog, project_dir=None):
    """Stand up build_context against a stub transcript library (no DB, no network)."""
    from nolan.acquire import context as C
    from nolan import transcript_frames as tfr
    from nolan import transcript_lib as tl
    db = tmp_path / "clips.db"
    db.write_bytes(b"")
    monkeypatch.setattr(C, "_resolve_clips_db", lambda cfg: db)
    monkeypatch.setattr(C, "VideoIndex", lambda p: type("I", (), {"footage_video_ids": lambda s: set()})(),
                        raising=False)
    import nolan.indexer as _ix
    import nolan.vector_search as _vsm
    monkeypatch.setattr(_ix, "VideoIndex", lambda p: type("I", (), {"footage_video_ids": lambda s: set()})())
    monkeypatch.setattr(_vsm, "VectorSearch",
                        lambda **k: type("V", (), {"search": lambda s, **kw: []})())
    monkeypatch.setattr(tl, "load_catalog", lambda *a, **k: catalog)
    monkeypatch.setattr(tl, "copyright_free_ids", lambda *a, **k: set())
    monkeypatch.setattr(tfr, "visual_search", lambda q, n=24, **k: hits)
    monkeypatch.setattr(tfr, "frames_for_video", lambda v, **k: frames)
    # the SHOT GRID both tiers now snap to, stubbed from the same keyframe fixture
    monkeypatch.setattr(tfr, "shot_grid", lambda base_dir=None: {
        vid: sorted(f["t"] for f in frames if f.get("kind") == "keyframe") for vid in catalog})
    return C.build_context(type("Cfg", (), {"clip_seconds": 30})(), want_stock=False, want_library=False,
                           want_clip=False, want_gen=False, want_clips_library=False,
                           want_transcript_lib=False, want_transcript_frames=True,
                           project_dir=project_dir)


def test_the_clip_window_is_the_real_shot_not_a_fixed_guess(monkeypatch, tmp_path):
    """A keyframe comes from `detect_cuts` → `plan_shots`, one per detected shot, so the gap to the NEXT
    keyframe is the shot's true length. `_clip_window`'s own docstring says a transcript segment cannot
    give this ("a true single-shot trim needs the `shots` table") — the frame tier is that table.
    Live check on diamond-v2 returned 3.1s / 8.3s / 11.6s shots where the segment tier gave a flat 5.0s."""
    cat = {"vid1": {"url": "https://www.youtube.com/watch?v=vid1", "kind": "youtube", "channel": "c",
                    "frames": 4}}
    frames = [{"t": 60.0, "kind": "keyframe"}, {"t": 68.3, "kind": "keyframe"},
              {"t": 71.4, "kind": "keyframe"}]
    hits = [{"video_id": "vid1", "start": 60.0, "score": 0.7, "caption": "a shovel", "summary": "a shovel",
             "asset_type": "live-footage", "content_kind": "broll", "objects": ["shovel"]}]
    ctx = _wire(monkeypatch, tmp_path, frames, hits, cat)
    out = ctx.search_clips({"query": "q", "queries": ["q"]}, 4)
    assert len(out) == 1 and out[0].source == "transcript_frames"
    assert out[0].meta["clip_start"] == 60.0
    assert abs(out[0].meta["clip_dur"] - 8.3) < 0.01          # to the NEXT cut, not a fixed window


def test_one_film_cannot_fill_a_beat(monkeypatch, tmp_path):
    """A long documentary has many matching shots; without a per-video cap the whole beat becomes one
    film, which is the same failure the near-duplicate collapse exists to prevent on the library side."""
    cat = {"v": {"url": "https://www.youtube.com/watch?v=v", "kind": "youtube", "channel": "c", "frames": 9}}
    frames = [{"t": float(i * 10), "kind": "keyframe"} for i in range(9)]
    hits = [{"video_id": "v", "start": float(i * 10), "score": 0.9 - i * 0.01, "caption": f"shot {i}",
             "summary": f"shot {i}", "asset_type": "live-footage", "content_kind": "broll", "objects": []}
            for i in range(8)]
    ctx = _wire(monkeypatch, tmp_path, frames, hits, cat)
    out = ctx.search_clips({"query": "q", "queries": ["q"]}, 8)
    assert len(out) == 2, f"one film took {len(out)} slots"


def test_a_claimed_range_is_not_pulled_twice(monkeypatch, tmp_path):
    """The claim ledger is the ONE dedup channel between the hero pool and this recall pool. A frame hit
    landing inside a range the heroes already took must be skipped, exactly as a segment hit is."""
    cat = {"v": {"url": "https://www.youtube.com/watch?v=v", "kind": "youtube", "channel": "c", "frames": 2}}
    frames = [{"t": 60.0, "kind": "keyframe"}, {"t": 65.0, "kind": "keyframe"}]
    hits = [{"video_id": "v", "start": 60.0, "score": 0.7, "caption": "x", "summary": "x",
             "asset_type": "live-footage", "content_kind": "broll", "objects": []}]
    # patched BEFORE build_context: the closure binds these names when it runs, and the claims are read
    # LAZILY per search (a snapshot at context-build time is the bug that once cut the pool from 9 to 1)
    import nolan.acquire.shared as sh
    claim = {"url": "https://www.youtube.com/watch?v=v", "start": 59.0, "dur": 8.0,
             "owner": "hero", "file": "hero.mp4"}
    monkeypatch.setattr(sh, "load_claims", lambda p: [claim])
    monkeypatch.setattr(sh, "range_is_claimed", lambda claims, url, start, dur: claims[0] if claims else None)
    ctx = _wire(monkeypatch, tmp_path, frames, hits, cat, project_dir=tmp_path)
    out = ctx.search_clips({"query": "q", "queries": ["q"]}, 4)
    assert out == [], "a range the hero pool already claimed was pulled a second time"


def test_the_k_nearest_store_is_tail_trimmed(monkeypatch, tmp_path):
    """REGRESSION. The frame store returns `k` captions for ANY query however weak — measured live,
    "Odysseus and the ancient Greek epic" retrieved the 1936 Berlin Olympics at 0.52 and Lindbergh at
    0.53, while genuine hits on a diamond beat scored 0.62-0.71. Without the same `clip_lib_min_sim`
    tail-trim the segment tier applies, an off-domain beat spends real DOWNLOADS on that junk. It is a
    trim, not a topic gate — discrimination is the downstream CLIP frame floor and the VLM."""
    cat = {"olympics": {"url": "https://archive.org/details/olympics", "kind": "archive",
                        "channel": "", "frames": 109},
           "good": {"url": "https://www.youtube.com/watch?v=good", "kind": "youtube",
                    "channel": "c", "frames": 12}}
    frames = [{"t": 0.0, "kind": "keyframe"}, {"t": 6.0, "kind": "keyframe"}]
    hits = [{"video_id": "good", "start": 0.0, "score": 0.66, "caption": "on topic",
             "summary": "on topic", "asset_type": "live-footage", "content_kind": "broll", "objects": []},
            {"video_id": "olympics", "start": 0.0, "score": 0.52, "caption": "1936 Berlin Olympics",
             "summary": "1936 Berlin Olympics", "asset_type": "archival-footage",
             "content_kind": "broll", "objects": []}]
    ctx = _wire(monkeypatch, tmp_path, frames, hits, cat)
    out = ctx.search_clips({"query": "q", "queries": ["q"]}, 4)
    assert [c.meta["source_url"] for c in out] == ["https://www.youtube.com/watch?v=good"]

def test_the_two_tiers_do_not_pull_the_same_shot_twice(monkeypatch, tmp_path):
    """Two indexes over ONE corpus find the same shot from both sides. Neither tier can see the other's
    picks — each dedups only within itself, and the claim ledger is read at SEARCH time but written at
    DOWNLOAD time (run concurrently by the engine), so it cannot catch an overlap inside a single need.

    Measured live on a diamond beat: the segment tier returned SouthDak1940 @537.2s+5.0s while the frame
    tier returned the same film @534.9s+12.0s — the second CONTAINS the first. Two downloads of one shot,
    and two near-identical clips in the author's menu. The FRAME must win: its range is the real shot
    (keyframe → next cut), the segment's is a flat guess from an arbitrary point in a 45s window."""
    from nolan.acquire import context as C
    from nolan import transcript_frames as tfr
    from nolan import transcript_lib as tl
    url = "https://archive.org/details/SouthDak1940"
    cat = {"SouthDak1940": {"url": url, "kind": "archive", "channel": "", "frames": 35}}

    class _Hit:                       # what VectorSearch yields for a transcript segment
        def __init__(self, ts, score):
            self.video_id, self.video_path, self.score = 7, url, score
            self.timestamp_start, self.timestamp_end = ts, ts + 40.0
            self.description, self.transcript = "said something", "said something"

    db = tmp_path / "c.db"; db.write_bytes(b"")
    monkeypatch.setattr(C, "_resolve_clips_db", lambda cfg: db)
    import nolan.indexer as _ix, nolan.vector_search as _vsm
    monkeypatch.setattr(_ix, "VideoIndex", lambda p: type("I", (), {"footage_video_ids": lambda s: set()})())
    # 537.2s OVERLAPS the frame shot; 100.0s does not and must survive
    monkeypatch.setattr(_vsm, "VectorSearch", lambda **k: type(
        "V", (), {"search": lambda s, **kw: [_Hit(537.2, 0.704), _Hit(100.0, 0.68)]})())
    monkeypatch.setattr(tl, "load_catalog", lambda *a, **k: cat)
    monkeypatch.setattr(tl, "copyright_free_ids", lambda *a, **k: set())
    monkeypatch.setattr(tfr, "visual_search", lambda q, n=24, **k: [
        {"video_id": "SouthDak1940", "start": 534.9, "score": 0.709, "caption": "a drill",
         "summary": "a drill", "asset_type": "archival-footage", "content_kind": "broll", "objects": []}])
    monkeypatch.setattr(tfr, "frames_for_video", lambda v, **k: [
        {"t": 534.9, "kind": "keyframe"}, {"t": 546.9, "kind": "keyframe"}])
    monkeypatch.setattr(tfr, "shot_grid", lambda base_dir=None: {"SouthDak1940": [534.9, 546.9]})

    ctx = C.build_context(type("Cfg", (), {"clip_seconds": 30})(), want_stock=False, want_library=False,
                          want_clip=False, want_gen=False, want_clips_library=False,
                          want_transcript_lib=True, want_transcript_frames=True, clip_lib_min_sim=0.55)
    out = ctx.search_clips({"query": "q", "queries": ["q"]}, 4)
    by_src = [(c.source, round(float(c.meta["clip_start"]), 1)) for c in out]
    assert ("transcript_frames", 534.9) in by_src, f"the frame shot must survive: {by_src}"
    # the frame range 534.9-546.9 CONTAINS the 537.2 segment window — it must not be pulled as well
    assert not any(s == "transcript_lib" and 534.9 <= t <= 546.9 for s, t in by_src), \
        f"the same shot was pulled twice: {by_src}"
    # …and a NON-overlapping segment from the same film is untouched (this is a dedup, not a tier kill)
    assert any(s == "transcript_lib" and t < 200 for s, t in by_src), f"over-culled: {by_src}"
