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
  python web-video-lab/pacing_lint.py render-service/_lab_chapter/jobs/<chapter>.json [--fps 30]
Exit code 1 if any beat FAILs a hard threshold (use it as a pre-render gate).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# thresholds (warn → yellow, fail → hard gate)
WPM_SLOW, WPM_FAST = 105, 180
FIRST_REVEAL_WARN, FIRST_REVEAL_FAIL = 3.0, 6.0   # seconds of empty stage
DEAD_GAP_WARN, DEAD_GAP_FAIL = 5.0, 9.0           # seconds with no reveal
DENSITY_HIGH = 1.2                                # reveals/sec → cluttered


def _beat(step: dict, fps: int) -> dict:
    dur_f = max(1, int(step.get("durationInFrames", 1)))
    dur_s = dur_f / fps
    words = step.get("words", [])
    wc = len(words)
    wpm = wc / (dur_s / 60) if dur_s else 0
    reveals = sorted(set(int(r) for r in step.get("revealFrames", []) if r is not None))
    first_s = (reveals[0] / fps) if reveals else 0.0
    # leading empty stage = first reveal time (THE black-screen signal). Inter-anchor gap is
    # only computed between ACTUAL reveals (never a synthetic 0/end mark), so a block that
    # reveals continuously from frame 0 (revealFrames=[0]) reads gap 0 — no false positive.
    inter_f = max((b - a) for a, b in zip(reveals, reveals[1:])) if len(reveals) >= 2 else 0
    gap_s = inter_f / fps
    dens = (len(reveals) / dur_s) if dur_s else 0
    flags = []
    if first_s >= FIRST_REVEAL_FAIL: flags.append(("FAIL", f"first reveal {first_s:.1f}s (late payload / empty stage)"))
    elif first_s >= FIRST_REVEAL_WARN: flags.append(("warn", f"first reveal {first_s:.1f}s"))
    if gap_s >= DEAD_GAP_FAIL: flags.append(("warn", f"{gap_s:.1f}s between reveals"))
    elif gap_s >= DEAD_GAP_WARN: flags.append(("warn", f"{gap_s:.1f}s between reveals"))
    if wpm > WPM_FAST: flags.append(("warn", f"fast {wpm:.0f} wpm"))
    elif 0 < wpm < WPM_SLOW: flags.append(("warn", f"slow {wpm:.0f} wpm"))
    if dens > DENSITY_HIGH: flags.append(("warn", f"dense {dens:.1f} reveals/s"))
    return {"block": step.get("block", "?"), "dur_s": dur_s, "wpm": wpm,
            "first_s": first_s, "gap_s": gap_s, "dens": dens, "flags": flags}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--fps", type=int, default=30)
    a = ap.parse_args()
    job = json.loads(Path(a.job).read_text(encoding="utf-8"))
    steps = job.get("props", {}).get("steps", [])
    fps = a.fps

    print(f"\nPACING · {Path(a.job).name} · {len(steps)} beats\n" + "─" * 78)
    print(f"{'#':>2} {'block':16} {'dur':>5} {'wpm':>4} {'1st':>5} {'gap':>5} {'r/s':>4}  flags")
    total_f, total_w, failed = 0, 0, 0
    for i, st in enumerate(steps, 1):
        b = _beat(st, fps)
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
