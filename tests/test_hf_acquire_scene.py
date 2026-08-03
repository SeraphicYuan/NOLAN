"""Scene-scoped acquisition: the FULL engine at one beat, plus the duration term it unlocks.

The edit loop had two doors and neither was right: `replace.search` (scene-scoped, pool-safe, but only
`ctx.search_stock` — no library, no clips, no CLIP, no dedup, no VLM floor) and `run_pool` (full engine,
whole-project, and it overwrote pool.json). A real batch used the second with `sources=("stock",)` and
hand-placed everything.

Scene scope also KNOWS three things the project-wide need-derivation cannot, and each is asserted here:
the beat's window (→ `min_duration`), the words spoken over it (→ the query), and what the essay already
shows (→ dedup across runs, not just within one).
"""
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"

from nolan.acquire import AcquireConfig, Candidate, Context, acquire_need           # noqa: E402
from nolan.acquire.engine import clip_duration, duration_penalty                    # noqa: E402
from nolan.hyperframes import acquire_scene as acq                                  # noqa: E402

_VO = "the auction house takes its cut before anyone else is paid".split()


@pytest.fixture()
def comp():
    name = "_hf_acq_scene_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    fdir = dst / "compositions" / "frames"
    fdir.mkdir(parents=True)
    (fdir / "01-beat.spec.json").write_text(json.dumps({"frames": [{"id": "01-beat", "dur": 24.0, "scenes": [
        {"id": "s1", "type": "statement", "start": 0, "dur": 19.0,
         "data": {"lines": ["the cut"], "ground": {"kind": "video", "src": "assets/old.mp4"}}},
        {"id": "s2", "type": "statement", "start": 19.0, "dur": 5.0,
         "data": {"lines": ["and the rest"], "ground": {"kind": "image", "src": "assets/used.jpg"}}},
    ]}]}), encoding="utf-8")
    (dst / "hyperframes.json").write_text('{"theme":"highlighter-editorial"}', encoding="utf-8")
    (dst / "audio_meta.json").write_text(json.dumps({"voices": [{
        "frame": 1, "path": "assets/voice/01.wav", "duration_s": 24.0,
        "words": [{"word": w, "start": i * 1.5, "end": i * 1.5 + 1.0} for i, w in enumerate(_VO)]}]}),
        encoding="utf-8")
    (dst / "assets").mkdir()
    (dst / "assets" / "old.mp4").write_bytes(b"O" * 4096)
    from PIL import Image                                   # a REAL image: avg_hash must be able to read it
    Image.new("RGB", (96, 64), (30, 90, 200)).save(dst / "assets" / "used.jpg")
    try:
        yield name
    finally:
        shutil.rmtree(dst, ignore_errors=True)


# --- the need ---------------------------------------------------------------------------------

def test_the_need_carries_the_scenes_real_window(comp):
    need = acq.derive_need(comp, "01-beat", "s1", modality="video")
    assert need["min_duration"] == 19.0, \
        "the window is the field the project-wide need-derivation can only guess at"
    assert need["media_type"] == "video"
    assert need["id"] == "01-beat~s1"


def test_an_image_need_carries_no_min_duration(comp):
    need = acq.derive_need(comp, "01-beat", "s2", modality="image")
    assert "min_duration" not in need, "duration is meaningless for a still"


def test_the_query_comes_from_what_is_spoken_over_the_scene(comp):
    need = acq.derive_need(comp, "01-beat", "s1")
    joined = " ".join(need["queries"]).lower()
    assert "auction" in joined and "house" in joined, f"narration must drive the query: {need['queries']}"


def test_an_explicit_query_overrides_the_derived_one(comp):
    need = acq.derive_need(comp, "01-beat", "s1", query="gavel falling in a saleroom")
    assert need["query"] == "gavel falling in a saleroom"


# --- the duration term -------------------------------------------------------------------------

def test_a_snippet_that_needs_heavy_looping_is_docked(tmp_path):
    cfg = AcquireConfig()
    short = Candidate(ref="a", source="clips_library", modality="video", meta={"duration": 2.5})
    assert duration_penalty(short, 19.0, cfg) == pytest.approx(cfg.w_duration), \
        "2.5s under a 19s hold is 7.6 repeats — saturate the penalty"


