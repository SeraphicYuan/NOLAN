"""The batch review artifact — the aggregate view a 25-proposal batch never had.

Per-proposal accept is the wrong altitude: the reviewer's question is "does the essay still hang
together", and nothing answered it until a 25-minute render landed. Every input already existed
(rationale, requirement coverage, gate output, the cached per-frame clip, `proposal_preview`); they had
just never been assembled into one page.

Three properties matter beyond "it renders a grid":
  * the BEFORE frame comes from the cached `clip.mp4` — the shipped pixels, not a re-derivation;
  * a re-ANCHOR is resolved against the transcript, because it is the one edit a still cannot show;
  * a video-grounded scene is FLAGGED as unverifiable by a still, instead of showing a blank plate and
    letting the reviewer believe it.
"""
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"

from nolan.hyperframes import contact_sheet as cs      # noqa: E402
from nolan.hyperframes import edit as hfedit           # noqa: E402

_VO = "somebody taught it to you and you never asked who".split()


@pytest.fixture()
def comp():
    name = "_hf_sheet_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    fdir = dst / "compositions" / "frames"
    fdir.mkdir(parents=True)
    (fdir / "01-beat.spec.json").write_text(json.dumps({"frames": [{"id": "01-beat", "dur": 10.0, "scenes": [
        {"id": "s1", "type": "statement", "start": 0, "dur": 5,
         "data": {"lines": ["taught"], "anchor": "somebody taught it"}},
        {"id": "s2", "type": "statement", "start": 5, "dur": 5,
         "data": {"lines": ["never asked"], "ground": {"kind": "video", "src": "assets/x.mp4"}}},
    ]}]}), encoding="utf-8")
    (dst / "hyperframes.json").write_text('{"theme":"highlighter-editorial"}', encoding="utf-8")
    (dst / "audio_meta.json").write_text(json.dumps({"voices": [{
        "frame": 1, "path": "assets/voice/01.wav", "duration_s": 10.0,
        "words": [{"word": w, "start": i, "end": i + 0.8} for i, w in enumerate(_VO)]}]}), encoding="utf-8")
    try:
        yield name
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def _propose(comp, sid, patch, **kw):
    return hfedit.propose_scene_edit(comp, "01-beat", sid,
                                     ops=[{"op": "patch", "scene_id": sid, "patch": patch}],
                                     agent="pytest", **kw)


def test_the_sheet_is_one_row_per_proposal_in_scene_order(comp):
    _propose(comp, "s2", {"data.kicker": "B"}, rationale="second")
    _propose(comp, "s1", {"data.kicker": "A"}, rationale="first")
    sheet = cs.build_sheet(comp, previews=False)
    assert [r["scene_id"] for r in sheet["rows"]] == ["s1", "s2"], \
        "review order is the ESSAY's order, not the order the agent happened to propose in"
    assert sheet["summary"]["proposals"] == 2 and sheet["summary"]["frames"] == 1


def test_a_row_carries_everything_the_reviewer_was_clicking_through_for(comp):
    p = _propose(comp, "s1", {"data.kicker": "A"}, rationale="the note asked for an eyebrow",
                 requirements=[{"req_id": "r1", "status": "met", "note": "added"},
                               {"req_id": "r2", "status": "unmet", "note": "no landing spot"}])
    row = cs.build_sheet(comp, [p["id"]], previews=False)["rows"][0]
    assert row["rationale"] == "the note asked for an eyebrow"
    assert row["ops"] == ["patch s1: data.kicker"]
    assert [q["status"] for q in row["requirements"]] == ["met", "unmet"]
    assert row["block"] == "statement" and row["narration"], "what is SPOKEN over the scene, for context"


def test_unmet_requirements_are_counted_in_the_summary(comp):
    _propose(comp, "s1", {"data.kicker": "A"}, rationale="x",
             requirements=[{"req_id": "r1", "status": "unmet", "note": "nope"}])
    assert cs.build_sheet(comp, previews=False)["summary"]["unmet_requirements"] == 1, \
        "an honest miss must be visible at the TOP of the review, not buried in one modal"


def test_a_reanchor_is_resolved_against_the_transcript(comp):
    """The edit a before/after still cannot show — identical pixels, and the scene simply lands
    somewhere else at the next sync. This is the class that produced the batch's only real regression."""
    bad = _propose(comp, "s1", {"data.anchor": "someone taught it to you"}, rationale="re-anchor")
    row = cs.build_sheet(comp, [bad["id"]], previews=False)["rows"][0]
    assert row["anchor"]["new"] == "someone taught it to you"
    assert row["anchor"]["resolved_at"] is None
    assert "UNRESOLVED" in row["anchor"]["verdict"]
    assert row["anchor"]["suggest"], "and it must offer the verbatim span from the transcript"


def test_a_good_reanchor_reports_where_it_lands(comp):
    ok = _propose(comp, "s1", {"data.anchor": "you never asked"}, rationale="re-anchor")
    row = cs.build_sheet(comp, [ok["id"]], previews=False)["rows"][0]
    assert row["anchor"]["resolved_at"] is not None and row["anchor"]["verdict"] == "resolves"


def test_a_non_anchor_edit_has_no_anchor_block(comp):
    p = _propose(comp, "s1", {"data.kicker": "A"}, rationale="x")
    assert "anchor" not in cs.build_sheet(comp, [p["id"]], previews=False)["rows"][0]


def test_a_video_grounded_scene_is_flagged_as_unverifiable_by_a_still(comp):
    p = _propose(comp, "s2", {"data.kicker": "B"}, rationale="x")
    row = cs.build_sheet(comp, [p["id"]], previews=False)["rows"][0]
    assert row["needs_motion_check"] is True, \
        "a seeked <video> does not decode into a snapshot — say so rather than showing a blank plate"
    assert cs.build_sheet(comp, previews=False)["summary"]["needs_motion_check"] == 1


def test_a_capability_gap_is_surfaced_at_the_top(comp):
    p = hfedit.propose_scene_edit(
        comp, "01-beat", "s1",
        ops=[{"op": "patch", "scene_id": "s1", "patch": {"data.at": 3}}],
        rationale="cue the line", agent="pytest")
    sheet = cs.build_sheet(comp, [p["id"]], previews=False)
    assert sheet["rows"][0]["gate_ok"] is False
    assert sheet["summary"]["blocked"] == 1


def test_before_still_is_absent_not_fabricated_when_there_is_no_clip(comp):
    assert cs.before_still(comp, "01-beat", 2.0) is None, \
        "no cached clip means no BEFORE — inventing one from a recompose would not be the shipped pixels"


def test_markdown_reads_the_batch_as_prose(comp):
    _propose(comp, "s1", {"data.anchor": "someone taught it to you"}, rationale="re-anchor",
             requirements=[{"req_id": "r1", "status": "partial", "note": "converted the block"}])
    _propose(comp, "s2", {"data.kicker": "B"}, rationale="eyebrow")
    out = cs.write_markdown(comp)
    text = out.read_text(encoding="utf-8")
    assert "# Batch review" in text
    assert "`01-beat`" in text and "s1" in text and "s2" in text
    assert "UNRESOLVED" in text, "the anchor verdict belongs in the readable version too"
    assert "r1" in text and "partial" in text
    assert "render_scene(comp, '01-beat', 's2')" in text, "tell the reviewer how to check what a still can't"
    assert text.index("s1") < text.index("s2"), "scene order — this is how you read an essay"
