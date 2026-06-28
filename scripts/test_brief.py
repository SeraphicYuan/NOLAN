"""
Tests for the brief layer (nolan.brief): NL-shaped brief -> validated motion spec.

Covers the user's case-in-point — "use these 6 pictures, do a 2x3 grid, and zoom pic X
when the voiceover says 'keyword'" — proving cue->time resolution, plus a free-layout
montage exercising the motion-verb compiler (enter / fade / pan / path).
"""
import os
import sys
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

OUT = os.path.abspath("test_output/brief")
os.makedirs(OUT, exist_ok=True)
LIB = "_library/images"


def lib_images(n):
    db = sqlite3.connect(os.path.join(LIB, "catalog.db"))
    rows = db.execute("SELECT path, title FROM assets WHERE status='active' ORDER BY id LIMIT ?", (n,)).fetchall()
    db.close()
    return [{"src": os.path.abspath(os.path.join(LIB, p)), "caption": (t or "").strip().rstrip(".").title()} for p, t in rows]


def fake_words(phrase_at):
    """A scene-local transcript: a few words, with 'keyword' planted at a known time."""
    words = [("the", 0.2, 0.4), ("market", 0.5, 0.9), ("crashed", 1.0, 1.5),
             ("and", 1.6, 1.8), ("the", 1.9, 2.1), ("keyword", phrase_at, phrase_at + 0.4),
             ("appeared", phrase_at + 0.5, phrase_at + 1.1)]
    return words


def test_grid_cue_timing():
    """The headline case: 2x3 grid, focus image 4 when the VO says 'keyword'."""
    from nolan.brief import resolve_brief, SceneContext

    ctx = SceneContext(duration=6.0, words=fake_words(3.2))
    brief = {
        "kind": "photo-story", "layout": "grid", "grid": "2x3",
        "images": [i["src"] for i in lib_images(6)],
        "fly_in": "one-by-one",
        "focus": {"image": 4, "at": {"cue": "keyword"}, "hold": 1.4},
    }
    spec, msgs = resolve_brief(brief, ctx)
    print("grid messages:", msgs)
    assert spec["effect"] == "photo-grid", spec["effect"]
    assert spec["content"]["cols"] == 3 and spec["content"]["rows"] == 2
    assert spec["content"]["focusIndex"] == 4
    # the focus must land on the cue's start time (3.2s), not a guess
    assert abs(spec["style"]["focusAt"] - 3.2) < 0.05, spec["style"]["focusAt"]
    assert not [m for m in msgs if "not found" in m], msgs
    print("  OK grid: focusAt =", spec["style"]["focusAt"], "(cue 'keyword' @ 3.2s)")
    return spec


def test_missing_cue_degrades():
    from nolan.brief import resolve_brief, SceneContext
    ctx = SceneContext(duration=6.0, words=fake_words(3.2))
    brief = {"kind": "photo-story", "layout": "grid", "grid": "2x3",
             "images": [i["src"] for i in lib_images(6)],
             "focus": {"image": 0, "at": {"cue": "nonexistent"}}}
    spec, msgs = resolve_brief(brief, ctx)
    assert any("not found" in m for m in msgs), "should warn on missing cue"
    assert "focusAt" in spec["style"], "should still produce a usable spec"
    print("  OK missing-cue degrades gracefully:", [m for m in msgs if "not found" in m][0])


def test_free_verbs():
    """Free layout: motion verbs compile to keyframe tracks (enter / fade / pan / path)."""
    from nolan.brief import resolve_brief, SceneContext
    imgs = lib_images(3)
    ctx = SceneContext(duration=5.0, words=fake_words(2.5))
    brief = {
        "kind": "photo-story", "layout": "free", "background": "#241016",
        "images": [
            {"src": imgs[0]["src"], "place": [0.25, 0.5], "scale": 0.5, "caption": imgs[0]["caption"],
             "motion": [{"enter": "left", "at": "start"}, {"tilt": -6, "at": {"cue": "keyword"}}]},
            {"src": imgs[1]["src"], "place": [0.75, 0.5], "scale": 0.5, "caption": imgs[1]["caption"],
             "motion": [{"enter": "right", "at": 0.4}, {"pan": -35, "at": {"cue": "keyword"}}]},
            {"src": imgs[2]["src"], "place": [0.5, 0.3], "scale": 0.28, "frame": "plain",
             "motion": [{"fade": "in", "at": 1.0},
                        {"path": [{"to": [0.5, 0.3], "at": 1.6}, {"to": [0.5, 0.72], "at": 3.0}]},
                        {"fade": "out", "at": 4.2}]},
        ],
    }
    spec, msgs = resolve_brief(brief, ctx)
    print("free messages:", msgs)
    assert spec["effect"] == "photo-montage-pro"
    cards = spec["content"]["cards"]
    assert all("keys" in c for c in cards), "verbs should compile to keys"
    # pan verb -> a rotY key at the cue time (2.5s)
    rotY_keys = [k for k in cards[1]["keys"] if "rotY" in k]
    assert any(abs(k["at"] - 2.5) < 0.05 for k in rotY_keys), rotY_keys
    print("  OK free: card2 rotY keys", [(round(k['at'],2), k['rotY']) for k in rotY_keys])
    return spec


def main():
    render = "--render" in sys.argv
    grid_spec = test_grid_cue_timing()
    test_missing_cue_degrades()
    free_spec = test_free_verbs()
    print("\nALL BRIEF TESTS PASS")

    if render:
        from nolan.motion import render as motion_render
        import subprocess, imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        for name, spec in (("grid", grid_spec), ("free", free_spec)):
            out = os.path.abspath(f"{OUT}/brief_{name}.mp4")
            print(f"rendering {name}...")
            motion_render(spec, out)
            r = subprocess.run([ff, "-hide_banner", "-i", out], capture_output=True, text=True)
            assert "1920x1080" in r.stderr, f"{name} bad resolution"
            print(f"  -> {out}")


if __name__ == "__main__":
    main()
