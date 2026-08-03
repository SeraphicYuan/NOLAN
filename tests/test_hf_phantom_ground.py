"""The phantom-GROUND gate + the capability-gap ledger.

Incident: in one 25-comment batch edit, three notes (12%) asked for a background image on a
`juxtaposition` scene. `data.ground` validated rc=0 "OK" and painted nothing — `juxtaposition`'s
composer reads `backdrop` (a colour) and never calls `media_ground()`/`_data_ground()`. Nothing in the
catalog states the negative, so the only way to learn it was to read compose.py. That is
docs/WIRING_CHECKLIST.md #1 (the gate accepting what the composer never reads), and it is the sibling
of the phantom-CUE gate that already lives next to this one.

Two things are pinned here:
  1. an image/paper ground on a non-ground block is REFUSED, and the refusal names the alternative;
  2. a VIDEO ground is NOT refused on any block — `collect_video_grounds` is block-agnostic and
     root-mounts it, which is exactly how a `math` scene's Manim clip reaches the screen. A gate that
     "tidily" refused all grounds on non-ground blocks would break maths.
And that a refusal carrying the CAPABILITY-GAP token is COUNTED, so "12% of notes wanted this" becomes
a number you can read instead of a remark in a retro.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge"
AUTHOR = BRIDGE / "author.py"
VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"

from nolan.block_registry import consumes_ground      # noqa: E402
from nolan.hyperframes import edit as hfedit          # noqa: E402


def _validate(tmp_path, scene):
    spec = {"frames": [{"id": "f1", "dur": 8.0, "scenes": [scene]}]}
    f = tmp_path / "s.json"
    f.write_text(json.dumps(spec), encoding="utf-8")
    r = subprocess.run([sys.executable, "-X", "utf8", str(AUTHOR), "--spec", str(f), "--validate-only"],
                       cwd=str(BRIDGE), capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout + r.stderr)


def _nonground(ground=None):
    """A block that genuinely paints no ground. `diagram` is the exemplar rather than `juxtaposition`,
    which USED to be one — the capability ledger below counted the asks and it was given `_data_ground`.
    That is the loop working, and it is why this fixture names the block it does."""
    d = {"root": {"label": "the land", "children": [{"label": "a shell company"}]}}
    if ground is not None:
        d["ground"] = ground
    return {"id": "s1", "type": "diagram", "start": 0, "dur": 5, "data": d}


def test_image_ground_on_a_non_ground_block_is_refused(tmp_path):
    assert not consumes_ground("diagram"), "premise of this test"
    rc, out = _validate(tmp_path, _nonground({"kind": "image", "src": "assets/x.jpg"}))
    assert rc != 0, f"an inert ground must be REFUSED, not silently accepted:\n{out}"
    assert "CAPABILITY-GAP data.ground" in out
    assert "layout" in out and "statement" in out, f"the refusal must name the alternative:\n{out}"


def test_paper_ground_on_a_non_ground_block_is_refused(tmp_path):
    rc, out = _validate(tmp_path, _nonground({"kind": "paper"}))
    assert rc != 0 and "CAPABILITY-GAP" in out


def test_video_ground_is_allowed_on_any_block(tmp_path):
    """collect_video_grounds root-mounts a video ground regardless of block — refusing it would break math."""
    rc, out = _validate(tmp_path, _nonground({"kind": "video", "src": "assets/x.mp4"}))
    assert rc == 0, f"a VIDEO ground is real for every block (root-mounted):\n{out}"


def test_math_scene_with_its_manim_video_ground_still_validates(tmp_path):
    """`math` is deliberately outside both ground sets; its clip IS a root-mounted video ground."""
    sc = {"id": "s1", "type": "math", "start": 0, "dur": 5,
          "data": {"template": "equation_walkthrough",
                   "ledger": [{"id": "e1", "latex": "a^2+b^2=c^2", "source": "narration"}],
                   "steps": [{"latex": "a^2+b^2=c^2", "ledger": "e1"}],
                   "ground": {"kind": "video", "src": "assets/math/x.mp4"}}}
    rc, out = _validate(tmp_path, sc)
    assert "CAPABILITY-GAP" not in out, f"the phantom-ground gate must not touch maths:\n{out}"


def test_ground_block_still_accepts_an_image_ground(tmp_path):
    sc = {"id": "s1", "type": "statement", "start": 0, "dur": 5,
          "data": {"lines": ["hello"], "ground": {"kind": "image", "src": "assets/x.jpg"}}}
    rc, out = _validate(tmp_path, sc)
    assert rc == 0 and "CAPABILITY-GAP" not in out, out


# --- the ledger -------------------------------------------------------------------------------------

@pytest.fixture()
def comp():
    name = "_hf_gaps_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    fdir = dst / "compositions" / "frames"
    fdir.mkdir(parents=True)
    (fdir / "f1.spec.json").write_text(json.dumps({"frames": [{"id": "f1", "dur": 8.0, "scenes": [
        _nonground()]}]}), encoding="utf-8")
    (dst / "hyperframes.json").write_text('{"theme":"highlighter-editorial"}', encoding="utf-8")
    try:
        yield name
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def test_a_blocked_proposal_records_the_capability_ask(comp):
    p = hfedit.propose_scene_edit(
        comp, "f1", "s1",
        ops=[{"op": "patch", "scene_id": "s1",
              "patch": {"data.ground": {"kind": "image", "src": "assets/x.jpg"}}}],
        rationale="human asked for a photographic background behind the two claims", agent="pytest")
    assert p["gate_ok"] is False
    assert p.get("capability_gap") is True, "a CAPABILITY-GAP refusal is a feature request, flag it as one"
    gaps = hfedit.list_gaps(comp)
    assert gaps and gaps[0]["block"] == "diagram" and gaps[0]["field"] == "data.ground"
    assert gaps[0]["asks"] == 1 and comp in gaps[0]["comps"]
    assert gaps[0]["examples"], "keep an example note so the ask is readable, not just counted"


def test_gaps_tally_repeated_asks(comp):
    for i in range(3):
        hfedit.propose_scene_edit(
            comp, "f1", "s1",
            ops=[{"op": "patch", "scene_id": "s1",
                  "patch": {"data.ground": {"kind": "image", "src": f"assets/{i}.jpg"}}}],
            rationale=f"note {i}", agent="pytest")
    gaps = hfedit.list_gaps(comp)
    assert gaps[0]["asks"] == 3, "the point of the ledger is the COUNT"


def test_an_ordinary_gate_failure_is_not_a_capability_gap(comp):
    p = hfedit.propose_scene_edit(comp, "f1", "s1",
                                  ops=[{"op": "patch", "scene_id": "s1", "patch": {"data.root": None}}],
                                  rationale="break it", agent="pytest")
    assert p["gate_ok"] is False
    assert "capability_gap" not in p
    assert hfedit.list_gaps(comp) == []


# --- the capability the ledger argued for ----------------------------------------------------------

def _compose(scene):
    import importlib.util
    import sys as _s
    if str(BRIDGE) not in _s.path:
        _s.path.insert(0, str(BRIDGE))
    import compose
    return compose.compose_frame("f1", 6, [scene], theme="highlighter-editorial")


def _jx(ground=None, **extra):
    d = {"left": {"type": "text", "lines": "they promised"},
         "right": {"type": "text", "lines": "it cost"}, **extra}
    if ground is not None:
        d["ground"] = ground
    return {"id": "s1", "type": "juxtaposition", "start": 0, "dur": 6, "data": d}


def test_juxtaposition_now_paints_an_authored_ground():
    """The end of the loop that started with 3 of 25 notes asking for it."""
    from nolan.block_registry import consumes_ground
    assert consumes_ground("juxtaposition")
    html = _compose(_jx({"kind": "image", "src": "assets/x.jpg", "dim": 0.55}))
    assert "assets/x.jpg" in html, "the photograph must actually be on screen"
    assert 'class="clip scrim"' in html, \
        "display type over footage needs the polarity-correct veil — that is why _data_ground, not a raw div"


def test_an_unauthored_juxtaposition_is_unchanged():
    """The flat `backdrop` colour stays the DEFAULT. A capability that changes existing scenes is a
    regression wearing a feature's clothes."""
    html = _compose(_jx(title="Two sides", vs=True))
    assert "blk-juxtaposition" in html and 'class="clip scrim"' not in html
    import re
    assert sorted({int(x) for x in re.findall(r'data-track-index="(\d+)"', html)}) == [0, 1, 2, 3]


