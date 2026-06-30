"""CLI shim — Tier-0 validation now lives in nolan.flows.gate.validate (in-process).
Usage: python web-video-lab/art_validate.py <job.json> [--flow art] | --show-palette <flow>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nolan.flows.gate.validate import show_palette, validate

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("job", nargs="?")
    ap.add_argument("--flow", default=None, help="flow id (enables palette check)")
    ap.add_argument("--show-palette", metavar="FLOW", default=None, help="print a flow's palette and exit")
    a = ap.parse_args()
    if a.show_palette:
        sys.exit(show_palette(a.show_palette))
    errs, _ = validate(a.job, a.flow)
    sys.exit(1 if errs else 0)
