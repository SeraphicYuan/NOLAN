"""CLI shim — the pacing linter now lives in nolan.flows.gate.pacing.lint (in-process).
Usage: python web-video-lab/pacing_lint.py <job.json> [--profile explainer|art] [--fps 30]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nolan.flows.gate.pacing import lint

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--profile", default="explainer", help="flow id in flows/registry.json")
    ap.add_argument("--fps", type=int, default=30)
    a = ap.parse_args()
    _, failed = lint(a.job, a.profile, a.fps)
    sys.exit(1 if failed else 0)
