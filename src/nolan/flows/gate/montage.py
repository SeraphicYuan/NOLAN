"""Assemble per-beat stills into one LABELED contact sheet (Pillow). In-process port of the
former web-video-lab/_montage.py — now a function call (no subprocess, no 2nd interpreter),
since the canonical interpreter (nolan env python) has Pillow.

spec = {"base": "<dir with sheet_NNN.png>", "out": "<png path>", "cols": N, "rows": M,
        "cellw": 640, "cells": [{"file": "sheet_000.png", "label": "...", "empty": bool}, ...]}
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def build_sheet(spec: dict) -> Path:
    base = Path(spec["base"])
    cells = spec["cells"]
    cols, rows = spec["cols"], spec["rows"]
    cw = spec.get("cellw", 640)
    bar, pad = 28, 8

    ims = [Image.open(base / c["file"]).convert("RGB") for c in cells]
    ch = int(cw * ims[0].height / ims[0].width)
    W = pad + cols * (cw + pad)
    H = pad + rows * (ch + bar + pad)
    sheet = Image.new("RGB", (W, H), (20, 18, 16))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        font = ImageFont.load_default()

    for i, (im, c) in enumerate(zip(ims, cells)):
        r, cc = divmod(i, cols)
        x = pad + cc * (cw + pad)
        y = pad + r * (ch + bar + pad)
        sheet.paste(im.resize((cw, ch)), (x, y + bar))
        draw.rectangle([x, y, x + cw, y + bar], fill=(200, 60, 50) if c.get("empty") else (40, 38, 34))
        draw.text((x + 6, y + 6), c["label"] + (" — EMPTY" if c.get("empty") else ""),
                  fill=(240, 235, 225), font=font)

    out = Path(spec["out"])
    sheet.save(out)
    print(f"montage -> {out}  {W}x{H}")
    return out
