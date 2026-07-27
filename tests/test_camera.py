"""The camera umbrella — registry / solver / emitter / selector.

The properties here are the ones a finished video depends on. A black edge, a move that outlives its
beat, or a tween the seeking renderer cannot evaluate are all defects you only see after a 25-minute
render, which is exactly why they are pinned at this level instead.
"""
import itertools
import re

import pytest

from nolan import camera
from nolan.camera import registry, select, solve


# --- registry -------------------------------------------------------------------------------------

def test_every_move_is_executable():
    """A registered move that `plan()` cannot resolve is a catalog lie (pitfall #1 in the camera's own
    umbrella): the menu offers something the executor does not build."""
    for mid in registry.MOVES:
        p = camera.plan(mid, dur=8.0, target=(0.5, 0.5), box=(0.3, 0.3, 0.2, 0.2), img=(3000, 2000))
        assert p["move"] in registry.MOVES, mid
        assert "from" in p and "to" in p and "notes" in p


def test_every_move_declares_when_to_use_and_a_family():
    for mid, m in registry.MOVES.items():
        assert m.family in registry.FAMILIES, mid
        assert len(m.when_to_use) > 30, f"{mid}: when_to_use must actually route a decision"
        assert len(m.purpose) > 10, mid


def test_a_move_whose_need_is_unmet_degrades_and_says_so():
    mv, why = registry.degrade("parallax", available={"target"})      # no cutout
    assert mv == "push-in" and why and "parallax" in why
    mv, why = registry.degrade("push-to-detail", available={"target"})  # no box
    assert mv == "push-in" and why
    mv, why = registry.degrade("push-in", available={"target"})
    assert mv == "push-in" and why is None


def test_degrade_never_raises_and_never_loops():
    for mid in registry.MOVES:
        mv, _ = registry.degrade(mid, available=set())
        assert mv in registry.MOVES
    assert registry.degrade("not-a-move", available=set())[0] == "push-in"


# --- the amplitude law ----------------------------------------------------------------------------

def test_amplitude_scales_with_the_beat():
    """The dead-long-hold fix: a 16s beat must travel further than a 4s one, and both are capped."""
    short, long = solve.scale_amplitude(4.0), solve.scale_amplitude(16.0)
    assert short < long
    assert solve.scale_amplitude(120.0) <= 0.16 and solve.scale_amplitude(0.5) >= 0.05


def test_amplitude_is_monotonic():
    vals = [solve.scale_amplitude(d) for d in range(1, 40)]
    assert all(b >= a for a, b in zip(vals, vals[1:]))


# --- the solver: the property that matters --------------------------------------------------------

def _exposes_edge(kf, canvas=(1920, 1080)):
    """A keyframe exposes an edge when it translates further than the scale's overscan allows."""
    w, h = canvas
    s = kf["scale"]
    ox, oy = w * (s - 1) / 2, h * (s - 1) / 2
    return abs(kf["x"]) > ox + 0.51 or abs(kf["y"]) > oy + 0.51


def test_no_framing_ever_exposes_an_edge():
    """Swept across targets, durations and directions — including targets in the corners, which is
    where a naive 'centre the subject' lands you outside the image."""
    targets = [None] + [(x, y) for x in (0.0, 0.05, 0.5, 0.95, 1.0) for y in (0.0, 0.5, 1.0)]
    for dur, t in itertools.product((1.0, 4.0, 9.0, 17.0, 40.0), targets):
        for p in (camera.plan("push-in", dur=dur, target=t),
                  camera.plan("pull-out", dur=dur, target=t),
                  camera.plan("drift", dur=dur, target=t)):
            for k in ("from", "to"):
                assert not _exposes_edge(p[k]), (p["move"], dur, t, k, p[k])
    for dur, d in itertools.product((2.0, 8.0, 30.0), ("right", "left", "down", "up")):
        p = camera.plan(f"pan-{d}", dur=dur)
        for k in ("from", "to"):
            assert not _exposes_edge(p[k]), (d, dur, k, p[k])


def test_an_unreachable_target_is_clamped_AND_reported():
    """Silent clamping is the 'no silent caps' violation — the camera must say it did less."""
    p = camera.plan("push-in", dur=10.0, target=(0.02, 0.98))
    assert p["notes"], "a clamped framing reported nothing"
    assert any("unreachable" in n or "clamped" in n for n in p["notes"])


