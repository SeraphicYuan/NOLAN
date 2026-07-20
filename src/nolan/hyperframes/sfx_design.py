"""Auto-author `scene.data.sfx` — the SFX pairing operator.

Places sound cues in the RIGHT place by reading BOTH signals the render exposes
after word-sync:
  • VISUAL  — the spec: scene.type (newshead/stat/document/social_card/…), the
              ground asset (image vs video), the reveal style, the numbers in
              the copy → diegetic / structural cues (paper on a document,
              camera-shutter on a photo, cash on a $-stat, glitch on a decode).
  • VERBAL  — the transcript + per-word timings (audio_meta.voices[].words[])
              + scene.operative → emphasis cues placed ON the spoken word
              (impact on the operative beat, cash on the spoken "$43 billion").

Deterministic backbone (this file); an optional LLM pass (`llm=True`) refines the
taste calls the rules can't compute — which beats deserve an emphasis hit vs
SILENCE, dread detection, spoken-diegetic matches. Everything passes the
registry + restraint gate before it's written. Output is a PROPOSAL: it writes
`scene.data.sfx`, a human reviews, then `apply_scene_sfx` (Phase 3) renders it.

CLI:  python -X utf8 -m nolan.hyperframes.sfx_design <comp> [--apply] [--llm]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from nolan.sound.registry import KINDS, BY_ID
from .sync import _phrase_time

_GLITCH_REVEALS = {"decode", "scramble", "glitch"}
# a whoosh is a MOTION cue — fire it on a frame transition INTO a graphic-forward
# scene (a real visual change worth a sweep), not on every section boundary.
_GRAPHIC_TYPES = {"newshead", "stat", "comparison", "document", "social_card",
                  "chart", "diagram", "linedraw", "geo", "timeline"}
_MONEY_RE = re.compile(r"\$\s?\d|\b\d[\d.,]*\s*(?:billion|million|trillion|dollars?|cents?)\b", re.I)
# min seconds between two cues of the SAME family within a frame (restraint budget)
_MIN_GAP = {"whoosh": 8.0, "impact-soft": 6.0, "impact-hard": 10.0, "sub-drop": 12.0,
            "cash": 5.0, "paper": 5.0, "glitch": 6.0, "notification": 6.0,
            "camera-shutter": 4.0, "data-punch": 6.0, "stinger": 12.0}
_PER_SCENE_CAP = 2


def _frame_words(audio_meta: Dict[str, Any], frame_num: int) -> List[Dict[str, Any]]:
    for v in audio_meta.get("voices", []):
        if v.get("frame") == frame_num:
            return v.get("words") or []
    return []


def _word_at(phrase: str, words: List[Dict[str, Any]], scene_start: float,
             dur: float) -> Optional[float]:
    """Frame-local time of `phrase` → a scene-local `at` (clamped into the scene).

    audio_meta words are dicts; `_phrase_time` wants WordTimestamp — convert.
    """
    if not phrase or not words:
        return None
    from nolan.whisper import WordTimestamp
    wt = [WordTimestamp(word=(w.get("word") or w.get("text") or ""),
                        start=float(w.get("start", 0) or 0), end=float(w.get("end", 0) or 0))
          for w in words]
    t = _phrase_time(phrase, wt, after=max(0.0, scene_start - 0.2))
    if t is None:
        return None
    at = round(t - scene_start, 3)
    return at if -0.2 <= at <= dur + 0.2 else None


def _scene_context(scene: Dict[str, Any], words: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Gather the VISUAL + VERBAL signals for one scene."""
    d = scene.get("data") or {}
    start = float(scene.get("start") or 0.0)
    dur = float(scene.get("dur") or 0.0)
    # verbal: the words spoken during this scene (frame-local window)
    span = [w for w in words if start - 0.05 <= float(w.get("start", 0)) < start + dur]
    text = " ".join(w.get("text") or w.get("word") or "" for w in span)
    money_m = _MONEY_RE.search(text)
    money_at = None
    if money_m:
        # anchor to the number token's spoken time
        tok = re.search(r"[\$\d][\w.,%]*", money_m.group(0))
        money_at = _word_at(tok.group(0) if tok else money_m.group(0), words, start, dur)
    ground = d.get("ground") or {}
    return {
        "type": scene.get("type"), "start": start, "dur": dur, "data": d,
        "cue": (float(d["cue"]) if isinstance(d.get("cue"), (int, float)) else None),
        "reveal": d.get("reveal"),
        "ground_kind": ground.get("kind") if isinstance(ground, dict) else None,
        "has_image": bool(d.get("image") or d.get("cutout")),
        "operative": d.get("operative") or d.get("highlight") or d.get("titleHi"),
        "text": text, "has_money": bool(money_m),
        "money_at": money_at if money_at is not None else None,
        "words": words,
    }


