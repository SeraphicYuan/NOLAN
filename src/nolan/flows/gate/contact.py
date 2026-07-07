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

CHK = RS / "remotion-lib" / "output" / "chk"

# Full-bleed media blocks: bright pixels at the frame edge are the IMAGE, not
# escaping text — the overflow heuristic skips these.
_MEDIA_BLOCKS = {"ArtworkStage", "PhotoMontage", "PhotoGrid", "Flashback",
                 "ImageCompare", "PaperFigure", "DetailLoupe", "LottieIcon",
                 "RouteMap",
                 # render story v2: full-bleed video/imagery steps — footage
                 # bright at an edge is the SHOT, not escaping text
                 "Video", "StatOver", "SplitScreen", "AnnotateOverVideo",
                 "PhotoMontagePro", "PhotoGridPro"}

# Text/graphic steps: the overflow heuristic APPLIES (bright pixels at the
# frame edge really are escaping content). Every Chapter-hostable step name
# must appear in exactly one of these two sets — enforced by
# tests/test_step_classification.py, so a new block/comp cannot ship
# unclassified (the Video-flagged-as-overflow lesson).
_TEXT_BLOCKS = {
    "ArchetypeCards", "BarChart", "ChapterCard", "ComparisonVS", "DataTable",
    "Distribution", "Formula", "Heatmap", "HeroStatement", "KineticHeadline",
    "LineChart", "ListReveal", "LocationStamp", "LoopDiagram", "LowerThird",
    "NewsHeadline", "PercentBar", "PieCallout", "ProgressBar", "PullQuote",
    "QuestionCard", "Ranking", "SourceCitation", "StatCount", "StepFlow",
    "Timeline", "TweetCard", "UnlockGrid", "ValueLadder", "VerdictCard",
    "WebVsBoxes",
    # text-led motion comps (theme-background typography/annotation)
    "Kinetic", "BarCompare", "KShape", "AnnotateStat", "PremiumCard",
    "TimelinePro",
}


def _edge_overflow(png_path, band_frac: float = 0.012, contrast: int = 70,
                   density: float = 0.004) -> str:
    """'left'/'right' if glyphs (pixels CONTRASTING the background) crowd an
    outer edge band, else ''.

    Text never legitimately touches the outer ~1% of the frame — content
    there escaped its slot (tick labels piling through the right edge). The
    original heuristic used ABSOLUTE brightness (>170), which assumed dark
    themes: kraft-paper's bright paper background flagged every clean card
    (the Homer test's 8 false positives). Now the background level is
    estimated from the frame's corner patches and overflow means glyph-like
    CONTRAST against it — theme-polarity-independent.
    """
    from PIL import Image
    import numpy as np
    img = np.asarray(Image.open(png_path).convert("L")).astype(np.int16)
    h, w = img.shape
    band = max(4, int(w * band_frac))
    pad = max(8, int(min(h, w) * 0.03))
    corners = np.concatenate([img[:pad, :pad].ravel(), img[:pad, -pad:].ravel(),
                              img[-pad:, :pad].ravel(), img[-pad:, -pad:].ravel()])
    bg = float(np.median(corners))
    for side, sl in (("left", img[:, :band]), ("right", img[:, w - band:])):
        if (np.abs(sl - bg) > contrast).mean() > density:
            return side
    return ""


def contact(job_path, fracs=(0.55, 0.92), sheet_name=None, overflow=False):
    """Render diagnostic stills + a contact sheet. Returns (flags:list, sheet_path).

    flags entries: (beat, block, frame, pblack:int) for empty/near-black
    beats, plus — when ``overflow=True`` — (beat, block, frame,
    "overflow-left/right") for text escaping the frame on non-media blocks.
    """
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

    r = subprocess.run([NODE, "remotion-lib/still.mjs", _win(job_path),
                        _win(samples_path), "remotion-lib/output/chk"],
                       cwd=str(RS), capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise RuntimeError("still render failed")

    empties, cells = [], []
    for idx, beat, block, f, frame in legend:
        bf = subprocess.run([str(FFMPEG), "-i", f"remotion-lib/output/chk/sheet_{idx:03d}.png",
                            "-vf", "blackframe=amount=0:threshold=32", "-f", "null", "-"],
                           cwd=str(RS), capture_output=True, text=True)
        m = re.search(r"pblack:(\d+)", bf.stderr)
        pblack = int(m.group(1)) if m else 0
        empty = pblack >= 98
        if empty:
            empties.append((beat, block, frame, pblack))
        over = ""
        if overflow and not empty and block not in _MEDIA_BLOCKS:
            try:
                over = _edge_overflow(CHK / f"sheet_{idx:03d}.png")
            except Exception:
                over = ""
            if over:
                empties.append((beat, block, frame, f"overflow-{over}"))
        cells.append({"file": f"sheet_{idx:03d}.png", "empty": empty or bool(over),
                      "label": f"b{beat} {block} {int(f*100)}% f{frame}"})
        flag = "EMPTY" if empty else (f"OVER-{over[:1].upper()}" if over else "ok")
        print(f" {flag:<6} beat {beat:<2} {block:<14} frac {f:>4}  frame {frame:>6}  pblack={pblack:>3}%")

    sheet = RS / "remotion-lib" / "output" / sheet_name
    build_sheet({"base": str(CHK), "out": str(sheet), "cols": len(fracs), "rows": len(steps),
                 "cellw": 640, "cells": cells})

    print("-" * 78)
    print(f"sheet -> render-service/remotion-lib/output/{sheet_name}   (grid {len(fracs)}×{len(steps)})")
    for beat, block, frame, pb in empties:
        what = f"{pb}% black" if isinstance(pb, int) else str(pb)
        print(f" [FLAG] beat {beat} {block} @ frame {frame}: {what}")
    print(f"{len(empties)} empty/near-black beat(s)")
    return empties, sheet
