"""Deconstruction extract — assemble facts + interpretation for one video.

``build_extract`` composes everything below into ``extract.json`` plus a
draft ``recovered_plan.json`` (scene_plan schema, forward-pipeline ready):

1. **Facts** — per-shot rows from ``nolan.visual_facts`` (computed/persisted
   on demand; vision facts included when a provider is passed).
2. **Narration alignment** — library segment transcripts + shown-texts mapped
   onto shots by time overlap (reuses ``video_style.pairing.compose_shown``
   with its on-screen-text stripping).
3. **Beats** — editorial segmentation (LLM, deterministic fallback).
4. **Operators** — pairing classification per beat (LLM, band fallback),
   with a BGE said↔shown directness prior when an embedder is passed.
5. **Tempo recovery** — deterministic: per-beat cut density + measured motion
   → energy 0..1 → transition/motion_speed via ``tempo_plan._levers`` (the
   same mapping the forward pipeline uses, run in reverse).
6. **Evidence frames** — one representative JPEG per beat for the synthesis
   agent to look at.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from nolan.tempo_plan import _levers, _pace_dir, _PROFILES
from nolan.video_style.pairing import (LITERAL_MIN, TONAL_MAX, compose_shown,
                                       strip_onscreen_text)
from nolan.visual_facts import (ASSET_TYPE_TO_VISUAL, ensure_visual_facts,
                                extract_rep_frame)

from .beats import segment_beats
from .operators import classify_operators

EXTRACT_VERSION = 1


def _seg_to_dict(seg) -> Dict[str, Any]:
    ic = getattr(seg, "inferred_context", None)
    return {
        "timestamp_start": getattr(seg, "timestamp_start", 0.0),
        "timestamp_end": getattr(seg, "timestamp_end", 0.0),
        "transcript": getattr(seg, "transcript", None),
        "combined_summary": getattr(seg, "combined_summary", None),
        "frame_description": getattr(seg, "frame_description", None),
        "inferred_context": ic.to_dict() if ic and hasattr(ic, "to_dict") else ic,
    }


def _band(score: float) -> str:
    if score >= LITERAL_MIN:
        return "literal"
    if score >= TONAL_MAX:
        return "associative"
    return "tonal/abstract"


def _overlap(seg: Dict[str, Any], t0: float, t1: float) -> bool:
    s, e = seg.get("timestamp_start", 0.0), seg.get("timestamp_end", 0.0)
    return max(s, t0) < min(e or t1, t1)


def _align_to_shots(shots: List[Dict[str, Any]],
                    segs: List[Dict[str, Any]]) -> tuple:
    """Per shot: (narration said, imagery shown) from overlapping segments."""
    said, shown = [], []
    for sh in shots:
        t0, t1 = sh["timestamp_start"], sh["timestamp_end"]
        over = [s for s in segs if _overlap(s, t0, t1)]
        texts = [(s.get("transcript") or "").strip() for s in over]
        said.append(" ".join(t for t in texts if t))
        shs = []
        for s in over:
            clean, _ = strip_onscreen_text(compose_shown(s))
            if clean:
                shs.append(clean)
        shown.append(" | ".join(dict.fromkeys(shs)))       # dedupe, keep order
    return said, shown


def _norm(values: List[float]) -> List[float]:
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def _recover_tempo(beats: List[Dict[str, Any]], shots: List[Dict[str, Any]],
                   profile: str = "balanced") -> None:
    """Annotate beats in place with energy/pace_dir/transition/motion_speed."""
    if not beats:
        return
    prof = _PROFILES.get(profile, _PROFILES["balanced"])
    cut_rates, motions = [], []
    for b in beats:
        rows = shots[b["first_shot"]:b["last_shot"] + 1]
        dur = max(0.5, b["t1"] - b["t0"])
        cut_rates.append(len(rows) / dur * 60.0)
        motions.append(sum(r.get("motion_magnitude") or 0.0 for r in rows) / max(1, len(rows)))
    n_cuts, n_mot = _norm(cut_rates), _norm(motions)
    floor, climax = prof["floor"], prof["climax"]
    energies = [round(min(0.95, max(0.05, floor + (climax - floor) *
                                    (0.6 * c + 0.4 * m))), 2)
                for c, m in zip(n_cuts, n_mot)]
    for i, b in enumerate(beats):
        b["cuts_per_min"] = round(cut_rates[i], 1)
        b["mean_motion"] = round(motions[i], 4)
        b["energy"] = energies[i]
        b["pace_dir"] = _pace_dir(energies[i - 1] if i else None, energies[i],
                                  energies[i + 1] if i + 1 < len(energies) else None)
        transition, speed, _shots = _levers(energies[i], prof)
        b["transition"] = transition       # derived from energy, not measured
        b["motion_speed"] = speed
        rows = shots[b["first_shot"]:b["last_shot"] + 1]
        hints = [r.get("treatment_hint") for r in rows if r.get("treatment_hint")]
        b["dominant_treatment"] = (max(set(hints), key=hints.count) if hints else None)


def _draft_plan(video_path: str, beats: List[Dict[str, Any]],
                shots: List[Dict[str, Any]], shot_said: List[str]) -> Dict[str, Any]:
    """Deterministic draft recovered_plan.json in scene_plan schema.

    One scene per shot for short beats; montage beats (>8 shots) collapse to
    a single scene so the plan stays reviewable. The synthesis agent refines.
    """
    def fmt(t: float) -> str:
        return f"{int(t // 60)}:{int(t % 60):02d}"

    sections: Dict[str, List[Dict[str, Any]]] = {}
    n = 0

    def scene(t0, t1, said, vt, desc, beat) -> Dict[str, Any]:
        nonlocal n
        n += 1
        sc = {"id": f"scene_{n:03d}", "start": fmt(t0),
              "duration": f"{max(1, round(t1 - t0))}s",
              "narration_excerpt": (said or "")[:400],
              "visual_type": vt, "visual_description": (desc or "")[:300],
              "energy": beat.get("energy"), "transition": beat.get("transition"),
              "motion_speed": beat.get("motion_speed"),
              "recovered": {"operator": beat.get("operator"),
                            "treatment": beat.get("dominant_treatment")}}
        return sc

    for b in beats:
        rows = shots[b["first_shot"]:b["last_shot"] + 1]
        key = f"{b['title']}"
        sections[key] = []
        if len(rows) > 8:
            types = [r.get("asset_type") for r in rows if r.get("asset_type")]
            vt = ASSET_TYPE_TO_VISUAL.get(
                max(set(types), key=types.count) if types else "other", "b-roll")
            sections[key].append(scene(
                b["t0"], b["t1"], b.get("said"), vt,
                f"montage of {len(rows)} shots ({', '.join(sorted(set(types))[:4]) or 'mixed'})",
                b))
        else:
            for i, r in enumerate(rows):
                vt = ASSET_TYPE_TO_VISUAL.get(r.get("asset_type") or "other", "b-roll")
                desc = r.get("identity_hint") or r.get("asset_type") or ""
                sections[key].append(scene(
                    r["timestamp_start"], r["timestamp_end"],
                    shot_said[b["first_shot"] + i] if b["first_shot"] + i < len(shot_said) else "",
                    vt, desc, b))
    return {"sections": sections,
            "_meta": {"source": "deconstruction-draft", "video_path": str(video_path),
                      "generated_at": datetime.now().isoformat()}}


async def build_extract(video_path: str, index, *, llm=None, embed=None,
                        vision_provider=None, frames_dir: Optional[Path] = None,
                        profile: str = "balanced") -> tuple:
    """Full Tier-2 assembly. Returns (extract_dict, draft_plan_dict)."""
    shots = await ensure_visual_facts(video_path, index,
                                      vision_provider=vision_provider)
    segs = [_seg_to_dict(s) for s in index.get_segments(video_path)]
    duration = max((s["timestamp_end"] for s in shots), default=0.0)
    shot_said, shot_shown = _align_to_shots(shots, segs)

    beat_res = await segment_beats(shots, shot_said, duration, llm=llm)
    beats = beat_res["beats"]
    for b in beats:
        rows = shots[b["first_shot"]:b["last_shot"] + 1]
        b["t0"], b["t1"] = rows[0]["timestamp_start"], rows[-1]["timestamp_end"]
        b["shot_count"] = len(rows)
        b["said"] = " ".join(t for t in shot_said[b["first_shot"]:b["last_shot"] + 1] if t)[:1200]
        b["shown"] = " | ".join(dict.fromkeys(
            t for t in shot_shown[b["first_shot"]:b["last_shot"] + 1] if t))[:1200]
        types = sorted({r.get("asset_type") for r in rows if r.get("asset_type")})
        b["asset_types"] = ", ".join(types)
        idents = sorted({r.get("identity_hint") for r in rows if r.get("identity_hint")})
        if idents:
            b["identified_assets"] = idents

    # directness prior (optional, needs both texts + an embedder)
    pairs = [(i, b) for i, b in enumerate(beats) if b.get("said") and b.get("shown")]
    if embed is not None and pairs:
        try:
            from nolan.video_style.pairing import _cos
            vecs = embed([b["said"] for _, b in pairs] + [b["shown"] for _, b in pairs])
            half = len(pairs)
            for j, (_, b) in enumerate(pairs):
                d = round(_cos(vecs[j], vecs[half + j]), 3)
                b["directness"], b["band"] = d, _band(d)
        except Exception:
            pass

    op_res = await classify_operators(beats, llm=llm)
    _recover_tempo(beats, shots, profile=profile)

    if frames_dir is not None:
        frames_dir = Path(frames_dir)
        frames_dir.mkdir(parents=True, exist_ok=True)
        for i, b in enumerate(beats):
            mid_shot = shots[(b["first_shot"] + b["last_shot"]) // 2]
            f = frames_dir / f"beat_{i:02d}.jpg"
            if extract_rep_frame(Path(video_path), mid_shot["rep_timestamp"], f):
                b["frame"] = f.name

    extract = {
        "version": EXTRACT_VERSION,
        "video_path": str(video_path),
        "duration": duration,
        "shot_count": len(shots),
        "segment_count": len(segs),
        "beats": beats,
        "beat_source": beat_res["source"],
        "operator_source": op_res["source"],
        "shots": shots,
        "notes": ["transition values are derived from recovered energy via the"
                  " forward tempo mapping (dissolves are not measured in v1)"],
        "generated_at": datetime.now().isoformat(),
    }
    plan = _draft_plan(video_path, beats, shots, shot_said)
    return extract, plan
