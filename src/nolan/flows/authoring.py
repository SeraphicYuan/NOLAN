"""Authoring mode (Phase 5, Gate A) — draft a per-beat plan BEFORE assets/render.

Given a project's script + word-timestamped voiceover, draft a per-beat plan: a planned
motion (from the flow's palette), planned assets, and an asset WISHLIST — what you ideally
want for the beat, even if it's not in the pool yet — each with a status: have / find /
generate. The human tweaks this at Gate A (cheapest stage, drives everything downstream).
The wishlist is the asset shopping list. See web-video-lab/flows/EDITOR.md.

Autonomy (one pipeline; the mode only decides whether Gate A blocks; Gate B is always on):
  auto      — Gate A off: draft -> resolve -> render straight through (review at Gate B).
  semi-auto — Gate A on:  draft, then PAUSE for human tweak + asset linking, then resume.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path


def _win2posix(p: str) -> str:
    """Localize a path to the running interpreter (WSL python3 or nolan Windows python)."""
    p = str(p)
    if os.name == "nt":
        m = re.match(r"^/mnt/([a-z])/(.*)$", p)
        return f"{m.group(1).upper()}:/" + m.group(2) if m else p
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", p)
    return f"/mnt/{m.group(1).lower()}/" + m.group(2).replace("\\", "/") if m else p


def _segments(project) -> list:
    p = Path(project) / "assets" / "voiceover" / "segments" / "segments.json"
    return json.loads(p.read_text(encoding="utf-8")).get("segments", [])


def draft_plan(project, flow, *, llm=None) -> dict:
    """Draft a flow-spec-shaped plan from the project's segments.

    Deterministic baseline (one beat per voiceover segment, planned with the flow's primary
    palette motion + an asset wishlist). If `llm` is given it refines block choice + wishlist
    (flow.palette is the menu it must pick from) — optional; the baseline is always valid.
    """
    segs = _segments(project)
    segdir = Path(project) / "assets" / "voiceover" / "segments"
    primary = flow.palette[0] if flow.palette else "ArtworkStage"
    beats = []
    for s in segs:
        stem = Path(s["file"]).stem
        wf = segdir / f"{stem}.words.json"
        narration = ""
        if wf.exists():
            narration = " ".join(w.get("word", "") for w in json.loads(wf.read_text(encoding="utf-8")))
        beats.append({
            "segment": stem,
            "narration": narration[:600],                       # context for the refiner
            "block": primary,                                   # planned motion (from palette)
            "_planned_asset": None,                             # nothing bound yet
            "_wishlist": [{"want": f"a visual for “{s.get('title','')}”", "status": "find"}],
        })
    if llm is not None:
        beats = _llm_refine(llm, beats, segs, flow)
    return {"flow": flow.id, "theme": flow.defaults.get("theme", "midnight-press"),
            "captions": False, "fps": 30,
            "project": str(Path(project).resolve()),
            "palette": flow.palette,                            # the motion menu (authoring aid)
            "beats": beats}


def _llm_refine(llm, beats, segs, flow):  # pragma: no cover - exercised only with a live client
    """Hook for an LLM to pick richer blocks (from flow.palette) + a concrete wishlist per
    beat. Returns refined beats. Kept side-effect-free + optional so the baseline stands alone."""
    return beats


# ---------------------------------------------------------------- tmux-agent refine (Gate A)

def build_authoring_prompt(agent: str, draft_path: str, palette: list) -> str:
    """One-line prompt sent to a Claude Code tmux agent to refine an authoring draft."""
    pal = ", ".join(palette)
    return (
        f"You are fleet agent '{agent}' doing AUTHORING-mode refine for an art-explainer video. "
        f"Read the JSON draft at \"{draft_path}\" — beats[] each with 'segment', 'narration', a "
        f"placeholder 'block', and a '_wishlist'. For EACH beat: (1) set 'block' to the best motion "
        f"from this palette based on the narration — {pal} — e.g. a side-by-side contrast → "
        f"ImageCompare, naming several figures → PhotoMontage, zooming a detail → DetailLoupe, a "
        f"closing line → EndCard, else ArtworkStage; (2) rewrite '_wishlist' as a concrete list of "
        f"the specific visual(s) you'd want for that beat, each {{want, status:'find'|'generate'}}. "
        f"Write the refined JSON back to the SAME file \"{draft_path}\" (keep all other fields). Then "
        f"write .nolan/agents/{agent}.json = {{\"agent\":\"{agent}\",\"state\":\"done\",\"scene_ids\":[],"
        f"\"message\":\"authoring refined\",\"result\":[<chosen blocks>]}}. Start by writing that file "
        f"with state 'working'. Do ONLY this; do not render."
    )


def dispatch_refine(project, agent: str = "nolan4", *, draft_name: str = "_authoring_draft.spec.json") -> Path:
    """Gate A via a tmux Claude agent: write a fresh draft, then dispatch <agent> to refine it.

    Returns the draft path. Poll `.nolan/agents/<agent>.json` (fleet.read_status) for state 'done',
    then read the refined draft. Does NOT touch the canonical flow.spec.json.
    """
    from nolan import fleet
    from nolan.webui.operations import _dispatch_to_tmux
    from .project import load_flow_spec

    flow, _ = load_flow_spec(project)
    draft_path = Path(project) / ".flow" / draft_name
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(json.dumps(draft_plan(project, flow), indent=2, ensure_ascii=False), encoding="utf-8")
    fleet.write_status(agent, state="dispatched", project=Path(project).name, plan=str(draft_path),
                       scene_ids=[], note="authoring refine", message="dispatched", result=None, error=None)
    _dispatch_to_tmux(agent, build_authoring_prompt(agent, str(draft_path), flow.palette))
    return draft_path


def plan_status(spec: dict) -> list:
    """Per-beat asset status — have (bound + exists) / find / generate."""
    out = []
    for i, b in enumerate(spec.get("beats", [])):
        src = b.get("src") or (b.get("left") or {}).get("src") or (b.get("cards") or [{}])[0].get("src")
        have = bool(src) and Path(_win2posix(src)).exists()
        wl = (b.get("_wishlist") or [None])[0]
        if have:
            status, want = "have", None
        elif wl:                                    # an unfilled wishlist item -> shopping list
            status, want = wl.get("status", "find"), wl.get("want")
        else:
            status, want = "n/a", None              # text-only beat (EndCard) needs no asset
        out.append({"beat": i, "block": b.get("block"), "status": status, "want": want})
    return out


def author(project, flow, *, overwrite: bool = False) -> Path:
    """Gate A — ensure projects/<slug>/flow.spec.json exists (draft if missing). Returns it."""
    sp = Path(project) / "flow.spec.json"
    if overwrite or not sp.exists():
        sp.write_text(json.dumps(draft_plan(project, flow), indent=2, ensure_ascii=False), encoding="utf-8")
    return sp


def run(project, *, mode: str = "auto", llm=None, **run_kw):
    """Run a flow with an autonomy mode.

    auto      -> draft (if needed) then render straight through; returns the delivered mp4.
    semi-auto -> draft (if needed) then PAUSE; returns {paused_at, plan, status} for the
                 human to tweak in authoring mode. Resume later with run(..., mode="auto").
    """
    from . import get_flow
    from .base import run_flow_for_project
    from .project import flow_spec_path, load_flow_spec

    if flow_spec_path(project).exists():
        flow, _ = load_flow_spec(project)
    else:
        raise FileNotFoundError(
            f"{Path(project).name} has no flow.spec.json — call author(project, get_flow(<id>)) "
            "first, or seed a flow id.")

    if mode == "semi-auto":
        sp = author(project, flow)                  # draft if missing; never overwrites edits
        spec = json.loads(sp.read_text(encoding="utf-8"))
        status = plan_status(spec)
        return {"paused_at": "authoring", "plan": str(sp), "beats": len(spec.get("beats", [])),
                "status": status,
                "needs_assets": [s["beat"] for s in status if s["status"] in ("find", "generate")]}
    return run_flow_for_project(project, **run_kw)
