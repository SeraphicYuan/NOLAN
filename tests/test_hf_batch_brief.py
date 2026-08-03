"""What the batch agent is actually TOLD, and the two bookkeeping bugs behind its reports.

Everything here is derived from one 25-comment batch-edit run:

  * the brief never carried the block CATALOG, so the agent had to read compose.py to discover that
    `juxtaposition` consumes `backdrop` (a colour) and not `ground` — 3 of 25 notes hit that;
  * the brief never carried the NARRATION, so a re-anchor was retyped from the script instead of copied
    from the transcript ("someone taught it to you" vs the spoken "somebody") — the single genuine
    regression of the batch;
  * `_extract_requirements` split on `.`, which tore a cited URL into three "requirements" and made the
    coverage report — the only channel by which a missed ask is visible — read as nonsense;
  * proposal ids came from `len(props)+1` under a read-modify-write, so two writers collide.
"""
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"

from nolan.hyperframes import batch as hfbatch        # noqa: E402
from nolan.hyperframes import edit as hfedit          # noqa: E402

_VO = "what they promised was one thing and what it cost was somebody else's problem".split()


@pytest.fixture()
def comp():
    name = "_hf_batch_brief_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    fdir = dst / "compositions" / "frames"
    fdir.mkdir(parents=True)
    (fdir / "01-beat.spec.json").write_text(json.dumps({"frames": [{"id": "01-beat", "dur": 10.0, "scenes": [
        {"id": "s1", "type": "juxtaposition", "start": 0, "dur": 5,
         "data": {"left": {"type": "text", "text": "promised"}, "right": {"type": "text", "text": "cost"},
                  "anchor": "what they promised"}},
        {"id": "s2", "type": "statement", "start": 5, "dur": 5, "data": {"lines": ["and what it cost"]}},
    ]}]}), encoding="utf-8")
    (dst / "hyperframes.json").write_text('{"theme":"highlighter-editorial"}', encoding="utf-8")
    (dst / "audio_meta.json").write_text(json.dumps({"voices": [{
        "frame": 1, "path": "assets/voice/01.wav", "duration_s": 10.0,
        "words": [{"word": w, "start": i * 0.5, "end": i * 0.5 + 0.4} for i, w in enumerate(_VO)]}]}),
        encoding="utf-8")
    try:
        yield name
    finally:
        shutil.rmtree(dst, ignore_errors=True)


# --- requirement extraction ---------------------------------------------------------------------

def test_a_cited_url_stays_one_requirement():
    reqs = hfbatch._extract_requirements(
        "make it kinetic. see https://www.youtube.com/watch?v=abc123 for the look")
    assert len(reqs) == 2, f"a URL must not be split on its dots: {reqs}"
    assert "https://www.youtube.com/watch?v=abc123" in reqs[1]["text"]


def test_ordinary_sentences_still_split():
    reqs = hfbatch._extract_requirements("swap the photo. then slow the reveal; also fix the kicker")
    assert [r["id"] for r in reqs] == ["r1", "r2", "r3"]


def test_extraction_is_never_empty():
    assert hfbatch._extract_requirements("hmm") == [{"id": "r1", "text": "hmm"}]


# --- the brief -----------------------------------------------------------------------------------

def test_brief_carries_the_catalog_for_blocks_in_play(comp):
    hfedit.stage_comment(comp, "01-beat", "put a photo behind this", scene_id="s1")
    brief, _ = hfbatch.compile_batch_brief(comp)
    assert "Block capabilities" in brief
    assert "**juxtaposition**" in brief and "backdrop" in brief, \
        "the block whose ground-lessness cost 3 of 25 notes must be described in the brief"
    assert "**layout**" in brief, "the general conversion path is always briefed, in play or not"
    assert "NOT consumed" in brief and "REFUSED" in brief, "state the negative explicitly"


def test_brief_carries_the_spoken_narration_per_scene(comp):
    hfedit.stage_comment(comp, "01-beat", "re-anchor this", scene_id="s1")
    brief, _ = hfbatch.compile_batch_brief(comp)
    assert "VO:" in brief
    assert "what they promised was one thing" in brief, "the agent must be able to COPY the anchor"
    assert "anchor='what they promised'" in brief


def test_brief_states_the_anchor_and_verify_contracts(comp):
    hfedit.stage_comment(comp, "01-beat", "tweak", scene_id="s1")
    brief, _ = hfbatch.compile_batch_brief(comp)
    assert "VERBATIM" in brief and "UNRESOLVED" in brief
    assert "snapshot_frame" in brief and "proposal_preview" in brief
    assert "acquire_for_scene" in brief and "never write `pool.json`" in brief
    assert "--verify" in brief and "MANDATORY" in brief


def test_empty_changeset_says_so(comp):
    brief, cs = hfbatch.compile_batch_brief(comp)
    assert cs == [] and "No staged comments" in brief


# --- proposal id / concurrency --------------------------------------------------------------------

def test_ids_come_from_the_ids_present_not_from_len():
    assert hfedit._next_proposal_id([]) == "p1"
    assert hfedit._next_proposal_id([{"id": "p1"}, {"id": "p7"}]) == "p8", \
        "len()+1 would return p3 and collide with a live proposal"
    assert hfedit._next_proposal_id([{"id": "weird"}]) == "p1"


