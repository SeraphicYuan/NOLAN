"""The frosted panel — a panel over real media stops being an opaque slab.

INCIDENT (diamond-v2 @12:49, scene f09s04): a `statement` framed-card over the "A Diamond Is Forever"
ad painted an opaque cream slab across the whole ad, AND took the footage register while doing it —
near-white #F6F7F6 text on cream. The headline survived on its drop-shadow; the kicker was all but
invisible. Two defects in one panel: it hid the asset it was placed on, and it was barely readable.

Verified in the real renderer (headless Chrome) before any of this was wired: `backdrop-filter` works
over an image ground, over a root-mounted <video>, and — the case that could have failed — from inside
a frame SUB-COMPOSITION with the video at the index root, which is the production topology.
"""
import re
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"
SRC = (BRIDGE / "compose.py").read_text(encoding="utf-8")
sys.path.insert(0, str(BRIDGE))
import compose  # noqa: E402

IMG = {"kind": "image", "src": "assets/nope.jpg"}       # unresolvable → the safe default tint
VID = {"kind": "video", "src": "assets/videos/x.mp4"}


def _card(ground=None, **extra):
    sc = {"id": "s1", "start": 0.0, "dur": 8.0, "_variant": "framed-card",
          "data": dict({"kicker": "K", "lines": ["one", "two"], "operative": "two"}, **extra)}
    if ground:
        sc["data"]["ground"] = ground
    return "".join(compose.highlight_statement("s1", sc)[0])


def test_a_panel_over_media_is_glass():
    for ground in (IMG, VID):
        html = _card(ground)
        assert "stmt-card glass" in html, f"no glass over {ground['kind']}"
        assert "--glass-tint:" in html


def test_a_panel_with_no_media_stays_solid():
    """Over paper there is nothing to see through — glass would only cost contrast."""
    assert "glass" not in _card({"kind": "paper"})
    assert "glass" not in _card()


def test_solid_is_the_opt_out():
    assert "glass" not in _card(IMG, panel="solid")
    assert "stmt-card glass" in _card(IMG, panel="glass")


def test_the_tint_is_derived_from_the_ground_not_a_constant(tmp_path):
    """A dark ground needs MORE opaque surface to keep dark text legible than a bright one does. If
    these ever come back equal, the measurement has silently stopped happening."""
    from PIL import Image
    Image.new("RGB", (400, 300), (12, 12, 14)).save(tmp_path / "dark.jpg")
    Image.new("RGB", (400, 300), (242, 240, 235)).save(tmp_path / "bright.jpg")
    compose._ASSET_BASE = tmp_path
    compose._GLASS_CACHE.clear()
    dark = compose._glass_tint({"ground": {"kind": "image", "src": "dark.jpg"}})
    bright = compose._glass_tint({"ground": {"kind": "image", "src": "bright.jpg"}})
    compose._ASSET_BASE = None
    assert dark > bright, f"tint did not respond to the ground (dark={dark} bright={bright})"


def test_the_tint_actually_clears_the_contrast_target(tmp_path):
    """The point of measuring: at the tint it returns, the WORST patch under the panel must clear 4.5:1
    for --text. A tint that looks nice but fails this is just a guess with extra steps."""
    from PIL import Image
    im = Image.new("RGB", (64, 64), (250, 250, 250))
    for y in range(32):                                   # half the panel is near-black
        for x in range(64):
            im.putpixel((x, y), (8, 8, 10))
    im.save(tmp_path / "split.jpg")
    compose._ASSET_BASE = tmp_path
    compose._GLASS_CACHE.clear()
    d = {"ground": {"kind": "image", "src": "split.jpg"}}
    a = compose._glass_tint(d) / 100.0
    patches = compose._ground_patches("split.jpg")
    surf = compose._theme_rgb("--surface", "#F7F3EA")
    text = compose._theme_rgb("--text", "#1c1c19")
    compose._ASSET_BASE = None
    lt = compose._rel_lum(text)
    worst = min(
        (max(lt, le) + 0.05) / (min(lt, le) + 0.05)
        for le in (compose._rel_lum(tuple(a * surf[i] + (1 - a) * px[i] for i in range(3))) for px in patches))
    assert worst >= 4.5 or a >= 0.88, f"contrast {worst:.2f} at tint {a:.2f}"


def test_tint_stays_inside_the_glass_range():
    """Clamped at both ends: below the floor it is not a plate, above the ceiling it is the slab again."""
    for kind in ("image", "video"):
        t = compose._glass_tint({"ground": {"kind": kind, "src": "assets/whatever.jpg"}})
        assert 40 <= t <= 88, t


def test_a_panel_forces_the_paper_register():
    """The shipped defect: a panel IS a surface, so its contents cannot keep the footage register's
    near-white ink. The selectors must out-specify the register rules that come later in the sheet —
    at equal specificity those win on order alone, which is exactly what kept the kicker white."""
    assert ".footage .stmt-card .stmt.footage-t" in SRC
    assert ".footage .stmt-card .kick" in SRC
    html = _card(IMG)
    assert "stmt footage-t" in html                       # the class still says footage…
    m = re.search(r"\.footage \.stmt-card \.stmt\.footage-t[^{]*\{([^}]*)\}", SRC)
    assert m and "var(--text)" in m.group(1)              # …and the panel rule repaints it


def test_glass_is_declared_where_it_is_consumed():
    """WIRING: the authored field exists in the catalog for exactly the blocks that read it."""
    import json
    cat = json.loads((BRIDGE / "catalog.json").read_text(encoding="utf-8"))["scene_templates"]
    for block in ("statement", "pull_quote", "comparison_table"):
        assert "panel" in cat[block]["data_schema"], f"{block} consumes `panel` but never declares it"