def test_a_clip_that_covers_the_window_is_not_docked(tmp_path):
    cfg = AcquireConfig()
    ok = Candidate(ref="b", source="stock:pexels", modality="video", meta={"duration": 20.0})
    assert duration_penalty(ok, 19.0, cfg) == 0.0


def test_a_mild_shortfall_is_only_mildly_docked(tmp_path):
    """`ensure_grounds_fit` genuinely loop-fills 7.1s→15.7s, so a near-miss must stay competitive —
    this is a penalty, not the hard floor the retro asked for."""
    cfg = AcquireConfig()
    near = Candidate(ref="c", source="stock:pexels", modality="video", meta={"duration": 12.0})
    assert 0.0 < duration_penalty(near, 19.0, cfg) < 0.2


def test_stills_and_needs_without_a_window_are_untouched(tmp_path):
    cfg = AcquireConfig()
    img = Candidate(ref="d", source="stock:pexels", modality="image", meta={"duration": 1.0})
    assert duration_penalty(img, 19.0, cfg) == 0.0
    vid = Candidate(ref="e", source="stock:pexels", modality="video", meta={"duration": 1.0})
    assert duration_penalty(vid, 0.0, cfg) == 0.0


def test_duration_can_be_switched_off(tmp_path):
    cfg = AcquireConfig(w_duration=0.0)
    short = Candidate(ref="f", source="clips_library", modality="video", meta={"duration": 1.0})
    assert duration_penalty(short, 19.0, cfg) == 0.0


def test_ranking_prefers_the_clip_that_covers_the_hold(tmp_path):
    """The reported symptom: 2.0-2.5s library snippets filled a beat whose hold was 4-19s while
    9-22s stock shots never got a look."""
    snip, long = tmp_path / "snip.mp4", tmp_path / "long.mp4"
    snip.write_bytes(b"S" * 4096)
    long.write_bytes(b"L" * 4096)
    ctx = Context(
        search_clips=lambda need, n: [Candidate(ref="snip", source="clips_library", modality="video",
                                                path=snip, meta={"duration": 2.5})],
        search_stock=lambda need, n: [Candidate(ref="long", source="stock:pexels", modality="video",
                                                path=long, meta={"duration": 20.0})],
        relevance=lambda t, p: 0.0,
        video_relevance=lambda t, p: 0.45)                 # EQUALLY relevant — duration is the tiebreak
    cfg = AcquireConfig(per_need=2, sources=("clips_library", "stock"))
    kept = acquire_need({"id": "n1", "query": "q", "media_type": "video", "min_duration": 19.0},
                        ctx, cfg, tmp_path, [])
    assert kept[0].source == "stock:pexels", [(c.source, round(c.score, 3)) for c in kept]


def test_clip_duration_prefers_metadata_and_survives_a_missing_file():
    assert clip_duration(Candidate(ref="a", source="s", modality="video", meta={"duration": 7})) == 7.0
    assert clip_duration(Candidate(ref="b", source="s", modality="video")) is None


# --- dedup against what the essay already shows ---------------------------------------------------

def test_in_use_assets_seed_the_dedup(comp):
    """The project pool build dedups WITHIN one run. An edit is a later run, so without this a scene
    can be handed a shot the viewer already saw in another beat."""
    assert acq._pool_hashes(comp), "used.jpg is mounted on s2 and must contribute a hash"


def test_the_asset_being_replaced_does_not_block_its_own_swap(comp):
    """`used.jpg` is used by s2 alone; when re-acquiring FOR s2 it must not veto near-identical
    candidates, or a deliberate re-fetch of a better crop of the same picture is impossible."""
    assert acq._pool_hashes(comp, exclude_scene="s2") == []
    assert acq._pool_hashes(comp, exclude_scene="s1") != [], "another scene's asset still blocks"


def test_an_unreadable_asset_is_skipped_not_fatal(comp):
    """`old.mp4` is a stub ffmpeg cannot decode. A hash failure must cost that one asset, never the run."""
    assert acq._pool_hashes(comp) is not None


# --- the full-access contract ---------------------------------------------------------------------

def test_every_tier_is_reachable_from_the_edit_loop():
    from nolan.acquire.config import AcquireConfig as C
    assert set(C().sources) <= set(acq.DEFAULT_SOURCES), \
        "the edit path must not offer FEWER tiers than the author pipeline"
    assert "visuallib" in acq.DEFAULT_SOURCES


