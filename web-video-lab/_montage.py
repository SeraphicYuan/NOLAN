"""Assemble per-beat stills into one LABELED contact sheet (PIL).

Run with the nolan env python (D:\\env\\nolan\\python.exe) — it has Pillow, which the
bare WSL python3 does not. Invoked by art_contact.py; not meant to be run by hand.

Arg: <spec.json> = {
  "base": "<dir with sheet_NNN.png>", "out": "<png path>", "cols": N, "rows": M,
  "cellw": 640, "cells": [{"file": "sheet_000.png", "label": "...", "empty": bool}, ...]
}
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
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
    draw.text((x + 6, y + 6), c["label"] + (" — EMPTY" if c.get("empty") else ""), fill=(240, 235, 225), font=font)

sheet.save(spec["out"])
print(f"montage -> {spec['out']}  {W}x{H}")