def test_a_push_that_ARRIVES_reports_nothing():
    """The other half of "no silent caps": a note that always fires is a note nobody reads.

    On the v3 end-to-end, 6 of 7 pushes carried a clamp line — every one of them describing a move
    working exactly as designed. Two causes, both fixed: the note was computed on BOTH keyframes, and
    the opening keyframe of a push sits at ~1.01 where the overscan is half a percent of the frame and
    no target can be centred (arriving is the whole point of a push); and a `> 0.5px` threshold called
    a 2px shortfall a clamp. It now reports the RESTING framing, and only a miss the eye could catch.
    """
    # the common case: a contrast centroid lands near centre, and the push reaches it
    for t in ((0.5, 0.5), (0.54, 0.48), (0.47, 0.52), (0.52, 0.53)):
        assert not camera.plan("push-in", dur=9.0, target=t)["notes"], t
    # a target the scale genuinely cannot reach still says so
    assert camera.plan("push-in", dur=9.0, target=(0.62, 0.40))["notes"]
    # a pull-out RESTS wide, which is where it can least reach — that end is the one that reports
    assert not camera.plan("pull-out", dur=9.0, target=(0.51, 0.48))["notes"]
    assert camera.plan("pull-out", dur=9.0, target=(0.05, 0.95))["notes"]
    # and the scale cap is a different note, never suppressed
    assert any("cap" in n for n in camera.plan("push-in", dur=90.0, amount=0.9)["notes"])


def test_the_box_sets_the_scale_not_the_amplitude_law():
    """A small logo must be pushed into much harder than a half-frame face — that is what a box buys."""
    small = camera.plan("push-to-detail", dur=8.0, box=(0.42, 0.42, 0.08, 0.08))
    big = camera.plan("push-to-detail", dur=8.0, box=(0.2, 0.2, 0.6, 0.6))
    assert small["to"]["scale"] > big["to"]["scale"]
    assert small["to"]["scale"] <= solve.SCALE_CAP


def test_a_tall_source_pans_its_real_long_axis():
    """Cover-fit crops a poster to a centre band, so panning the crop can never reveal the top. The
    long-axis mode sizes the element to the full image instead."""
    p = camera.plan("pan-down", dur=10.0, img=(2400, 7200))     # a real poster scan
    assert p["mode"] == "long-axis" and p["element_height"] > 1080
    assert p["from"]["y"] != p["to"]["y"]
    assert camera.emit_style(p).startswith("height:")
    wide = camera.plan("pan-down", dur=10.0, img=(4000, 1400))
    assert wide["mode"] == "cover"                    # a wide source has no long axis to reveal


def test_a_long_axis_pan_frames_the_PICTURE_not_the_FILE():
    """f09 shipped a pan across a photographed ad and travelled over the ad's own black surround.

    The first fix was a symmetric 6% overscan — an invented number against a measured problem. That
    source carries 7.7% black on the left and 11.8% on the right (asymmetric: the page is photographed
    askew), so 6% could not remove it, and on a source with NO border the same 6% quietly cropped real
    picture. The geometry now solves against a measured content box, and both halves of that matter:
    """
    img = (1536, 1600)
    bordered = camera.plan("pan-down", dur=16.0, img=img, content=(0.06, 0.03, 0.94, 1.0))
    # the content, not the file, spans the canvas — so the element is wider by exactly the border
    assert bordered["element_width"] > 1920 * 1.05, bordered
    assert bordered["element_left"] < -50, "the left border is not being pushed off-frame"
    # and the pan STARTS below the top border rather than on it
    assert bordered["from"]["y"] < -1.0, bordered["from"]
    assert any("surround" in n for n in bordered["notes"]), bordered["notes"]

    # a source with no border must be left alone — only the sub-pixel bleed
    clean = camera.plan("pan-down", dur=16.0, img=img, content=(0.0, 0.0, 1.0, 1.0))
    assert abs(clean["element_width"] - 1920 * solve.LONG_AXIS_BLEED) < 1.0, clean
    assert not [n for n in clean["notes"] if "surround" in n]
    # …and omitting the measurement entirely behaves exactly like an unbordered source
    assert camera.plan("pan-down", dur=16.0, img=img)["element_width"] == clean["element_width"]


def test_a_narrow_source_will_not_fake_a_long_axis_pan():
    """Long-axis is width-fit, so the floor there is 'at least canvas-wide' — a different question
    from the cover-mode upscale, and asking the wrong one holds on the move that was actually right."""
    p = camera.plan("pan-down", dur=10.0, img=(500, 2700))       # 3.8x width-fit — genuine mush
    assert p["move"] == "hold" and any("width-fit" in n for n in p["notes"])
    ok = camera.plan("pan-down", dur=10.0, img=(1024, 3000))      # 1.9x — no worse than standing still
    assert ok["mode"] == "long-axis" and ok["move"] == "pan-down", ok["notes"]


def test_a_low_res_source_holds_instead_of_upscaling():
    """~10 library sources are still 360p. Pushing into one is mush; say so and hold."""
    p = camera.plan("push-in", dur=12.0, img=(640, 360))
    assert p["move"] == "hold" and any("upscale" in n for n in p["notes"])
    ok = camera.plan("push-in", dur=12.0, img=(3840, 2160))
    assert ok["move"] == "push-in" and not any("upscale" in n for n in ok["notes"])
    # the common case must survive: a 1920x1080 stock still takes a normal push. At a 2% tolerance
    # the floor switched the whole feature off across most of a real pool.
    stock = camera.plan("push-in", dur=12.0, img=(1920, 1080))
    assert stock["move"] == "push-in", stock["notes"]
    # the REAL pool's shapes must move: these are actual diamond-v2 assets that the delta-based floor
    # held, each already softer than its own move while standing perfectly still.
    for real in ((1024, 1024), (1024, 602), (900, 508), (1536, 1600), (1179, 786)):
        p = camera.plan("push-in", dur=12.0, img=real)
        assert p["move"] != "hold", (real, p["notes"])
    # and the genuinely tiny still holds
    for tiny in ((492, 640), (510, 1072), (640, 360)):
        assert camera.plan("push-in", dur=12.0, img=tiny)["move"] == "hold", tiny


