"""Pacing lint — measured, enforced pacing numbers. In-process port of the former
web-video-lab/pacing_lint.py.

Per beat + overall: WPM, first-reveal (the black-screen signal), gap (dead air between
reveals), reveals/sec (density). Thresholds come from the flow's profile in registry.json
(art is contemplative, explainer is punchy). A beat FAILs on a hard threshold.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..base import ROOT

REGISTRY = ROOT / "web-video-lab" / "flows" / "registry.json"

# fallback profile = the explainer flow (used if registry/profile is unavailable).
_DEFAULT = {
    "wpm": [130, 165],
    "first_reveal_fail_s": 6.0, "first_reveal_warn_s": 3.0,
    "dead_gap_fail_s": 9.0, "dead_gap_warn_s": 5.0,
    "density_high_rps": 1.2, "min_hold_warn_s": 0.0,
}


def _load_profile(profile_id: str) -> dict:
    th = dict(_DEFAULT)
    try:
        types = json.loads(REGISTRY.read_text(encoding="utf-8")).get("types", [])
        p = next((t["pacing"] for t in types if t["id"] == profile_id), None)
        if p:
            th.update(p)
    except Exception:
        pass
    return th


def _beat(step: dict, fps: int, th: dict) -> dict:
    dur_f = max(1, int(step.get("durationInFrames", 1)))
    dur_s = dur_f / fps
    words = step.get("words", [])
    wpm = len(words) / (dur_s / 60) if dur_s else 0
    reveals = sorted(set(int(r) for r in step.get("revealFrames", []) if r is not None))
    first_s = (reveals[0] / fps) if reveals else 0.0
    inter_f = max((b - a) for a, b in zip(reveals, reveals[1:])) if len(reveals) >= 2 else 0
    gap_s = inter_f / fps
    dens = (len(reveals) / dur_s) if dur_s else 0
    wpm_lo, wpm_hi = th["wpm"]
    flags = []
    if first_s >= th["first_reveal_fail_s"]:
        flags.append(("FAIL", f"first reveal {first_s:.1f}s (late payload / empty stage)"))
    elif first_s >= th["first_reveal_warn_s"]:
        flags.append(("warn", f"first reveal {first_s:.1f}s"))
    if gap_s >= th.get("dead_gap_fail_s", 9.0):
        flags.append(("FAIL", f"{gap_s:.1f}s dead air between reveals"))
    elif gap_s >= th["dead_gap_warn_s"]:
        flags.append(("warn", f"{gap_s:.1f}s between reveals"))
    if wpm > wpm_hi: flags.append(("warn", f"fast {wpm:.0f} wpm"))
    elif 0 < wpm < wpm_lo: flags.append(("warn", f"slow {wpm:.0f} wpm"))
    if dens > th["density_high_rps"]: flags.append(("warn", f"dense {dens:.1f} reveals/s"))
    if th.get("min_hold_warn_s", 0) and dur_s < th["min_hold_warn_s"]:
        flags.append(("warn", f"rushed {dur_s:.1f}s hold"))
    return {"block": step.get("block", "?"), "dur_s": dur_s, "wpm": wpm,
            "first_s": first_s, "gap_s": gap_s, "dens": dens, "flags": flags}


def lint(job_path, profile: str = "explainer", fps: int = 30):
    """Lint a job's pacing. Returns (rows:list, failed:int); prints the per-beat table."""
    job_path = Path(job_path)
    th = _load_profile(profile)
    job = json.loads(job_path.read_text(encoding="utf-8"))
    steps = job.get("props", {}).get("steps", [])

    print(f"\nPACING · {job_path.name} · {len(steps)} beats · profile={profile}\n" + "-" * 78)
    print(f"{'#':>2} {'block':16} {'dur':>5} {'wpm':>4} {'1st':>5} {'gap':>5} {'r/s':>4}  flags")
    total_f, total_w, failed, rows = 0, 0, 0, []
    for i, st in enumerate(steps, 1):
        b = _beat(st, fps, th)
        rows.append(b)
        total_f += b["dur_s"] * fps
        total_w += st.get("words", []) and len(st["words"]) or 0
        tag = " ".join(f"[{lvl}] {msg}" for lvl, msg in b["flags"]) or "ok"
        if any(lvl == "FAIL" for lvl, _ in b["flags"]):
            failed += 1
        print(f"{i:>2} {b['block']:16} {b['dur_s']:>4.0f}s {b['wpm']:>4.0f} "
              f"{b['first_s']:>4.1f}s {b['gap_s']:>4.1f}s {b['dens']:>4.1f}  {tag}")
    dur_s = total_f / fps
    print("-" * 78)
    print(f"total {dur_s/60:.1f} min · overall {total_w/(dur_s/60) if dur_s else 0:.0f} wpm · {failed} beat(s) FAILED")
    return rows, failed
