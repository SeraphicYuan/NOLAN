"""HF-pool refine-scope — the human's selection over the acquired HyperFrames pool, wired to the author.

The scored HF pool (`pool.json`) had no selection channel and the shortlist never reached the HF author
(who reads only `capture/extracted/asset-descriptions.md`). This closes that gap the same way key-assets
did: a `selected` flag per pool item (default True — the pool is the scope until pruned), toggled on the
`/pool` HF view, and — crucially — **a re-write of the author's menu filtered to selected**, so a
deselected asset leaves `asset-descriptions.md` and won't be authored in.

`render_inventory_lines` is the SINGLE inventory format, used by BOTH the bridge's acquisition-time write
and the post-curation re-write here, so the two never drift.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional


def render_inventory_lines(pool: list) -> List[str]:
    """The full asset-descriptions.md line list for a pool — only assets with `selected` (default True),
    so the human's refine-scope shapes the author's menu. The one place this format lives."""
    lines = ["# Asset descriptions (NOLAN pool → HyperFrames inventory)\n",
             "Candidate assets collected by the NOLAN acquisition fan-out. The storyboard step",
             "SELECTS from these into per-frame `asset_candidates` — HyperFrames keeps selection.\n"]
    for it in pool:
        if not it.get("selected", True):                     # refine-scope: excluded → leaves the menu
            continue
        f = it.get("file")
        if not f:
            continue
        tag = " [video]" if it.get("media_type") == "video" else ""
        cred = f"{it.get('source') or '?'}" + (f" / {it['photographer']}" if it.get("photographer") else "")
        lines.append(f"- `assets/{f}`{tag} — {it.get('caption', '')}  "
                     f"_(need: {it.get('id', '?')}; {cred}; {it.get('license') or 'license?'})_")
    return lines


def write_inventory_from_pool(comp_dir: Path, pool: Optional[list] = None) -> int:
    """Re-write capture/extracted/asset-descriptions.md from pool.json, filtered to selected. Returns
    the count listed. Call after a human toggles selection so the author's menu stays in sync."""
    comp_dir = Path(comp_dir)
    if pool is None:
        pj = comp_dir / "pool.json"
        if not pj.exists():
            return 0
        try:
            pool = json.loads(pj.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return 0
    ex = comp_dir / "capture" / "extracted"
    ex.mkdir(parents=True, exist_ok=True)
    (ex / "asset-descriptions.md").write_text("\n".join(render_inventory_lines(pool)) + "\n", encoding="utf-8")
    return sum(1 for it in pool if it.get("selected", True) and it.get("file"))


def set_pool_selected(comp_dir: Path, file: str, selected: bool) -> bool:
    """Toggle a pool.json item's `selected` (matched by file) AND re-sync the author's menu. Returns
    True if the file matched."""
    comp_dir = Path(comp_dir)
    pj = comp_dir / "pool.json"
    if not pj.exists():
        return False
    try:
        pool = json.loads(pj.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    hit = False
    for it in pool:
        if it.get("file") == file:
            it["selected"] = bool(selected)
            hit = True
    if hit:
        pj.write_text(json.dumps(pool, indent=2), encoding="utf-8")
        write_inventory_from_pool(comp_dir, pool)            # keep asset-descriptions.md in sync
    return hit
