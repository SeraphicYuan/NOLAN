"""Timeline view — the scene plan DERIVED onto a time axis (read-only, P2).

A lite-NLE view over artifacts that already exist; like the asset pool this
computes at request time and stores nothing. Lanes:

  sections  narration-owned spans (sec_*.wav durations — LOCKED, narration
            owns duration)
  scenes    plan windows (start_seconds..end_seconds)
  units     the visual treatment per scene: media + a MOTION BADGE.
            Authored motion (motion_spec/layout_spec/motif/recipe) is shown
            as authored; stills get the SAME still-treatment pre-pass the
            premium renderer runs (still_motion.assign_still_treatments),
            marked derived — what the next render WILL do, not a promise.
  sfx       ambience cue markers (human or auto-authored, from scene.sfx)
  vo        the narration RMS envelope (the beat anchors made visible)

Times are global seconds (the aligner writes absolute starts).
"""

from __future__ import annotations

import json
import logging
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _wav_duration(p: Path) -> float:
    try:
        with wave.open(str(p), "rb") as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception as exc:
        logger.warning("timeline: unreadable wav %s: %s", p.name, exc)
        return 0.0


def _vo_envelope(wavs: List[Path], rate: float = 4.0) -> List[float]:
    """Concatenated per-window RMS across the section wavs, normalized 0..1.
    ``rate`` = samples per second of timeline (4 -> 250ms windows)."""
    import numpy as np
    peaks: List[float] = []
    for p in wavs:
        try:
            with wave.open(str(p), "rb") as w:
                sr = w.getframerate()
                n = w.getnframes()
                raw = np.frombuffer(w.readframes(n), dtype=np.int16)
                if w.getnchannels() > 1:
                    raw = raw.reshape(-1, w.getnchannels()).mean(axis=1)
            win = max(1, int(sr / rate))
            usable = (len(raw) // win) * win
            if usable:
                chunks = raw[:usable].astype(np.float64).reshape(-1, win)
                peaks.extend(np.sqrt((chunks ** 2).mean(axis=1)).tolist())
        except Exception as exc:
            logger.warning("timeline: envelope failed for %s: %s", p.name, exc)
    if not peaks:
        return []
    top = max(peaks) or 1.0
    return [round(v / top, 3) for v in peaks]


def _motion_badge(scene: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """One badge per scene: WHAT moves and WHO decided (authored|derived)."""
    ms = scene.get("motion_spec")
    if isinstance(ms, dict) and ms.get("effect"):
        return {"badge": ms["effect"], "source": "authored"}
    ls = scene.get("layout_spec")
    if isinstance(ls, dict) and (ls.get("template") or ls.get("block")):
        return {"badge": ls.get("template") or ls.get("block"),
                "source": "authored"}
    if scene.get("motif"):
        return {"badge": f"motif:{scene['motif']}", "source": "authored"}
    if scene.get("recipe"):
        return {"badge": f"recipe:{scene['recipe']}", "source": "authored"}
    if scene.get("matched_clip") or scene.get("rendered_clip"):
        return {"badge": "clip", "source": "authored"}
    if scene.get("_still_treatment"):
        # a human lock (authored still_treatment) surfaces as authored; the
        # pre-pass already honored it, so badge == the locked value
        src = "authored" if scene.get("still_treatment") else "derived"
        return {"badge": scene["_still_treatment"], "source": src}
    return None


def _media_name(scene: Dict[str, Any]) -> Optional[str]:
    for key in ("matched_asset", "rendered_clip"):
        if scene.get(key):
            return Path(str(scene[key])).name
    if scene.get("generated_asset"):
        return str(scene["generated_asset"])
    mc = scene.get("matched_clip")
    if isinstance(mc, dict) and mc.get("video_path"):
        return Path(str(mc["video_path"])).name
    return None


def build_timeline(project_path: Path, envelope_rate: float = 4.0) -> Dict[str, Any]:
    project_path = Path(project_path)
    plan_path = project_path / "scene_plan.json"
    if not plan_path.exists():
        raise FileNotFoundError(f"no scene_plan.json in {project_path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    # the SAME pre-pass premium runs at plan load — the derived badges show
    # what the next render will actually do (in memory; plan is not written)
    from nolan.still_motion import assign_still_treatments
    assign_still_treatments(plan)

    sections_map = [(k, v) for k, v in (plan.get("sections") or {}).items()
                    if isinstance(v, list)]

    # sections lane: narration owns duration -> spans from the section wavs
    wavs = sorted((project_path / "assets" / "voiceover" / "_work")
                  .glob("sec_*.wav"))
    sections = []
    t = 0.0
    for i, w in enumerate(wavs):
        d = _wav_duration(w)
        name = sections_map[i][0] if i < len(sections_map) else w.stem
        sections.append({"name": name, "index": i,
                         "start": round(t, 3), "end": round(t + d, 3)})
        t += d
    total = round(t, 3)

    scenes_lane: List[Dict[str, Any]] = []
    units: List[Dict[str, Any]] = []
    sfx: List[Dict[str, Any]] = []
    for si, (sec_name, scenes) in enumerate(sections_map):
        for s in scenes:
            if not isinstance(s, dict):
                continue
            start = s.get("start_seconds")
            end = s.get("end_seconds")
            entry = {
                "id": s.get("id"), "section": sec_name,
                "start": start, "end": end,
                "visual_type": s.get("visual_type"),
                "excerpt": (s.get("narration_excerpt") or "")[:120],
                "energy": s.get("energy"),
            }
            scenes_lane.append(entry)
            media = _media_name(s)
            badge = _motion_badge(s)
            shots = s.get("shots") if isinstance(s.get("shots"), list) else None
            units.append({
                "scene_id": s.get("id"), "start": start, "end": end,
                "media": media,
                "kind": ("clip" if (s.get("matched_clip")
                                    or s.get("rendered_clip"))
                         else "image" if media else None),
                "motion": badge,
                "shots": len(shots) if shots else 0,
                "pinned": bool(s.get("pinned_asset")),
                "citation": (s.get("asset_license") or {}).get("title")
                            if isinstance(s.get("asset_license"), dict) else None,
            })
            cue = s.get("sfx")
            if isinstance(cue, dict) and (cue.get("query") or cue.get("file")):
                sfx.append({
                    "t": round(float(start or 0.0) + float(cue.get("at") or 0.0), 3),
                    "scene_id": s.get("id"),
                    "label": cue.get("query") or Path(str(cue["file"])).name,
                    "volume": cue.get("volume"),
                })

    notes = plan.get("meta", {}).get("timeline_notes") or []

    return {
        "project": project_path.name,
        "duration": total,
        "sections": sections,
        "scenes": scenes_lane,
        "units": units,
        "sfx": sfx,
        "vo": {"rate": envelope_rate, "peaks": _vo_envelope(wavs, envelope_rate)},
        "notes": notes,
        "has_narration": bool(wavs),
    }
