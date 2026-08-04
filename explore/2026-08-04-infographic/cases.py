"""The adversarial three — and the NOLAN theme bridge they test.

Test design is the point. Picking easy structures gives a FALSE GREEN LIGHT: `list-row` /
`list-column` / `chart-bar` pass trivially AND are exactly what NOLAN already has as
`bullet_list` / `ledger` / `chart`, so a pass there proves the pipe and nothing else.

    trivial  list-row                    -> the pipe works at all
    wanted   list-pyramid                -> real value: NOLAN has no block for it
    wanted   sequence-roadmap-vertical   -> real value: NOLAN has no block for it
    loud     sequence-ascending-stairs-3d-> the theming FLOOR

The theme surface is ThemeSeed {colorPrimary, colorBg, isDarkMode} + palette + text attributes.
That retheme colour and type. It cannot retheme GEOMETRY. So the verdict is a per-structure
PARTITION, not a boolean.

    python -X utf8 explore/2026-08-04-infographic/cases.py --theme highlighter-editorial
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

# Reuse the PROVEN tokens.css reader rather than writing a second one — `theme.json.preview` is a
# four-colour summary for the picker, `tokens.css` is what compositions actually render in.
from nolan.mathanim.style import (  # noqa: E402
    theme_palette as _theme_palette, distance, MIN_ROLE_DISTANCE,
)

# MEASURED, and the first attempt at this was wrong. WCAG luminance contrast is the WRONG metric
# for palette fills: against this theme's #E7E9E6 shell the highlighter accent #FFF200 scores 1.04
# and the surface tint #F1F3F2 scores 1.10 — indistinguishable by contrast, yet one is obviously a
# different colour and the other is invisible. OKLab perceptual distance separates them properly:
#
#     surface  0.031   same colour as the background   -> reject
#     accent   0.197   clearly a different colour      -> keep
#     mute     0.400 / text-2 0.510 / text 0.637       -> keep
#
# So reuse mathanim's ALREADY-CALIBRATED MIN_ROLE_DISTANCE (0.12) rather than inventing a second
# threshold. Contrast still governs TEXT legibility; this governs "is that a distinct mark".


def theme_tokens(slug: str) -> dict:
    """A NOLAN theme's colours + faces. `preview` is the canonical 4-colour summary every theme
    declares; `fonts` names the real families (already installed on this render machine — see
    scripts/install_theme_fonts.py)."""
    f = REPO / "themes" / slug / "theme.json"
    if not f.exists():
        raise SystemExit(f"no such theme: {slug} ({f})")
    return json.loads(f.read_text(encoding="utf-8"))


def antv_theme(slug: str, theme: dict, palette_kind: str) -> dict:
    """NOLAN theme -> AntV ThemeConfig.

    MEASURED, not assumed: a first pass set `colorPrimary` and produced byte-identical output.
    Reading the emitted colours showed why — `colorBg` and the text fills DID land, but every item
    colour comes from `themeConfig.palette`, which defaults to AntV's 11 brand hues
    (#1783FF #00C9C9 #F0884D #D580FF ...). **The palette is what makes it look like AntV**, and it
    is the only colour lever that matters here.

    NOLAN's editorial register does not want a categorical rainbow. Its blocks read as ink + muted
    + ONE accent, so the two candidate palettes are:

      ink     the text ramp, monochrome  — the quiet reading
      accent  accent first, then the ramp — the loud reading

    Both are rendered so the stills decide.
    """
    tokens = _theme_palette(slug)          # tokens.css is the real palette; preview is a summary
    text = tokens.get("text") or "#111111"
    text2 = tokens.get("text-2") or text
    mute = tokens.get("text-mute") or text2
    accent = tokens.get("accent") or text
    surface = tokens.get("surface") or tokens.get("shell") or "#FFFFFF"

    bg = tokens.get("shell") or "#FFFFFF"

    if palette_kind == "ink":
        palette = [text, text2, mute, surface]
    elif palette_kind == "accent":
        palette = [accent, text, text2, mute]
    else:
        raise ValueError(f"unknown palette kind: {palette_kind}")

    # A palette entry has to be a DISTINCT MARK against the background it lands on. The first pass
    # used `surface` as the 4th ink colour; the stills showed step "04" as a near-invisible chevron
    # and an unreadable roadmap node. Drop anything the viewer cannot separate from the ground, and
    # anything that collides with a colour already in the palette.
    kept: list[str] = []
    for c in palette:
        if distance(c, bg) < MIN_ROLE_DISTANCE:
            continue
        if any(distance(c, k) < MIN_ROLE_DISTANCE for k in kept):
            continue
        kept.append(c)
    if len(kept) < 2:
        raise SystemExit(
            f"theme {slug!r} palette {palette_kind!r} keeps <2 separable colours against {bg} "
            f"(OKLab distance floor {MIN_ROLE_DISTANCE}) — not enough to differentiate items"
        )
    palette = kept

    return {
        "colorBg": tokens.get("shell") or "#FFFFFF",
        "colorPrimary": accent,
        "palette": palette,
        "base": {"text": {"fill": text}},
        "title": {"fill": text},
        "desc": {"fill": mute},
    }


def font_for(theme: dict) -> str:
    fonts = theme.get("fonts") or {}
    return fonts.get("displayEn") or fonts.get("body") or "Inter"


CASES = [
    # (case id, kind, template, data)
    ("trivial-list-row", "trivial", "list-row-simple-horizontal-arrow", {
        "title": "How a frame gets made",
        "items": [
            {"label": "Author", "desc": "a typed scene spec"},
            {"label": "Resolve", "desc": "bind data and assets"},
            {"label": "Compose", "desc": "HTML plus one paused timeline"},
            {"label": "Render", "desc": "seek frame by frame"},
        ],
    }),
    ("wanted-list-pyramid", "wanted", "list-pyramid-badge-card", {
        "title": "What a video essay rests on",
        "items": [
            {"label": "Narration", "desc": "owns every duration"},
            {"label": "Structure", "desc": "beats, frames, scenes"},
            {"label": "Craft", "desc": "motion, type, sound"},
        ],
    }),
    ("wanted-roadmap", "wanted", "sequence-roadmap-vertical-plain-text", {
        "title": "The finish DAG",
        "items": [
            {"label": "Word sync", "desc": "align voices to the script"},
            {"label": "Sources", "desc": "data, documents, maths"},
            {"label": "Gates", "desc": "timing and provenance"},
            {"label": "Assemble", "desc": "one video"},
        ],
    }),
    ("loud-stairs-3d", "loud", "sequence-ascending-stairs-3d-simple", {
        "title": "Escalating cost",
        "items": [
            {"label": "Draft"},
            {"label": "Review"},
            {"label": "Render"},
            {"label": "Ship"},
        ],
    }),
]


def build_spec(template: str, data: dict, slug: str, theme: dict, palette_kind: str) -> dict:
    return {
        "template": template,
        "data": data,
        "themeConfig": antv_theme(slug, theme, palette_kind),
        "_nolan": {"font": font_for(theme)},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", default="highlighter-editorial")
    ap.add_argument("--out", default=str(HERE / "_out"))
    args = ap.parse_args()

    theme = theme_tokens(args.theme)
    out = Path(args.out) / args.theme
    out.mkdir(parents=True, exist_ok=True)

    failures = 0
    for cid, kind, template, data in CASES:
        for variant in ("ink", "accent"):
            spec = build_spec(template, data, args.theme, theme, variant)
            sf = out / f"{cid}.{variant}.spec.json"
            svg = out / f"{cid}.{variant}.svg"
            sf.write_text(json.dumps(spec, indent=1), encoding="utf-8")
            r = subprocess.run(
                ["node", str(HERE / "render_svg.mjs"), str(sf), str(svg)],
                cwd=str(HERE), capture_output=True, text=True,
            )
            tag = f"{kind:8} {cid:22} {variant:6}"
            if r.returncode != 0:
                failures += 1
                print(f"FAIL {tag} :: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'rc=' + str(r.returncode)}")
                continue
            remote = [l for l in r.stderr.splitlines() if l.startswith("remote-font-ref:")]
            print(f"ok   {tag} :: {svg.stat().st_size:>6} bytes, {len(remote)} remote refs")
            if remote:
                failures += 1
                for l in remote:
                    print(f"       ^ {l}")

    print(f"\n{'FAILURES: ' + str(failures) if failures else 'all cases rendered, zero remote references'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
