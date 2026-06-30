"""The pre-render GATE - cheapest checks first, fail-fast, before any render. In-process
port of the former web-video-lab/art_check.py (now imports the tiers, no subprocess).

  Tier 0  validate   structural + palette   ~1s, no render
  Tier 0  pacing      temporal               ~1s, no render
  Tier 1  contact     spatial (stills)       ~seconds

`run_gate(job, flow_id)` raises RuntimeError on the first failing tier; flow-agnostic
(the flow id selects the palette + pacing profile).
"""
from __future__ import annotations

from pathlib import Path

from .validate import validate, show_palette  # noqa: F401 (show_palette re-exported for the CLI shim)
from .pacing import lint
from .contact import contact


def run_gate(job_path, flow_id: str) -> None:
    """Run the full gate. Raises RuntimeError on the first failing tier."""
    job_path = Path(job_path)

    print("\n=== Tier 0 · validate (structural + palette) ===")
    errs, _ = validate(job_path, flow_id)
    if errs:
        raise RuntimeError(f"GATE BLOCKED at validate ({len(errs)} error(s)) - fix before render")

    print("\n=== Tier 0 · pacing (temporal) ===")
    _, failed = lint(job_path, profile=flow_id)
    if failed:
        raise RuntimeError(f"GATE BLOCKED at pacing ({failed} beat(s) FAILED) - fix before render")

    print("\n=== Tier 1 · contact (spatial) ===")
    empties, _ = contact(job_path)
    if empties:
        raise RuntimeError(f"GATE BLOCKED at contact ({len(empties)} empty/near-black beat(s))")

    print("\n>> GATE GREEN - all tiers passed.")
