"""The composer↔camera seam: every ground move comes from the ONE emitter.

Before this, four blocks hand-wrote their own ken-burns and had already drifted apart — `media_ground`
1.03→1.08, `_data_ground` 1.03→1.10, carousel 1.05→1.16, and `_layout_cell` a literal `duration:6`.
All linear, all about the centre, none scaled to the beat. These tests are what stops a fifth from
being written.
"""
import re
import sys
from pathlib import Path

import pytest

BRIDGE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"
SRC = (BRIDGE / "compose.py").read_text(encoding="utf-8")
sys.path.insert(0, str(BRIDGE))
import compose  # noqa: E402


def _ground_tl(dur=10.0, start=0.0, **ground):
    g = dict({"kind": "image", "src": "assets/x.jpg"}, **ground)
    return compose.media_ground("s1", g, start, dur)


# The MEDIA PLATES a camera can move. Explicit, because the two obvious automatic discriminators both
# fail: matching every `scale:` tween catches element ENTRANCES (a badge popping 0->1 in 0.45s, which is
# not a camera), and matching only the selectors I happened to remember is how `detail_zoom` — the one
# block that IS a camera — slipped through on `-cam` with a literal 0.95s leg. Add a new media layer
# here when you add one; the assertion below is what makes forgetting expensive.
_MEDIA_SELECTORS = ("-gnd", "-dgnd", "-img", "-cam", "-fg", "-media")

# KNOWN DEFERRED, stated rather than hidden: `geo`'s `-plane` / `-world` tweens are a MAP camera moving
# in projection space between locations. The registry models a picture plane, not a map, so porting it
# is real work rather than a rename — and pretending otherwise by widening the list would make this
# test lie. See docs/CAMERA_PROGRAM.md "Not yet built".
_MAP_CAMERA = ("-plane", "-world")


def test_no_block_hand_writes_a_camera_tween_any_more():
    """A camera move on a media plate must come from the module, and must not carry a literal duration."""
    offenders = []
    for m in re.finditer(r'tl\.(?:to|fromTo)\("#\{([^"]*)"[^;]*?\bscale:', SRC):
        sel = m.group(1)
        if not any(k in sel for k in _MEDIA_SELECTORS) or any(k in sel for k in _MAP_CAMERA):
            continue
        line = SRC[SRC.rfind("\n", 0, m.start()) + 1:SRC.find("\n", m.start())]
        if "_camera_for" in line:
            continue
        if re.search(r"duration:\s*[\d.]+\s*[,}]", line):       # a LITERAL, not a computed fraction
            offenders.append(line.strip()[:110])
    assert not offenders, f"camera tweens with a literal duration: {offenders}"


def test_the_map_camera_is_the_only_declared_exception():
    """If someone ports geo into the registry, this test should start failing — that is the point."""
    hits = [m.group(0) for m in re.finditer(r'tl\.to\("#\{sid\}-(?:plane|world)"[^;]*duration:[\d.]+', SRC)]
    assert hits, ("the map camera no longer hand-writes its tweens — remove it from _MAP_CAMERA and "
                  "from the 'Not yet built' list in docs/CAMERA_PROGRAM.md")


def test_the_ground_moves_and_the_move_is_eased():
    _frag, tl = _ground_tl(dur=12.0)
    cam = [t for t in tl if "-gnd" in t and "scale" in t]
    assert cam, "no camera tween emitted for an image ground"
    assert 'ease:"none"' not in cam[0], "linear is the PowerPoint tell"
    assert re.search(r'ease:"power', cam[0])


def test_amplitude_follows_the_beat_through_the_composer():
    """The dead-long-hold fix, end to end: a 17s hold must travel further than a 4s one."""
    def travel(dur):
        compose._CAMERA_PREV_FAMILY = None       # alternation is per-frame state; isolate the measure
        _f, tl = _ground_tl(dur=dur)
        line = next(t for t in tl if "-gnd" in t)
        a, b = (float(x) for x in re.findall(r"scale:([\d.]+)", line)[:2])
        return abs(b - a)
    assert travel(17.0) > travel(4.0) * 1.4, (travel(4.0), travel(17.0))


def test_legacy_kb_no_longer_freezes_the_amount():
    """Every `kb` in the tree is an authoring default, not a tuned value. It still says WHETHER to
    move; the amplitude law says how far."""
    compose._CAMERA_PREV_FAMILY = None
    _f, long_tl = _ground_tl(dur=17.0, kb=[1.02, 1.1])
    line = next(t for t in long_tl if "-gnd" in t)
    a, b = (float(x) for x in re.findall(r"scale:([\d.]+)", line)[:2])
    assert abs(b - a) > 0.085, f"the 8% default is still governing a 17s hold: {line}"


def test_kb_false_still_means_hold():
    _frag, tl = _ground_tl(dur=10.0, kb=False)
    assert not [t for t in tl if "-gnd" in t and "scale" in t]


def test_camera_none_is_an_explicit_hold():
    _frag, tl = _ground_tl(dur=10.0, camera="none")
    assert not [t for t in tl if "-gnd" in t and "scale" in t]


