"""Editorial Arc / tempo pass — assign each beat an ENERGY and the concrete render levers
that express it, using WHOLE-SCRIPT context (not one line in isolation).

A beat's total duration is locked to its voiceover length, so tempo cannot stretch a beat.
What it controls is how the fixed window is FILLED. This pass reads the `ScriptContext` (the
beat arc + the writer's `pace:a|d` seed from beatmap.md + narration) and produces, per beat:

  energy 0..1   — target intensity, designed as a CURVE across the whole piece (breathe at the
                  open/close, build to the climax) — refines beatmap's coarse accelerate/decelerate.
  pace_dir      — build | hold | release  (momentum relative to neighbours)
  transition    — cut | dissolve | fade   (the cheapest lever; fully plumbed via `assemble`)
  motion_speed  — slow | medium | fast    (drives motion duration / the still-motion treatment)
  shots         — suggested cut density (1 = one held shot); for the later cut-density lever

It generates toward a per-flow PROFILE (punchy explainer vs contemplative art — the same
targets `flows/gate/pacing.py` lints against). LLM path is primary; a deterministic rule-based
fallback maps the beatmap pace tags directly so the pass always yields a plan.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional

from .script_context import ScriptContext, _norm_title

# per-profile shaping — mirrors web-video-lab/flows/registry.json pacing intent
_PROFILES = {
    "punchy":         {"base": 0.55, "climax": 0.9, "floor": 0.3, "max_shots": 4},   # explainer
    "contemplative":  {"base": 0.35, "climax": 0.6, "floor": 0.2, "max_shots": 2},   # art
    "balanced":       {"base": 0.45, "climax": 0.75, "floor": 0.25, "max_shots": 3},
}
_TRANSITIONS = ("cut", "dissolve", "fade")
_SPEEDS = ("slow", "medium", "fast")


@dataclass
class BeatTempo:
    idx: int
    title: str
    energy: float                    # 0..1 target intensity
    pace_dir: str = "hold"           # build | hold | release
    transition: str = "cut"          # cut | dissolve | fade  (into this beat)
    motion_speed: str = "medium"     # slow | medium | fast
    shots: int = 1                   # suggested cut density
    reason: str = ""

    def to_dict(self) -> dict:
        return {"idx": self.idx, "title": self.title, "energy": round(self.energy, 3),
                "pace_dir": self.pace_dir, "transition": self.transition,
                "motion_speed": self.motion_speed, "shots": self.shots, "reason": self.reason}


@dataclass
class TempoPlan:
    slug: str
    profile: str
    beats: List[BeatTempo] = field(default_factory=list)
    source: str = "rules"            # "llm" | "rules"

    def get(self, idx: int) -> Optional[BeatTempo]:
        return self.beats[idx] if 0 <= idx < len(self.beats) else None

    def to_dict(self) -> dict:
        return {"slug": self.slug, "profile": self.profile, "source": self.source,
                "beats": [b.to_dict() for b in self.beats]}


def profile_for(ctx: ScriptContext, explicit: str = "") -> str:
    """Pick a pacing profile: explicit wins; else infer from style/subject; else balanced."""
    if explicit in _PROFILES:
        return explicit
    s = (ctx.style_id or "").lower()
    if "art" in s or "artwork" in s or "painting" in s:
        return "contemplative"
    if "explain" in s or "great-books" in s or "essay" in s:
        return "punchy"
    return "balanced"


# ---- energy → concrete levers ----------------------------------------------
def _levers(energy: float, prof: dict) -> tuple:
    """Map a target energy to (transition, motion_speed, shots)."""
    if energy < 0.35:
        trans, speed = "fade", "slow"
    elif energy < 0.55:
        trans, speed = "dissolve", "slow"
    elif energy < 0.75:
        trans, speed = "cut", "medium"
    else:
        trans, speed = "cut", "fast"
    shots = max(1, min(prof["max_shots"], round(1 + energy * (prof["max_shots"] - 1) * 1.15)))
    return trans, speed, shots


def _pace_dir(prev_e: Optional[float], e: float, nxt_e: Optional[float]) -> str:
    if prev_e is not None and e > prev_e + 0.08:
        return "build"
    if nxt_e is not None and e > nxt_e + 0.08:
        return "release"
    return "hold"


# ---- rule-based fallback ----------------------------------------------------
_PACE_ENERGY = {"accelerate": 0.78, "decelerate": 0.3,
                "accelerate→decelerate": 0.62, "decelerate→accelerate": 0.5, "": 0.5}


def _rule_energy(ctx: ScriptContext, prof: dict) -> List[float]:
    n = len(ctx.beats)
    out = []
    for i, b in enumerate(ctx.beats):
        base = _PACE_ENERGY.get(b.pace, 0.5)
        # arc shaping: gentle rise toward ~2/3, softer at the very open/close
        pos = i / max(1, n - 1)
        arc = 1.0 - abs(pos - 0.66) * 0.5           # peak near 2/3
        e = 0.6 * base + 0.4 * (prof["floor"] + (prof["climax"] - prof["floor"]) * arc)
        if i == 0:
            e = min(e, prof["base"] + 0.1)          # let the hook breathe a touch
        if i == n - 1:
            e = min(e, prof["floor"] + 0.15)        # contemplative close
        out.append(max(0.05, min(1.0, e)))
    return out


def _rule_plan(ctx: ScriptContext, profile: str) -> TempoPlan:
    prof = _PROFILES[profile]
    energies = _rule_energy(ctx, prof)
    beats = []
    for i, b in enumerate(ctx.beats):
        e = energies[i]
        prev_e = energies[i - 1] if i > 0 else None
        nxt_e = energies[i + 1] if i < len(energies) - 1 else None
        trans, speed, shots = _levers(e, prof)
        beats.append(BeatTempo(idx=i, title=b.title, energy=e,
                               pace_dir=_pace_dir(prev_e, e, nxt_e),
                               transition=trans, motion_speed=speed, shots=shots,
                               reason=f"pace:{b.pace or 'n/a'} → energy {e:.2f}"))
    return TempoPlan(slug=ctx.slug, profile=profile, beats=beats, source="rules")


# ---- LLM path ---------------------------------------------------------------
_TEMPO_SYS = (
    "You are a film editor designing the RHYTHM of a narrated video essay. You think about the "
    "whole piece as an energy CURVE — where it breathes, where it builds, where it lands — not "
    "beat by beat in isolation. Reply STRICT JSON only.")


def _tempo_prompt(ctx: ScriptContext, profile: str) -> str:
    prof = _PROFILES[profile]
    guide = {
        "punchy": "Explainer pace: keep it moving; drive fact-clusters with fast cuts; still let key reframes land.",
        "contemplative": "Art/contemplative pace: long holds, slow motion, few cuts; let images breathe (min hold ~2.5s).",
        "balanced": "Balanced pace: vary energy with the content; build to the emotional peak, breathe at open and close.",
    }[profile]
    return (
        f"{ctx.brief()}\n\n"
        f"PROFILE: {profile} — {guide}\n"
        f"Energy band for this profile: floor≈{prof['floor']}, base≈{prof['base']}, climax≈{prof['climax']}; "
        f"cut density up to {prof['max_shots']} shots on the most driving beats.\n\n"
        "Design the tempo as ONE energy curve across the beats above (in order). The narration length "
        "of each beat is FIXED — you are NOT changing durations, only how each beat is FILLED. Respect "
        "the writer's pace intent (pace:accelerate wants more energy/cuts; pace:decelerate wants holds), "
        "but shape a real arc: breathe at the open and the close, build toward the emotional/climactic beat.\n"
        "For EACH beat return: energy 0..1; pace_dir (build|hold|release); transition INTO it "
        "(cut=punchy | dissolve=soft | fade=breath); motion_speed (slow|medium|fast); shots "
        f"(1=one held shot .. {prof['max_shots']}=fast montage); reason (<=14 words).\n"
        'JSON: {"beats": [{"idx": <int, matches the beat number>, "energy": <0-1>, '
        '"pace_dir": "build|hold|release", "transition": "cut|dissolve|fade", '
        '"motion_speed": "slow|medium|fast", "shots": <int>, "reason": "<short>"}]}')


def _coerce(raw: dict, ctx: ScriptContext, profile: str) -> Optional[TempoPlan]:
    prof = _PROFILES[profile]
    items = raw.get("beats") if isinstance(raw, dict) else None
    if not isinstance(items, list) or not items:
        return None
    by_idx = {}
    for it in items:
        try:
            i = int(it.get("idx"))
        except (TypeError, ValueError):
            continue
        by_idx[i] = it
    beats = []
    for i, b in enumerate(ctx.beats):
        it = by_idx.get(i, {})
        try:
            e = float(it.get("energy"))
            e = max(0.0, min(1.0, e))
        except (TypeError, ValueError):
            e = _PACE_ENERGY.get(b.pace, 0.5)
        # levers: use the model's if valid, else derive from energy
        trans = it.get("transition") if it.get("transition") in _TRANSITIONS else None
        speed = it.get("motion_speed") if it.get("motion_speed") in _SPEEDS else None
        dtrans, dspeed, dshots = _levers(e, prof)
        try:
            shots = max(1, min(prof["max_shots"], int(it.get("shots"))))
        except (TypeError, ValueError):
            shots = dshots
        pace_dir = it.get("pace_dir") if it.get("pace_dir") in ("build", "hold", "release") else "hold"
        beats.append(BeatTempo(idx=i, title=b.title, energy=e, pace_dir=pace_dir,
                               transition=trans or dtrans, motion_speed=speed or dspeed,
                               shots=shots, reason=(it.get("reason") or "")[:120]))
    return TempoPlan(slug=ctx.slug, profile=profile, beats=beats, source="llm")


def blend_with_reference(plan: TempoPlan, reference: dict,
                         weight: float = 0.5) -> TempoPlan:
    """Tempo cloning: blend a reference video's MEASURED energy curve into the plan.

    ``reference`` is a ``reference_structure.json`` dict (written by clone/attach:
    beats with t0/t1/energy/function). Sponsor beats (function == "other") are
    excluded and the timeline renormalized, so content aligns to content. Each
    script beat's energy blends with the reference energy at the same normalized
    position (``weight`` = how much the reference shape wins); transition /
    motion_speed / shots are re-derived from the blended energy and pace_dir is
    recomputed. Degrades to the input plan when the reference is empty.
    """
    ref_beats = [b for b in (reference.get("beats") or [])
                 if b.get("function") != "other" and b.get("energy") is not None]
    if not plan.beats or not ref_beats or weight <= 0:
        return plan

    # Function-aware alignment: hooks and closes match by FUNCTION, not
    # position — a reference hook is often seconds long (a fast montage) and
    # pure positional alignment washes it out under its long slow neighbor.
    hooks = [b for b in ref_beats if b.get("function") == "hook"]
    closes = [b for b in ref_beats if b.get("function") == "close"]
    body = [b for b in ref_beats if b not in hooks and b not in closes] or ref_beats

    # body-only normalized spans (ads + endpoint beats removed)
    total = sum(max(0.01, (b.get("t1") or 0) - (b.get("t0") or 0)) for b in body)
    spans, cursor = [], 0.0
    for b in body:
        length = max(0.01, (b.get("t1") or 0) - (b.get("t0") or 0)) / total
        spans.append((cursor, cursor + length, float(b["energy"])))
        cursor += length

    def ref_energy(f: float) -> float:
        for lo, hi, e in spans:
            if lo <= f < hi:
                return e
        return spans[-1][2]

    prof = _PROFILES.get(plan.profile, _PROFILES["balanced"])
    w = min(1.0, max(0.0, weight))
    n = len(plan.beats)
    energies = []
    for i, bt in enumerate(plan.beats):
        if i == 0 and hooks:
            e_ref = max(float(b["energy"]) for b in hooks)   # the hook's spike
        elif i == n - 1 and closes:
            e_ref = float(closes[-1]["energy"])              # land like the reference lands
        else:
            e_ref = ref_energy((i + 0.5) / n)
        e = min(0.95, max(0.05, (1 - w) * bt.energy + w * e_ref))
        energies.append(round(e, 2))
    for i, bt in enumerate(plan.beats):
        bt.energy = energies[i]
        bt.pace_dir = _pace_dir(energies[i - 1] if i else None, energies[i],
                                energies[i + 1] if i + 1 < n else None)
        bt.transition, bt.motion_speed, bt.shots = _levers(energies[i], prof)
        bt.reason = (bt.reason + " · " if bt.reason else "") + \
            f"blended w/ reference curve (w={w:g})"
    plan.source = f"{plan.source}+reference"
    return plan


def motion_for_tempo(bt: BeatTempo, kind: str = "image") -> tuple:
    """Map a beat's tempo → (motion_id, duration_seconds) for the still-motion renderer.
    Energy sets both the treatment and how long it breathes — the renderable tempo lever.
    A moving CLIP plays 'as-is' unless the beat is driving (then a subtle push)."""
    e = bt.energy
    if kind in ("stock", "library"):                       # already-moving footage
        return ("subtle-push" if e >= 0.75 else "as-is", round(5.5 - 3.0 * e, 1))
    if e < 0.35:                                            # breathe — long, still or slow pull-out
        return ("hold" if e < 0.22 else "ken-burns-out", 5.5)
    if e < 0.6:
        return ("ken-burns-in", 4.5)
    if e < 0.78:
        return ("ken-burns-in", 3.5)
    return ("ken-burns-in", 2.6)                           # drive — fast push


def apply_to_plan(plan, tempo: TempoPlan) -> dict:
    """Write a TempoPlan's per-beat rhythm onto an orchestrator ScenePlan.

    The scene-plan's SECTIONS are the script beats (section title == script heading), so each
    section maps to one BeatTempo by title. Every scene in that section receives the beat's
    `transition`, `energy`, and `motion_speed` — the two levers the planner leaves flat
    (transitions are 100% empty; there is no energy signal for motion selection to read).

    Mutates `plan` in place (caller saves). Returns {sections, scenes, matched} counts."""
    by_title = {_norm_title(b.title): b for b in tempo.beats}
    titles = list(by_title.keys())
    n_sec = n_sc = matched = 0
    for section_title, scenes in plan.sections.items():
        n_sec += 1
        stoks = set(_norm_title(section_title).split())
        bt = by_title.get(_norm_title(section_title))
        if bt is None and stoks:                          # fuzzy fallback on token overlap
            best, best_score = None, 0.0
            for t in titles:
                ttoks = set(t.split())
                if not ttoks:
                    continue
                score = len(stoks & ttoks) / max(1, len(stoks | ttoks))
                if score > best_score:
                    best, best_score = by_title[t], score
            if best_score >= 0.3:
                bt = best
        for sc in scenes:
            n_sc += 1
            if bt is None:
                continue
            sc.transition = bt.transition
            sc.energy = round(bt.energy, 3)
            sc.motion_speed = bt.motion_speed
            # the beat's shot cadence: >1 asks the asset ladder to fetch that
            # many stills so premium can cut the scene into a shot list
            # (scene.shots). Consumed field — never author data with no reader.
            if int(getattr(bt, "shots", 1) or 1) > 1:
                sc.extra["shots_wanted"] = int(bt.shots)
            matched += 1
    return {"sections": n_sec, "scenes": n_sc, "matched": matched}


def apply_to_flow_spec(spec: dict, tempo: TempoPlan) -> dict:
    """Write a TempoPlan onto a FLOW `flow.spec.json` (the art/explainer pipeline).

    FLOW beats already carry per-beat MOTION knobs (`introHold`, `maxZoom`) — unlike the
    orchestrator's flat scenes — so tempo here DRIVES those: a low-energy beat gets a longer
    hold + gentler zoom (breathe); a high-energy beat gets a short hold + stronger push (drive).
    Also stamps `_energy` / `_transition` / `_motion_speed` as metadata. Beats map to BeatTempo
    positionally (flow beats and script beats are the same ordered list); mutates `spec` in place.

    Only MODULATES knobs the beat already declares, relative to the block's own baseline (the
    art pipeline sets deliberate values — introHold in frames, maxZoom ~1.4-1.5 — so we scale,
    never overwrite with absolutes). Never invents fields a block doesn't use."""
    beats = spec.get("beats") or []
    tb = tempo.beats
    n = min(len(beats), len(tb))
    for i in range(n):
        b, bt = beats[i], tb[i]
        e = bt.energy
        b["_energy"] = round(e, 3)
        b["_transition"] = bt.transition
        b["_motion_speed"] = bt.motion_speed
        ih = b.get("introHold")
        if isinstance(ih, (int, float)) and ih > 0:       # scale the hold: low e breathes, high e cuts in
            scaled = ih * (1.3 - 0.9 * e)                 # e=0 → 1.3x, e=1 → 0.4x
            b["introHold"] = int(round(scaled)) if isinstance(ih, int) else round(scaled, 2)
        mz = b.get("maxZoom")
        if isinstance(mz, (int, float)) and mz > 1.0:     # modulate zoom depth around the block's choice
            amt = mz - 1.0
            b["maxZoom"] = round(1.0 + amt * (0.7 + 0.6 * e), 3)   # e=0 → 0.7x gentler, e=1 → 1.3x push
    return {"beats": len(beats), "matched": n}


def design_tempo(ctx: ScriptContext, *, profile: str = "", llm=None) -> TempoPlan:
    """Design a TempoPlan for a script. Uses the LLM for the arc when given one, else rules.
    Always returns a full plan (one BeatTempo per script beat)."""
    profile = profile_for(ctx, profile)
    if not ctx.beats:
        return TempoPlan(slug=ctx.slug, profile=profile, beats=[], source="rules")
    if llm is not None:
        try:
            import asyncio
            txt = _run(llm.generate(_tempo_prompt(ctx, profile), _TEMPO_SYS))
            raw = _extract_json(txt)
            plan = _coerce(raw, ctx, profile)
            if plan:
                return plan
        except Exception:
            pass
    return _rule_plan(ctx, profile)


# ---- small utils ------------------------------------------------------------
def _run(coro):
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # already in a loop (shouldn't happen from sync callers) — run to completion
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        return ex.submit(lambda: asyncio.run(coro)).result()


def _extract_json(text: str) -> dict:
    if not text:
        return {}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}
