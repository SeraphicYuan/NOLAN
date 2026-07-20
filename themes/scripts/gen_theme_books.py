"""Generate a per-theme THEME BOOK: an engine-rendered identity card + the theme's specimens + its
metadata, composed into one reference poster (themes/_books/<theme>.png) + a machine-readable companion
(themes/_books/<theme>.json) for AUTHORING — an LLM greps a theme's look + capabilities from one image far
cheaper than parsing tokens.css. Fully code-driven: everything derives from tokens.css + theme.json + the
rendered specimens in themes/_samples (which the identity card + specimens are themselves engine renders of),
nothing hand-authored per theme. Run:  python -X utf8 gen_theme_books.py [theme|all]
"""
import json
import re
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
SAMP = REPO / "themes" / "_samples"
OUT = REPO / "themes" / "_books"
OUT.mkdir(parents=True, exist_ok=True)
_SPECIMENS_FALLBACK = ["centered-hero", "editorial-column", "framed", "swiss-grid", "sidebar", "timeline",
                       "split-screen", "full-bleed-overlay", "focal-card",
                       "stat", "bullet-list", "chart", "pull-quote", "comparison-table", "ledger"]


def _load_specimens():
    """AUTO-DERIVE the book's specimen list from gen_samples' rendered manifest — the BASE specimens (one per
    SEED: every archetype + block specimen, minus `identity` and the per-variant renders). So a new archetype
    or block added to gen_samples SEEDS appears in every theme book automatically (no hardcoded list to rot)."""
    try:
        man = json.loads((SAMP / "manifest.json").read_text(encoding="utf-8"))
        seen = []
        for m in man:
            a = m.get("archetype")
            if a and a != "identity" and not m.get("variant") and a not in seen:
                seen.append(a)
        return seen or _SPECIMENS_FALLBACK
    except Exception:
        return _SPECIMENS_FALLBACK


SPECIMENS = _load_specimens()


def _hexes(css):
    d = {}
    for k in ("shell", "surface", "surface-2", "text", "text-2", "accent"):
        m = re.search(rf"--{k}\s*:\s*(#[0-9a-fA-F]{{3,6}})", css)
        if m:
            d[k] = m.group(1)
    return d


def _font(sz, bold=False):
    for p in (("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
              "C:/Windows/Fonts/arial.ttf"):
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            pass
    return ImageFont.load_default()


def _wrap(text, width, fnt, draw):
    """Greedy word-wrap `text` to a pixel `width` for font `fnt`."""
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=fnt) <= width:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def build(theme):
    tj = json.loads((REPO / "themes" / theme / "theme.json").read_text(encoding="utf-8"))
    css = (REPO / "themes" / theme / "tokens.css").read_text(encoding="utf-8")
    hx = _hexes(css)
    fonts = tj.get("fonts", {}) if isinstance(tj.get("fonts"), dict) else {}
    W, pad = 1720, 34
    hh = 340                                   # header band
    idw = W - 2 * pad
    idh = int(idw * 9 / 16)                     # identity card 16:9
    cols = 3
    gap = 20
    cw = (W - 2 * pad - (cols - 1) * gap) // cols
    ch = int(cw * 9 / 16)
    rows = (len(SPECIMENS) + cols - 1) // cols
    grid_h = rows * (ch + 34)
    H = hh + idh + 44 + grid_h + pad
    im = Image.new("RGB", (W, H), (22, 22, 26))
    d = ImageDraw.Draw(im)

    # ── header ──
    d.text((pad, pad - 4), tj.get("name", theme), font=_font(50, bold=True), fill=(244, 244, 248))
    d.text((pad, pad + 56), f"{tj.get('typePersonality', '')}   ·   {'  '.join(tj.get('mood', [])[:5])}",
           font=_font(21), fill=(150, 195, 150))
    # palette swatches (base hexes)
    x, y = pad, pad + 104
    for k in ("shell", "surface", "accent", "text"):
        c = hx.get(k)
        if not c:
            continue
        d.rectangle([x, y, x + 128, y + 52], fill=c, outline=(90, 90, 96))
        d.text((x, y + 57), f"{k}  {c}", font=_font(15), fill=(184, 184, 194))
        x += 156
    # fonts + decoration (to the right of the swatches)
    fline = "  /  ".join(f"{r}: {v}" for r, v in
                         (("display", fonts.get("displayEn") or fonts.get("display", "")),
                          ("body", fonts.get("body", "")), ("mono", fonts.get("mono", ""))) if v)
    d.text((x + 6, y + 2), fline, font=_font(16), fill=(180, 180, 190))
    dec = [e if isinstance(e, str) else e.get("id") for e in (tj.get("decoration") or [])]
    d.text((x + 6, y + 28), "decoration: " + (", ".join(dec) or "—"), font=_font(16), fill=(170, 170, 182))
    # description (English) — the primary authoring blurb — + avoid-for (English)
    df = _font(18)
    yy = pad + 216
    for ln in _wrap(tj.get("description", ""), W - 2 * pad - 260, df, d)[:2]:
        d.text((pad, yy), ln, font=df, fill=(188, 188, 198))
        yy += 26
    av = tj.get("avoidFor")
    av = ", ".join(av) if isinstance(av, list) else (av or "")
    if av:
        d.text((pad, yy + 2), f"avoid:  {av}", font=_font(16), fill=(162, 162, 174))

    # ── identity card (engine render) ──
    idp = SAMP / f"identity__{theme}.png"
    if idp.exists():
        im.paste(Image.open(idp).convert("RGB").resize((idw, idh)), (pad, hh))
    d.text((pad, hh - 24), "IDENTITY  ·  palette · type roles · shape (rendered in the theme's own tokens)",
           font=_font(15), fill=(150, 150, 160))

    # ── specimen grid ──
    gy = hh + idh + 44
    for i, s in enumerate(SPECIMENS):
        r, c = divmod(i, cols)
        gx = pad + c * (cw + gap)
        yy = gy + r * (ch + 34)
        d.text((gx + 2, yy), s, font=_font(16), fill=(206, 206, 216))
        p = SAMP / f"{s}__{theme}.png"
        if p.exists():
            im.paste(Image.open(p).convert("RGB").resize((cw, ch)), (gx, yy + 22))

    im.save(OUT / f"{theme}.png")
    (OUT / f"{theme}.json").write_text(json.dumps({
        "theme": theme, "name": tj.get("name"), "personality": tj.get("typePersonality"),
        "mood": tj.get("mood"), "palette": hx, "fonts": fonts, "decoration": dec,
        "bestFor": tj.get("bestFor"), "avoidFor": tj.get("avoidFor"),
        "composition": tj.get("composition"), "specimens": SPECIMENS,
        "book_png": f"themes/_books/{theme}.png",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return OUT / f"{theme}.png"


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    themes = ([arg] if arg != "all"
              else sorted(d.name for d in (REPO / "themes").iterdir()
                          if d.is_dir() and (d / "theme.json").exists()))
    for t in themes:
        try:
            print("book:", build(t).name)
        except Exception as e:
            print(f"FAIL {t}: {e}")


if __name__ == "__main__":
    main()
