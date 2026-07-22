"""PDF → page images + LAYOUT MAP, via PyMuPDF (fitz).

One pass per page: render to a PNG, and extract a layout map of REGIONS with NORMALIZED bboxes (0..1 of the
page, so region targeting is resolution-independent). Region kinds (MVP):

    heading | paragraph | figure(raster) | word

Headings are detected by font size (a span ≥1.18× the page's modal body size) or a short bold block. Words
carry their own bbox for fine-grained targeting. Provenance = the source filename + a content hash, so the
A-P1-style gate can trust a region traces to a real document.

NOT yet segmented (logged, never silently dropped — a B-P2 follow-up): VECTOR-drawn figures (a diagram made
of paths, like a Transformer architecture figure) — only RASTER image blocks become `figure` regions here.
Equations fall out as paragraph/figure regions for now (term-by-term equation reveal is B-P3-from-samples).
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

_BOLD_FLAG = 16          # fitz span flags bit for bold


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "doc"


def _norm(bbox, W: float, H: float) -> List[float]:
    x0, y0, x1, y1 = bbox
    return [round(x0 / W, 5), round(y0 / H, 5), round(x1 / W, 5), round(y1 / H, 5)]


def _body_size(page) -> float:
    """The page's modal body font size (weighted by character count) — the baseline a heading rises above."""
    sizes: Counter = Counter()
    for b in page.get_text("dict").get("blocks", []):
        for ln in b.get("lines", []):
            for sp in ln.get("spans", []):
                sizes[round(sp.get("size", 10.0), 1)] += len(sp.get("text", "").strip())
    return sizes.most_common(1)[0][0] if sizes else 10.0


def _vector_figures(page, W: float, H: float) -> List:
    """Cluster the page's VECTOR drawings (paths/fills — a diagram like a Transformer architecture) into
    figure rects. Union any two drawing rects that overlap within a small gap; keep clusters that are big
    enough to be a real figure (≥3% of the page) and not a thin rule. Returns fitz.Rect-like [x0,y0,x1,y1]s."""
    rects = []
    for dr in page.get_drawings():
        r = dr.get("rect")
        if r is not None and r.width > 6 and r.height > 6:           # drop hairline rules / tiny marks
            rects.append([r.x0, r.y0, r.x1, r.y1])
    if not rects:
        return []
    GAP = 12.0
    changed = True
    while changed:                                                   # merge overlapping/near rects (O(n²) passes)
        changed = False
        out = []
        for r in rects:
            merged = False
            for o in out:
                if not (r[0] > o[2] + GAP or r[2] < o[0] - GAP or r[1] > o[3] + GAP or r[3] < o[1] - GAP):
                    o[0], o[1] = min(o[0], r[0]), min(o[1], r[1])
                    o[2], o[3] = max(o[2], r[2]), max(o[3], r[3])
                    merged = True
                    changed = True
                    break
            if not merged:
                out.append(list(r))
        rects = out
    page_area = W * H
    figs = []
    for r in rects:
        area = (r[2] - r[0]) * (r[3] - r[1])
        thin = (r[2] - r[0]) < 24 or (r[3] - r[1]) < 24
        if area >= 0.03 * page_area and not thin:
            figs.append(r)
    return figs


def _page_layout(page, pno: int) -> Dict:
    """The layout map for one page: text/figure regions + a words list, all NORMALIZED to the page rect."""
    W, H = float(page.rect.width), float(page.rect.height)
    body = _body_size(page)
    regions: List[Dict] = []
    bi = 0
    for b in page.get_text("dict").get("blocks", []):
        if b.get("type") == 1:                                       # a RASTER image block → figure
            regions.append({"id": f"p{pno}-fig{bi}", "kind": "figure", "bbox": _norm(b["bbox"], W, H)})
            bi += 1
            continue
        spans = [sp for ln in b.get("lines", []) for sp in ln.get("spans", [])]
        txt = " ".join(sp.get("text", "") for sp in spans).strip()
        if not txt:
            continue
        maxsz = max((sp.get("size", body) for sp in spans), default=body)
        bold = any(int(sp.get("flags", 0)) & _BOLD_FLAG for sp in spans)
        kind = "heading" if (maxsz >= body * 1.18 or (bold and len(txt) < 80)) else "paragraph"
        regions.append({"id": f"p{pno}-b{bi}", "kind": kind, "bbox": _norm(b["bbox"], W, H), "text": txt[:400]})
        bi += 1
    for vi, vr in enumerate(_vector_figures(page, W, H)):            # VECTOR-drawn figures (diagrams)
        regions.append({"id": f"p{pno}-vfig{vi}", "kind": "figure", "bbox": _norm(vr, W, H)})
    words = [{"id": f"p{pno}-w{wi}", "bbox": _norm((w[0], w[1], w[2], w[3]), W, H), "text": w[4]}
             for wi, w in enumerate(page.get_text("words"))]
    return {"page": pno, "size": {"w": round(W, 1), "h": round(H, 1)}, "regions": regions, "words": words}


