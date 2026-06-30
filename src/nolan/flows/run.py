"""Run a video flow end to end.

  PYTHONPATH=src python3 -m nolan.flows.run --flow art <spec.json> [--no-gate] [--deliver <path>]

This is the runner entry used for the integration test. The user-facing `nolan render-flow`
CLI subcommand (Windows-python bridge + project video_type lookup) is a follow-up.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from nolan.flows import get_flow
from nolan.flows.base import run_flow


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", help="authored flow spec (e.g. web-video-lab/art/dance.spec.json)")
    ap.add_argument("--flow", required=True, help="flow id (art, …)")
    ap.add_argument("--no-gate", action="store_true", help="skip the pre-render gate")
    ap.add_argument("--deliver", default=None, help="override delivery path")
    a = ap.parse_args()
    out = run_flow(get_flow(a.flow), Path(a.spec), gate=not a.no_gate,
                   deliver_to=Path(a.deliver) if a.deliver else None)
    print("OK ->", out)


if __name__ == "__main__":
    main()