def test_the_panels_move_off_the_tracks_the_ground_owns():
    html = _compose(_jx({"kind": "image", "src": "assets/x.jpg"}))
    import re
    assert sorted({int(x) for x in re.findall(r'data-track-index="(\d+)"', html)}) == [0, 1, 2, 3, 4], \
        "ground=0, veil=1, panels=2/3, overlay=4 — same-track overlap would be a different bug"


def test_a_video_ground_leaves_the_hole_for_the_root_mount():
    """No <video> element inside a frame sub-comp (illegal); `collect_video_grounds` root-mounts it and
    the veil goes over the hole — exactly what `chart` has always done."""
    html = _compose(_jx({"kind": "video", "src": "assets/x.mp4"}))
    assert 'class="clip scrim"' in html
    assert "<video " not in html and "<video\n" not in html


def test_the_catalog_now_declares_it():
    """The gate reads the composer; the AGENT reads the catalog. Both must say the same thing, or the
    brief goes on telling agents the field does not exist."""
    cat = json.loads((BRIDGE / "catalog.json").read_text(encoding="utf-8"))
    assert "ground" in cat["scene_templates"]["juxtaposition"]["data_schema"]


def test_a_ground_on_juxtaposition_is_no_longer_refused(tmp_path):
    rc, out = _validate(tmp_path, _jx({"kind": "image", "src": "assets/x.jpg"}))
    assert rc == 0 and "CAPABILITY-GAP" not in out, out
