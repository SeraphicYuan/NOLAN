"""Paper -> figure, the simplest honest version — and the gate that makes it trustworthy.

The product goal is: a paper explainer where a figure is generated from the paper and NOLAN does
smart things on top. The DIFFICULT half is "stays true to the paper" — Paper2SysArch's own baseline
scores 69.0 composite on the harder subset, i.e. roughly a third of the structure wrong. Shipping a
plausible-but-wrong architecture diagram in a video that claims to explain that paper is the same
defect class as a wrong equation.

So this starts at the GATE, not the generator, because the gate is the part NOLAN gets cheaply.

Generation targets NOLAN's BLOCK IR (`diagram`: {root:{label,children[]}, layout}), never SVG — a
generated diagram spec is themeable, animatable, editable in the loop and checkable. A generated
SVG is a picture you can only place.

    python -X utf8 explore/2026-08-04-infographic/paper2figure.py            # honest structure
    python -X utf8 explore/2026-08-04-infographic/paper2figure.py --perturb  # a claim that lies
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
OUT = HERE / "_p2f"

# The Transformer, as its own paper describes it (section 3): an encoder-decoder, each a stack of
# N=6 identical layers; encoder layers have multi-head self-attention + a feed-forward network,
# decoder layers add encoder-decoder attention. Hand-authored HERE so this test measures the GATE
# rather than an LLM — swapping in a real extraction step changes only this literal.
ARCHITECTURE = {
    "root": {
        "label": "Transformer",
        "sub": "encoder-decoder, N=6",
        "children": [
            {"label": "Encoder stack", "children": [
                {"label": "Multi-head self-attention"},
                {"label": "Feed-forward network"},
            ]},
            {"label": "Decoder stack", "children": [
                {"label": "Masked self-attention"},
                {"label": "Encoder-decoder attention"},
                # Deliberately the SAME label as the encoder's. Duplicate labels are real in graphs
                # and a Set-based recovery silently merges them — which is how the first run of this
                # gate under-counted the render and blamed the composer.
                {"label": "Feed-forward network"},
            ]},
        ],
    },
    "layout": "tree",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", default="highlighter-editorial")
    ap.add_argument("--perturb", action="store_true",
                    help="claim a node the render will not contain — the gate must catch it")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    spec = json.loads(json.dumps(ARCHITECTURE))          # deep copy

    rendered_spec = json.loads(json.dumps(spec))
    if args.perturb:
        # The realistic failure: the extraction asserts a component the figure never shows. This is
        # what "visually plausible but structurally incorrect" looks like in NOLAN's own IR.
        spec["root"]["children"][0]["children"].append({"label": "Positional encoding"})

    authored = OUT / "authored.json"
    authored.write_text(json.dumps(spec, indent=1), encoding="utf-8")

    scene = {"id": "s1", "type": "diagram", "start": 0, "dur": 10.0, "data": rendered_spec}

    sys.path.insert(0, str(BRIDGE))
    import compose  # noqa: E402

    fid = "p2f"
    html = compose.compose_frame(fid, 10.0, [scene], theme=args.theme)
    frame = OUT / f"{fid}.html"
    frame.write_text(html, encoding="utf-8")
    n = len(json.dumps(spec))
    print(f"composed {frame.name} ({len(html)} bytes) — authored spec {n} bytes"
          f"{'  [PERTURBED: claims a node the render lacks]' if args.perturb else ''}")

    r = subprocess.run(
        ["node", str(HERE / "roundtrip.mjs"), str(frame), fid, str(authored),
         str(OUT / "roundtrip.json")],
        cwd=str(HERE), text=True,
    )
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
