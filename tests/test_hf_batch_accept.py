"""Batch-scale editing safety: undo, list append, and a comment state for parked work.

Three gaps a 25-proposal batch exposed:

  * **No undo.** `_edit` reverts a single failed edit, but once N proposals were accepted there was no
    way back — and git is not the safety net here (a shared working tree with concurrent agents, and
    `git stash` is forbidden in this repo). Frame specs are small JSON; snapshotting them is cheap.
  * **`_set_path` could not append.** "add another bar / row / bullet" is one of the commonest notes a
    human writes, and `{"data.series.2": …}` on a two-item list raised IndexError. The only workaround
    was re-sending the whole array, which clobbers any concurrent edit to a sibling element.
  * **`deferred` was not a state.** An agent with real work blocked on an external resource (ComfyUI
    down) could say `blocked` — a capability judgement it had not made — or leave the comment dispatched
    and log an activity line invisible in the changeset. The real batch chose the second and the work
    vanished from the review.
"""
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"

from nolan.hyperframes import edit as hfedit          # noqa: E402


@pytest.fixture()
def comp():
    name = "_hf_batch_accept_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    fdir = dst / "compositions" / "frames"
    fdir.mkdir(parents=True)
    (fdir / "f1.spec.json").write_text(json.dumps({"frames": [{"id": "f1", "dur": 8.0, "scenes": [
        {"id": "s1", "type": "statement", "start": 0, "dur": 4, "data": {"lines": ["one"]}},
        {"id": "s2", "type": "statement", "start": 4, "dur": 4, "data": {"lines": ["two"]}},
    ]}]}), encoding="utf-8")
    (dst / "hyperframes.json").write_text('{"theme":"highlighter-editorial"}', encoding="utf-8")
    try:
        yield name
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def _kicker(comp, sid):
    spec, info = hfedit.load_frame_spec(comp, "f1")
    return hfedit._find_scene(spec["frames"][info["i"]], sid)["data"].get("kicker")


# --- dotted-path append ---------------------------------------------------------------------------

def test_plus_appends_to_a_list():
    obj = {"data": {"series": [{"v": 1}, {"v": 2}]}}
    hfedit._set_path(obj, "data.series.+", {"v": 3})
    assert [x["v"] for x in obj["data"]["series"]] == [1, 2, 3]


def test_an_out_of_range_index_raises_and_names_the_fix():
    obj = {"data": {"series": [{"v": 1}, {"v": 2}]}}
    with pytest.raises(IndexError) as e:
        hfedit._set_path(obj, "data.series.7", {"v": 9})
    assert "data.series.+" in str(e.value), "silent growth would render 5 blanks that validate"


def test_existing_index_writes_still_work():
    obj = {"data": {"items": [{"to": 1}, {"to": 2}]}}
    hfedit._set_path(obj, "data.items.0.to", 42)
    assert obj["data"]["items"][0]["to"] == 42


def test_a_traversal_index_out_of_range_is_also_loud():
    obj = {"data": {"items": [{"to": 1}]}}
    with pytest.raises(IndexError):
        hfedit._set_path(obj, "data.items.3.to", 9)


def test_plus_is_only_valid_as_the_last_segment():
    obj = {"data": {"items": [{"to": 1}]}}
    with pytest.raises(ValueError):
        hfedit._set_path(obj, "data.items.+.to", 9)


def test_append_reaches_the_gate_through_a_proposal(comp):
    """The op form an agent actually writes — nested lists inside a block's data."""
    p = hfedit.propose_scene_edit(
        comp, "f1", "s1",
        ops=[{"op": "patch", "scene_id": "s1", "patch": {"data.lines.+": "three"}}],
        rationale="add a third line", agent="pytest")
    assert p["gate_ok"] is True, p["gate_out"]
    hfedit.accept_proposal(comp, p["id"])
    spec, info = hfedit.load_frame_spec(comp, "f1")
    assert hfedit._find_scene(spec["frames"][info["i"]], "s1")["data"]["lines"] == ["one", "three"]


# --- batch accept + rollback ------------------------------------------------------------------------