def ingest_pdf(pdf_path, out_root, doc_id: Optional[str] = None, dpi: int = 150) -> Dict:
    """Ingest a PDF into `<out_root>/<doc_id>/`: a rendered PNG per page (`pages/pNNN.png`) + `layout.json`
    (per-page region maps), registered in `<out_root>/index.json` with provenance. Returns the layout dict."""
    import fitz
    src = Path(pdf_path)
    doc = fitz.open(str(src))
    doc_id = doc_id or _slug(src.stem)
    ddir = Path(out_root) / doc_id
    (ddir / "pages").mkdir(parents=True, exist_ok=True)
    pages: List[Dict] = []
    for pno in range(1, doc.page_count + 1):
        page = doc[pno - 1]
        rel = f"pages/p{pno:03d}.png"
        page.get_pixmap(dpi=dpi).save(str(ddir / rel))
        lm = _page_layout(page, pno)
        lm["image"] = rel
        pages.append(lm)
    h = hashlib.sha1(src.read_bytes()).hexdigest()[:12]
    layout = {"id": doc_id, "source": src.name, "hash": h, "dpi": dpi, "page_count": len(pages),
              "provenance": f"pdf:{src.name}#sha1:{h}", "pages": pages}
    (ddir / "layout.json").write_text(json.dumps(layout, ensure_ascii=False, indent=1), encoding="utf-8")
    _register(Path(out_root), layout)

    n_reg = sum(len(p["regions"]) for p in pages)
    n_head = sum(1 for p in pages for r in p["regions"] if r["kind"] == "heading")
    n_fig = sum(1 for p in pages for r in p["regions"] if r["kind"] == "figure")
    n_words = sum(len(p["words"]) for p in pages)
    print(f"ingested '{doc_id}': {len(pages)} pages, {n_reg} regions "
          f"({n_head} headings, {n_fig} figures [raster + clustered vector]), {n_words} words → {ddir}")
    return layout


_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp")


def ingest_document(comp, filename: str, data: bytes, doc_id: Optional[str] = None, dpi: int = 150) -> Dict:
    """Comp-scoped ingest for the UI/CLI: an uploaded PDF **or image** → ``<comp>/documents/<id>/`` (pages +
    layout + provenance). PyMuPDF ingests PDFs, so an image scan is wrapped to a 1-page PDF first (it will
    have a page image but no text layer — target it with an explicit rect or `find`/OCR, not a region id).
    Returns the layout dict. Thin wrapper over :func:`ingest_pdf`; keeps the original filename in provenance.
    """
    import io
    import shutil
    import tempfile
    from nolan.document.registry import _documents_dir
    ext = Path(filename).suffix.lower()
    if ext in _IMAGE_EXTS:
        from PIL import Image
        buf = io.BytesIO()
        Image.open(io.BytesIO(data)).convert("RGB").save(buf, format="PDF")
        data = buf.getvalue()
        src_name = Path(filename).stem + ".pdf"
    elif ext == ".pdf":
        src_name = Path(filename).name
    else:
        raise ValueError(f"unsupported document {filename!r} — use a .pdf or an image ({', '.join(_IMAGE_EXTS)})")
    docs_dir = _documents_dir(comp)
    docs_dir.mkdir(parents=True, exist_ok=True)
    tmpd = Path(tempfile.mkdtemp())
    try:
        tmp = tmpd / src_name
        tmp.write_bytes(data)
        return ingest_pdf(tmp, docs_dir, doc_id=doc_id, dpi=dpi)
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)


def _register(out_root: Path, layout: Dict) -> None:
    """Add/replace this document's entry in the source index (mirrors datasets/index.json)."""
    idx_path = out_root / "index.json"
    idx = {"documents": []}
    if idx_path.exists():
        try:
            idx = json.loads(idx_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            idx = {"documents": []}
    docs = [d for d in idx.get("documents", []) if d.get("id") != layout["id"]]
    docs.append({"id": layout["id"], "source": layout["source"], "hash": layout["hash"],
                 "page_count": layout["page_count"], "provenance": layout["provenance"]})
    idx["documents"] = docs
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")


def layout_for_page(layout: Dict, page: int) -> Optional[Dict]:
    return next((p for p in layout.get("pages", []) if p.get("page") == page), None)


def main():
    """python -X utf8 -m nolan.document.ingest <pdf> <out_root> [--id ID] [--dpi 150]"""
    import argparse
    ap = argparse.ArgumentParser(prog="nolan.document.ingest")
    ap.add_argument("pdf")
    ap.add_argument("out_root", help="documents dir (e.g. <comp>/documents)")
    ap.add_argument("--id", default=None)
    ap.add_argument("--dpi", type=int, default=150)
    a = ap.parse_args()
    ingest_pdf(a.pdf, a.out_root, doc_id=a.id, dpi=a.dpi)


if __name__ == "__main__":
    main()
