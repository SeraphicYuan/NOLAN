"""The pre-render GATE — cheapest checks first, fail-fast, before any full render.

Embodies the rule "check per beat before concatenating, never after": a beat only
earns a place in the full render once it passes every tier below. This is also what
makes safe parallel (subagent) rendering possible — each beat is independently gated.

  Tier 0  validate   structural (paths, bounds, reveal arity)     ~1s, no render
  Tier 0  pacing      temporal (wpm, first-reveal, gap, density)  ~1s, no render
  Tier 1  contact     spatial (one still/beat -> contact sheet)   ~seconds

Only when all three are green do you pay for render.mjs (Tier 3, ~minutes).

Usage: python art_check.py <job.json> [--profile art]
Exit 0 = GREEN (safe to full-render); nonzero = the first failing tier.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable


def run(title: str, cmd: list[str]) -> int:
    print(f"\n=== {title} ===")
    rc = subprocess.run(cmd).returncode
    print(f"--- {title}: {'PASS' if rc == 0 else 'FAIL'} (exit {rc}) ---")
    return rc


def main() -> int:
    args = sys.argv[1:]
    job = args[0]
    profile = next((args[i + 1] for i, a in enumerate(args) if a == "--profile" and i + 1 < len(args)), "art")

    tiers = [
        ("Tier 0 · validate (structural + palette)", [PY, str(HERE / "art_validate.py"), job, "--flow", profile]),
        ("Tier 0 · pacing (temporal)", [PY, str(HERE / "pacing_lint.py"), job, "--profile", profile]),
        ("Tier 1 · contact (spatial)", [PY, str(HERE / "art_contact.py"), job]),
    ]
    for title, cmd in tiers:
        if run(title, cmd) != 0:
            print(f"\n■ GATE BLOCKED at '{title}'. Fix before full render.")
            return 1

    print("\n■ GATE GREEN — all tiers passed. Safe to full-render:")
    print(f"    cd render-service && node _lab_chapter/render.mjs {job}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