# --- the emitter ----------------------------------------------------------------------------------

def test_a_move_is_a_fraction_of_its_beat_never_a_literal():
    """`_layout_cell`'s `duration:6` is the bug this forbids: it froze on a long beat and was cut on a
    short one."""
    for dur in (3.0, 8.0, 21.0):
        line = camera.emit("#g", camera.plan("push-in", dur=dur), 5.0, dur)[0]
        d = float(re.search(r"duration:([\d.]+)", line).group(1))
        assert abs(d - dur) < 0.01, (dur, line)


def test_a_cue_makes_the_move_ARRIVE_on_the_word():
    line = camera.emit("#g", camera.plan("push-in", dur=12.0), 10.0, 12.0, cue=15.0)[0]
    assert 'ease:"power2.out"' in line                      # decelerating into the word
    assert abs(float(re.search(r"duration:([\d.]+)", line).group(1)) - 5.0) < 0.01
    assert line.rstrip().endswith(",10.00);")               # …starting at the scene, not the cue


def test_a_cue_outside_the_beat_is_ignored():
    line = camera.emit("#g", camera.plan("push-in", dur=6.0), 10.0, 6.0, cue=99.0)[0]
    assert 'ease:"power1.inOut"' in line


def test_emitted_tweens_are_seek_safe():
    """The renderer seeks; it never plays. Anything whose state is not a pure function of timeline
    progress is a wrong frame."""
    lines = []
    for mid in registry.MOVES:
        lines += camera.emit("#g", camera.plan(mid, dur=9.0, target=(0.5, 0.5),
                                               box=(0.3, 0.3, 0.2, 0.2)), 2.0, 9.0)
    lines += camera.emit_blur("#g", 2.0, 9.0)
    lines += camera.emit_punch("#g", camera.plan("punch-in", dur=9.0), 4.0)
    assert lines
    for l in lines:
        assert not re.search(r"\brepeat\b|\byoyo\b|Math\.random|Date\.now", l), l
        assert re.search(r",\s*[\d.]+\);\s*$", l), f"no absolute time: {l}"
        assert "duration:" in l


def test_hold_emits_nothing():
    assert camera.emit("#g", camera.plan("hold", dur=9.0), 0.0, 9.0) == []


# --- the selector ---------------------------------------------------------------------------------

def test_narration_picks_the_move():
    assert select.select(narration="but it turns out the whole thing was invented", dur=9)[0] == "pull-out"
    assert select.select(narration="look at this detail in her hands", dur=9)[0] == "push-in"
    assert select.select(narration="the journey from Kimberley to London", dur=9)[0].startswith("pan-")
    assert select.select(narration="and then everything stops", dur=9)[0] == "hold"


def test_word_boundaries_are_respected():
    """' but ' must not fire on 'buttress' — the substring version of this rule is a false-positive
    machine."""
    mv, _ = select.select(narration="the flying buttress above the nave", dur=9)
    assert mv != "pull-out"


def test_two_consecutive_stills_never_share_a_family():
    mv, why = select.select(narration="look at this face", dur=9, prev_family="push")
    assert registry.family_of(mv) != "push", (mv, why)
    assert "alternated" in why


def test_a_short_beat_will_not_glide():
    assert select.select(narration="look at this", dur=2.0)[0] == "punch-in"
    assert select.select(narration="ordinary sentence", dur=2.0)[0] == "hold"


def test_hold_is_reachable_and_gets_chosen():
    """A system that always moves is as monotonous as one that never does."""
    picks = {select.select(narration=n, dur=d)[0]
             for n, d in [("silence", 8), ("x", 2), ("everything stops", 12)]}
    assert "hold" in picks


def test_the_selector_explains_itself():
    for narration in ("look at this detail", "but the whole empire", "a plain sentence"):
        mv, why = select.select(narration=narration, dur=8)
        assert why and len(why) > 8, (mv, why)


def test_an_authored_lock_wins():
    mv, why = select.select(narration="but everything changed", dur=9, authored="pan-left")
    assert mv == "pan-left" and "authored" in why


@pytest.mark.parametrize("img,expect", [((2400, 7200), "pan-down"), ((4000, 1400), None)])
def test_a_tall_source_overrides_sentiment(img, expect):
    mv, _ = select.select(narration="look at this detail", dur=9, img=img)
    if expect:
        assert mv == expect
    else:
        assert mv != "pan-down"
