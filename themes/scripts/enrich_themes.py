#!/usr/bin/env python3
"""Enrich each theme.json with authoring-facing metadata, derived from data
that already exists (no hand-duplication, no drift):

  • `fonts`    — primary display/body/cjk/mono families, parsed from the
                 theme's own tokens.css (tokens.css stays source of truth).
  • `avoidFor` — anti-pattern tags, promoted from themes/selector.json so the
                 chapter agent sees "do NOT use this theme for X" at authoring
                 time without having to open the selector.

Idempotent: re-running just refreshes the two derived keys. Run after adding a
theme or changing its fonts/avoid.

    python enrich_themes.py            # write
    python enrich_themes.py --check    # report drift, write nothing (exit 1 if stale)
"""

import argparse
import json
import re
import sys
from pathlib import Path

THEMES_DIR = Path(__file__).resolve().parent.parent  # themes/
SELECTOR = THEMES_DIR / "selector.json"

FONT_KEYS = {
    "displayEn": "--font-display-en",
    "body": "--font-body",
    "cjk": "--font-display-cn",
    "mono": "--font-mono",
}


def primary_family(css, var):
    m = re.search(re.escape(var) + r"\s*:\s*([^;]+);", css)
    if not m:
        return None
    first = m.group(1).split(",")[0].strip()
    return first.strip('"').strip("'")


def derive(tid, css, selector):
    fonts = {k: primary_family(css, v) for k, v in FONT_KEYS.items()}
    fonts = {k: v for k, v in fonts.items() if v}
    avoid = selector["themes"].get(tid, {}).get("avoid", [])
    return fonts, list(avoid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report drift only, exit 1 if stale")
    args = ap.parse_args()

    selector = json.loads(SELECTOR.read_text(encoding="utf-8"))
    stale, written = [], []
    for tj in sorted(THEMES_DIR.glob("*/theme.json")):
        tid = tj.parent.name
        css = (tj.parent / "tokens.css").read_text(encoding="utf-8")
        fonts, avoid = derive(tid, css, selector)
        d = json.loads(tj.read_text(encoding="utf-8"))
        want = {"fonts": fonts, "avoidFor": avoid}
        if {k: d.get(k) for k in want} == want:
            continue
        if args.check:
            stale.append(tid)
            continue
        d["fonts"] = fonts
        d["avoidFor"] = avoid
        tj.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(tid)

    if args.check:
        if stale:
            print(f"[stale] {len(stale)} theme.json need re-enrich: {stale}", file=sys.stderr)
            sys.exit(1)
        print("[ok] all theme.json enrichment up to date")
    else:
        print(f"enriched {len(written)} theme.json" + (f": {written}" if written else " (all already current)"))


if __name__ == "__main__":
    main()