def _deterministic_cues(ctx: Dict[str, Any], *, frame_first: bool,
                        transitions: str = "sparse") -> List[Tuple[str, float, int, str]]:
    """(kind, at, priority, why) candidates from the visual + verbal signals.

    `transitions`: whoosh cadence — "off" (none), "sparse" (default; only a frame
    that OPENS on a graphic-forward scene — a real visual change), "all" (every
    frame enter). Sparse keeps whooshes motion-motivated, not one-per-section.
    """
    t, d, dur = ctx["type"], ctx["data"], ctx["dur"]
    cue = ctx["cue"]
    reveal_t = cue if cue is not None else round(min(0.4, dur * 0.15), 3)
    out: List[Tuple[str, float, int, str]] = []

    if frame_first and transitions != "off" and (            # structural: the cut
            transitions == "all" or t in _GRAPHIC_TYPES):
        out.append(("whoosh", 0.0, 1, "frame enter"))

    if t == "newshead":                                        # visual: block type
        out.append(("paper", reveal_t, 3, "newspaper headline"))
        if ctx["has_image"]:
            out.append(("camera-shutter", round(reveal_t + 0.25, 3), 3, "framed photo"))
    elif t == "document":
        out.append(("paper", reveal_t, 3, "document"))
    elif t == "social_card":
        out.append(("notification", reveal_t, 3, "social card"))
    elif t == "stat":
        if ctx["has_money"]:
            out.append(("cash", ctx["money_at"] if ctx["money_at"] is not None else reveal_t,
                        3, "money stat"))
        else:
            out.append(("data-punch", reveal_t, 2, "stat lands"))

    if d.get("reveal") in _GLITCH_REVEALS:                     # visual: reveal style
        out.append(("glitch", reveal_t, 3, "glitch reveal"))

    if ctx["operative"] and t in ("statement", "stat") and dur <= 9:  # verbal: operative word
        at = cue if cue is not None else _word_at(ctx["operative"], ctx["words"], ctx["start"], dur)
        if at is not None:
            out.append(("impact-soft", round(at, 3), 2, "operative word"))

    if ctx["has_money"] and t != "stat":                       # verbal: spoken money
        out.append(("cash", ctx["money_at"] if ctx["money_at"] is not None else reveal_t,
                    3, "spoken money"))
    return out


def _budget(cues: List[Tuple[str, float, int, str]]) -> List[Tuple[str, float, int, str]]:
    """Restraint gate: per-family min-gap + per-scene cap, keep higher priority."""
    cues = sorted(cues, key=lambda c: (-c[2], c[1]))          # priority desc, then time
    kept: List[Tuple[str, float, int, str]] = []
    last: Dict[str, float] = {}
    for kind, at, pri, why in cues:
        gap = _MIN_GAP.get(kind, 6.0)
        if any(k == kind and abs(at - a) < gap for k, a in ((x[0], x[1]) for x in kept)):
            continue
        kept.append((kind, at, pri, why))
        last[kind] = at
    kept = sorted(kept, key=lambda c: c[1])[:_PER_SCENE_CAP]  # cap per scene, time order
    return kept


