#!/usr/bin/env python3
"""Theme-system health check. Guards the invariants that keep selection +
rendering working as themes are added. Exit 1 on any failure.

Checks per theme dir under themes/:
  1. has both theme.json and tokens.css
  2. theme.json has required keys + a 4-key preview with valid #hex
  3. has a selector.json entry (and no orphan selector entries point nowhere)
  4. selector `tone` (light/dark) agrees with theme.json `mood`
  5. enrichment (fonts/avoidFor) is present and current (delegates to enrich_themes --check)

    python validate_themes.py
"""

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
THEMES_DIR = HERE.parent / "themes"
SELECTOR = THEMES_DIR / "selector.json"
REQUIRED = {"id", "name", "nameZh", "description", "mood", "bestFor", "preview"}
PREVIEW_KEYS = {"shell", "surface", "text", "accent"}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

errors = []


def err(tid, msg):
    errors.append(f"  [{tid}] {msg}")


def main():
    selector = json.loads(SELECTOR.read_text(encoding="utf-8"))
    sel_themes = set(selector["themes"])
    disk = {p.name for p in THEMES_DIR.iterdir() if p.is_dir()}

    for orphan in sel_themes - disk:
        err(orphan, "selector entry has no theme dir on disk")

    for tid in sorted(disk):
        d = THEMES_DIR / tid
        tj, css = d / "theme.json", d / "tokens.css"
        if not tj.exists():
            err(tid, "missing theme.json"); continue
        if not css.exists():
            err(tid, "missing tokens.css")

        meta = json.loads(tj.read_text(encoding="utf-8"))
        missing = REQUIRED - set(meta)
        if missing:
            err(tid, f"theme.json missing keys: {sorted(missing)}")
        prev = meta.get("preview", {})
        if set(prev) != PREVIEW_KEYS:
            err(tid, f"preview keys {set(prev)} != {PREVIEW_KEYS}")
        for k, v in prev.items():
            if not HEX.match(str(v)):
                err(tid, f"preview.{k} not #rrggbb: {v!r}")

        if tid not in sel_themes:
            err(tid, "no selector.json entry"); continue
        tone = selector["themes"][tid].get("tone")
        mood = meta.get("mood", [])
        if tone == "dark" and "light" in mood:
            err(tid, "selector tone=dark but mood says light")
        if tone == "light" and "dark" in mood:
            err(tid, "selector tone=light but mood says dark")

    # enrichment freshness
    r = subprocess.run([sys.executable, str(HERE / "enrich_themes.py"), "--check"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        errors.append("  " + (r.stderr or r.stdout).strip())

    n = len(disk)
    if errors:
        print(f"FAIL — {len(errors)} issue(s) across {n} themes:")
        print("\n".join(errors))
        sys.exit(1)
    print(f"OK — {n} themes valid, all wired into selector + enrichment current")


if __name__ == "__main__":
    main()
