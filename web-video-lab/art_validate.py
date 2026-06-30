"""Tier-0 static validation of a render job — no render, runs in ~1s.

The cheapest gate: catches the errors that are most expensive to discover at minute 7
of a full render (or never, if the bad beat isn't sampled). Operates purely on the job
JSON + the block library on disk. Pairs with pacing_lint.py (temporal) and art_contact.py
(spatial); orchestrated by art_check.py.

Checks per beat:
  - every image path (recursively) resolves on disk
  - every audio path resolves
  - block name is a real block in the library
  - focus / region rectangles sit within the 0..1 frame (x+w<=1, y+h<=1, w,h>0)
  - revealFrames are within [0, durationInFrames) and the count meets the block's minimum

Usage: python art_validate.py <job.json>     (exit 0 = clean, 1 = errors)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BLOCKS = HERE.parent / "render-service" / "_lab_chapter" / "src" / "blocks"
LIB_INDEX = BLOCKS / "library" / "index.ts"
RAW_DIR = BLOCKS / "raw"
REGISTRY = HERE / "flows" / "registry.json"

# Minimum reveal slots a block needs to read correctly (None = any / focus-driven).
MIN_REVEALS = {
    "ImageCompare": 2,   # left + right (verdict optional)
    "DetailLoupe": 2,    # whole + loupe
    "ComparisonVS": 2,
}
IMG_RE = re.compile(r"\.(jpe?g|png|webp|gif|avif)$", re.I)


def win2posix(p: str) -> str:
    """D:/foo/bar or D:\\foo\\bar -> /mnt/d/foo/bar so WSL can stat it."""
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", str(p))
    return f"/mnt/{m.group(1).lower()}/" + m.group(2).replace("\\", "/") if m else str(p)


def _known_blocks() -> set[str]:
    """Block names are the keys of the `LIBRARY = { ... }` registry in index.ts
    (exports, not filenames — e.g. EndCard ships from ChapterCard.tsx)."""
    if not LIB_INDEX.exists():
        return set()
    m = re.search(r"export const LIBRARY\s*=\s*\{([^}]*)\}", LIB_INDEX.read_text(encoding="utf-8"))
    return {t.strip().split(":")[0].strip() for t in m.group(1).split(",") if t.strip()} if m else set()


def _raw_blocks() -> set[str]:
    """Bespoke one-off blocks (blocks/raw/*.tsx) — allowed in any flow but flagged."""
    return {f.stem for f in RAW_DIR.glob("*.tsx")} if RAW_DIR.exists() else set()


def _flow_palette(flow_id: str):
    """(blessed LIBRARY subset for this flow, shared-common set) from registry.json,
    or (None, common) if the flow id is unknown."""
    common = set()
    try:
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
        common = set(reg.get("common_palette", []))
        t = next((t for t in reg.get("types", []) if t["id"] == flow_id), None)
        return (set(t["palette"]) if t else None), common
    except Exception:
        return None, common


def _rects(props: dict):
    """Yield every (name, rect) with x/y/w/h fractions anywhere in props."""
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


def validate(job_path: Path, flow_id: str | None = None) -> int:
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
    print("─" * 78)
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

    print("─" * 78)
    for w in warns:
        print(f" [warn] {w}")
    for e in errs:
        print(f" [ERR]  {e}")
    print(f"{len(errs)} error(s), {len(warns)} warning(s)")
    return 1 if errs else 0


def show_palette(flow_id: str) -> int:
    """Authoring aid: print the blocks to reach for in a flow (+ shared + bespoke policy)."""
    palette, common = _flow_palette(flow_id)
    if palette is None:
        print(f"unknown flow '{flow_id}'"); return 1
    raw = sorted(_raw_blocks())
    print(f"PALETTE · flow={flow_id}\n" + "─" * 60)
    print("reach for (blessed):  " + ", ".join(sorted(palette - common)))
    print("shared (any flow):    " + ", ".join(sorted(common)))
    print("bespoke (RAW, allowed but flagged): " + (", ".join(raw) or "—"))
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("job", nargs="?")
    ap.add_argument("--flow", default=None, help="flow id in flows/registry.json (enables palette check)")
    ap.add_argument("--show-palette", metavar="FLOW", default=None, help="print a flow's palette and exit")
    a = ap.parse_args()
    if a.show_palette:
        sys.exit(show_palette(a.show_palette))
    sys.exit(validate(Path(a.job), a.flow))