def test_an_authored_move_is_honoured():
    compose._CAMERA_PREV_FAMILY = None
    _frag, tl = _ground_tl(dur=10.0, camera={"move": "pan-left"})
    line = next(t for t in tl if "-gnd" in t)
    xs = [float(v) for v in re.findall(r"x:(-?[\d.]+)", line)]
    assert xs and xs[0] < xs[1], f"pan-left should travel right→left: {line}"


def test_the_narration_reaches_the_selector():
    """Without this the cue rules can never fire, and every ground gets the same default push."""
    assert 'narration=str(sc.get("anchor")' in SRC
    compose._CAMERA_PREV_FAMILY = None
    _frag, tl = compose.media_ground("s1", {"kind": "image", "src": "assets/x.jpg"}, 0.0, 12.0,
                                     narration="but it turns out the whole market was invented")
    line = next(t for t in tl if "-gnd" in t)
    a, b = (float(x) for x in re.findall(r"scale:([\d.]+)", line)[:2])
    assert a > b, f"'but … the whole' should PULL OUT (start tight, widen): {line}"


def test_consecutive_grounds_do_not_repeat_a_family():
    """The aeneid note — 'every image got the same push'. State lives on the composer for the frame."""
    compose._CAMERA_PREV_FAMILY = None
    fams = []
    for i in range(4):
        _f, tl = compose.media_ground(f"s{i}", {"kind": "image", "src": "assets/x.jpg"}, i * 10.0, 9.0)
        line = next(t for t in tl if "-gnd" in t)
        xs = [float(v) for v in re.findall(r"x:(-?[\d.]+)", line)]
        fams.append("lateral" if xs and abs(xs[0]) > 1 else "push")
    assert len(set(fams)) > 1, f"the camera repeated one family across a frame: {fams}"


def test_a_video_ground_gets_no_transform():
    """A root-mounted clip moves itself; transforming the transparent hole would move the scrim."""
    _frag, tl = compose.media_ground("s1", {"kind": "video", "src": "assets/v.mp4"}, 0.0, 8.0)
    assert not [t for t in tl if "scale" in t]


def test_parallax_emits_two_layers_at_different_rates(tmp_path, monkeypatch):
    """One plate at two speeds is just a push — the RATE DIFFERENCE is the depth."""
    from PIL import Image
    src = tmp_path / "shot.jpg"
    Image.new("RGB", (3000, 2000), (180, 180, 180)).save(src)
    fg = tmp_path / "shot.fg.png"
    Image.new("RGBA", (3000, 2000), (0, 0, 0, 255)).save(fg)
    monkeypatch.setitem(compose.__dict__, "_ASSET_BASE", tmp_path)
    from nolan.camera import target as ct
    monkeypatch.setattr(ct, "cutout_path", lambda p, cache=True: fg)
    monkeypatch.setattr(ct, "subject_point", lambda p, cache=True: (0.5, 0.5))

    frag, tl = compose.media_ground("s1", {"kind": "image", "src": "shot.jpg",
                                           "camera": {"move": "parallax"}}, 0.0, 10.0)
    html = "".join(frag)
    assert 's1-fg' in html, "no foreground layer emitted"
    gnd = next(t for t in tl if '"#s1-gnd"' in t and "scale" in t)
    sub = next(t for t in tl if '"#s1-fg"' in t and "scale" in t)
    g0, g1 = (float(x) for x in re.findall(r"scale:([\d.]+)", gnd)[:2])
    s0, s1 = (float(x) for x in re.findall(r"scale:([\d.]+)", sub)[:2])
    assert abs(s1 - s0) > abs(g1 - g0) * 1.5, "the subject must travel further than the ground"
    assert any("blur(" in t and "#s1-gnd" in t for t in tl), "the background should soften behind it"


def test_parallax_without_a_cutout_degrades_to_a_push(monkeypatch):
    """A missing matte costs the depth, never the render."""
    from nolan.camera import target as ct
    monkeypatch.setattr(ct, "cutout_path", lambda p, cache=True: None)
    frag, tl = compose.media_ground("s1", {"kind": "image", "src": "assets/x.jpg",
                                           "camera": {"move": "parallax"}}, 0.0, 10.0)
    assert "s1-fg" not in "".join(frag)
    assert [t for t in tl if "-gnd" in t and "scale" in t], "it should still push"


def test_a_composer_without_the_camera_package_still_renders(monkeypatch):
    """Fail-soft at the seam: a static ground beats a dead composer."""
    real_import = __import__

    def _blocked(name, *a, **k):
        if name.startswith("nolan.camera") or name == "nolan":
            raise ImportError("camera unavailable")
        return real_import(name, *a, **k)

    monkeypatch.setattr("builtins.__import__", _blocked)
    frag, tl = compose.media_ground("s1", {"kind": "image", "src": "assets/x.jpg"}, 0.0, 9.0)
    assert any("-gnd" in f for f in frag)                 # the ground still paints
    assert not [t for t in tl if "scale" in t]            # it simply does not move