def test_accepting_a_set_reports_per_proposal_and_can_be_undone(comp):
    a = hfedit.propose_scene_edit(comp, "f1", "s1",
                                  ops=[{"op": "patch", "scene_id": "s1", "patch": {"data.kicker": "A"}}],
                                  rationale="a", agent="pytest")
    b = hfedit.propose_scene_edit(comp, "f1", "s2",
                                  ops=[{"op": "patch", "scene_id": "s2", "patch": {"data.kicker": "B"}}],
                                  rationale="b", agent="pytest")
    res = hfedit.accept_proposals(comp, [a["id"], b["id"]])
    assert res["ok"] and res["applied"] == [a["id"], b["id"]]
    assert (_kicker(comp, "s1"), _kicker(comp, "s2")) == ("A", "B")

    back = hfedit.rollback_batch(comp, res["rollback_token"])
    assert back["ok"], back["errors"]
    assert (_kicker(comp, "s1"), _kicker(comp, "s2")) == (None, None), \
        "the undo a 25-proposal review has to have"


def test_a_permissive_batch_keeps_the_proposals_that_work(comp):
    good = hfedit.propose_scene_edit(comp, "f1", "s1",
                                     ops=[{"op": "patch", "scene_id": "s1",
                                           "patch": {"data.kicker": "GOOD"}}],
                                     rationale="good", agent="pytest")
    res = hfedit.accept_proposals(comp, [good["id"], "p999"])
    assert res["applied"] == [good["id"]] and res["failed"] == ["p999"]
    assert res["rolled_back"] is False
    assert _kicker(comp, "s1") == "GOOD", "a reviewer accepting 25 independent notes wants the 24 that work"


def test_all_or_nothing_restores_everything_on_any_failure(comp):
    good = hfedit.propose_scene_edit(comp, "f1", "s1",
                                     ops=[{"op": "patch", "scene_id": "s1", "patch": {"data.kicker": "X"}}],
                                     rationale="good", agent="pytest")
    res = hfedit.accept_proposals(comp, [good["id"], "p999"], all_or_nothing=True)
    assert res["rolled_back"] is True
    assert _kicker(comp, "s1") is None, "half a coherent change is worse than none of it"
    assert hfedit.list_proposals(comp, status="proposed"), \
        "a rolled-back proposal must be re-acceptable, not stuck as 'accepted'"


# --- the deferred state -----------------------------------------------------------------------------

def test_deferred_is_not_terminal_and_carries_its_retry(comp):
    c = hfedit.stage_comment(comp, "f1", "regenerate this still", scene_id="s1")
    hfedit.resolve_comment(comp, "f1", c["id"], status="deferred",
                           reason="ComfyUI is down", retry="acquire_for_scene(comp,'f1','s1',generate=True)")
    d = hfedit.list_deferred(comp)
    assert len(d) == 1 and d[0]["reason"] == "ComfyUI is down"
    assert "acquire_for_scene" in d[0]["retry"], "a deferral with no way back is just dropping the work"
    assert hfedit.list_changeset(comp) == [], "deferred work is not OPEN work"
    assert len(hfedit.list_changeset(comp, include_deferred=True)) == 1, \
        "'the GPU is back, re-run the batch' must be one flag"


def test_a_deferred_comment_can_still_be_resolved_later(comp):
    c = hfedit.stage_comment(comp, "f1", "regen", scene_id="s1")
    hfedit.resolve_comment(comp, "f1", c["id"], status="deferred", reason="down")
    hfedit.resolve_comment(comp, "f1", c["id"], status="applied")
    assert hfedit.list_deferred(comp) == []


def test_terminal_states_still_stick(comp):
    c = hfedit.stage_comment(comp, "f1", "x", scene_id="s1")
    hfedit.resolve_comment(comp, "f1", c["id"], status="blocked", reason="no landing spot")
    hfedit.resolve_comment(comp, "f1", c["id"], status="applied")
    spec, info = hfedit.load_frame_spec(comp, "f1")
    got = spec["frames"][info["i"]]["meta"]["comments"][0]
    assert got["status"] == "blocked", "a terminal verdict must not be overwritten"


def test_an_unknown_state_is_refused(comp):
    hfedit.stage_comment(comp, "f1", "x", scene_id="s1")
    with pytest.raises(ValueError):
        hfedit.resolve_comment(comp, "f1", status="probably-fine")


# --- the seam a human actually means -----------------------------------------------------------------

def test_a_transition_on_a_frames_last_scene_is_refused(comp):
    """A SCENE's transition_out is a within-frame GSAP seam; on the last scene it fires at exactly
    frame.dur and plays for zero visible frames. A batch agent composed a trial and caught this before
    proposing it — which is the only reason it wasn't shipped as an inert edit."""
    p = hfedit.propose_scene_edit(
        comp, "f1", "s2", ops=[{"op": "transition", "scene_id": "s2", "kind": "crossfade"}],
        rationale="soften the seam", agent="pytest")
    assert p["gate_ok"] is False
    assert "frame_transition" in p["gate_out"], "the refusal must name the op that DOES work"


