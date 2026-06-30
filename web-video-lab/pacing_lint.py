"""Pacing linter — turn "good pacing" from vibes into measured, enforced numbers.

Runs on a gen_spec JOB json (no render needed) and reports, per beat + overall:
  • WPM            — words / minute of narration (intelligibility / drag)
  • first-reveal   — when the beat's first reveal lands (late payload / empty-stage = the
                     black-screen class of bug). NOTE: blocks that reveal continuously from
                     frame 0 (charts sweeping, figure highlights) use revealFrames=[0] and
                     correctly read first=0 — we only flag a LATE first reveal, not anchor
                     sparsity, so continuous-animation blocks don't false-positive.
  • gap            — longest stretch BETWEEN anchored reveals (a softer spacing signal)
  • reveals/sec    — visual event density (clutter vs sparse)
We have exact word timestamps + reveal frames, so these are exact, not guesses.

Usage:
  python web-video-lab/pacing_lint.py <job>.json [--profile explainer|art] [--fps 30]
The pacing thresholds come from the chosen flow's profile in flows/registry.json (different
video types pace differently — paper is punchy, art is contemplative). Exit code 1 if any
beat FAILs a hard threshold (use it as a pre-render gate).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# fallback profile = the explainer flow (used if registry/profile is unavailable).
_DEFAULT = {
    "wpm": [130, 165],
    "first_reveal_fail_s": 6.0, "first_reveal_warn_s": 3.0,
    "dead_gap_fail_s": 9.0, "dead_gap_warn_s": 5.0,
    "density_high_rps": 1.2, "min_hold_warn_s": 0.0,
}


def _load_profile(profile_id: str) -> dict:
    reg = Path(__file__).with_name("flows") / "registry.json"
    th = dict(_DEFAULT)
    try:
        types = json.loads(reg.read_text(encoding="utf-8")).get("types", [])
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
    # leading empty stage = first reveal time (THE black-screen signal). Inter-anchor gap is
    # only computed between ACTUAL reveals (never a synthetic 0/end mark), so a block that
    # reveals continuously from frame 0 (revealFrames=[0]) reads gap 0 — no false positive.
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
    # art-style: a beat that holds too briefly on its image reads as rushed.
    if th.get("min_hold_warn_s", 0) and dur_s < th["min_hold_warn_s"]:
        flags.append(("warn", f"rushed {dur_s:.1f}s hold"))
    return {"block": step.get("block", "?"), "dur_s": dur_s, "wpm": wpm,
            "first_s": first_s, "gap_s": gap_s, "dens": dens, "flags": flags}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--profile", default="explainer", help="flow id in flows/registry.json")
    ap.add_argument("--fps", type=int, default=30)
    a = ap.parse_args()
    th = _load_profile(a.profile)
    job = json.loads(Path(a.job).read_text(encoding="utf-8"))
    steps = job.get("props", {}).get("steps", [])
    fps = a.fps

    print(f"\nPACING · {Path(a.job).name} · {len(steps)} beats · profile={a.profile}\n" + "─" * 78)
    print(f"{'#':>2} {'block':16} {'dur':>5} {'wpm':>4} {'1st':>5} {'gap':>5} {'r/s':>4}  flags")
    total_f, total_w, failed = 0, 0, 0
    for i, st in enumerate(steps, 1):
        b = _beat(st, fps, th)
        total_f += b["dur_s"] * fps; total_w += st.get("words", []) and len(st["words"]) or 0
        tag = " ".join(f"[{lvl}] {msg}" for lvl, msg in b["flags"]) or "ok"
        if any(lvl == "FAIL" for lvl, _ in b["flags"]): failed += 1
        print(f"{i:>2} {b['block']:16} {b['dur_s']:>4.0f}s {b['wpm']:>4.0f} "
              f"{b['first_s']:>4.1f}s {b['gap_s']:>4.1f}s {b['dens']:>4.1f}  {tag}")
    dur_s = total_f / fps
    print("─" * 78)
    print(f"total {dur_s/60:.1f} min · overall {total_w/(dur_s/60):.0f} wpm · "
          f"{failed} beat(s) FAILED")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
