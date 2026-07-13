"""Temporal render gate — the DETERMINISTIC 'watch the motion, not a still' half.

render_gate samples ONE midpoint still per scene and VLM-judges legibility/relevance; hf_qa checks
spec-level clip duration + audio. Nothing looks at the rendered MOTION, so a frozen clip that
freeze-heal missed, a text 'slide' that settles in 2s then holds dead for 10, or dead air after the
reveals fire all ship silently (holbein POST_MORTEM — the 'reads like a slide' beats). This samples
several frames across each scene's window and measures frame-to-frame motion — cheap (ffmpeg + numpy,
no VLM) — flagging FROZEN / STATIC-HOLD / DEAD-AIR-TAIL. A STATIC-HOLD on a long ungrounded scene is
the deterministic signal that feeds the long-hold reliever.

  python -X utf8 -m nolan.hyperframes.temporal_gate <comp_dir>
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

_FROZEN_EPS = 0.002        # mean normalized frame diff below this ~= identical frames (frozen / truly static)
_STATIC_EPS = 0.020        # below this ~= very little movement across the window (a settled text slide)
_MIN_FLAG_DUR = 6.0        # a brief static hold is fine; only flag holds this long or longer


def _ffmpeg() -> str:
    from nolan.hf_qa import _ffmpeg as ff
    return ff()


# --- pure classification (testable without ffmpeg) ------------------------------------------------
def classify_motion(mean_motion: float, tail_motion: float, dur: float, grounded: bool) -> Optional[str]:
    """Verdict for one scene from its motion stats. None = fine."""
    if dur < _MIN_FLAG_DUR:
        return None                                        # short holds are readable, not slides
    if mean_motion < _FROZEN_EPS:
        return f"FROZEN ({dur:.1f}s, ~0 motion) — a frozen clip or a fully static frame"
    if not grounded and mean_motion < _STATIC_EPS:
        return f"STATIC-HOLD ({dur:.1f}s ungrounded, motion {mean_motion:.3f}) — reads like a slide; relieve it"
    if tail_motion < _FROZEN_EPS and mean_motion >= _FROZEN_EPS:
        return f"DEAD-AIR-TAIL ({dur:.1f}s) — motion up front then a dead tail (reveals fired, then nothing)"
    return None


# --- deterministic pixel-motion measurement -------------------------------------------------------
def _frame_at(mp4: Path, t: float, out: Path, ff: str) -> bool:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ff, "-y", "-ss", f"{t:.2f}", "-i", str(mp4), "-frames:v", "1",
                    "-vf", "scale=64:36", "-q:v", "5", str(out)], capture_output=True)
    return out.exists() and out.stat().st_size > 200


def _load_gray(path: Path):
    import numpy as np
    from PIL import Image
    with Image.open(path) as im:
        return np.asarray(im.convert("L"), dtype="float32") / 255.0


def frame_motion(paths: List[Path]) -> Dict:
    """Consecutive normalized mean-abs-diff across the sampled frames → {mean, tail, pairs}."""
    import numpy as np
    grays = []
    for p in paths:
        try:
            grays.append(_load_gray(p))
        except Exception:
            continue
    diffs: List[float] = []
    for a, b in zip(grays, grays[1:]):
        if a.shape != b.shape:
            continue
        diffs.append(float(np.mean(np.abs(a - b))))
    if not diffs:
        return {"mean": 0.0, "tail": 0.0, "pairs": 0}
    tail = diffs[-2:] or diffs
    return {"mean": round(sum(diffs) / len(diffs), 4),
            "tail": round(sum(tail) / len(tail), 4), "pairs": len(diffs)}


def scene_windows(comp_dir: Path) -> List[Dict]:
    """Per-scene GLOBAL window [start,end] + grounded flag (from specs + audio_meta frame offsets)."""
    comp_dir = Path(comp_dir)
    meta = {}
    mp = comp_dir / "audio_meta.json"
    if mp.exists():
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    frame_dur = {v.get("frame"): float(v.get("duration_s", 0) or 0) for v in meta.get("voices", [])}
    spec_files = sorted((comp_dir / "compositions" / "frames").glob("*.spec.json"))
    out, offset = [], 0.0
    for i, sf in enumerate(spec_files, start=1):
        spec = json.loads(sf.read_text(encoding="utf-8"))
        fdur = 0.0
        for fr in spec.get("frames", []):
            fdur = frame_dur.get(i, float(fr.get("dur", 0) or 0)) or float(fr.get("dur", 0) or 0)
            for sc in fr.get("scenes", []):
                st = float(sc.get("start", 0) or 0)
                du = float(sc.get("dur", 0) or 0)
                g = (sc.get("data", {}) or {}).get("ground") or {}
                grounded = g.get("kind") in ("image", "video")
                out.append({"frame": fr.get("id"), "scene": sc.get("id"), "type": sc.get("type"),
                            "start": round(offset + st, 3), "dur": round(du, 3), "grounded": grounded})
        offset += fdur
    return out


def _render_mp4(comp_dir: Path) -> Optional[Path]:
    rd = comp_dir / "renders"
    vids = sorted(rd.glob("*.mp4")) if rd.is_dir() else []
    return vids[0] if vids else None


def temporal_qa(comp_dir, mp4: Optional[Path] = None, k: int = 6, out_dir=None) -> Dict:
    """Sample k frames across each scene window, measure motion, flag FROZEN/STATIC/DEAD-AIR.
    Returns {ok, checked, flags:[...]}."""
    comp_dir = Path(comp_dir)
    mp4 = Path(mp4) if mp4 else _render_mp4(comp_dir)
    if not mp4 or not mp4.exists():
        return {"ok": True, "checked": 0, "flags": [], "note": "no render to inspect"}
    ff = _ffmpeg()
    stills = Path(out_dir or (comp_dir / "capture" / "_temporal"))
    flags, checked = [], 0
    for w in scene_windows(comp_dir):
        dur = w["dur"]
        if dur <= 0:
            continue
        lo, hi = w["start"] + 0.3, w["start"] + dur - 0.3
        if hi <= lo:
            continue
        times = [lo + (hi - lo) * j / (k - 1) for j in range(k)]
        paths = []
        for j, t in enumerate(times):
            p = stills / f"{w['frame']}_{w['scene']}_{j}.jpg"
            if _frame_at(mp4, t, p, ff):
                paths.append(p)
        if len(paths) < 2:
            continue
        checked += 1
        m = frame_motion(paths)
        verdict = classify_motion(m["mean"], m["tail"], dur, w["grounded"])
        if verdict:
            flags.append({**w, "mean_motion": m["mean"], "tail_motion": m["tail"], "verdict": verdict})
    flags.sort(key=lambda f: f["mean_motion"])
    return {"ok": not flags, "checked": checked, "flags": flags}


def main():
    import sys
    if len(sys.argv) < 2:
        sys.exit("usage: python -X utf8 -m nolan.hyperframes.temporal_gate <comp_dir>")
    rep = temporal_qa(sys.argv[1])
    print(f"TEMPORAL QA — checked {rep['checked']} scene(s) — {'PASS' if rep['ok'] else str(len(rep['flags'])) + ' FLAG'}")
    if rep.get("note"):
        print(f"  ({rep['note']})")
    for f in rep["flags"]:
        print(f"  ⚠ {f['frame']}/{f['scene']} ({f['type']}) — {f['verdict']}")
    if not rep["flags"] and rep["checked"]:
        print("  all scenes have live motion / are short enough to hold ✓")


if __name__ == "__main__":
    main()