def test_a_transition_on_a_non_final_scene_still_works(comp):
    p = hfedit.propose_scene_edit(
        comp, "f1", "s1", ops=[{"op": "transition", "scene_id": "s1", "kind": "crossfade"}],
        rationale="within-frame seam", agent="pytest")
    assert p["gate_ok"] is True, p["gate_out"]


def test_the_frame_level_seam_is_reachable_from_the_ops_grammar(comp):
    """`frame.transition_out` is the frame→frame clip wipe. It had NO op at all, so the one thing a
    batch agent needed for "the cut into the next section is harsh" was unreachable and the fix was
    "a one-liner you run yourself"."""
    from nolan.hyperframes.transitions import transition_kinds
    kind = sorted(transition_kinds())[0]          # a STOCKED CLIP transition, not a GSAP one
    p = hfedit.propose_scene_edit(
        comp, "f1", None, ops=[{"op": "frame_transition", "kind": kind, "dur": 1.0}],
        rationale="soften the frame seam", agent="pytest")
    assert p["gate_ok"] is True, p["gate_out"]
    hfedit.accept_proposal(comp, p["id"])
    spec, info = hfedit.load_frame_spec(comp, "f1")
    assert spec["frames"][info["i"]]["transition_out"] == {"kind": kind, "dur": 1.0}


def test_the_two_transition_vocabularies_are_not_interchangeable(comp):
    """A scene seam is a GSAP kind (`crossfade`); a frame seam is a STOCKED CLIP wipe (`ink-wipe`).
    Using one where the other belongs is a gate failure, and the refusal says which is which."""
    p = hfedit.propose_scene_edit(
        comp, "f1", None, ops=[{"op": "frame_transition", "kind": "crossfade"}],
        rationale="wrong vocabulary", agent="pytest")
    assert p["gate_ok"] is False and "not a stocked clip transition" in p["gate_out"]


def test_a_reported_gap_lands_in_the_ledger_without_a_gate_refusal(comp):
    """`log_gap` only matched gate TEXT, so the ledger was circular — it could count gaps we had
    already implemented a refusal for and was blind to every new one. An agent asked for a 3D exploded
    donut on a `pie`; `data.explode/depth/shadow` all validate rc=0 as unknown keys, so nothing was
    refused and nothing was logged."""
    hfedit.report_gap(comp, "pie", "data.explode", "asked for a 3D exploded donut with a drop shadow",
                      frame_id="f1", scene_id="s1", agent="pytest", workaround="left flat")
    gaps = hfedit.list_gaps(comp)
    row = next(g for g in gaps if g["block"] == "pie")
    assert row["field"] == "data.explode" and row["asks"] == 1
    assert row["examples"], "a counted gap must stay readable, not just tallied"


# --- a frame's scenes must FIT it ---------------------------------------------------------------------

def test_a_retime_that_overruns_the_frame_is_refused(comp):
    """Narration owns duration: `frame.dur` comes from the VO section, so time given to one scene must
    be TAKEN from another. Asked to give a timeline "+6s, from whatever else can spare it", an agent
    granted +8.7s and took back 7.16s, leaving the frame 1.56s over — reported the requirement `met`,
    and the gate passed it because the gate validates the schema and this is arithmetic.

    Measured before making it blocking: 0 of 122 shipped frames overrun."""
    p = hfedit.propose_scene_edit(
        comp, "f1", "s1", ops=[{"op": "retime", "scene_id": "s1", "dur": 9.0}],
        rationale="give s1 more room without taking it from anywhere", agent="pytest")
    assert p["gate_ok"] is False
    assert "TIMING" in p["gate_out"] and "Narration owns duration" in p["gate_out"]
    # s1 now ends at 9.0 in an 8.0s frame — the overrun is 1.00s, and the refusal must say so
    assert "+1.00s" in p["gate_out"], "the refusal must name how much to give back"


def test_a_retime_that_balances_is_accepted(comp):
    """s1 4s + s2 4s in an 8s frame: grow s1 to 6 and pull s2 back to 6.0/2.0 — total unchanged."""
    p = hfedit.propose_scene_edit(
        comp, "f1", "s1",
        ops=[{"op": "retime", "scene_id": "s1", "dur": 6.0},
             {"op": "retime", "scene_id": "s2", "start": 6.0, "dur": 2.0}],
        rationale="borrow two seconds from s2", agent="pytest")
    assert p["gate_ok"] is True, p["gate_out"]


