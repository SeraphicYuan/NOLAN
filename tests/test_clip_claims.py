"""The clip CLAIM ledger — the one dedup channel between the hero pool (keyassets) and the b-roll pool
(acquire). Both materialise clips by downloading a RANGE of a source URL in separate passes over the same
project, so without this the same shot lands twice under two names and both reach the author's menu."""
from nolan.acquire.shared import claims_path, load_claims, range_is_claimed, record_claim


def test_claim_roundtrip_and_overlap_detection(tmp_path):
    assert load_claims(tmp_path) == []                       # no ledger yet → nothing claimed
    record_claim(tmp_path, url="https://yt/x", start=100.0, dur=30.0, owner="hero", file="ka_x.mp4")
    assert claims_path(tmp_path).exists()
    claims = load_claims(tmp_path)
    assert len(claims) == 1 and claims[0]["owner"] == "hero"

    # the SAME shot with slightly different in/out points is a duplicate (in/out rarely match exactly)
    dup = range_is_claimed(claims, "https://yt/x", 105.0, 30.0)
    assert dup and dup["file"] == "ka_x.mp4"
    # a different part of the same video is NOT
    assert range_is_claimed(claims, "https://yt/x", 400.0, 30.0) is None
    # a different video at the same timecode is NOT
    assert range_is_claimed(claims, "https://yt/other", 100.0, 30.0) is None


def test_overlap_threshold_is_share_of_the_shorter_window(tmp_path):
    record_claim(tmp_path, url="https://a/v", start=0.0, dur=30.0, owner="pool", file="a1.mp4")
    claims = load_claims(tmp_path)
    # a 6s clip fully inside the claimed 30s window: 100% of the shorter window → duplicate
    assert range_is_claimed(claims, "https://a/v", 10.0, 6.0)
    # 3s of a 30s window overlapping the tail: 10% of the shorter → distinct enough to keep
    assert range_is_claimed(claims, "https://a/v", 27.0, 30.0) is None


def test_missing_url_and_corrupt_ledger_are_survivable(tmp_path):
    assert range_is_claimed([], "", 0, 10) is None
    record_claim(tmp_path, url="", start=0, dur=5, owner="pool")   # no url → not recorded, no crash
    assert load_claims(tmp_path) == []
    claims_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    claims_path(tmp_path).write_text("{not json", encoding="utf-8")
    assert load_claims(tmp_path) == []                        # unreadable ledger → empty, never raises


def test_rebuilding_a_pool_releases_its_own_claims_but_not_the_heroes(tmp_path):
    """The ledger is append-only, so a pool REBUILD must release its own ranges first — otherwise the
    second acquisition sees them as taken, skips them, and looks like the source went dry."""
    from nolan.acquire.shared import clear_claims
    record_claim(tmp_path, url="https://yt/hero", start=0, dur=20, owner="hero", file="ka_a.mp4")
    record_claim(tmp_path, url="https://yt/b1", start=0, dur=20, owner="pool", file="a1_00.mp4")
    record_claim(tmp_path, url="https://yt/b2", start=0, dur=20, owner="pool", file="a2_00.mp4")

    assert clear_claims(tmp_path, "pool") == 2
    left = load_claims(tmp_path)
    assert [c["owner"] for c in left] == ["hero"]                  # heroes survive a pool rebuild
    assert range_is_claimed(left, "https://yt/b1", 0, 20) is None  # b-roll ranges are re-acquirable
    assert range_is_claimed(left, "https://yt/hero", 0, 20)        # …and the pool still defers to heroes


def test_clearing_an_owner_with_no_claims_is_a_no_op(tmp_path):
    from nolan.acquire.shared import clear_claims
    record_claim(tmp_path, url="https://yt/hero", start=0, dur=20, owner="hero", file="ka_a.mp4")
    assert clear_claims(tmp_path, "pool") == 0
    assert len(load_claims(tmp_path)) == 1


def test_transcript_lib_reads_claims_lazily_not_at_context_build(tmp_path, monkeypatch):
    """REGRESSION (cost 8 of 9 pooled transcript_lib clips): the acquire context SNAPSHOTTED the claim
    ledger when it was built, but the caller releases the previous build's claims AFTER building it. So a
    rebuild ran against 93 stale claims and skipped nearly every candidate as 'already taken'. Reading
    lazily makes correctness independent of call order — assert the source does exactly that."""
    import inspect

    from nolan.acquire import context as ctx_mod
    src = inspect.getsource(ctx_mod.build_context)
    body = src[src.index("want_transcript_lib:"):]
    search_fn = body[body.index("def _search_transcript_lib"):]
    assert "load_claims(project_dir)" in search_fn, "claims must be read INSIDE the per-need search"
    # …and never hoisted into the enclosing context build
    before_search = body[:body.index("def _search_transcript_lib")]
    assert "load_claims(" not in before_search, "claim ledger must not be snapshotted at context-build time"


def test_pool_releases_claims_before_building_the_context(tmp_path):
    """Belt-and-braces on the same bug: the release must precede the context build at the call site."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"
           / "pool.py").read_text(encoding="utf-8")
    assert src.index('clear_claims(project, "pool")') < src.index("ctx = build_context(")
