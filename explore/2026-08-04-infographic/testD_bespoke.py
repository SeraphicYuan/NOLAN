"""Test D submission: the same brief as a BESPOKE `raw` scene, scored by the same verdict.

The baseline (`collage` block) scores 6/6 and looks like five objects in a line. The design problem
this attempt sets itself:

  * SEMANTIC GROUPING — the script has two halves. meter / water / gavel are what a data centre
    COSTS; chips / cash are the BET it makes. So costs cluster left and mid, the bet lands right,
    and the gavel's handle points right to carry the eye across the turn in the sentence.
  * SCALE HIERARCHY — `gpu_card` is the thesis ("the chips will earn it all back") and is the
    largest object on screen. The baseline gave all five the same weight.
  * OVERLAP AND CONTACT — objects overlap and each sits on a soft contact ellipse, so the frame
    reads as one tableau rather than a lineup of floating cutouts.

Constraints obeyed (BESPOKE_BRIEF.md):
  * every id prefixed with the scene id
  * ONLY transform + opacity animated; static layout uses left/top on an OUTER wrapper that is
    never tweened, and GSAP animates an INNER element — so the positioning transform is never
    clobbered
  * depth without filters: no blur, no box-shadow. Contact shadows are radial-gradient ellipses
    (a background, not a filter) and recession is scale + opacity only
  * nothing exits; every subject holds to the end
  * nothing below 83% of frame height
  * no Math.random / Date.now / yoyo / infinite repeat

    python -X utf8 explore/2026-08-04-infographic/testD_bespoke.py
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
SID = "s1"

# centre-x, centre-y (px on 1920x1080), rendered HEIGHT (or width for the wide gavel), entry.
# Bottoms are all <= 790px, comfortably above the 896px caption line.
# REVISION 2, after looking at revision 1. Its defects were all spatial, none mechanical: the
# gavel's head collided with the water glass rim by accident (it read as balancing on it), the
# contact ellipses were invisible at 0.16 on a light shell, a dead gap ran down the middle between
# two unrelated clusters, and the horizon sat at 72% while objects floated above and below it.
#
# Fix: give every object a SHARED BASELINE at y=700 (bottoms land within +/-25px of it, the small
# variance reading as depth), tighten the spread so the group overlaps as one mass, and put the
# horizon ON that baseline so it becomes a ground the objects stand on rather than a stray rule.
BASELINE_Y = 700
LAYOUT = {
    "smart_meter_00": dict(cx=470,  cy=575, h=240, enter="left",   rot=-5),
    "water_glass_00": dict(cx=650,  cy=540, h=330, enter="bottom", rot=0),
    "gavel_01":       dict(cx=880,  cy=610, w=400, enter="top",    rot=-9),
    "gpu_card_00":    dict(cx=1180, cy=475, h=460, enter="right",  rot=3),
    "cash_stack_00":  dict(cx=1470, cy=600, h=230, enter="bottom", rot=-7),
}
FROM = {"left": (-70, 0), "right": (70, 0), "top": (0, -60), "bottom": (0, 55)}


def build(narration: dict) -> dict:
    anchors = narration["anchors"]
    dur = narration["duration_s"]
    html: list[str] = []
    tl: list[str] = []

    html.append(
        f'<div id="{SID}-wrap" class="clip" data-start="0" data-duration="{dur:.2f}" '
        f'data-track-index="0" style="position:absolute;inset:0;overflow:hidden;'
        f'background:var(--shell);">'
    )
    # A faint horizon so the objects sit in a space rather than float. Theme rule colour, low alpha.
    html.append(
        f'<div id="{SID}-horizon" style="position:absolute;left:18%;top:{BASELINE_Y}px;'
        f'width:64%;height:1px;background:var(--text);opacity:0;"></div>'
    )
    html.append(
        f'<div id="{SID}-kicker" style="position:absolute;left:6%;top:9%;opacity:0;'
        f'font-family:var(--font-display-en);font-size:26px;letter-spacing:.18em;'
        f'text-transform:uppercase;color:var(--text-mute);">The bill arrives</div>'
    )
    # One drifting camera group; a slow scale is transform-only and seek-exact.
    html.append(f'<div id="{SID}-cam" style="position:absolute;inset:0;transform-origin:50% 55%;">')

    order = list(anchors.items())
    for asset, a in order:
        L = LAYOUT[asset]
        src = (TESTD / "assets" / f"{asset}.cutout.png").resolve().as_posix()
        if "h" in L:
            size = f'height:{L["h"]}px;'
            box_h = L["h"]
        else:
            size = f'width:{L["w"]}px;'
            box_h = int(L["w"] * 138 / 370)          # gavel aspect
        # OUTER: static placement, never animated. INNER: what GSAP tweens.
        html.append(
            f'<div id="{SID}-{asset}-pos" style="position:absolute;left:{L["cx"]}px;top:{L["cy"]}px;">'
            f'<div id="{SID}-{asset}-in" style="position:absolute;left:0;top:0;'
            f'transform:translate(-50%,-50%);opacity:0;">'
            # contact ellipse — a background gradient, NOT a filter/box-shadow
            f'<div id="{SID}-{asset}-sh" style="position:absolute;left:50%;top:{box_h//2 + 6}px;'
            f'width:{int(box_h*1.02)}px;height:{max(14,int(box_h*0.15))}px;'
            f'transform:translate(-50%,-50%);opacity:0;border-radius:50%;'
            f'background:radial-gradient(closest-side,var(--text) 0%,transparent 72%);"></div>'
            f'<img src="{src}" style="display:block;{size}">'
            f'</div></div>'
        )
        t = a["start"]
        dx, dy = FROM[L["enter"]]
        tl.append(
            f'tl.fromTo("#{SID}-{asset}-in",'
            f'{{opacity:0,x:{dx},y:{dy},scale:.9,rotation:{L["rot"]}}},'
            f'{{opacity:1,x:0,y:0,scale:1,rotation:0,duration:.55,ease:"power3.out"}},{t:.2f});'
        )
        tl.append(
            f'tl.fromTo("#{SID}-{asset}-sh",{{opacity:0,scaleX:.55}},'
            f'{{opacity:.30,scaleX:1,duration:.7,ease:"power2.out"}},{t + 0.06:.2f});'
        )

    html.append("</div></div>")

    tl.insert(0, f'tl.fromTo("#{SID}-kicker",{{opacity:0,y:10}},'
                 f'{{opacity:1,y:0,duration:.6,ease:"power2.out"}},0.55);')
    tl.insert(1, f'tl.fromTo("#{SID}-horizon",{{opacity:0,scaleX:.4}},'
                 f'{{opacity:.22,scaleX:1,duration:1.1,ease:"power2.out"}},0.35);')
    tl.append(f'tl.fromTo("#{SID}-cam",{{scale:1}},'
              f'{{scale:1.035,duration:{dur:.2f},ease:"none"}},0);')

    return {"id": SID, "type": "raw", "start": 0, "dur": dur,
            "data": {"html": html, "tl": tl}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", default="highlighter-editorial")
    args = ap.parse_args()

    narration = json.loads((TESTD / "narration.json").read_text(encoding="utf-8"))
    scene = build(narration)

    # Gate FIRST — a bespoke scene that cannot clear author.py is not a submission.
    sys.path.insert(0, str(BRIDGE))
    import author  # noqa: E402
    errs = author._raw_seek_errors("testD", SID, scene["data"])
    print(f"seek-safety gate: {'PASS' if not errs else 'FAIL'}")
    for e in errs:
        print("  " + e)
    if errs:
        return 1

    import compose  # noqa: E402
    fid = "testD-bespoke"
    html = compose.compose_frame(fid, scene["dur"], [scene], theme=args.theme)
    out = TESTD / f"{fid}.html"
    out.write_text(html, encoding="utf-8")
    print(f"composed {out.name} ({len(html)} bytes)")

    r = subprocess.run(
        ["node", str(HERE / "verdict.mjs"), str(out), fid,
         str(TESTD / "narration.json"), str(TESTD / "bespoke.verdict.json")],
        cwd=str(HERE), text=True,
    )
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
