"""CLI shim — the pre-render gate now lives in nolan.flows.gate.run_gate (in-process).
Usage: python web-video-lab/art_check.py <job.json> [--profile art]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nolan.flows.gate import run_gate


def main() -> int:
    args = sys.argv[1:]
    job = args[0]
    profile = next((args[i + 1] for i, a in enumerate(args) if a == "--profile" and i + 1 < len(args)), "art")
    try:
        run_gate(job, profile)
    except Exception as e:  # noqa: BLE001 - surface the blocked tier
        print(f"\n■ {e}")
        return 1
    print("    (safe to full-render)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
