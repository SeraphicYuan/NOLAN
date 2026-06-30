"""Tier-1 spatial pre-flight — one still per beat, NOT the whole video.

Renders a handful of diagnostic stills (default 2 per beat, at ~55% and ~92% of each
beat's duration, where it's "fullest") via renderStill, assembles them into a single
contact sheet, and auto-flags any near-black / empty beat. This catches the spatial
class of defects (clipped/off-frame content, single-panel compare, dead beat) at ~1%
of the cost of a full render — the whole sheet is ~seconds.

Runs entirely on WSL python3 + the Windows node/ffmpeg already used by render.mjs.

Usage: python art_contact.py <job.json> [--fracs 0.55,0.92] [--out <name>.contact.png]
Exit 0 = no empty beats; 1 = an empty/near-black beat was flagged.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RS = HERE.parent / "render-service"                       # cwd for node + ffmpeg
_NT = os.name == "nt"
NODE = "C:/Program Files/nodejs/node.exe" if _NT else "/mnt/c/Program Files/nodejs/node.exe"
NOLAN_PY = "D:/env/nolan/python.exe" if _NT else "/mnt/d/env/nolan/python.exe"  # has Pillow
FFMPEG = RS / "node_modules/@remotion/compositor-win32-x64-msvc/ffmpeg.exe"
CHK = RS / "_lab_chapter" / "output" / "chk"


def posix2win(p) -> str:
    p = str(Path(p).resolve())
    m = re.match(r"^/mnt/([a-z])/(.*)$", p)
    return f"{m.group(1).upper()}:/" + m.group(2) if m else p


def _arg(s: str) -> str:
    i = s.find("=")
    return s[i + 1:] if i >= 0 else ""


def main() -> int:
    args = sys.argv[1:]
    job_path = Path(args[0])
    fracs = [float(x) for x in (next((_arg(a) for a in args if a.startswith("--fracs")), "0.55,0.92")).split(",")]
    sheet_name = next((_arg(a) for a in args if a.startswith("--out")), job_path.stem.replace(".job", "") + ".contact.png")

    job = json.loads(job_path.read_text(encoding="utf-8"))
    steps = job.get("props", {}).get("steps", [])

    # build the sample list: for each beat, a still at each fraction of its duration
    CHK.mkdir(parents=True, exist_ok=True)
    samples, legend, offset = [], [], 0
    for i, s in enumerate(steps):
        dur = int(s.get("durationInFrames", 1))
        block = s.get("block", "?")
        for f in fracs:
            idx = len(samples)
            frame = offset + min(dur - 1, round(f * dur))
            out = f"sheet_{idx:03d}.png"
            samples.append({"frame": frame, "out": out})
            legend.append((idx, i, block, f, frame))
        offset += dur

    samples_path = CHK / "_samples.json"               # intermediate, kept out of art/
    samples_path.write_text(json.dumps(samples), encoding="utf-8")

    print(f"CONTACT · {job_path.name} · {len(steps)} beats × {len(fracs)} = {len(samples)} stills")
    print("─" * 78)

    # render the stills (bundle+select once, renderStill per frame)
    r = subprocess.run([NODE, "_lab_chapter/still.mjs", posix2win(job_path),
                        posix2win(samples_path), "_lab_chapter/output/chk"],
                       cwd=str(RS), capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        print("[ERR] still render failed")
        return 1

    # auto-check each still for near-black / empty (the dead-beat class) via blackframe
    empties, cells = [], []
    for idx, beat, block, f, frame in legend:
        bf = subprocess.run([str(FFMPEG), "-i", f"_lab_chapter/output/chk/sheet_{idx:03d}.png",
                            "-vf", "blackframe=amount=0:threshold=32", "-f", "null", "-"],
                           cwd=str(RS), capture_output=True, text=True)
        m = re.search(r"pblack:(\d+)", bf.stderr)
        pblack = int(m.group(1)) if m else 0
        empty = pblack >= 98
        if empty:
            empties.append((beat, block, frame, pblack))
        cells.append({"file": f"sheet_{idx:03d}.png", "empty": empty,
                      "label": f"b{beat} {block} {int(f*100)}% f{frame}"})
        print(f" {'EMPTY' if empty else 'ok':<5} beat {beat:<2} {block:<14} frac {f:>4}  frame {frame:>6}  pblack={pblack:>3}%")

    # assemble one labeled contact sheet via the nolan-env python (has Pillow)
    spec_path = CHK / "_montage.json"
    spec_path.write_text(json.dumps({
        "base": posix2win(CHK), "out": posix2win(RS / "_lab_chapter" / "output" / sheet_name),
        "cols": len(fracs), "rows": len(steps), "cellw": 640, "cells": cells}), encoding="utf-8")
    mz = subprocess.run([NOLAN_PY, posix2win(HERE / "_montage.py"), posix2win(spec_path)],
                        capture_output=True, text=True)
    print(mz.stdout.strip() or mz.stderr.strip()[-400:])

    print("─" * 78)
    print(f"sheet -> render-service/_lab_chapter/output/{sheet_name}   (grid {len(fracs)}×{len(steps)})")
    for beat, block, frame, pb in empties:
        print(f" [EMPTY] beat {beat} {block} @ frame {frame} is {pb}% black")
    print(f"{len(empties)} empty/near-black beat(s)")
    return 1 if empties else 0


if __name__ == "__main__":
    sys.exit(main())
