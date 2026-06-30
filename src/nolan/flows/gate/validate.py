"""Tier-0 static validation of a render job — no render, ~1s. In-process port of the
former web-video-lab/art_validate.py.

Per beat: every image/audio path resolves, block name is real (library or raw), focus/region
rects sit in the 0..1 frame, reveal frames in range + count meets the block's minimum, and the
block sits in the flow's palette (soft warn — RAW allowed-but-flagged, shared set exempt).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from ..base import ROOT

BLOCKS = ROOT / "render-service" / "remotion-lib" / "src" / "blocks"
LIB_INDEX = BLOCKS / "library" / "index.ts"
RAW_DIR = BLOCKS / "raw"
REGISTRY = ROOT / "web-video-lab" / "flows" / "registry.json"

# Minimum reveal slots a block needs to read correctly.
MIN_REVEALS = {"ImageCompare": 2, "DetailLoupe": 2, "ComparisonVS": 2}
IMG_RE = re.compile(r"\.(jpe?g|png|webp|gif|avif)$", re.I)


def win2posix(p: str) -> str:
    """Localize a path to the running interpreter so it can be stat'd — WSL python3
    (/mnt/d/...) or the nolan Windows python that serves the WebUI/CLI (D:/...)."""
    p = str(p)
    if os.name == "nt":
        m = re.match(r"^/mnt/([a-z])/(.*)$", p)
        return f"{m.group(1).upper()}:/" + m.group(2) if m else p
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", p)
    return f"/mnt/{m.group(1).lower()}/" + m.group(2).replace("\\", "/") if m else p


def _known_blocks() -> set:
    """Block names = keys of `LIBRARY = { ... }` in index.ts (exports, not filenames)."""
    if not LIB_INDEX.exists():
        return set()
    m = re.search(r"export const LIBRARY\s*=\s*\{([^}]*)\}", LIB_INDEX.read_text(encoding="utf-8"))
    return {t.strip().split(":")[0].strip() for t in m.group(1).split(",") if t.strip()} if m else set()


def _raw_blocks() -> set:
    return {f.stem for f in RAW_DIR.glob("*.tsx")} if RAW_DIR.exists() else set()


def _flow_palette(flow_id):
    """(blessed LIBRARY subset for this flow, shared-common set), or (None, common) if unknown."""
    common = set()
    try:
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
        common = set(reg.get("common_palette", []))
        t = next((t for t in reg.get("types", []) if t["id"] == flow_id), None)
        return (set(t["palette"]) if t else None), common
    except Exception:
        return None, common


def _rects(props: dict):
    for f in props.get("focuses", []) or []:
        if all(k in f for k in "xywh"):
            yield f.get("caption") or f.get("word") or "focus", f
    r = props.get("region")
    if isinstance(r, dict) and all(k in r for k in "xywh"):
        yield "region", r


def _images(obj):
    if isinstance(obj, str) and IMG_RE.search(obj):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _images(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _images(v)


def validate(job_path, flow_id=None):
    """Validate a job. Returns (errors:list, warnings:list); prints a per-beat table."""
    job_path = Path(job_path)
    job = json.loads(job_path.read_text(encoding="utf-8"))
    steps = job.get("props", {}).get("steps", [])
    known = _known_blocks()
    raw = _raw_blocks()
    palette, common = _flow_palette(flow_id) if flow_id else (None, set())
    errs, warns = [], []

    hdr = f"VALIDATE · {job_path.name} · {len(steps)} beats"
    if flow_id:
        hdr += f" · flow={flow_id}" + ("" if palette is not None else " (unknown flow — palette check skipped)")
    print(hdr)
    print("-" * 78)
    for i, s in enumerate(steps):
        tag = f"beat {i} [{s.get('block', '?')}]"
        block = s.get("block", "")
        dur = int(s.get("durationInFrames", 0))
        props = s.get("props", {}) or {}

        if known and block not in known and block not in raw:
            errs.append(f"{tag}: unknown block '{block}' (not in library/ or raw/)")
        elif palette is not None and block not in palette and block not in common:
            if block in raw:
                warns.append(f"{tag}: '{block}' is a bespoke RAW block (not cataloged)")
            else:
                warns.append(f"{tag}: '{block}' is outside the '{flow_id}' palette (intentional?)")

        for img in _images(props):
            if not Path(win2posix(img)).exists():
                errs.append(f"{tag}: image not found -> {img}")

        au = s.get("audioSrc")
        if au and not Path(win2posix(au)).exists():
            errs.append(f"{tag}: audio not found -> {au}")

        for name, r in _rects(props):
            x, y, w, h = (r.get(k, 0) for k in "xywh")
            if w <= 0 or h <= 0:
                errs.append(f"{tag}: rect '{name}' has non-positive w/h ({w}x{h})")
            if x < 0 or y < 0 or x + w > 1.001 or y + h > 1.001:
                errs.append(f"{tag}: rect '{name}' out of frame (x{x} y{y} w{w} h{h})")

        reveals = s.get("revealFrames", []) or []
        for rf in reveals:
            if rf < 0 or (dur and rf >= dur):
                warns.append(f"{tag}: reveal frame {rf} outside [0,{dur})")
        need = MIN_REVEALS.get(block)
        if need and len(reveals) < need:
            errs.append(f"{tag}: {block} needs >={need} reveal slots, got {len(reveals)}")

        flag = "OK " if not any(tag in e for e in errs) else "ERR"
        print(f" {flag} beat {i:<2} {block:<14} {dur:>5}f  imgs={sum(1 for _ in _images(props))}  reveals={len(reveals)}")

    print("-" * 78)
    for w in warns:
        print(f" [warn] {w}")
    for e in errs:
        print(f" [ERR]  {e}")
    print(f"{len(errs)} error(s), {len(warns)} warning(s)")
    return errs, warns


def show_palette(flow_id: str) -> int:
    """Authoring aid: print the blocks to reach for in a flow (+ shared + bespoke policy)."""
    palette, common = _flow_palette(flow_id)
    if palette is None:
        print(f"unknown flow '{flow_id}'"); return 1
    raw = sorted(_raw_blocks())
    print(f"PALETTE · flow={flow_id}\n" + "-" * 60)
    print("reach for (blessed):  " + ", ".join(sorted(palette - common)))
    print("shared (any flow):    " + ", ".join(sorted(common)))
    print("bespoke (RAW, allowed but flagged): " + (", ".join(raw) or "—"))
    return 0
