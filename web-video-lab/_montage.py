"""CLI shim — the contact-sheet montage now lives in nolan.flows.gate.montage.build_sheet
(in-process; no longer a separate interpreter). Kept for standalone use.
Arg: <spec.json>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nolan.flows.gate.montage import build_sheet

if __name__ == "__main__":
    build_sheet(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
