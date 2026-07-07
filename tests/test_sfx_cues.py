"""SFX auto-cue pass + content-cued shot cadence (diversity round 2b).

Pins: keyword→ambience mapping, discipline rules (visual scenes only,
human sfx wins, per-section cap, min gap, low volume), and enumeration
narration requesting shot cadence at ANY energy.
"""

from nolan.audio_mix import author_sfx_cues
from nolan.tempo_plan import _enumeration_shots


def _scene(sid, text, t0, **kw):
    s = {"id": sid, "narration_excerpt": text, "start_seconds": t0,
         "end_seconds": t0 + 8, "matched_asset": "a.jpg"}
    s.update(kw)
    return s


def test_cues_map_content_to_ambience():
    plan = {"sections": {"a": [
        _scene("s1", "the manuscript was to be burned, thrown to the flames", 0),
        _scene("s2", "the fleet sailed for the open sea", 30),
    ]}}
    cues = author_sfx_cues(plan)
    assert ("s1", "fire crackling ambience") in cues
    assert ("s2", "ocean waves ambience") in cues
    sfx = plan["sections"]["a"][0]["sfx"]
    assert sfx["volume"] <= 0.25 and sfx["at"] == 0.0   # ambience, not an event


def test_discipline_rules():
    plan = {"sections": {"a": [
        # human cue wins
        _scene("s1", "fire everywhere", 0, sfx={"query": "my own", "at": 1}),
        # text scene stays clean
        {"id": "s2", "narration_excerpt": "fire and storm",
         "start_seconds": 10, "end_seconds": 16},
        # too close to the previous cue (min gap)
        _scene("s3", "the storm broke over the sea", 12),
        _scene("s4", "wind over the plain", 40),
        _scene("s5", "horses and riders in the rain", 70),
        _scene("s6", "bells rang over the crowd", 100),   # over per-section cap
    ]}}
    cues = author_sfx_cues(plan, max_per_section=2, min_gap_s=20)
    ids = [c[0] for c in cues]
    assert "s1" not in ids                     # human authored — untouched
    assert plan["sections"]["a"][0]["sfx"] == {"query": "my own", "at": 1}
    assert "s2" not in ids                     # no visual
    assert ids == ["s4", "s5"]                 # s3 gap-blocked... cap at 2
    assert "s6" not in ids


def test_no_match_no_cue():
    plan = {"sections": {"a": [
        _scene("s1", "scholars have long said the poem speaks in two voices", 0)]}}
    assert author_sfx_cues(plan) == []
    assert "sfx" not in plan["sections"]["a"][0]


# --- enumeration → shot cadence -------------------------------------------------

def test_enumeration_requests_montage():
    assert _enumeration_shots(
        "the lovers left behind, the young men killed, the price a man pays, "
        "the cost of empire") == 3
    assert _enumeration_shots(
        "not an aristocrat, not a soldier, and not a rich man either") == 3
    assert _enumeration_shots("a single quiet thought") == 0
    assert _enumeration_shots("one, two") == 0            # too short to montage