def test_concurrent_proposals_neither_collide_nor_vanish(comp):
    """Two writers each read-modify-write the same array; without the lock one proposal is lost."""
    from concurrent.futures import ThreadPoolExecutor

    def mk(i):
        return hfedit.propose_scene_edit(
            comp, "01-beat", "s2",
            ops=[{"op": "patch", "scene_id": "s2", "patch": {"data.kicker": f"K{i}"}}],
            rationale=f"r{i}", agent=f"a{i}")

    with ThreadPoolExecutor(max_workers=6) as ex:
        made = list(ex.map(mk, range(6)))
    ids = [p["id"] for p in made]
    assert len(set(ids)) == 6, f"ids collided: {ids}"
    assert len(hfedit.list_proposals(comp)) == 6, "a proposal was lost to a concurrent write"


def test_the_lock_is_released_even_when_the_gate_rejects(comp):
    hfedit.propose_scene_edit(comp, "01-beat", "s1",
                              ops=[{"op": "patch", "scene_id": "s1", "patch": {"data.left": None}}],
                              rationale="bad", agent="pytest")
    assert not (hfedit._comp_dir(comp) / ".hf_proposals.lock").exists()
    assert hfedit.propose_scene_edit(comp, "01-beat", "s2",
                                     ops=[{"op": "patch", "scene_id": "s2",
                                           "patch": {"data.kicker": "ok"}}],
                                     rationale="fine", agent="pytest")["id"] == "p2"


# --- the mandatory closing step -------------------------------------------------------------------

def test_batch_verify_runs_the_pre_render_gates_and_reports(comp, monkeypatch):
    """The proposal gate is a SPEC check. Word-sync, the timing gate and the provenance/style gates
    live in the finish DAG and never run at propose/accept time — so a batch could be fully reviewed
    and accepted and only THEN hard-block. `batch_verify` is that pass, made a step of the loop."""
    seen = {}

    class _R:
        returncode = 1
        stdout = ("word-sync: 01-beat/s1 UNRESOLVED (anchor not found — placed by fallback)\n"
                  "  ok: everything else\n")
        stderr = "✗ scene-timing gate: s2 visual lag 7.2s\n"

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return _R()

    monkeypatch.setattr(hfbatch.subprocess, "run", fake_run)
    res = hfbatch.batch_verify(comp)
    assert "--no-render" in seen["cmd"] and "nolan.hyperframes.finish" in seen["cmd"]
    assert "--no-sound" in seen["cmd"], "the bgm step can wipe voices[] while iterating"
    assert res["ok"] is False
    assert any("UNRESOLVED" in f for f in res["findings"])
    assert any("visual lag" in f for f in res["findings"])


def test_batch_verify_passes_cleanly(comp, monkeypatch):
    class _R:
        returncode = 0
        stdout = "OK — spec validates\n  built 01-beat.html\n"
        stderr = ""

    monkeypatch.setattr(hfbatch.subprocess, "run", lambda cmd, **kw: _R())
    res = hfbatch.batch_verify(comp)
    assert res["ok"] is True and res["findings"] == []
    acts = hfedit.list_activity(comp)
    assert any("verify" in a.get("summary", "") for a in acts), "the verify verdict belongs in the feed"


# --- frame-sharded dispatch -----------------------------------------------------------------------

def test_shards_split_by_FRAME_so_two_agents_never_share_a_spec_file():
    cs = [{"frame_id": "f1", "id": "c1"}, {"frame_id": "f1", "id": "c2"},
          {"frame_id": "f2", "id": "c3"}, {"frame_id": "f3", "id": "c4"}]
    shards = hfbatch.shard_by_frame(cs, 2)
    assert sum(len(s) for s in shards) == 3
    flat = [f for s in shards for f in s]
    assert sorted(flat) == ["f1", "f2", "f3"]
    assert len(set(flat)) == len(flat), "a frame must appear in exactly ONE shard — it is one spec file"


def test_shards_balance_by_comment_count_not_frame_count():
    cs = ([{"frame_id": "heavy", "id": f"c{i}"} for i in range(8)]
          + [{"frame_id": "a", "id": "x"}, {"frame_id": "b", "id": "y"}, {"frame_id": "c", "id": "z"}])
    shards = hfbatch.shard_by_frame(cs, 2)
    loads = sorted(sum(sum(1 for c in cs if c["frame_id"] == f) for f in s) for s in shards)
    assert loads == [3, 8], f"the 8-comment frame should not share a shard with all the rest: {shards}"


def test_more_agents_than_frames_leaves_no_empty_shard():
    cs = [{"frame_id": "f1", "id": "c1"}]
    assert hfbatch.shard_by_frame(cs, 6) == [["f1"]]


def test_sharded_dispatch_tells_each_agent_its_boundary(comp, monkeypatch):
    hfedit.stage_comment(comp, "01-beat", "one", scene_id="s1")
    sent = []
    import nolan.webui.operations as ops
    monkeypatch.setattr(ops, "_dispatch_to_tmux", lambda s, m: sent.append((s, m)))
    res = hfbatch.dispatch_batch_sharded(comp, ["nolan1", "nolan2"])
    assert res["ok"] and len(res["shards"]) == 1          # only one frame exists
    kick = Path(res["shards"][0]["brief_path"]).read_text(encoding="utf-8")
    assert "Your shard is these frames and ONLY these: 01-beat" in kick
    assert "another agent" in kick, "the isolation rule must be stated, not assumed"
    assert "nolan-hf-edit" in sent[0][1], "the kickoff must point at the skill that carries the contract"


def test_sharded_dispatch_marks_only_its_own_comments(comp, monkeypatch):
    hfedit.stage_comment(comp, "01-beat", "one", scene_id="s1")
    import nolan.webui.operations as ops
    monkeypatch.setattr(ops, "_dispatch_to_tmux", lambda s, m: None)
    hfbatch.dispatch_batch_sharded(comp, ["nolan1"])
    assert hfedit.list_changeset(comp) == [], "dispatched comments leave the changeset"
