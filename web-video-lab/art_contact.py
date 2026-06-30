"""CLI shim — Tier-1 contact now lives in nolan.flows.gate.contact (in-process).
Usage: python web-video-lab/art_contact.py <job.json> [--fracs 0.55,0.92] [--out <name>.contact.png]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nolan.flows.gate.contact import contact


def _arg(s: str) -> str:
    i = s.find("=")
    return s[i + 1:] if i >= 0 else ""


if __name__ == "__main__":
    args = sys.argv[1:]
    job = args[0]
    fracs = tuple(float(x) for x in (next((_arg(a) for a in args if a.startswith("--fracs")), "0.55,0.92")).split(","))
    out = next((_arg(a) for a in args if a.startswith("--out")), None)
    empties, _ = contact(job, fracs, out)
    sys.exit(1 if empties else 0)