def design(comp: str, *, apply: bool = False, llm: bool = False,
           transitions: str = "sparse", whoosh_gap: float = 45.0,
           bed: Optional[str] = None) -> Dict[str, Any]:
    """Propose scene.data.sfx across a comp from its spec + word timings.

    Returns ``{plan: [{frame, scene, cues:[{cue,at,why}]}], total, applied}``.
    `apply` writes the cues into the frame specs; `llm` refines taste calls;
    `transitions` sets the whoosh cadence (off | sparse | all); `whoosh_gap` is the
    minimum seconds between whooshes across frames (a whoosh is also skipped if the
    frame repeats the previous whoosh's scene type) — whooshes are a rare accent.
    `bed` (a bed-family cue-kind, e.g. 'room-tone' | 'tension-drone' | 'nature-bed')
    lays a subtle emotional-floor bed under every frame (opt-in; the executor tiles
    it to fill). None = no bed.
    """
    from .edit import _project_dir, list_frames, load_frame_spec, save_frame_spec

    pdir = Path(_project_dir(comp))
    am = json.loads((pdir / "audio_meta.json").read_text(encoding="utf-8")) \
        if (pdir / "audio_meta.json").exists() else {"voices": []}
    if bed and (bed not in BY_ID or BY_ID[bed].family != "bed"):
        raise ValueError(f"--bed {bed!r} is not a bed-family cue-kind "
                         f"({[k for k, c in BY_ID.items() if c.family == 'bed']})")

    # absolute frame starts + per-frame duration (each frame = its VO duration)
    starts, dur_by_frame, acc = {}, {}, 0.0
    for v in sorted(am.get("voices", []), key=lambda v: v.get("frame", 0)):
        starts[v.get("frame")] = acc
        dur_by_frame[v.get("frame")] = float(v.get("duration_s") or 0)
        acc += float(v.get("duration_s") or 0)
    last_whoosh_t, last_whoosh_type = -1e9, None

    plan: List[Dict[str, Any]] = []
    total = 0
    frames = list_frames(comp)
    for idx, fr in enumerate(frames):
        fid = fr.get("id") if isinstance(fr, dict) else fr
        m = re.match(r"0*(\d+)", str(fid))
        num = int(m.group(1)) if m else idx + 1
        words = _frame_words(am, num)
        spec, info = load_frame_spec(comp, fid)
        frame = spec["frames"][info["i"]]
        scenes = frame.get("scenes", [])
        changed = False
        for si, sc in enumerate(scenes):
            ctx = _scene_context(sc, words)
            cands = _deterministic_cues(ctx, frame_first=(si == 0), transitions=transitions)
            kept = _budget(cands)
            # whooshes are a RARE accent: drop one that's < whoosh_gap since the
            # last, or that repeats the previous whoosh's scene type
            pruned = []
            for c in kept:
                if c[0] == "whoosh":
                    abs_t = starts.get(num, 0.0) + c[1]
                    if abs_t - last_whoosh_t < whoosh_gap or ctx["type"] == last_whoosh_type:
                        continue
                    last_whoosh_t, last_whoosh_type = abs_t, ctx["type"]
                pruned.append(c)
            kept = pruned
            if llm and kept is not None:
                kept = _llm_refine(ctx, kept)                 # taste layer (optional)
            cues = [{"cue": k, "at": a, "why": w} for k, a, _p, w in kept if k in KINDS]
            if si == 0 and bed:                               # emotional-floor bed, spanning the frame
                cues.insert(0, {"cue": bed, "at": 0.0, "why": "emotional bed",
                                "span": round(dur_by_frame.get(num, 0.0), 3)})
            if cues:
                plan.append({"frame": fid, "scene": sc.get("id"),
                             "type": ctx["type"], "cues": cues})
                total += len(cues)
                if apply:
                    sc.setdefault("data", {})["sfx"] = [
                        {"cue": c["cue"], "at": c["at"],
                         **({"span": c["span"]} if c.get("span") else {})} for c in cues]
                    changed = True
        if apply and changed:
            save_frame_spec(pdir / "compositions" / "frames" / f"{fid}.spec.json", spec)

    return {"plan": plan, "total": total, "applied": bool(apply)}