def test_the_fit_check_is_pure_and_tolerant_of_rounding():
    fr = {"id": "f1", "dur": 10.0, "scenes": [{"id": "a", "start": 0, "dur": 5},
                                              {"id": "b", "start": 5, "dur": 5.02}]}
    assert hfedit.frame_fit_error(fr) is None, "2 centiseconds is rounding, not an overrun"
    fr["scenes"][1]["dur"] = 6.0
    assert "b" in hfedit.frame_fit_error(fr)
    assert hfedit.frame_fit_error({"id": "f", "dur": 0, "scenes": []}) is None


def test_an_introduced_overlap_is_reported_but_not_refused(comp):
    """Same-track overlap is LEGAL in a frame comp — diamond-v2 post-mortem item 5 was withdrawn for
    exactly this, and gating on it broke valid work. But an overlap that is the RESIDUE of an
    unbalanced retime is not a compositional choice. Live: an agent freed 7.16s from a neighbour,
    spent 8.72s, left the last two shots stacked for 1.56s — and reported the requirement `met`."""
    p = hfedit.propose_scene_edit(
        comp, "f1", "s1",
        ops=[{"op": "retime", "scene_id": "s1", "dur": 5.5}],     # s1 now ends 1.5s into s2
        rationale="stretch s1", agent="pytest")
    assert p["gate_ok"] is True, "legal — it must not be refused"
    assert p.get("timing") and "OVERLAP 1.50s" in p["timing"][0]
    assert "check it was intended" in p["timing"][0]


def test_a_balanced_retime_reports_no_timing_advisory(comp):
    p = hfedit.propose_scene_edit(
        comp, "f1", "s1",
        ops=[{"op": "retime", "scene_id": "s1", "dur": 6.0},
             {"op": "retime", "scene_id": "s2", "start": 6.0, "dur": 2.0}],
        rationale="borrow cleanly", agent="pytest")
    assert p["gate_ok"] is True
    seams = [n for n in p.get("timing", []) if "OVERLAP" in n or "GAP" in n]
    assert seams == [], seams        # the arithmetic balances — no seam was introduced


def test_a_pre_existing_seam_is_not_reported_as_new(comp):
    """Only what THIS edit introduced — otherwise every proposal on a comp with a deliberate overlap
    would carry a permanent false advisory."""
    spec, info = hfedit.load_frame_spec(comp, "f1")
    spec["frames"][info["i"]]["scenes"][1]["start"] = 3.0        # a deliberate 1s overlap, pre-existing
    hfedit.save_frame_spec(Path(info["spec_file"]), spec)
    p = hfedit.propose_scene_edit(comp, "f1", "s1",
                                  ops=[{"op": "patch", "scene_id": "s1", "patch": {"data.kicker": "K"}}],
                                  rationale="unrelated", agent="pytest")
    assert "timing" not in p


# --- a hand-typed timing number is a PREVIEW, not an instruction ------------------------------------

def _fr(scenes, dur=8.0):
    return {"id": "f1", "dur": dur, "scenes": scenes}


def test_a_retime_whose_anchor_did_not_move_is_reported_as_transient():
    """`place_scenes` rewrites start/dur for every scene on every finish, from the anchors. A July
    retime on 06-dido/c1 was found already back at its pre-edit values — the edit applied, the render
    honoured it, and the next hf-finish silently put it back. Nobody was told, at either end."""
    before = _fr([{"id": "s1", "start": 0, "dur": 4, "data": {"anchor": "the ships burn"}},
                  {"id": "s2", "start": 4, "dur": 4, "data": {"anchor": "he sails on"}}])
    after = _fr([{"id": "s1", "start": 0, "dur": 4, "data": {"anchor": "the ships burn"}},
                 {"id": "s2", "start": 5.5, "dur": 2.5, "data": {"anchor": "he sails on"}}])
    notes = hfedit.retime_durability(before, after)
    assert any("TRANSIENT" in n and "s2" in n and "anchor" in n for n in notes)


