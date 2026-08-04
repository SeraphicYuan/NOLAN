"""Does PyMuPDF close the vector-figure gap, without MinerU?

`src/nolan/document/ingest.py` states the gap in its own docstring:

    NOT yet segmented (logged, never silently dropped - a B-P2 follow-up): VECTOR-drawn figures
    (a diagram made of paths, like a Transformer architecture figure) - only RASTER image blocks
    become `figure` regions here.

Most ML papers draw their architecture figures as VECTORS, so today the single most important
figure in the average paper NOLAN would explain is the one it silently cannot extract. Paper2Any
reaches for MinerU + SAM3 (a VLM pipeline, a heavy new dependency, its own env). PyMuPDF 1.28 is
ALREADY in the nolan env and exposes `page.get_drawings()`. If clustering those paths recovers the
figure regions deterministically, the VLM is unnecessary - "deterministic code where correctness
is computable", per the capability-routing policy.

    python -X utf8 explore/2026-08-04-infographic/vector_figures.py <pdf> [--page N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import fitz  # PyMuPDF

# A caption is the ground truth for "this is a figure": papers label them. Matching the caption
# lets the probe REPORT recall honestly instead of asserting that whatever it found is right.
CAPTION = ("figure", "fig.", "fig ")


def _rects_overlap_or_near(a: fitz.Rect, b: fitz.Rect, pad: float) -> bool:
    return bool(fitz.Rect(a.x0 - pad, a.y0 - pad, a.x1 + pad, a.y1 + pad).intersects(b))


def cluster_drawings(page: fitz.Page, pad: float = 12.0, min_paths: int = 4,
                     min_area_frac: float = 0.010) -> list[fitz.Rect]:
    """Group vector paths into figure-sized regions.

    Single-linkage on proximity: two paths join a cluster when their bboxes are within `pad`
    points. Rules, underlines and table borders survive as clusters too, so they are filtered by
    path COUNT and AREA rather than by guessing at semantics.
    """
    drawings = page.get_drawings()
    boxes = [d["rect"] for d in drawings if d.get("rect") and d["rect"].get_area() > 0]
    if not boxes:
        return []

    clusters: list[list[fitz.Rect]] = []
    for box in boxes:
        hit = [i for i, c in enumerate(clusters)
               if any(_rects_overlap_or_near(box, m, pad) for m in c)]
        if not hit:
            clusters.append([box])
            continue
        # Merge every cluster this box bridges — otherwise cluster identity depends on input order.
        merged = [box]
        for i in sorted(hit, reverse=True):
            merged.extend(clusters.pop(i))
        clusters.append(merged)

    page_area = abs(page.rect.get_area()) or 1.0
    out = []
    for members in clusters:
        r = members[0]
        for m in members[1:]:
            r = r | m
        if len(members) >= min_paths and r.get_area() / page_area >= min_area_frac:
            out.append(r)
    return sorted(out, key=lambda r: (r.y0, r.x0))


def captions(page: fitz.Page) -> list[tuple[str, fitz.Rect]]:
    found = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        text = " ".join(s["text"] for l in block.get("lines", []) for s in l.get("spans", []))
        low = text.strip().lower()
        if any(low.startswith(c) for c in CAPTION):
            found.append((text.strip()[:70], fitz.Rect(block["bbox"])))
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--page", type=int, default=None, help="1-based; default = every page")
    ap.add_argument("--dump", default=None, help="write cropped PNGs here")
    args = ap.parse_args()

    doc = fitz.open(args.pdf)
    pages = [args.page - 1] if args.page else range(doc.page_count)

    raster_total = vector_total = 0
    for pno in pages:
        page = doc[pno]
        raster = page.get_images(full=True)
        vectors = cluster_drawings(page)
        caps = captions(page)
        if not (raster or vectors or caps):
            continue

        raster_total += len(raster)
        vector_total += len(vectors)
        print(f"\n--- page {pno + 1} --- raster={len(raster)}  vector-clusters={len(vectors)}  captions={len(caps)}")
        for cap, crect in caps:
            # A caption with a vector cluster ABOVE it is the recovered figure.
            owner = next((r for r in vectors if r.y1 <= crect.y0 + 6 and abs(r.x0 - crect.x0) < 300), None)
            mark = "VECTOR" if owner else ("raster" if raster else "UNMATCHED")
            print(f"   [{mark:9}] {cap}")
        for i, r in enumerate(vectors):
            frac = r.get_area() / abs(page.rect.get_area())
            print(f"   cluster {i}: {r.width:6.0f}x{r.height:6.0f}pt  {frac:5.1%} of page")
            if args.dump:
                out = Path(args.dump)
                out.mkdir(parents=True, exist_ok=True)
                page.get_pixmap(clip=r, dpi=150).save(out / f"p{pno+1}_v{i}.png")

    print(f"\ntotals: raster images={raster_total}  vector clusters={vector_total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
