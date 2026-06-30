"""Tier-1 spatial pre-flight — one still per beat, NOT the whole video. In-process port of
the former web-video-lab/art_contact.py.

Renders 2 stills/beat (at ~55% and ~92% of each beat) via still.mjs, assembles a labeled
contact sheet (Pillow, in-process), and auto-flags any near-black / empty beat (ffmpeg
blackframe). Catches clipped/off-frame/dead-beat defects at ~1% of a full render's cost.
Node (still.mjs) + ffmpeg stay subprocess (external runtimes).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from ..base import FFMPEG, NODE, RS, _win
from .montage import build_sheet

CHK = RS / "_lab_chapter" / "output" / "chk"


def contact(job_path, fracs=(0.55, 0.92), sheet_name=None):
    """Render diagnostic stills + a contact sheet. Returns (empties:list, sheet_path)."""
    job_path = Path(job_path)
    sheet_name = sheet_name or (job_path.stem.replace(".job", "") + ".contact.png")
    job = json.loads(job_path.read_text(encoding="utf-8"))
    steps = job.get("props", {}).get("steps", [])

    CHK.mkdir(parents=True, exist_ok=True)
    samples, legend, offset = [], [], 0
    for i, s in enumerate(steps):
        dur = int(s.get("durationInFrames", 1))
        block = s.get("block", "?")
        for f in fracs:
            idx = len(samples)
            frame = offset + min(dur - 1, round(f * dur))
            samples.append({"frame": frame, "out": f"sheet_{idx:03d}.png"})
            legend.append((idx, i, block, f, frame))
        offset += dur

    samples_path = CHK / "_samples.json"
    samples_path.write_text(json.dumps(samples), encoding="utf-8")

    print(f"CONTACT · {job_path.name} · {len(steps)} beats × {len(fracs)} = {len(samples)} stills")
    print("-" * 78)

    r = subprocess.run([NODE, "_lab_chapter/still.mjs", _win(job_path),
                        _win(samples_path), "_lab_chapter/output/chk"],
                       cwd=str(RS), capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise RuntimeError("still render failed")

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

    sheet = RS / "_lab_chapter" / "output" / sheet_name
    build_sheet({"base": str(CHK), "out": str(sheet), "cols": len(fracs), "rows": len(steps),
                 "cellw": 640, "cells": cells})

    print("-" * 78)
    print(f"sheet -> render-service/_lab_chapter/output/{sheet_name}   (grid {len(fracs)}×{len(steps)})")
    for beat, block, frame, pb in empties:
        print(f" [EMPTY] beat {beat} {block} @ frame {frame} is {pb}% black")
    print(f"{len(empties)} empty/near-black beat(s)")
    return empties, sheet
