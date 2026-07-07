# -*- coding: utf-8 -*-
"""Motif accumulation probe — render THREE visits to one timeline motif and
one route-map motif through the REAL pipeline path (validate → resolve →
chapter_step_for_spec → Chapter render), then extract frames to LOOK at:
visit N must show visits 1..N-1 settled and only its own delta animating.

Run:  python -X utf8 scripts/bench_motifs.py
Out:  render-service/remotion-lib/output/bench_motifs.mp4 + D:/tmp/refframes/motif_*.png
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from nolan.flows.base import render_chapter  # noqa: E402
from nolan.motion import chapter_step_for_spec  # noqa: E402
from nolan.motion.motifs import resolve_plan_motifs, validate_plan_motifs  # noqa: E402

FPS, STEP = 30, 150

PLAN = {
    "schema_version": 2,
    "motifs": [
        {"id": "eras", "effect": "timeline",
         "base": {"title": "Greek memory", "start": -800, "end": 1600,
                  "eras": [{"label": "Archaic", "from": -800, "to": -480},
                           {"label": "Classical", "from": -480, "to": -323},
                           {"label": "Transmission", "from": -323, "to": 1450}]}},
        {"id": "voyage", "effect": "route-map",
         "base": {"title": "The long way home",
                  "pins": [{"x": 0.2, "y": 0.38, "label": "Troy"}]}},
    ],
    "sections": {"probe": [
        {"id": "t1", "motif": {"id": "eras", "delta": {
            "markers": [{"year": -750, "label": "Homer composes"}],
            "focus": {"from": -800, "to": -600}}}},
        {"id": "t2", "motif": {"id": "eras", "delta": {
            "markers": [{"year": -280, "label": "Alexandria edits"}],
            "focus": {"from": -480, "to": -100}}}},
        {"id": "t3", "motif": {"id": "eras", "delta": {
            "markers": [{"year": 1488, "label": "First printed edition"}]}}},
        {"id": "r1", "motif": {"id": "voyage", "delta": {
            "pins": [{"x": 0.52, "y": 0.62, "label": "Aeaea"}]}}},
        {"id": "r2", "motif": {"id": "voyage", "delta": {
            "pins": [{"x": 0.82, "y": 0.3, "label": "Ithaca"}]}}},
    ]},
}


def main():
    errors = validate_plan_motifs(PLAN)
    assert not errors, errors
    n = resolve_plan_motifs(PLAN)
    print(f"materialized {n} motif scene(s)")
    steps = []
    for s in PLAN["sections"]["probe"]:
        block, props = chapter_step_for_spec(s["motion_spec"], REPO)
        steps.append({"block": block, "props": props, "revealFrames": [0],
                      "words": [], "durationInFrames": STEP})
        print(f"  {s['id']}: {block} "
              f"({sum(1 for m in (props.get('markers') or props.get('pins') or []) if m.get('isNew'))} new)")

    job = {"out": "bench_motifs.mp4", "theme": "vintage-editorial", "fps": FPS,
           "captions": False, "scale": 0.5, "props": {"steps": steps}}
    jp = REPO / "render-service" / "remotion-lib" / "output" / "bench_motifs_job.json"
    jp.write_text(json.dumps(job, indent=1), encoding="utf-8")
    mp4 = render_chapter(jp)
    print("rendered", mp4)

    ff = Path(r"D:\env\nolan\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe")
    out = Path(r"D:\tmp\refframes")
    ids = [s["id"] for s in PLAN["sections"]["probe"]]
    for i, sid in enumerate(ids):
        for tag, off in (("mid", STEP // 2), ("end", STEP - 8)):
            fr = i * STEP + off
            r = subprocess.run([str(ff), "-y", "-i", str(mp4),
                                "-vf", f"select=eq(n\\,{fr})", "-frames:v", "1",
                                "-update", "1", str(out / f"motif_{sid}_{tag}.png")],
                               capture_output=True)
            if r.returncode != 0:
                print(f"!! frame extract failed for {sid}_{tag}")
    print("frames in", out)


if __name__ == "__main__":
    main()
