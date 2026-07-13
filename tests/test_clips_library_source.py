"""clips_library acquisition source — the LOCAL video library wired into the acquire engine.

Pure wiring tests (no DB) prove the source is registered + the engine fans out to it and keeps its
video candidates; the real-DB tests prove semantic retrieval over the rich per-clip metadata and the
local-trim materialisation, and SKIP cleanly when the library/vector store isn't present."""
import shutil
from pathlib import Path

import pytest


# --- pure wiring (no DB) --------------------------------------------------------------------------
def test_clips_library_is_a_default_source():
    from nolan.acquire import AcquireConfig
    assert "clips_library" in AcquireConfig().sources


def test_clips_library_ranked_in_every_tier_above_generic_stock():
    from nolan.acquire.engine import TIERS
    for order in TIERS.values():
        assert "clips_library" in order
        # curated + local: just below the saved image library, never buried under generic stock
        assert order.index("clips_library") <= order.index("library") + 1
    assert TIERS["general"].index("clips_library") < TIERS["general"].index("pexels")


def test_context_exposes_search_clips_field():
    from nolan.acquire import Context
    assert "search_clips" in Context.__dataclass_fields__


def test_engine_fanout_invokes_search_clips_and_keeps_video(tmp_path):
    """acquire_need must call ctx.search_clips, materialise the clip via download(), and KEEP the
    (unscored) video candidate — the whole point of adding the source."""
    from nolan.acquire import Candidate, Context, AcquireConfig, acquire_need

    trimmed = tmp_path / "clip.mp4"
    trimmed.write_bytes(b"\0" * 30_000)  # >20KB so the keep-loop treats it as a real file

    def search_clips(need, n):
        return [Candidate(ref="vid#1.0", source="clips_library", modality="video", path=None,
                          relevance=0.7, meta={"source_video": "vid.mp4", "clip_start": 0.0, "clip_dur": 8.0})]

    def download(c, dest):
        c.path = trimmed
        return True

    ctx = Context(search_clips=search_clips, download=download)
    cfg = AcquireConfig(sources=("clips_library",), per_need=4)
    kept = acquire_need({"id": "n1", "query": "x", "media_type": "video", "evocative": True,
                         "category": "art"}, ctx, cfg, tmp_path, [])
    assert any(c.source == "clips_library" and c.modality == "video" and c.path == trimmed for c in kept)


def test_search_clips_not_called_when_source_disabled(tmp_path):
    from nolan.acquire import Context, AcquireConfig, acquire_need
    called = {"n": 0}

    def search_clips(need, n):
        called["n"] += 1
        return []

    ctx = Context(search_clips=search_clips)
    cfg = AcquireConfig(sources=("stock",))  # clips_library NOT enabled
    acquire_need({"id": "n1", "query": "x"}, ctx, cfg, tmp_path, [])
    assert called["n"] == 0


# --- real DB (skip if the library / vector store is absent) ---------------------------------------
def _library_db():
    try:
        from nolan.config import load_config
        db = Path(load_config().indexing.database).expanduser()
    except Exception:
        return None
    return db if (db.exists() and (db.parent / "vectors").exists()) else None


_DB = _library_db()
_needs_db = pytest.mark.skipif(_DB is None, reason="video library DB / vector store not present")


@_needs_db
def test_db_resolves_to_vectors_paired_library_regardless_of_cwd():
    """The resolver must anchor to the repo-root config's library (whose vector store exists), NOT the
    stale ~/.nolan default that load_config() falls back to when run from the bridge dir."""
    from nolan.config import load_config
    from nolan.acquire.context import _resolve_clips_db
    db = _resolve_clips_db(load_config())
    assert db is not None and db.exists() and (db.parent / "vectors").exists()


@_needs_db
def test_retrieval_leverages_rich_metadata():
    """A beat's meaning must retrieve the footage that MEANS the same thing, carrying the rich
    per-clip description/similarity — not a filename match."""
    from nolan.config import load_config
    from nolan.acquire import build_context

    ctx = build_context(load_config(), clip_seconds=8, want_stock=False, want_library=False,
                        want_clip=False, want_gen=False, want_clips_library=True,
                        clip_lib_max=4, clip_lib_min_sim=0.0)
    assert ctx.search_clips is not None
    cands = ctx.search_clips({"id": "t", "query": "Odysseus and the ancient Greek epic",
                              "queries": ["Odysseus and the ancient Greek epic poem"]}, 4)
    assert cands, "expected library clips for an on-topic Homer query"
    for c in cands:
        assert c.source == "clips_library" and c.modality == "video"
        assert c.relevance > 0 and c.meta.get("description") and c.meta.get("source_video")


@_needs_db
def test_download_trims_a_local_clip(tmp_path):
    from nolan.config import load_config
    from nolan.acquire import build_context

    ctx = build_context(load_config(), clip_seconds=6, want_stock=False, want_library=False,
                        want_clip=False, want_gen=False, want_clips_library=True,
                        clip_lib_max=2, clip_lib_min_sim=0.0)
    cands = ctx.search_clips({"id": "t", "query": "ancient Greek warship at sea",
                              "queries": ["ancient Greek warship sailing on the ocean"]}, 2)
    if not cands:
        pytest.skip("no candidates to trim")
    assert ctx.download(cands[0], tmp_path) is True
    p = cands[0].path
    assert p and p.exists() and p.stat().st_size > 20_000
