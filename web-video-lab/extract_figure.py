"""Extract a paper figure for the PaperFigure block (the lift-and-place tier).

For *empirical* figures we can't honestly redraw (attention heatmaps, plots of
real data, PnL/backtest curves, sample outputs), we lift the paper's own image
rather than fabricate it. Extraction = find the figure's image -> (download) ->
trim margins -> (optionally matte near-white to transparent). The block then
frames it on a themed "exhibit card" with a cited caption (a deliberate specimen).

Two input formats (run with the nolan python — PIL):
  # arXiv HTML (figures are separate <img> assets):
  D:\\env\\nolan\\python.exe web-video-lab/extract_figure.py \
      --html paper.html --figure 3 --out figures/fig3.png [--matte]

  # MinerU parsed folder (content.md with '![](images/<hash>.jpg)' + 'Figure N:' lines):
  D:\\env\\nolan\\python.exe web-video-lab/extract_figure.py \
      --md <folder>/content.md --figure 1 --out figures/fig1.png

  # catalog every figure (number/image/caption/source) as JSON — what a chapter
  # agent reads to choose which figures to lift (use --out for a utf-8 file;
  # the Windows console codepage mangles smart quotes on a redirect):
  D:\\env\\nolan\\python.exe web-video-lab/extract_figure.py \
      --md <folder>/content.md --list --out figures_catalog.json
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import urlopen

from PIL import Image


def _figure_img_src(html: str, fig_num: int) -> str:
    """Return the src of the first <img> belonging to Figure N."""
    # walk imgs in document order; the first one whose following text starts the
    # "Figure N:" caption is the figure's image.
    for m in re.finditer(r'<img[^>]+src="([^"]+)"', html):
        tail = html[m.start():m.start() + 2000]
        cap = re.search(r"Figure\s*(\d+)\s*:", tail)
        if cap and int(cap.group(1)) == fig_num:
            return m.group(1)
    raise SystemExit(f"no <img> found for Figure {fig_num}")


# ─── MinerU markdown ('![](images/<hash>.jpg)' then a 'Figure N: …' line) ───
def mineru_figures(md: str) -> list[dict]:
    """Catalog every figure in a MinerU content.md: the image ref followed by its
    'Figure N: caption' (and optional 'Source:' line). Returns doc-ordered dicts
    {figure, image, caption, source}. This is what a chapter agent reads to pick
    which empirical figures to lift."""
    lines = md.splitlines()
    figs: list[dict] = []
    for i, ln in enumerate(lines):
        m = re.match(r"!\[\]\(([^)]+)\)", ln.strip())
        if not m:
            continue
        img = m.group(1)
        # the caption is the next non-empty line starting "Figure N:"
        cap, num, src = "", None, ""
        for j in range(i + 1, min(i + 4, len(lines))):
            t = lines[j].strip()
            cm = re.match(r"Figure\s*(\d+)\s*:\s*(.*)", t)
            if cm:
                num, cap = int(cm.group(1)), cm.group(2).strip()
            elif t.startswith("Source:"):
                src = t[len("Source:"):].strip()
            elif cm is None and not cap and t:
                break
        if num is not None:
            figs.append({"figure": num, "image": img, "caption": cap, "source": src})
    return figs


def _mineru_img_rel(md: str, fig_num: int) -> str:
    for f in mineru_figures(md):
        if f["figure"] == fig_num:
            return f["image"]
    raise SystemExit(f"no figure {fig_num} in markdown")


def _load(src: str, base_url: str | None, html_path: Path) -> Image.Image:
    if src.startswith("http"):
        return Image.open(urlopen(src)).convert("RGBA")
    if base_url:
        return Image.open(urlopen(urljoin(base_url, src))).convert("RGBA")
    # local relative to the html file's directory
    return Image.open(html_path.parent / src).convert("RGBA")


def _trim(im: Image.Image, pad: int = 12, thresh: int = 250) -> Image.Image:
    """Crop near-white margins, then pad with transparent pixels."""
    rgb = im.convert("RGB")
    # a mask of "has ink" = any channel below threshold
    from PIL import ImageChops

    bg = Image.new("RGB", rgb.size, (255, 255, 255))
    diff = ImageChops.difference(rgb, bg).convert("L")
    bbox = diff.point(lambda p: 255 if p > (255 - thresh) else 0).getbbox()
    if bbox:
        im = im.crop(bbox)
    out = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    out.paste(im, (pad, pad))
    return out


def _matte(im: Image.Image, thresh: int = 244) -> Image.Image:
    """Set near-white pixels transparent. NOTE: corrupts light-ink/grayscale
    figures on dark themes (the invisible-ink trap) — use the exhibit card for
    those; reserve --matte for figures with their own dark/colored fill."""
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if r >= thresh and g >= thresh and b >= thresh:
                px[x, y] = (r, g, b, 0)
    return im


def main() -> None:
    ap = argparse.ArgumentParser()
    src_grp = ap.add_mutually_exclusive_group(required=True)
    src_grp.add_argument("--html", help="arXiv-style paper HTML (local file)")
    src_grp.add_argument("--md", help="MinerU content.md (markdown)")
    ap.add_argument("--figure", type=int, help="figure number to extract")
    ap.add_argument("--out", help="output png")
    ap.add_argument("--list", action="store_true", help="print the figure catalog as JSON and exit")
    ap.add_argument("--base-url", default=None, help="(html) resolve relative img srcs")
    ap.add_argument("--matte", action="store_true", help="near-white -> transparent")
    a = ap.parse_args()

    # ── MinerU markdown ──
    if a.md:
        import json
        md_path = Path(a.md)
        md = md_path.read_text(encoding="utf-8")
        if a.list:
            cat = json.dumps(mineru_figures(md), indent=2, ensure_ascii=False)
            if a.out:  # write utf-8 directly (Windows console codepage mangles smart quotes)
                Path(a.out).write_text(cat, encoding="utf-8")
                print(f"wrote {a.out}")
            else:
                print(cat)
            return
        if a.figure is None or not a.out:
            raise SystemExit("need --figure and --out (or --list)")
        rel = _mineru_img_rel(md, a.figure)
        im = _trim(Image.open(md_path.parent / rel).convert("RGBA"))
        if a.matte:
            im = _matte(im)
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        im.save(out)
        print(f"Figure {a.figure}: {rel} -> {out}  ({im.width}x{im.height}, matte={a.matte})")
        return

    # ── arXiv HTML ──
    html_path = Path(a.html)
    html = html_path.read_text(encoding="utf-8")
    if a.list:
        import json
        figs = []
        for m in re.finditer(r'<img[^>]+src="([^"]+)"', html):
            cap = re.search(r"Figure\s*(\d+)\s*:\s*([^<]*)", html[m.start():m.start() + 2000])
            if cap:
                figs.append({"figure": int(cap.group(1)), "image": m.group(1),
                             "caption": re.sub(r"\s+", " ", cap.group(2)).strip()})
        print(json.dumps(figs, indent=2, ensure_ascii=False))
        return
    if a.figure is None or not a.out:
        raise SystemExit("need --figure and --out (or --list)")
    src = _figure_img_src(html, a.figure)
    im = _trim(_load(src, a.base_url, html_path))
    if a.matte:
        im = _matte(im)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    print(f"Figure {a.figure}: {src} -> {out}  ({im.width}x{im.height}, matte={a.matte})")


if __name__ == "__main__":
    main()
