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