def _llm_refine(ctx: Dict[str, Any], cues: List[Tuple[str, float, int, str]]):
    """Optional taste pass — refine which beats get an emphasis hit vs silence.

    Kept intentionally thin + safe: the LLM only PRUNES the deterministic
    candidates and may set an emphasis on an obviously dramatic line; it can
    never invent an unregistered kind (the caller filters to KINDS, and the
    restraint budget already ran). Falls back to the deterministic set on any
    error so the operator never fails on the model.
    """
    try:
        from nolan.config import load_config
        from nolan.llm import create_text_llm
        from nolan.sound.registry import BY_ID
        cand = [{"cue": k, "at": a, "why": w} for k, a, _p, w in cues]
        catalog = {k: BY_ID[k].when_to_use for k in {c["cue"] for c in cand}}
        prompt = (
            "You are placing sound effects on ONE scene of a video essay. Restraint is the rule: "
            "silence is a valid choice; keep only the cues that land on a motivated moment.\n\n"
            f"Scene type: {ctx['type']}  duration: {ctx['dur']:.1f}s\n"
            f"Transcript: {ctx['text'][:400]!r}\n"
            f"Operative phrase: {ctx['operative']!r}\n"
            f"Candidate cues (cue @ scene-local seconds — why): {json.dumps(cand)}\n"
            f"When-to-use for these kinds: {json.dumps(catalog, ensure_ascii=False)}\n\n"
            "Return ONLY a JSON list of the cues to KEEP, each {\"cue\":..,\"at\":..}. "
            "Drop any that would over-clutter or fight the narration. Do not add new kinds."
        )
        llm = create_text_llm(load_config())
        raw = llm.complete(prompt) if hasattr(llm, "complete") else llm(prompt)
        picked = json.loads(re.search(r"\[.*\]", raw, re.S).group(0))
        keep = {(p["cue"], round(float(p["at"]), 3)) for p in picked if p.get("cue") in KINDS}
        return [c for c in cues if (c[0], round(c[1], 3)) in keep] or cues
    except Exception:
        return cues


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="nolan.hyperframes.sfx_design",
                                 description="Auto-author scene.data.sfx from the spec + VO timings.")
    ap.add_argument("comp")
    ap.add_argument("--apply", action="store_true", help="write the cues into the frame specs")
    ap.add_argument("--llm", action="store_true", help="LLM taste pass over the deterministic candidates")
    ap.add_argument("--transitions", choices=["off", "sparse", "all"], default="sparse",
                    help="whoosh cadence: sparse (default; graphic-opening frames only), all, off")
    ap.add_argument("--whoosh-gap", type=float, default=45.0,
                    help="min seconds between whooshes (they're a rare accent; default 45)")
    ap.add_argument("--bed", default=None,
                    help="lay a subtle emotional-floor bed under every frame "
                         "(a bed-family kind: room-tone | tension-drone | nature-bed | …)")
    a = ap.parse_args()
    res = design(a.comp, apply=a.apply, llm=a.llm, transitions=a.transitions,
                 whoosh_gap=a.whoosh_gap, bed=a.bed)
    for p in res["plan"]:
        cues = ", ".join(f"{c['cue']}@{c['at']}s ({c['why']})" for c in p["cues"])
        print(f"  {p['frame']}/{p['scene']} [{p['type']}]: {cues}")
    print(f"\n{res['total']} cue(s) across {len(res['plan'])} scene(s)"
          + (" — WRITTEN to specs (review, then hf-finish)" if res["applied"]
             else " — dry run (add --apply to write)"))


if __name__ == "__main__":
    main()