def test_a_scene_with_nothing_to_go_on_fails_loudly_not_silently(comp, monkeypatch):
    monkeypatch.setattr(acq, "derive_need", lambda *a, **k: {"id": "x", "query": "", "queries": [],
                                                             "media_type": "image"})
    res = acq.acquire_for_scene(comp, "01-beat", "s2")
    assert res["ok"] is False and "no query" in res["detail"]


# --- the whole path, with the organs faked --------------------------------------------------------

def test_acquire_for_scene_lands_candidates_with_provenance(comp, monkeypatch, tmp_path):
    """The full door: engine → VLM floor → scene shortlist → pool.json (APPEND, with licence intact)."""
    from PIL import Image
    src = tmp_path / "cand.jpg"
    Image.new("RGB", (120, 80), (200, 40, 40)).save(src)

    def fake_acquire_need(need, ctx, cfg, cand_dir, taken):
        assert need["media_type"] == "image"
        return [Candidate(ref="c0", source="stock:pexels", modality="image", path=src,
                          relevance=0.62,
                          meta={"license": "CC0", "photographer": "A. Person",
                                "source_url": "https://example.test/1", "source": "pexels"})]

    monkeypatch.setattr("nolan.acquire.acquire_need", fake_acquire_need)
    monkeypatch.setattr("nolan.acquire.build_context", lambda cfg, **kw: object())
    monkeypatch.setattr("nolan.config.load_config", lambda *a, **k: object())
    res = acq.acquire_for_scene(comp, "01-beat", "s2", query="an auction saleroom",
                                modality="image", vlm_floor=False, log=lambda *a: None)
    assert res["ok"] and len(res["landed"]) == 1
    name = res["landed"][0]["name"]

    pool = json.loads((acq._comp_dir(comp) / "pool.json").read_text(encoding="utf-8"))
    row = next(e for e in pool if e["file"] == name)
    assert row["license"] == "CC0" and row["photographer"] == "A. Person", \
        "licence + attribution decide whether an asset can ship — they must survive the landing"
    assert row["source_url"] == "https://example.test/1"
    assert row["relevance"] == 0.62
    assert row["scene_id"] == "s2", "a scene-scoped fetch records which beat asked for it"

    spec, info = acq.load_frame_spec(comp, "01-beat")
    sc = acq._find_scene(spec["frames"][info["i"]], "s2")
    assert any(i["name"] == name for i in sc["meta"]["shortlist"]), \
        "landed assets go to the SHORTLIST — wiring one in is a gated proposal, not a side-door"
    assert sc["data"]["ground"]["src"] == "assets/used.jpg", "the canonical spec must be untouched"


def test_acquire_for_scene_widens_clip_seconds_to_the_window(comp, monkeypatch, tmp_path):
    """The better half of the duration fix: a remote clip is FETCHED long enough for the hold rather
    than docked for being short. `clip_seconds` bounds every remote source's ffmpeg range-seek."""
    seen = {}

    def fake_build_context(cfg, **kw):
        seen.update(kw)
        return object()

    monkeypatch.setattr("nolan.acquire.build_context", fake_build_context)
    monkeypatch.setattr("nolan.acquire.acquire_need", lambda *a, **k: [])
    monkeypatch.setattr("nolan.config.load_config", lambda *a, **k: object())
    acq.acquire_for_scene(comp, "01-beat", "s1", query="a gavel falls", modality="video",
                          log=lambda *a: None)
    assert seen["clip_seconds"] >= 19, f"a 19s hold must fetch >=19s of footage, got {seen['clip_seconds']}"


def test_generation_is_off_unless_asked(comp, monkeypatch):
    """Generation is GPU work and a fleet agent runs outside the hub's in-process lock — spending the
    GPU must be a deliberate argument, never a default of 'get me an asset'."""
    seen = {}
    monkeypatch.setattr("nolan.acquire.build_context", lambda cfg, **kw: seen.update(kw) or object())
    monkeypatch.setattr("nolan.acquire.acquire_need", lambda *a, **k: [])
    monkeypatch.setattr("nolan.config.load_config", lambda *a, **k: object())
    acq.acquire_for_scene(comp, "01-beat", "s2", query="q", modality="image", log=lambda *a: None)
    assert seen["want_gen"] is False
