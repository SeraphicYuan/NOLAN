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
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .edit import (_comp_dir, list_assets, list_changeset, load_frame_spec, log_activity,
                   resolve_comment, resolve_mentions, save_frame_spec)

_SKILL = "hyperframes-batch@1"


def _extract_requirements(text: str) -> List[Dict[str, str]]:
    """Decompose a comment into atomic, checkable requirements so the agent maps each op to one and REPORTS
    coverage — turning a silent miss (e.g. 'add kinetic work' collapsed into nothing) into a visible one at
    review. Heuristic: split on sentence/imperative boundaries. Advisory, never a gate. Never empty."""
    text = (text or "").strip()
    if not text:
        return []
    parts = re.split(r"[.;\n]+|\s+(?:then|also|and then)\s+", text, flags=re.I)
    reqs = [p.strip(" ,").strip() for p in parts]
    reqs = [r for r in reqs if len(r) >= 4]
    return [{"id": f"r{i + 1}", "text": r} for i, r in enumerate(reqs)] or [{"id": "r1", "text": text}]


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
         f"Theme: **{_theme(comp) or '(default)'}**.  Frames to edit: **{len(by_frame)}**, "
         f"comments: **{len(changeset)}**.", ""]
    if not changeset:
        L.append("_No staged comments — nothing to do. Stage frame comments first._")
        return "\n".join(L), changeset

    for fid, comments in by_frame.items():
        fr = None
        try:
            spec, info = load_frame_spec(comp, fid)
            fr = spec["frames"][info["i"]]
            scenes = ", ".join(f"{s.get('id')}={s.get('type')}" for s in fr.get("scenes", []))
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

    L += [
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
        "Report progress to `.nolan/agents/<agent>.json` via `nolan.fleet.write_status` (working→done|error).",
    ]
    return "\n".join(L), changeset


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
            msg = (f"You are fleet agent '{session}'. Read {kick} and execute the batch HyperFrames edit it "
                   f"describes. For EACH requested edit, record a PROPOSAL via "
                   f"nolan.hyperframes.propose_scene_edit(comp='{comp}', frame_id=…, scene_id=…, ops=…, "
                   f"rationale=…, agent='{session}', comment_id=…) — do NOT edit canonical specs or render. The "
                   f"human reviews + accepts each proposal. Report to .nolan/agents/{session}.json via "
                   f"nolan.fleet.write_status(state=working|done|error).")
            operations._dispatch_to_tmux(session, msg)
            dispatched = session
            log_activity(comp, "batch", f"dispatched {len(changeset)} comment(s) to {session}",
                         outcome="dispatched")
            for c in changeset:                                  # mark them dispatched so they leave the changeset
                resolve_comment(comp, c["frame_id"], c["id"], status="dispatched")
        except Exception as e:
            return {"ok": False, "detail": f"dispatch failed: {e}", "brief_path": str(kick)}
    return {"ok": True, "brief_path": str(kick), "dispatched": dispatched,
            "comments": len(changeset), "frames": len({c["frame_id"] for c in changeset}), "brief": brief}
