"""Batch-agent edit mode (#5) for compose-first HyperFrames.

The loop the human wants: stage free-text comments across many frames (the changeset, #4), then hand the
WHOLE batch to ONE Claude agent that edits each frame and re-renders. This module is the two new pieces:

  compile_batch_brief(comp)  → ONE detailed, self-contained agent brief from the changeset + project/frame
                               context ("automatically generate a nice detailed instruction").
  dispatch_batch(comp, ...)  → write the brief as a kickoff file (with provenance), dispatch it to a tmux
                               fleet agent (reusing operations._dispatch_to_tmux), mark the comments dispatched.

Contract (CLAUDE.md): the agent's output is a PROPOSAL — it records edits via `propose_scene_edit` (each
gated by author.py --validate-only), which NEVER touch the canonical spec; the human reviews the ops +
rationale and `accept_proposal`s the ones they want (that is what applies them through the gate). Draft →
validate → accept. No side-doors into canonical files.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .edit import (_comp_dir, catalog, frame_transcripts, list_assets, list_changeset, load_frame_spec,
                   log_activity, resolve_comment, resolve_mentions, save_frame_spec)

_SKILL = "hyperframes-batch@2"

# The block types every batch brief carries even when no comment touches them: they are the answers the
# agent needs when a note asks for something its current block can't do (`layout` is the general
# arranger and the documented conversion path; the three text blocks are where a prose beat lands).
_ALWAYS_BRIEF = ("layout", "statement", "stat", "pull_quote")

_URL_RE = re.compile(r"https?://\S+")


def _extract_requirements(text: str) -> List[Dict[str, str]]:
    """Decompose a comment into atomic, checkable requirements so the agent maps each op to one and REPORTS
    coverage — turning a silent miss (e.g. 'add kinetic work' collapsed into nothing) into a visible one at
    review. Heuristic: split on sentence/imperative boundaries. Advisory, never a gate. Never empty.

    URLs are MASKED before the split and restored after: a bare `.`/`;` split tore
    `https://www.youtube.com/watch?v=…` into three "requirements" (`…https://www`, `youtube`,
    `com/watch?v=…`), which made the coverage report — the batch loop's only honesty channel — read as
    nonsense for any comment that cited a source."""
    text = (text or "").strip()
    if not text:
        return []
    urls: List[str] = []

    def _mask(m):
        urls.append(m.group(0))
        return f"\x00U{len(urls) - 1}\x00"
    masked = _URL_RE.sub(_mask, text)
    parts = re.split(r"[.;\n]+|\s+(?:then|also|and then)\s+", masked, flags=re.I)
    reqs = []
    for p in parts:
        p = p.strip(" ,").strip()
        for i, u in enumerate(urls):
            p = p.replace(f"\x00U{i}\x00", u)
        if len(p) >= 4:
            reqs.append(p)
    return [{"id": f"r{i + 1}", "text": r} for i, r in enumerate(reqs)] or [{"id": "r1", "text": text}]


def _capability_brief(block_types) -> str:
    """The catalog slice for the blocks IN PLAY — purpose + the EXACT data fields each one consumes.

    `_catalog_brief` (the single-note LLM path) has always had this; the batch brief did not, which is
    why a batch agent had to read compose.py to discover that `juxtaposition` takes `backdrop` (a colour)
    and not `ground`. Three of twenty-five notes in one batch asked for a background on that block. The
    answer was on disk the whole time; it just was not delivered."""
    cat = catalog()
    templ = cat.get("scene_templates", {})
    want = sorted({t for t in block_types if t in templ} | {t for t in _ALWAYS_BRIEF if t in templ})
    L = ["## Block capabilities (the blocks in play — the catalog is the TRUTH, not compose.py)",
         "A field NOT listed for a block is NOT consumed by it: writing it validates and paints nothing.",
         "`data.ground` (image/paper) is REFUSED on a block that doesn't paint it — the gate names the",
         "alternative, and logs the ask as a capability gap. A VIDEO ground root-mounts on any block.", ""]
    for t in want:
        e = templ[t]
        fields = ", ".join((e.get("data_schema") or {}).keys())
        L.append(f"- **{t}** — {(e.get('purpose') or '')[:140]}")
        L.append(f"    data: {fields}")
        if e.get("not_for"):
            L.append(f"    not for: {(e['not_for'])[:120]}")
    trans = ", ".join(k for k in cat.get("transitions", {}) if k != "_doc")
    revs = ", ".join(k for k in cat.get("reveals", {}) if k != "_doc")
    L += ["", f"TRANSITIONS: {trans}", f"REVEALS: {revs}", ""]
    return "\n".join(L)


def _theme(comp: str) -> str:
    try:
        return json.loads((_comp_dir(comp) / "hyperframes.json").read_text(encoding="utf-8")).get("theme") or ""
    except Exception:
        return ""


def compile_batch_brief(comp: str, frame_id: Optional[str] = None,
                        persist_requirements: bool = False) -> Tuple[str, List[Dict]]:
    """Compile the pending changeset + project/frame context into one agent brief. Returns (markdown, changeset).
    `frame_id` scopes to a single frame (the frame-level batch); None = the whole project (every frame).
    `persist_requirements` (set at DISPATCH, not the read-only preview) extracts + stores a requirement
    checklist on each comment so the kickoff lists explicit, checkable asks the agent reports coverage on."""
    changeset = [c for c in list_changeset(comp) if not frame_id or c.get("frame_id") == frame_id]
    by_frame: Dict[str, List[Dict]] = {}
    for c in changeset:
        by_frame.setdefault(c["frame_id"], []).append(c)
    asset_paths = [a["path"] for a in list_assets(comp)]   # for the legacy positional @assetN fallback

    L = [f"# Batch edit — HyperFrames comp `{comp}`", "",
         "**Load the `nolan-hf-edit` skill first — it is the CONTRACT.** This file is the DATA for one "
         "run (which frames, which comments, what each scene says and shows); the skill carries the "
         "rules that do not change between runs: the proposal contract, the ops grammar, the anchor "
         "rule, the verify tiers, acquisition, the concurrency policy and the closing step. Everything "
         "restated below is a summary of it, not a replacement.", "",
         f"Theme: **{_theme(comp) or '(default)'}**.  Frames to edit: **{len(by_frame)}**, "
         f"comments: **{len(changeset)}**.", ""]
    if not changeset:
        L.append("_No staged comments — nothing to do. Stage frame comments first._")
        return "\n".join(L), changeset

    blocks_in_play = set()
    for fid in by_frame:
        try:
            spec, info = load_frame_spec(comp, fid)
            blocks_in_play |= {s.get("type") for s in spec["frames"][info["i"]].get("scenes", [])}
        except Exception:
            pass

    for fid, comments in by_frame.items():
        fr = None
        narration: Dict[str, str] = {}
        try:
            spec, info = load_frame_spec(comp, fid)
            fr = spec["frames"][info["i"]]
            try:
                narration = frame_transcripts(comp, fid)
            except Exception:
                narration = {}
            # Per scene: what block it is, its window, its narration ANCHOR, and — the piece the brief
            # never carried — the words actually SPOKEN over it. An agent that can read the narration can
            # re-anchor correctly; one that can't will invent an anchor that never resolves.
            rows = []
            for s in fr.get("scenes", []):
                anc = (s.get("data", {}) or {}).get("anchor") or s.get("anchor") or ""
                said = (narration.get(s.get("id")) or "").strip()
                rows.append(f"    - `{s.get('id')}` {s.get('type')} "
                            f"[{float(s.get('start', 0) or 0):.1f}s +{float(s.get('dur', 0) or 0):.1f}s]"
                            + (f" anchor={anc!r}" if anc else "")
                            + (f"\n        VO: “{said[:220]}”" if said else ""))
            scenes = "\n" + "\n".join(rows) if rows else "(none)"
            head = f"## Frame `{fid}`  (dur {fr.get('dur', '?')}s)"
        except Exception:
            spec = info = None
            scenes, head = "(spec unavailable)", f"## Frame `{fid}`"
        # At dispatch, extract + persist a requirement checklist onto each comment (idempotent).
        by_id = {cm.get("id"): cm for cm in (fr.get("meta", {}).get("comments", []) if fr else [])}
        dirty = False
        if persist_requirements and fr is not None:
            for c in comments:
                cm = by_id.get(c["id"])
                if cm is not None and not cm.get("requirements"):
                    cm["requirements"] = _extract_requirements(cm.get("text"))
                    c["requirements"] = cm["requirements"]
                    dirty = True
            if dirty:
                save_frame_spec(Path(info["spec_file"]), spec)
        L.append(head)
        L.append(f"Current scenes: {scenes}")
        L.append("Requested edits:")
        for c in comments:
            tgt = f"  _(scene {c['scene_id']})_" if c.get("scene_id") else ""
            L.append(f"  - {c['text']}{tgt}")
            # Resolve @-mentions so the agent gets real refs, not a positional '@asset0' it can't decode.
            for line in resolve_mentions(c.get("text"), fr, asset_paths, c.get("mentions")):
                L.append(f"    · {line}")
            reqs = c.get("requirements") or (by_id.get(c["id"], {}).get("requirements") if by_id else None)
            if reqs:
                L.append("    Requirements — satisfy EACH, then report coverage on the proposal:")
                for r in reqs:
                    L.append(f"      [{r['id']}] {r['text']}")
        L.append("")

    L.append(_capability_brief(blocks_in_play))
    L += [
        "## Anchors — a new or changed `anchor` must be VERBATIM from the transcript",
        "A scene's `anchor` is the spoken phrase it lands on. `sync.place_scenes` locates it as an exact "
        "token subsequence of the aligned VO, so a paraphrase does not merely score lower — it does not "
        "match at all, the scene is placed by fallback, and the report reads `UNRESOLVED @conf 0.0`. In "
        "one batch the single genuine regression in 25 edits was exactly this: the anchor said "
        "\"someone taught it to you\", the VO says \"somebody\".",
        "So: COPY the anchor out of the `VO:` line above — never retype it from the script. Anchor the "
        "phrase where the beat's topic OPENS, not a closing aside, and not a number (Whisper writes "
        "numbers as digits, so a spelled-out number-leading anchor mis-matches).",
        "An anchor edit changes NOTHING until `word-sync` runs — see the closing step below.",
        "",
        "## Verify BEFORE you propose — a render is the last resort, not the first check",
        "Costs, cheapest first: read the spec (free) · `hfedit.recompose_frame` (~1s, proves it composes) · "
        "`hfedit.snapshot_frame(comp, frame_id, at=<t>)` (seconds — a still of ONE frame's scaffold; never "
        "snapshot the whole comp, it loads every root video and times out) · "
        "`hfedit.proposal_preview(comp, proposal_id)` (a still of what the proposal WOULD look like, "
        "canonical untouched) · a full frame render (minutes — only when motion or a video ground is the "
        "point).",
        "A menu caption is a CLAIM; the pixels are the fact. Contact-sheet every clip you place "
        "(`ffmpeg -ss 1 -i <clip> -frames:v 1 -vf scale=480:-1 out.jpg`) before proposing it — watermarks, "
        "hard-subs and branded uploads are invisible to every text-level gate.",
        "",
        "## How to apply — PROPOSALS, not direct edits (the contract)",
        "You do NOT touch the canonical spec. For EACH requested edit, build a structured op plan and record it "
        "as a **PROPOSAL** the human reviews + accepts:",
        "```python",
        "from nolan.hyperframes import propose_scene_edit",
        f"propose_scene_edit(comp='{comp}', frame_id='<frame>', scene_id='<scene>',",
        "    ops=[{'op':'patch','scene_id':'<scene>','patch':{'data.<field>': <value>},'deletes':[]}],",
        "    rationale='<one line: what changes and why>', agent='<your session>', comment_id='<comment id>')",
        "```",
        "Op kinds (the `_apply_ops` plan): `patch` (scene_id, patch:{'data.x':v,'start':s,'dur':d}, deletes:[]) · "
        "`add` (scene:{…}, index?) · `remove` (scene_id) · `retime` (scene_id, start?, dur?) · `transition` "
        "(scene_id, kind, dur?). Each proposal is GATED (author.py --validate-only) at creation; one that fails "
        "is recorded `blocked` with the gate output — fix and re-propose.",
        "Split by computability: an asset swap / timing / motion change is a deterministic `patch`; reserve "
        "judgement for the open-ended notes. Do NOT recompose or render — the human accepts each proposal "
        "(which applies it through the gate + rebuilds) and re-renders.",
        "This is FULL-AUTO: make reasonable calls yourself (don't stop to ask); the human eyeballs the END "
        "result. So SHOW YOUR WORK — pass `requirements=[{'req_id':'r1','status':'met|partial|unmet|deferred',"
        "'note':'…'}]` to propose_scene_edit, mapping your ops to each Requirement above. An honest `unmet`/"
        "`deferred` (e.g. a note with no landing spot, or materials you couldn't source) is a first-class "
        "signal — surface it, don't bury or fake it.",
        "A refusal that says CAPABILITY-GAP is NOT your mistake — the block genuinely cannot do what the "
        "note asked. It is logged as a feature request; record the requirement `unmet` (or `partial` with "
        "the cost, if you convert the scene to another block) and move on.",
        "",
        "## Assets — never hand-roll acquisition",
        "To get new footage/stills for a scene use `nolan.hyperframes.acquire_scene.acquire_for_scene("
        "comp, frame_id, scene_id, ...)`: it derives the need from that scene's own narration + window "
        "(so `min_duration` is right), runs the FULL engine (library, clips, transcript tiers, stock, "
        "museums, generation) with relevance + fitness + dedup + the VLM usability floor, dedups against "
        "what this essay already uses, and MERGES into `pool.json`.",
        "Do NOT call the whole-project pool bridge to fetch one asset, and never write `pool.json` "
        "yourself. A locally-dropped file goes through `hfedit.add_scene_asset` (validates the bytes, "
        "registers it in the pool with provenance).",
        "",
        "## Closing step — MANDATORY, once, after your last proposal",
        "`python -X utf8 -m nolan.hyperframes.batch --verify <comp>` (or `batch_verify(comp)`) runs "
        "`hf-finish --no-render`: word-sync, the timing gate, number/math provenance and the style gate. "
        "Those are the HARD gates, they do NOT run at proposal time, and an unresolved anchor or a "
        "≥6s visual lag will block the render AFTER the human has finished reviewing. Report its verdict "
        "in your final message — a batch that ends without it is not done.",
        "",
        "Report progress to `.nolan/agents/<agent>.json` via `nolan.fleet.write_status` (working→done|error).",
    ]
    return "\n".join(L), changeset


_GATE_MARKERS = ("UNRESOLVED", "visual lag", "mis-order", "SPEC REJECTED", "STYLE", "provenance",
                 "CAPABILITY-GAP", "weak anchor")


def batch_verify(comp: str, sound: bool = False, timeout: int = 1800) -> Dict:
    """The MANDATORY closing step of a batch: run the finish DAG up to (not including) the render.

    Why this exists. The proposal gate is `author.py --validate-only` — a SPEC check. The gates that
    actually stop a render are further down the DAG and see things a spec cannot: `word-sync` resolves
    every anchor against the aligned VO, the scene-timing gate HARD-BLOCKS a ≥6s visual lag or a
    mis-ordered scene, and the number/math-provenance and style gates run on the assembled composition.
    None of them run when a proposal is created or accepted. So a batch could be fully proposed, fully
    reviewed and fully accepted, and only THEN hard-block — after every human turn had been spent.

    Costs about a minute and needs no new checking code: it is the pre-render half of `hf-finish` that
    the pipeline skill already prescribes, made a step of the batch loop instead of something an agent
    might remember. `--no-sound` by default because the bgm step can wipe `voices[]` while iterating.
    """
    # `--no-autoground`: a VERIFY must not change the video. auto-ground picks a picture for a long
    # hold by fit and writes it to the canonical spec — during one review pass it placed grounds on 6
    # scenes, including a Met CC0 painting behind the closing thesis of an AI data-centre essay. It
    # still REPORTS what it would place, so the information is not lost, only the silent write is.
    cmd = [sys.executable, "-X", "utf8", "-m", "nolan.hyperframes.finish", comp,
           "--no-render", "--no-autoground"]
    if not sound:
        cmd.append("--no-sound")
    try:
        r = subprocess.run(cmd, cwd=str(Path(__file__).resolve().parents[3]), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout)
        out = (r.stdout + r.stderr)
        rc = r.returncode
    except subprocess.TimeoutExpired:
        out, rc = f"timed out after {timeout}s", 124
    findings = [ln.strip() for ln in out.splitlines() if any(m in ln for m in _GATE_MARKERS)]
    ok = rc == 0
    log_activity(comp, "batch", f"verify (finish --no-render): {'PASS' if ok else 'BLOCKED'}",
                 outcome="applied" if ok else "error",
                 detail=None if ok else "\n".join(findings[:6])[:400])
    return {"ok": ok, "returncode": rc, "findings": findings[:40], "output": out[-4000:]}


def shard_by_frame(changeset: List[Dict], n: int) -> List[List[str]]:
    """Split the frames in a changeset across `n` agents, balanced by comment count.

    FRAME is the shard key, and that is the whole reason sharding is safe here: one frame is one
    `*.spec.json`, so two agents on different frames never touch the same file, never race
    `_gate_and_build`'s read-mutate-write, and never revert each other. Sharding by COMMENT would put
    two agents in one spec.

    (The shared surfaces that remain — `.hf_proposals.json`, `.hf_activity.jsonl`, `pool.json` — are
    exactly the ones hardened first: a cross-process lock, an append-only log, and a merge.)"""
    load = sorted({c["frame_id"] for c in changeset},
                  key=lambda f: -sum(1 for c in changeset if c["frame_id"] == f))
    shards: List[List[str]] = [[] for _ in range(max(1, min(n, len(load) or 1)))]
    weight = [0] * len(shards)
    for fid in load:
        k = weight.index(min(weight))
        shards[k].append(fid)
        weight[k] += sum(1 for c in changeset if c["frame_id"] == fid)
    return [s for s in shards if s]


def dispatch_batch_sharded(comp: str, sessions: List[str], agent: Optional[str] = None,
                           now: Optional[str] = None) -> Dict:
    """Fan the changeset out across several fleet agents, one shard of FRAMES each.

    One agent working 25 comments sequentially is the batch loop's wall-clock. Almost all of that time
    is proposal construction, gate subprocesses, stock search and snapshots — none of which touch the
    GPU, and all of which parallelise. What does touch the GPU (generation, TTS, CLIP) now queues on the
    machine-wide `nolan.gpu_lock`, so more agents means more throughput rather than more VRAM collisions.
    """
    changeset = list_changeset(comp)
    if not changeset:
        return {"ok": False, "detail": "no staged comments — stage some frame comments first"}
    shards = shard_by_frame(changeset, len(sessions))
    out, errors = [], []
    for sess, frames in zip(sessions, shards):
        briefs = []
        for fid in frames:
            b, _cs = compile_batch_brief(comp, fid, persist_requirements=True)
            briefs.append(b)
        kick = _comp_dir(comp) / f".hf_batch_kickoff.{sess}.md"
        stamp = now or datetime.now().strftime("%Y-%m-%d %H:%M")
        kick.write_text(
            f"<!-- provenance: skill={_SKILL} · comp={comp} · agent={sess} · date={stamp} · "
            f"shard={len(frames)} frame(s) -->\n\n"
            f"> **You are one of {len(shards)} agents on this batch.** Your shard is these frames and "
            f"ONLY these: {', '.join(frames)}. Do not read or edit another frame's spec — another agent "
            f"holds it. Shared surfaces are safe to write concurrently (proposals are locked, the "
            f"activity log is append-only, the pool merges). Run the closing `--verify` ONLY if you are "
            f"agent `{sessions[0]}`; it covers the whole comp and one run is enough.\n\n"
            + "\n\n---\n\n".join(briefs), encoding="utf-8")
        try:
            from nolan.webui import operations
            operations._dispatch_to_tmux(sess, _kickoff_message(comp, sess, kick))
            for c in changeset:
                if c["frame_id"] in frames:
                    resolve_comment(comp, c["frame_id"], c["id"], status="dispatched")
            out.append({"session": sess, "frames": frames, "brief_path": str(kick)})
        except Exception as e:
            errors.append(f"{sess}: {e}")
    log_activity(comp, "batch", f"sharded {len(changeset)} comment(s) across {len(out)} agent(s)",
                 outcome="dispatched" if out else "error", detail="; ".join(errors) or None)
    return {"ok": bool(out), "shards": out, "errors": errors,
            "comments": len(changeset), "frames": len({c["frame_id"] for c in changeset})}


def _kickoff_message(comp: str, session: str, kick: Path) -> str:
    return (f"You are fleet agent '{session}'. Read {kick} and execute the batch HyperFrames edit it "
            # No backticks: the receiving TUI renders the dispatched line as markdown and HIDES a
            # backticked span, so "Load the `nolan-hf-edit` skill" displayed as "Load the  skill".
            # The agent still received it (the kickoff file names the skill too), but anyone reading
            # the pane to debug a run saw an instruction with its object missing.
            f"describes. Load the nolan-hf-edit skill FIRST — it is the contract. For EACH requested "
            f"edit record a PROPOSAL via nolan.hyperframes.propose_scene_edit(comp='{comp}', frame_id=…, "
            f"scene_id=…, ops=…, rationale=…, agent='{session}', comment_id=…) — do NOT edit canonical "
            f"specs or render. The human reviews + accepts each proposal. Report to "
            f".nolan/agents/{session}.json via nolan.fleet.write_status(state=working|done|error).")


def dispatch_batch(comp: str, session: Optional[str] = None, agent: Optional[str] = None,
                   now: Optional[str] = None, frame_id: Optional[str] = None) -> Dict:
    """Compile the brief, write it as a kickoff file (with provenance), optionally dispatch to a tmux fleet
    session, and mark the dispatched comments. `frame_id` scopes to one frame; None = the whole project.
    `now` is injectable for deterministic tests."""
    brief, changeset = compile_batch_brief(comp, frame_id, persist_requirements=True)
    if not changeset:
        return {"ok": False, "detail": "no staged comments — stage some frame comments first"}
    stamp = now or datetime.now().strftime("%Y-%m-%d %H:%M")
    prov = (f"<!-- provenance: skill={_SKILL} · comp={comp} · agent={agent or session or 'unassigned'} · "
            f"date={stamp} · comments={len(changeset)} -->\n\n")
    kick = _comp_dir(comp) / ".hf_batch_kickoff.md"
    kick.write_text(prov + brief, encoding="utf-8")

    dispatched = None
    if session:
        try:
            from nolan.webui import operations
            operations._dispatch_to_tmux(session, _kickoff_message(comp, session, kick))
            dispatched = session
            log_activity(comp, "batch", f"dispatched {len(changeset)} comment(s) to {session}",
                         outcome="dispatched")
            for c in changeset:                                  # mark them dispatched so they leave the changeset
                resolve_comment(comp, c["frame_id"], c["id"], status="dispatched")
        except Exception as e:
            return {"ok": False, "detail": f"dispatch failed: {e}", "brief_path": str(kick)}
    return {"ok": True, "brief_path": str(kick), "dispatched": dispatched,
            "comments": len(changeset), "frames": len({c["frame_id"] for c in changeset}), "brief": brief}


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="python -m nolan.hyperframes.batch",
                                 description="Batch-edit brief / dispatch / verify for a HyperFrames comp.")
    ap.add_argument("comp")
    ap.add_argument("--verify", action="store_true",
                    help="the MANDATORY closing step: run the finish DAG's pre-render gates "
                         "(word-sync, timing, number/math provenance, style) and report")
    ap.add_argument("--brief", action="store_true", help="print the compiled agent brief (read-only)")
    ap.add_argument("--frame", help="scope to one frame id")
    ap.add_argument("--sound", action="store_true", help="verify WITH the bgm/sfx bed (default: without)")
    a = ap.parse_args()
    if a.verify:
        res = batch_verify(a.comp, sound=a.sound)
        print(res["output"])
        print(f"\n{'✓ PASS' if res['ok'] else '✗ BLOCKED'} — pre-render gates "
              f"({len(res['findings'])} finding(s))")
        for f in res["findings"][:20]:
            print(f"  · {f}")
        sys.exit(0 if res["ok"] else 1)
    brief, changeset = compile_batch_brief(a.comp, a.frame)
    print(brief)
    if not a.brief:
        print(f"\n({len(changeset)} open comment(s) — pass --brief to silence this note, "
              f"or use dispatch_batch() to hand it to an agent)")


if __name__ == "__main__":
    main()
