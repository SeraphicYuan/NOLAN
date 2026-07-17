"""Phase 4 of the HF edit-loop program (docs/HF_EDIT_LOOP.md): agent/batch edits are PROPOSALS
(draft → gate → human accept), never direct mutations of the canonical spec. Covers propose (gated,
non-mutating), accept (applies through the gate + provenance + resolves the comment), reject (reopens it),
and that the batch brief instructs the agent to propose."""
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"

from nolan.hyperframes import edit as hfedit           # noqa: E402
from nolan.hyperframes import batch as hfbatch         # noqa: E402


@pytest.fixture()
def comp():
    """A throwaway comp with a gate-passing `statement` scene (so author.py --validate-only can run)."""
    name = "_hf_proposals_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    fdir = dst / "compositions" / "frames"
    fdir.mkdir(parents=True)
    (fdir / "f1.spec.json").write_text(json.dumps({"frames": [{"id": "f1", "dur": 8.0, "scenes": [
        {"id": "s1", "type": "statement", "start": 0, "dur": 5, "data": {"lines": ["hello"]}}]}]}), encoding="utf-8")
    (dst / "hyperframes.json").write_text('{"theme":"highlighter-editorial"}', encoding="utf-8")
    try:
        yield name
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def _canonical_kicker(comp):
    spec, info = hfedit.load_frame_spec(comp, "f1")
    return spec["frames"][info["i"]]["scenes"][0]["data"].get("kicker")


def test_propose_gates_without_touching_canonical(comp):
    p = hfedit.propose_scene_edit(comp, "f1", "s1",
                                  ops=[{"op": "patch", "scene_id": "s1", "patch": {"data.kicker": "HELLO"}}],
                                  rationale="add a kicker", agent="nolan1", comment_id="c1")
    assert p["gate_ok"] is True and p["status"] == "proposed"
    assert _canonical_kicker(comp) is None                 # canonical spec is UNTOUCHED by a proposal
    props = hfedit.list_proposals(comp, status="proposed")
    assert len(props) == 1 and props[0]["provenance"]["agent"] == "nolan1"

    # a proposal whose ops FAIL the gate is recorded but flagged (not silently kept)
    bad = hfedit.propose_scene_edit(comp, "f1", "s1",
                                    ops=[{"op": "patch", "scene_id": "s1", "patch": {"data.lines": []}}],  # empty → gate fail
                                    rationale="break it")
    assert bad["gate_ok"] is False and bad["gate_out"]


def test_accept_applies_to_canonical_with_provenance(comp):
    hfedit.stage_comment(comp, "f1", "add a kicker", scene_id="s1")   # a staged comment (c1)
    cid = hfedit.list_changeset(comp)[0]["id"]
    p = hfedit.propose_scene_edit(comp, "f1", "s1",
                                  ops=[{"op": "patch", "scene_id": "s1", "patch": {"data.kicker": "WORKED"}}],
                                  rationale="add a kicker", agent="nolan2", comment_id=cid)
    r = hfedit.accept_proposal(comp, p["id"])
    assert r["applied"] is True and r["proposal"]["status"] == "accepted"
    assert _canonical_kicker(comp) == "WORKED"             # now the canonical spec HAS the edit
    # provenance stamped on the scene; the linked comment resolved
    spec, info = hfedit.load_frame_spec(comp, "f1")
    prov = spec["frames"][info["i"]]["scenes"][0]["meta"]["provenance"]
    assert any(x.get("agent") == "nolan2" and x.get("kind") == "proposal" for x in prov)
    assert not hfedit.list_changeset(comp)                 # the comment left the changeset (applied)


def test_reject_reopens_comment(comp):
    hfedit.stage_comment(comp, "f1", "try something", scene_id="s1")
    cid = hfedit.list_changeset(comp)[0]["id"]
    p = hfedit.propose_scene_edit(comp, "f1", "s1",
                                  ops=[{"op": "patch", "scene_id": "s1", "patch": {"data.kicker": "NOPE"}}],
                                  rationale="maybe", agent="nolan3", comment_id=cid)
    out = hfedit.reject_proposal(comp, p["id"], reason="not what I meant")
    assert out["proposal"]["status"] == "rejected"
    assert _canonical_kicker(comp) is None                 # canonical never touched
    assert len(hfedit.list_changeset(comp)) == 1           # the comment was REOPENED for re-dispatch


def test_batch_brief_instructs_proposals(comp):
    hfedit.stage_comment(comp, "f1", "brighten it", scene_id="s1")
    brief, cs = hfbatch.compile_batch_brief(comp)
    assert "propose_scene_edit" in brief and "PROPOSAL" in brief
    assert "brighten it" in brief and "scene s1" in brief


def test_batch_brief_frame_scope():
    """A frame-level batch scopes to one frame's comments; None = the whole project (both frames)."""
    name = "_hf_batchscope_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    fdir = dst / "compositions" / "frames"
    fdir.mkdir(parents=True)
    for fid in ("f1", "f2"):
        (fdir / f"{fid}.spec.json").write_text(json.dumps({"frames": [{"id": fid, "dur": 8.0, "scenes": [
            {"id": "s1", "type": "statement", "start": 0, "dur": 5, "data": {"lines": ["hi"]}}]}]}), encoding="utf-8")
    (dst / "hyperframes.json").write_text('{"theme":"highlighter-editorial"}', encoding="utf-8")
    try:
        hfedit.stage_comment(name, "f1", "edit one", scene_id="s1")
        hfedit.stage_comment(name, "f2", "edit two", scene_id="s1")
        _, all_cs = hfbatch.compile_batch_brief(name)               # whole project
        _, f1_cs = hfbatch.compile_batch_brief(name, frame_id="f1")  # just f1
        assert len(all_cs) == 2 and len(f1_cs) == 1 and f1_cs[0]["frame_id"] == "f1"
    finally:
        shutil.rmtree(dst, ignore_errors=True)