def test_a_retime_that_moves_the_anchor_is_not_flagged():
    """Moving the anchor is the SANCTIONED way to move a shot — the hand numbers then merely preview
    what sync will compute. Flagging it would train agents to ignore the advisory."""
    before = _fr([{"id": "s1", "start": 0, "dur": 4, "data": {"anchor": "the ships burn"}},
                  {"id": "s2", "start": 4, "dur": 4, "data": {"anchor": "he sails on"}}])
    after = _fr([{"id": "s1", "start": 0, "dur": 4, "data": {"anchor": "the ships burn"}},
                 {"id": "s2", "start": 5.5, "dur": 2.5, "data": {"anchor": "Augustus himself"}}])
    assert hfedit.retime_durability(before, after) == []


def test_lengthening_a_scene_names_the_NEXT_scenes_anchor():
    """dur is derived as the next scene's start minus this one's, so the lever for "hold it longer"
    is the NEXT anchor. An agent told only "it reverts" would move the wrong one."""
    before = _fr([{"id": "s1", "start": 0, "dur": 4, "data": {"anchor": "the ships burn"}},
                  {"id": "s2", "start": 4, "dur": 4, "data": {"anchor": "he sails on"}}])
    after = _fr([{"id": "s1", "start": 0, "dur": 6, "data": {"anchor": "the ships burn"}},
                 {"id": "s2", "start": 6, "dur": 2, "data": {"anchor": "he sails on"}}])
    notes = hfedit.retime_durability(before, after)
    assert any("s1" in n and "s2's anchor" in n for n in notes), notes


def test_a_structural_edit_is_exempt():
    """v5's p5/p6 hand-compute a timeline around a scene they ADD with its own anchor — sync then
    recomputes it correctly. Measured: a blocking rule scored 0 true positives and these 2 false ones
    across 59 proposals, which is why this is advisory AND structurally exempt."""
    before = _fr([{"id": "s1", "start": 0, "dur": 4, "data": {"anchor": "the ships burn"}},
                  {"id": "s2", "start": 4, "dur": 4, "data": {"anchor": "he sails on"}}])
    after = _fr([{"id": "s1", "start": 0, "dur": 4, "data": {"anchor": "the ships burn"}},
                 {"id": "s1b", "start": 4, "dur": 2, "data": {"anchor": "the bill comes due"}},
                 {"id": "s2", "start": 6, "dur": 2, "data": {"anchor": "he sails on"}}])
    assert hfedit.retime_durability(before, after) == []


def test_the_last_scenes_dur_cannot_be_authored_at_all():
    before = _fr([{"id": "s1", "start": 0, "dur": 4, "data": {"anchor": "the ships burn"}},
                  {"id": "s2", "start": 4, "dur": 4, "data": {"anchor": "he sails on"}}])
    after = _fr([{"id": "s1", "start": 0, "dur": 4, "data": {"anchor": "the ships burn"}},
                 {"id": "s2", "start": 4, "dur": 2, "data": {"anchor": "he sails on"}}])
    notes = hfedit.retime_durability(before, after)
    assert any("LAST scene" in n for n in notes), notes


def test_the_single_edit_path_reports_it_too(comp):
    """The proposal gate was not where this bit — a human dragging a scene in the edit UI was."""
    res = hfedit.retime_scene(comp, "f1", "s2", start=5.5, dur=2.5)
    assert res.get("applied"), res
    assert any("TRANSIENT" in n for n in res.get("timing", [])), res


def test_the_review_sheet_actually_shows_the_timing_advisory(comp):
    """The advisory existed for a day and reached nobody: `propose_scene_edit` wrote `prop["timing"]`
    and no consumer read it, so BATCH_REVIEW.md rendered a batch as clean while the gate had findings.
    An authored field with no consumer is a bug (CLAUDE.md), and an ADVISORY with no consumer is the
    worse kind — the reviewer reads the silence as "checked"."""
    from nolan.hyperframes import contact_sheet as cs
    p = hfedit.propose_scene_edit(comp, "f1", "s2",
                                  ops=[{"op": "retime", "scene_id": "s2", "start": 5.5, "dur": 2.5}],
                                  rationale="nudge it later", agent="pytest")
    assert p.get("timing"), "the gate must flag a retime whose anchor did not move"
    sheet = cs.build_sheet(comp, previews=False)
    row = next(r for r in sheet["rows"] if r["proposal_id"] == p["id"])
    assert row["timing"] == p["timing"]
    assert sheet["summary"]["timing_notes"] >= 1
    md = cs.write_markdown(comp, sheet).read_text(encoding="utf-8")
    assert "**timing**" in md and "TRANSIENT" in md
