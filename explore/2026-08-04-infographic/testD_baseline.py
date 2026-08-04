"""Test D baseline: the same script + assets through the SHIPPED `collage` block.

This is the benchmark. Without it, "Claude Design produced a collage" is a demo; with it, the
question becomes "did it beat the craft already in the repo", which is the only version worth
answering.

    python -X utf8 explore/2026-08-04-infographic/testD_baseline.py [--theme <slug>]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge"
TESTD = HERE / "_testD"

# rest positions, tuned so five subjects of very different aspect ratios share one tableau without
# collision and without entering the caption band (y is the REST CENTRE, 0..1 of frame height).
PLACEMENT = {
    "smart_meter_00": {"x": 0.16, "y": 0.42, "scale": 0.30, "from": "left"},
    "water_glass_00": {"x": 0.36, "y": 0.52, "scale": 0.26, "from": "bottom"},
    "gavel_01":       {"x": 0.55, "y": 0.36, "scale": 0.75, "from": "top"},
    "gpu_card_00":    {"x": 0.74, "y": 0.48, "scale": 0.30, "from": "right"},
    "cash_stack_00":  {"x": 0.90, "y": 0.60, "scale": 0.34, "from": "bottom"},
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", default="highlighter-editorial")
    args = ap.parse_args()

    narration = json.loads((TESTD / "narration.json").read_text(encoding="utf-8"))
    dur = narration["duration_s"]
    anchors = narration["anchors"]

    subjects = []
    for asset, a in anchors.items():
        p = PLACEMENT[asset]
        subjects.append({
            "src": str((TESTD / "assets" / f"{asset}.cutout.png").resolve()).replace("\\", "/"),
            "x": p["x"], "y": p["y"], "scale": p["scale"], "from": p["from"],
            # `at` is the ENTRY CUE — the block's own word-anchoring contract. Feeding it the
            # aligner's real time is what makes the +/-150ms check a fair test of the block rather
            # than of my guess at a stagger.
            "at": a["start"],
        })

    scene = {"id": "s1", "type": "collage", "start": 0, "dur": dur,
             "data": {"subjects": subjects, "backdrop": "var(--shell)", "camera": "push"}}

    sys.path.insert(0, str(BRIDGE))
    import compose  # noqa: E402

    fid = "testD-baseline"
    html = compose.compose_frame(fid, dur, [scene], theme=args.theme)
    out = TESTD / f"{fid}.html"
    out.write_text(html, encoding="utf-8")
    print(f"composed {out.name} ({len(html)} bytes, {len(subjects)} subjects, {dur:.2f}s)")

    r = subprocess.run(
        ["node", str(HERE / "verdict.mjs"), str(out), fid,
         str(TESTD / "narration.json"), str(TESTD / "baseline.verdict.json")],
        cwd=str(HERE), text=True,
    )
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
