"""Gate on what is IN THE PIXELS, not on what the menu's caption claims.

Four defects shipped into the-diamond-illusion-v2's pool, from THREE distinct holes — fixing only the
prompt would have closed one of them:

  1. `clips_library` clips SKIPPED the VLM entirely ("pre-captioned + curated"), so a talking head
     shipped captioned as a "digital stock market ticker" and a clip hard-subbed with another
     creator's subtitles shipped clean. Their stored description describes the SOURCE video, not the
     range we trimmed.
  2. `pexels_video` a24_06 WAS judged and scored usable=8.0 — because `usable` rates how CUTTABLE a
     shot is, never whether it DEPICTS the beat. A bowl of food under "a dim prison cell".
  3. The HERO path (`keyassets._verify_video`) asked subject-match only, so a scraped upload with a
     FOLLOW button, SUBSCRIBED chrome and "@diamondtrends.net" burned in passed — it did show a
     diamond. Our menu labelled it "archive; Internet Archive".
"""
import inspect
from pathlib import Path

from nolan.acquire.judge import (SCRAPED_SOURCES, caption_verified, is_junk, is_scraped, judge_prompt,
                                 parse_verdict)

SRC = Path(__file__).resolve().parents[1] / "src" / "nolan"
BRIDGE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"


# --- hole 3: chrome is disqualifying on its own -----------------------------------------------

def test_chrome_is_junk_at_any_usability_score():
    assert is_junk({"usable": 10.0, "chrome": True})
    assert is_junk({"usable": 9.5, "flags": "", "chrome": True})


def test_chrome_unanswered_never_drops_the_asset():
    """A dead VLM must not empty the pool — the cheap gates already ran."""
    assert not is_junk({"usable": None, "chrome": None})
    assert not is_junk({"usable": 8.0, "chrome": None})


def test_the_prompt_asks_for_chrome_and_depicts():
    p = judge_prompt({"query": "a dim prison cell"}, video=True)
    assert '"chrome"' in p and '"depicts"' in p
    for cue in ("watermark", "subscribe", "lower-third"):
        assert cue in p.lower()


def test_hero_path_rejects_chrome_regardless_of_subject_match():
    src = inspect.getsource(__import__("nolan.keyassets.resolve", fromlist=["x"])._verify_video)
    assert "_has_chrome" in src
    # it must short-circuit BEFORE the subject match can accept the frame
    assert src.index("_has_chrome") < src.index("_verify_match")


# --- hole 2: usable != depicts ------------------------------------------------------------------

def test_depicts_is_parsed_tri_state():
    assert parse_verdict({"depicts": True})["depicts"] is True
    assert parse_verdict({"depicts": "false"})["depicts"] is False
    assert parse_verdict({})["depicts"] is None


def test_a_usable_but_wrong_asset_is_kept_and_flagged_not_dropped():
    """a24_06 was good footage of the wrong thing. Dropping good b-roll is wasteful; shipping a WRONG
    caption is worse — the author picks by caption and places it on a beat it doesn't illustrate."""
    v = parse_verdict({"usable": 8.0, "depicts": False, "caption": "a hand holding a bowl of food"})
    assert not is_junk(v)                       # still usable footage
    assert caption_verified(v) is False         # …but the claim about it failed


# --- hole 1: scraped sources are never exempt ---------------------------------------------------

def test_is_scraped_covers_both_scraped_sources_and_nothing_else():
    assert set(SCRAPED_SOURCES) == {"clips_library", "transcript_lib"}
    assert is_scraped("clips_library (local)") and is_scraped("transcript_lib (youtube)")
    for clean in ("pexels_video", "pixabay_video", "krea2 (generated)", "met", "artvee"):
        assert not is_scraped(clean)


def test_pool_no_longer_exempts_library_clips_from_the_vlm():
    """REGRESSION: an early-return on `clips_library` set usable=True and skipped the filmstrip.

    Reads `nolan/acquire/vlm_floor.py`, not the bridge: the floor MOVED out of the CLI script into the
    acquire organ so the edit-loop's scene-scoped acquisition could reach it too (it had no floor at
    all, and landed clips with burned-in subtitles). The bridge now delegates."""
    src = (SRC / "acquire" / "vlm_floor.py").read_text(encoding="utf-8")
    body = src[src.index("async def judge(item)"):src.index("await asyncio.gather")]
    assert 'item.setdefault("usable", True)' not in body, "the blanket VLM exemption is back"
    assert "content_kind\", \"broll\")" not in body


def test_pool_records_origin_and_caption_verification():
    src = (SRC / "acquire" / "vlm_floor.py").read_text(encoding="utf-8")
    for field in ("origin_verified", "caption_verified", "chrome"):
        assert field in src, f"pool.json must carry `{field}` provenance"


def test_the_author_menu_surfaces_both_verdicts():
    from nolan.hyperframes.pool_select import render_inventory_lines
    line = render_inventory_lines([{
        "file": "videos/a1.mp4", "media_type": "video", "caption": "vault", "id": "a1",
        "source": "transcript_lib (youtube)", "origin_verified": False, "caption_verified": False}])[-1]
    assert "UNVERIFIED ORIGIN" in line and "caption unverified" in line


def test_a_clean_verified_asset_carries_no_scare_tags():
    from nolan.hyperframes.pool_select import render_inventory_lines
    line = render_inventory_lines([{
        "file": "b.jpg", "media_type": "image", "caption": "a clean still", "id": "a2",
        "source": "pexels", "caption_verified": True}])[-1]
    assert "UNVERIFIED" not in line and "unverified" not in line
