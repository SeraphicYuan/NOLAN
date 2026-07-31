"""The regions PRODUCER — honesty tests.

`regions` shipped as an unpopulated column and stayed that way through two attempts to fill it.
The first was consumer-blocked (nothing could spend a focal point). The second was the mistake
these tests exist to prevent: asking a VLM for `focal_zone`, which answered "middle-centre" on
**50 of 50** rows. A language model can say what is in a picture; it cannot say where.

    The model NAMES. A detector LOCALISES.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from nolan import regions                                             # noqa: E402


def _subject_at(path, box, canvas=(600, 600), seed=5):
    """A textured blob at a known box on a flat ground."""
    import numpy as np
    from PIL import Image
    W, H = canvas
    x0, y0, x1, y1 = [int(v) for v in box]
    canvas_arr = np.full((H, W, 3), 128, dtype=np.uint8)
    rng = np.random.default_rng(seed)
    canvas_arr[y0:y1, x0:x1] = rng.integers(0, 255, size=(y1 - y0, x1 - x0, 3), dtype=np.uint8)
    Image.fromarray(canvas_arr).save(path)
    return (x0 / W, y0 / H, x1 / W, y1 / H)


def test_subject_is_located_where_it_actually_is(tmp_path):
    """The whole point: a measured box, not a constant."""
    p = tmp_path / "left.png"
    _subject_at(p, (60, 200, 240, 400))                # clearly left of centre
    r = regions.detect_subject(p)
    assert r is not None and r.label == "subject" and r.kind == "energy"
    cx, cy = r.centre
    assert cx < 0.45, f"subject centre {cx:.2f} should be left of frame centre"
    assert 0.3 < cy < 0.7


def test_the_answer_is_not_always_the_centre(tmp_path):
    """REGRESSION for the field this replaces: the VLM returned middle-centre on 50/50."""
    seen = []
    for i, box in enumerate([(40, 40, 200, 200), (400, 60, 560, 220), (220, 380, 380, 540)]):
        p = tmp_path / f"s{i}.png"
        _subject_at(p, box, seed=10 + i)
        r = regions.detect_subject(p)
        assert r is not None
        seen.append(tuple(round(v, 1) for v in r.centre))
    assert len(set(seen)) == 3, f"located the same point for different subjects: {seen}"


def test_dead_margin_is_excluded_before_locating(tmp_path):
    """On a coin photograph at 31% content, the energy centroid of the FULL frame is dragged
    toward the middle of a grey field that contains nothing."""
    import numpy as np
    from PIL import Image
    W, H = 1000, 400
    canvas = np.full((H, W, 3), 128, dtype=np.uint8)
    rng = np.random.default_rng(7)
    canvas[150:250, 80:240] = rng.integers(0, 255, size=(100, 160, 3), dtype=np.uint8)
    Image.fromarray(canvas).save(p := tmp_path / "coin.png")
    r = regions.detect_subject(p)
    assert r is not None
    cx, _ = r.centre
    assert cx < 0.35, f"centre {cx:.2f} drifted toward the empty field"


def test_no_separable_subject_returns_none(tmp_path):
    """A full-bleed textile has detail everywhere and nothing to push into. None is more useful
    than an asserted centre."""
    import numpy as np
    from PIL import Image
    rng = np.random.default_rng(11)
    Image.fromarray(rng.integers(0, 255, size=(400, 400, 3), dtype=np.uint8)).save(
        p := tmp_path / "busy.png")
    r = regions.detect_subject(p)
    assert r is None or r.conf < 0.15


def test_focal_point_declines_rather_than_guess(tmp_path):
    """Pushing on a badly-located target is worse than pushing on the centre: the move looks
    deliberate either way, and only one of them is."""
    import numpy as np
    from PIL import Image
    rng = np.random.default_rng(13)
    Image.fromarray(rng.integers(0, 255, size=(400, 400, 3), dtype=np.uint8)).save(
        busy := tmp_path / "busy.png")
    assert regions.focal_point(busy) is None

    _subject_at(clear := tmp_path / "clear.png", (80, 80, 260, 260))
    fp = regions.focal_point(clear)
    assert fp is not None and 0.0 <= fp[0] <= 1.0 and 0.0 <= fp[1] <= 1.0


def test_focal_point_feeds_the_camera_solver(tmp_path):
    """THE SEAM. `solve_push(target=)` was the consumer that unblocked this column; a producer
    that does not fit it would be another authored field with nothing to spend it."""
    from nolan.camera.solve import solve_push
    _subject_at(p := tmp_path / "s.png", (60, 200, 240, 400))
    target = regions.focal_point(p)
    assert target is not None
    plan = solve_push(dur=4.0, target=target)
    assert plan and isinstance(plan, dict)


def test_crop_safety_is_the_first_payoff(tmp_path):
    """A 16:9 cover on a tall portrait is how you decapitate someone."""
    # subject occupying the top third of a square frame
    _subject_at(p := tmp_path / "portrait.png", (200, 20, 400, 220), canvas=(600, 600))
    assert regions.crop_safe(p, aspect=1.0) is True
    assert regions.crop_safe(p, aspect=16 / 9) is False, "a wide cover must cut this subject"

    # a subject safely inside the middle band survives the same crop
    _subject_at(q := tmp_path / "centred.png", (240, 250, 360, 350), canvas=(600, 600))
    assert regions.crop_safe(q, aspect=16 / 9) is True


def test_label_and_kind_vocabularies_are_closed():
    for r_label in ("subject", "face", "text", "watermark", "negative_space"):
        assert r_label in regions.REGION_LABELS
    assert set(regions.REGION_KINDS) == {"matting", "energy", "vlm-named"}


def test_regions_serialise_for_the_column(tmp_path):
    import json
    _subject_at(p := tmp_path / "s.png", (60, 60, 200, 200))
    r = regions.detect_subject(p)
    blob = regions.regions_json([r])
    back = json.loads(blob)
    assert back[0]["label"] == "subject" and len(back[0]["box"]) == 4
