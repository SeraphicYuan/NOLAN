"""Deterministic pixel measurement — honesty tests.

`pixels.py` exists because a VLM was measured against pixel truth and lost (`has_border` agreed
16/50, worse than chance). A module that replaces a model with arithmetic has to prove the
arithmetic, so every claim its docstring makes is pinned below with a synthetic image whose
answer is known by construction.

Two of these tests are regressions for mistakes made while writing it, and they are the reason
the file is worth its length:

  * `test_full_bleed_is_not_cropped` — the false-positive direction. If the content box eats into
    a picture that fills its frame, the gate starts refusing good assets, which is the failure
    mode WIRING_CHECKLIST class 11 is about.
  * `test_filled_rectangle_is_not_round` — the first `shape` implementation asked "are the
    corners background?", which is true of any object on a plain ground, and called an engraving,
    a garment and three Greek kraters round (12 of 19 wrong).
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from nolan import pixels                                                 # noqa: E402


def _noise_rgb(w, h, seed=0):
    """Textured content — a flat fill would be indistinguishable from background."""
    import numpy as np
    rng = np.random.default_rng(seed)
    return rng.integers(40, 220, size=(h, w, 3), dtype=np.uint8)


def _on_ground(path, content_wh, canvas_wh, ground=(128, 128, 128), seed=0):
    """Paste a textured rectangle centred on a flat ground. The content box is known exactly."""
    import numpy as np
    from PIL import Image
    cw, ch = content_wh
    W, H = canvas_wh
    canvas = np.zeros((H, W, 3), dtype=np.uint8)
    canvas[:, :] = ground
    x0, y0 = (W - cw) // 2, (H - ch) // 2
    canvas[y0:y0 + ch, x0:x0 + cw] = _noise_rgb(cw, ch, seed)
    Image.fromarray(canvas).save(path)
    return (x0, y0, x0 + cw, y0 + ch)


# --------------------------------------------------------------------------- content box

def test_content_box_finds_the_object_and_ignores_the_sweep(tmp_path):
    """THE measurement: a coin on a wide grey field is not a wide asset."""
    p = tmp_path / "coin.png"
    expect = _on_ground(p, (200, 200), (1000, 400))
    f = pixels.measure(p)
    assert f is not None
    x0, y0, x1, y1 = f.content_box
    # within a couple of pixels of the truth on every side
    for got, want in zip((x0, y0, x1, y1), expect):
        assert abs(got - want) <= 3, f"content_box {f.content_box} != {expect}"
    assert f.effective_width == pytest.approx(200, abs=6)
    assert f.effective_height == pytest.approx(200, abs=6)
    # 200x200 of content in a 1000x400 file = 10%
    assert f.content_fraction == pytest.approx(0.10, abs=0.02)


def test_effective_dims_are_smaller_than_the_file_when_there_is_margin(tmp_path):
    """The gate bug in one assertion: the file says 1000x400, the asset is 200x200."""
    p = tmp_path / "obj.png"
    _on_ground(p, (200, 200), (1000, 400))
    f = pixels.measure(p)
    assert f.effective_dims != (f.width, f.height)
    assert max(f.effective_dims) < min(f.width, f.height)


def test_full_bleed_is_not_cropped(tmp_path):
    """FALSE-POSITIVE GUARD. A picture that fills its frame keeps every pixel — otherwise the
    resolution floor starts refusing assets that are perfectly good."""
    import numpy as np
    from PIL import Image
    p = tmp_path / "painting.png"
    Image.fromarray(_noise_rgb(600, 800, seed=3)).save(p)
    f = pixels.measure(p)
    assert f.content_box == (0, 0, 600, 800)
    assert f.content_fraction == pytest.approx(1.0, abs=0.01)
    assert f.effective_dims == (600, 800)
    assert sorted(f.edge_contact) == ["bottom", "left", "right", "top"]


def test_margin_is_reported_per_side(tmp_path):
    """Per-side, because the defect that motivated this was ASYMMETRIC — a photographed page
    with 7.7% black on one side and 11.8% on the other."""
    import numpy as np
    from PIL import Image
    W, H = 400, 400
    canvas = np.zeros((H, W, 3), dtype=np.uint8)
    canvas[:, :] = (10, 10, 10)
    canvas[0:H, 40:W] = _noise_rgb(W - 40, H, seed=5)      # dead margin on the LEFT only
    Image.fromarray(canvas).save(p := tmp_path / "page.png")
    f = pixels.measure(p)
    assert f.margin["left"] == pytest.approx(0.10, abs=0.02)
    assert f.margin["right"] < 0.01
    assert "left" not in f.edge_contact
    assert "right" in f.edge_contact


def test_a_flat_painted_sky_is_not_dead_margin(tmp_path):
    """REGRESSION, found by looking at the corpus rather than by reasoning about it.

    Horace Pippin's "Cabin in the Cotton" (artic:111617) has a flat painted blue sky across the
    top 17.8% of the panel. Uniformity alone called it dead margin, which would have handed the
    gate a painting 18% shorter than it is. Ground is achromatic; a sky is not.
    """
    import numpy as np
    from PIL import Image
    W, H = 400, 300
    canvas = np.zeros((H, W, 3), dtype=np.uint8)
    canvas[:, :] = (28, 62, 104)                  # flat, saturated, unmistakably sky
    canvas[60:H, :] = _noise_rgb(W, H - 60, seed=23)
    Image.fromarray(canvas).save(p := tmp_path / "pippin.png")
    f = pixels.measure(p)
    assert f.margin["top"] == 0.0, "a saturated flat band is picture, not mount"
    assert f.content_fraction == pytest.approx(1.0, abs=0.01)

    # ...but the SAME geometry in neutral grey is a studio sweep and must still be trimmed.
    canvas[:60, :] = (140, 140, 140)
    Image.fromarray(canvas).save(q := tmp_path / "sweep.png")
    assert pixels.measure(q).margin["top"] == pytest.approx(0.20, abs=0.03)


def test_unreadable_file_measures_none_never_zero(tmp_path):
    """A measurement that failed must be ABSENT. Returning zeros would read to the gate as a
    flawless image."""
    bad = tmp_path / "not_an_image.png"
    bad.write_bytes(b"this is not a PNG")
    assert pixels.measure(bad) is None
    assert pixels.effective_dims(bad) is None


# --------------------------------------------------------------------------- object on a sweep

def test_object_on_sweep_needs_both_signals(tmp_path):
    """`banner_suspect` refused 4 of 4 museum rows by firing on a plain ground alone. This flag
    requires a uniform border AND content that does not fill the frame."""
    on_sweep = tmp_path / "sweep.png"
    _on_ground(on_sweep, (200, 200), (800, 600))
    assert pixels.measure(on_sweep).object_on_sweep is True

    # A flat artwork shot edge to edge: uniform border is irrelevant because content fills it.
    from PIL import Image
    full = tmp_path / "full.png"
    Image.fromarray(_noise_rgb(800, 600, seed=7)).save(full)
    f = pixels.measure(full)
    assert f.object_on_sweep is False


# --------------------------------------------------------------------------- shape

def test_disc_is_round(tmp_path):
    import numpy as np
    from PIL import Image, ImageDraw
    W = H = 400
    im = Image.new("RGB", (W, H), (240, 240, 240))
    im.paste(Image.fromarray(_noise_rgb(W, H, seed=11)),
             (0, 0), Image.new("L", (W, H), 0))          # keep ground flat
    d = ImageDraw.Draw(im)
    d.ellipse([20, 20, W - 20, H - 20], fill=(30, 90, 160))
    # texture inside the disc so it is unambiguously content
    noise = Image.fromarray(_noise_rgb(W, H, seed=12))
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).ellipse([20, 20, W - 20, H - 20], fill=255)
    im.paste(noise, (0, 0), mask)
    im.save(p := tmp_path / "tondo.png")
    assert pixels.measure(p).shape == "round"


def test_filled_rectangle_is_not_round(tmp_path):
    """REGRESSION. The first implementation called any object on a plain ground round."""
    from PIL import Image
    Image.fromarray(_noise_rgb(400, 400, seed=13)).save(p := tmp_path / "print.png")
    assert pixels.measure(p).shape == "rect"


def test_square_object_on_a_ground_is_not_round(tmp_path):
    """REGRESSION, the exact shape of the bug: square content, flat ground, background corners
    OUTSIDE the content box — which the corner heuristic scored as round."""
    p = tmp_path / "dalmatic.png"
    _on_ground(p, (300, 300), (400, 400))
    assert pixels.measure(p).shape == "rect"


# --------------------------------------------------------------------------- tone

def test_greyscale_reproduction_is_detected(tmp_path):
    import numpy as np
    from PIL import Image
    g = np.random.default_rng(2).integers(30, 220, size=(300, 300), dtype=np.uint8)
    Image.fromarray(np.dstack([g, g, g])).save(p := tmp_path / "grey.png")
    f = pixels.measure(p)
    assert f.greyscale is True
    assert f.saturation < 0.05

    Image.fromarray(_noise_rgb(300, 300, seed=17)).save(q := tmp_path / "colour.png")
    assert pixels.measure(q).greyscale is False


# --------------------------------------------------------------------------- quiet cells

def test_quiet_cells_discriminate(tmp_path):
    """A field that answers "where can type go" with "anywhere" is the VLM template this
    replaced. A flat panel is all-quiet; dense noise is none."""
    import numpy as np
    from PIL import Image
    Image.fromarray(np.full((300, 300, 3), 120, dtype=np.uint8)).save(flat := tmp_path / "f.png")
    assert len(pixels.measure(flat).quiet_cells) == 9

    Image.fromarray(_noise_rgb(300, 300, seed=19)).save(busy := tmp_path / "b.png")
    assert pixels.measure(busy).quiet_cells == []


# --------------------------------------------------------------------------- the gate seam

def test_gate_floor_judges_content_not_file(tmp_path):
    """D2, the live bug in one test: an object on a sweep must not buy a pass with dead margin.

    Characterised before wiring — 1 of 46 held rows and 7 of 841 discovery rows newly refused,
    every content box inspected by eye, 834 discovery rows still passing.
    """
    from nolan import asset_gate
    p = tmp_path / "coin.png"
    # 1200x1200 file, but only a 400x400 object in the middle: comfortably over the archival
    # floor as a FILE (700 / 600k), comfortably under it as CONTENT.
    _on_ground(p, (400, 400), (1200, 1200))

    assert asset_gate.content_dims(p) != (1200, 1200)
    v = asset_gate.check_file(p, tier="archival")
    assert v.ok is False
    assert any("resolution floor" in r for r in v.reasons)
    # the reason must name BOTH numbers, or the refusal is unactionable
    assert any("content" in r and "dead margin" in r for r in v.reasons), v.reasons


def test_gate_floor_still_passes_a_full_bleed_image(tmp_path):
    """The other direction. A check whose failures are all false positives gets skipped, and
    takes its one true positive with it (checklist #11)."""
    from PIL import Image
    from nolan import asset_gate
    Image.fromarray(_noise_rgb(1000, 1000, seed=31)).save(p := tmp_path / "painting.png")
    assert asset_gate.content_dims(p) == (1000, 1000)
    assert asset_gate.check_file(p, tier="archival").ok is True


def test_gate_falls_back_to_file_dims_when_measurement_fails(tmp_path):
    """An image the detector cannot read must not become an image the gate cannot refuse."""
    from nolan import asset_gate
    bad = tmp_path / "broken.png"
    bad.write_bytes(b"not a png")
    assert asset_gate.content_dims(bad) is None      # _probe fails too; floor is simply skipped
    v = asset_gate.check_file(bad, tier="archival")
    assert v.ok is True                              # no size known -> other checks still apply


def test_effective_dims_scales_declared_full_size(tmp_path):
    """The discovery tier's exact case: measure the LOCAL 512px thumbnail, but answer in the
    full image's pixels, which only the catalog knows."""
    p = tmp_path / "thumb.png"
    _on_ground(p, (128, 128), (512, 512))          # content is 1/4 of each axis
    got = pixels.effective_dims(p, declared=(4000, 4000))
    assert got is not None
    assert got[0] == pytest.approx(1000, abs=60)
    assert got[1] == pytest.approx(1000, abs=60)
