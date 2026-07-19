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
THEMES_DIR = HERE.parent  # themes/
SELECTOR = THEMES_DIR / "selector.json"
ARCHETYPES = THEMES_DIR / "composition" / "archetypes.json"
REQUIRED = {"id", "name", "nameZh", "description", "mood", "bestFor", "preview", "composition"}
PREVIEW_KEYS = {"shell", "surface", "text", "accent"}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# ── eyebrow legibility floor (finding #2) ────────────────────────────────────
# The eyebrow is small tracked uppercase; a theme that points --eyebrow-color at an accent too close to
# its own --shell renders a near-invisible kicker (vellum shipped a dusty teal at 2.2:1 on its navy field).
# WCAG large-text AA is 3:1 — we require the eyebrow colour to clear it against the canvas. Only themes
# that EXPLICITLY set --eyebrow-color are checked; the seed/block default (var(--text-2)) is always legible.
EYEBROW_MIN_CONTRAST = 3.0


def _tokens(css_text):
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r"--([\w-]+)\s*:\s*([^;]+);", css_text)}


def _rgb(val, tokens, bg=None, depth=0):
    """Resolve a CSS colour token to an (r,g,b) triple, following one+ var() levels and compositing
    rgba() over `bg` (an (r,g,b) already-resolved background). Returns None if unparseable."""
    val = (val or "").strip()
    if depth > 6:
        return None
    m = re.match(r"var\(\s*--([\w-]+)\s*(?:,\s*(.+))?\)\s*$", val)
    if m:
        inner = tokens.get(m.group(1))
        if inner is None and m.group(2) is not None:
            inner = m.group(2).strip()
        return _rgb(inner, tokens, bg, depth + 1) if inner is not None else None
    m = re.match(r"#([0-9a-fA-F]{3})$", val)
    if m:
        return tuple(int(c * 2, 16) for c in m.group(1))
    m = re.match(r"#([0-9a-fA-F]{6})$", val)
    if m:
        return tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))
    m = re.match(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+))?\s*\)$", val)
    if m:
        r, g, b = (float(m.group(i)) for i in (1, 2, 3))
        a = float(m.group(4)) if m.group(4) is not None else 1.0
        if a < 1.0 and bg is not None:
            r, g, b = (a * ch + (1 - a) * bg[i] for i, ch in enumerate((r, g, b)))
        return (r, g, b)
    return None


def _contrast(a, b):
    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    def lum(t):
        return 0.2126 * lin(t[0]) + 0.7152 * lin(t[1]) + 0.0722 * lin(t[2])
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)

try:
    ARCHETYPE_IDS = set(json.loads(ARCHETYPES.read_text(encoding="utf-8"))["archetypes"])
except Exception:
    ARCHETYPE_IDS = set()

errors = []


def err(tid, msg):
    errors.append(f"  [{tid}] {msg}")


def main():
    selector = json.loads(SELECTOR.read_text(encoding="utf-8"))
    sel_themes = set(selector["themes"])
    # a theme dir is one that HAS a theme.json (excludes scripts/, etc.)
    disk = {p.name for p in THEMES_DIR.iterdir() if p.is_dir() and (p / "theme.json").exists()}

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

        # composition archetype parity — default + allowed must be real archetypes (no drift vs the registry)
        comp = meta.get("composition")
        if isinstance(comp, dict):
            dft, allowed = comp.get("default"), comp.get("allowed") or []
            if dft not in ARCHETYPE_IDS:
                err(tid, f"composition.default {dft!r} not in the archetype registry {sorted(ARCHETYPE_IDS)}")
            for a in allowed:
                if a not in ARCHETYPE_IDS:
                    err(tid, f"composition.allowed has unknown archetype {a!r}")
            if dft and dft not in allowed:
                err(tid, "composition.default must also be listed in composition.allowed")
        elif comp is not None:
            err(tid, "composition must be an object {default, allowed}")

        # eyebrow legibility floor — an explicit --eyebrow-color must clear 3:1 against --shell
        if css.exists():
            toks = _tokens(css.read_text(encoding="utf-8"))
            eb = toks.get("eyebrow-color")
            if eb:
                shell = _rgb(toks.get("shell", "#111"), toks)
                col = _rgb(eb, toks, bg=shell)
                if shell and col:
                    ratio = _contrast(col, shell)
                    if ratio < EYEBROW_MIN_CONTRAST:
                        err(tid, f"--eyebrow-color {eb!r} is {ratio:.2f}:1 on --shell "
                                 f"(need >= {EYEBROW_MIN_CONTRAST:.0f}:1 — kicker would be near-invisible)")

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
