"""Resolve `document` annotations authored by TEXT into page-fraction rects (the draft->resolve->build
seam). An author writes {type:"highlight", find:"1% as Vegan"} instead of pixel-eyeballing a rect; this
step locates the phrase on the page and fills in `rect`/`at`, plus stamps `page_size` so the composer
sizes the sheet to the page aspect (coords then map 1:1). Coordinates stay supported as the escape hatch.

  <nolan python> resolve_doc_annotations.py --spec spec.json --project <proj_dir> --out resolved.json

- IMAGE source (png/jpg/screenshot/scan): Tesseract OCR -> word boxes -> phrase match. (deterministic-ish)
- PDF source (.pdf, optional): PyMuPDF text layer -> EXACT word coords + renders the page to PNG.
Runs with the nolan Windows python (Tesseract binary + PIL live there). Needs Tesseract on PATH for images.
"""
import argparse, json, re, shutil, subprocess, sys
from pathlib import Path


def _norm(s):
    return re.sub(r"[^a-z0-9%$&]", "", s.lower())


def ocr_words(img_path):
    """Tesseract TSV -> [{t,l,top,w,h,line}] (confident words only)."""
    tess = shutil.which("tesseract")
    if not tess:
        sys.exit("Tesseract not on PATH — install it or export the page differently.")
    r = subprocess.run([tess, str(img_path), "stdout", "--psm", "6", "tsv"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    rows = r.stdout.splitlines()
    if not rows:
        return []
    hdr = {h: i for i, h in enumerate(rows[0].split("\t"))}
    words = []
    for ln in rows[1:]:
        c = ln.split("\t")
        if len(c) <= hdr["text"]:
            continue
        txt = c[hdr["text"]].strip()
        try:
            conf = float(c[hdr["conf"]])
        except ValueError:
            conf = -1
        if not txt or conf < 30:
            continue
        words.append({"t": txt,
                      "l": int(c[hdr["left"]]), "top": int(c[hdr["top"]]),
                      "w": int(c[hdr["width"]]), "h": int(c[hdr["height"]]),
                      "line": (c[hdr["block_num"]], c[hdr["par_num"]], c[hdr["line_num"]])})
    return words


def pdf_words(pdf_path, page_no, render_png, dpi=200):
    """PyMuPDF (optional): render page -> PNG and return EXACT word boxes in pixel space of that PNG."""
    import fitz  # PyMuPDF
    doc = fitz.open(str(pdf_path))
    page = doc[page_no]
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    page.get_pixmap(matrix=mat).save(str(render_png))
    words = []
    for (x0, y0, x1, y1, txt, bno, lno, wno) in page.get_text("words"):
        words.append({"t": txt, "l": int(x0 * zoom), "top": int(y0 * zoom),
                      "w": int((x1 - x0) * zoom), "h": int((y1 - y0) * zoom), "line": (bno, lno)})
    return words


def locate(words, phrase, iw, ih):
    """Return a padded page-fraction rect PER LINE the phrase spans (usually one). Concatenation match
    tolerates OCR word splits/merges."""
    tgt = "".join(_norm(w) for w in phrase.split())
    if not tgt:
        return []
    nw = [_norm(w["t"]) for w in words]
    for i in range(len(words)):
        acc, matched, j = "", [], i
        while j < len(words) and len(acc) < len(tgt) + 4:
            acc += nw[j]; matched.append(j); j += 1
            if acc == tgt:
                by_line = {}
                for m in matched:
                    by_line.setdefault(words[m]["line"], []).append(words[m])
                out = []
                for grp in by_line.values():
                    x0 = min(b["l"] for b in grp); y0 = min(b["top"] for b in grp)
                    x1 = max(b["l"] + b["w"] for b in grp); y1 = max(b["top"] + b["h"] for b in grp)
                    hh = y1 - y0; px = hh * 0.35; py = hh * 0.22
                    out.append([max(0, (x0 - px)) / iw, max(0, (y0 - py)) / ih,
                                min(iw, (x1 - x0 + 2 * px)) / iw, (hh + 2 * py) / ih])
                return out
            if not tgt.startswith(acc):
                break
    return []


def _bind_document(data, project_dir):
    """B-P2 — bind an INGESTED document (`data.document` = a layout-map id) to the scene: use its rendered
    page as `source` (+ page_size + provenance), and resolve any `{region:"p3-fig0"}` annotation to a rect
    from the layout map — the STABLE-ID path (robust vs an ambiguous `find` phrase, and the only way to
    target a FIGURE, which has no text to find). Region bboxes are normalized (0..1); annotations use
    rect=[fx,fy,fw,fh]. Complements the `find` path below (both run). No-op if nolan.document is absent."""
    doc_id = data.get("document")
    if not doc_id:
        return
    try:
        import sys as _sys
        _src = str(Path(__file__).resolve().parents[3] / "src")
        if _src not in _sys.path:
            _sys.path.insert(0, _src)
        from nolan.document.registry import load_document, region_bbox
    except Exception as e:
        print(f"  ! nolan.document unavailable — cannot resolve document {doc_id!r} ({e})")
        return
    doc = load_document(project_dir, doc_id)
    if doc is None:
        print(f"  ! document {doc_id!r} is not ingested — run `python -m nolan.document.ingest`")
        return
    page_no = int(data.get("page", 1))
    img = doc.image_path(page_no)
    if img and img.exists():
        try:
            rel = str(img.relative_to(Path(project_dir))).replace("\\", "/")
        except ValueError:
            rel = str(img)
        data.setdefault("source", rel)
        try:
            from PIL import Image
            data["page_size"] = list(Image.open(img).size)
        except Exception:
            pass
    data["_document"] = {"id": doc_id, "page": page_no, "provenance": doc.provenance}
    # B-P3 · a region the CAMERA frames or LIFTS (data.focus = a region id → focus_rect [x0,y0,w,h])
    foc = data.get("focus")
    if isinstance(foc, str) and "focus_rect" not in data:
        fb = region_bbox(doc, page_no, foc)
        if fb:
            data["focus_rect"] = [round(fb[0], 4), round(fb[1], 4), round(fb[2] - fb[0], 4), round(fb[3] - fb[1], 4)]
        else:
            print(f"  ! focus region {foc!r} not on page {page_no} of {doc_id!r}")
    reg_text = {r.get("id"): r.get("text", "") for r in (doc.page(page_no) or {}).get("regions", [])}
    for a in data.get("annotations", []):
        rid = a.get("region")
        if not rid:
            continue
        # VO-SYNC SPINE (B-P3): auto-fill `sync` from the region's TEXT so the annotation fires WHEN that text
        # is read (the sync layer resolves `sync` → cue). The author can override with an explicit `sync`.
        if reg_text.get(rid) and "sync" not in a and "cue" not in a:
            a["sync"] = " ".join(reg_text[rid].split()[:12])
        if "rect" in a or "at" in a:                          # position already resolved (or authored)
            continue
        bb = region_bbox(doc, page_no, rid)
        if not bb:
            print(f"  ! region {rid!r} not on page {page_no} of {doc_id!r} — leaving unresolved")
            continue
        x0, y0, x1, y1 = bb
        t = a.get("type", "highlight")
        if t in ("label", "stamp"):
            a["at"] = [round((x0 + x1) / 2, 4), round((y0 + y1) / 2, 4)]
        elif t == "underline":
            a["rect"] = [round(x0, 4), round(y1, 4), round(x1 - x0, 4)]
        else:
            a["rect"] = [round(x0, 4), round(y0, 4), round(x1 - x0, 4), round(y1 - y0, 4)]
        a.pop("region", None)
        print(f"  OK {t}: region {rid} -> rect")


def resolve_scene(data, project_dir):
    _bind_document(data, project_dir)                    # B-P2: ingested-document binding (region-id + page source)
    src = data.get("source")
    src0 = src[0] if isinstance(src, list) else src
    if not src0:
        return data
    p = project_dir / src0
    from PIL import Image
    if str(p).lower().endswith(".pdf"):
        try:
            png = p.with_suffix(".page.png")
            words = pdf_words(p, int(data.get("pdf_page", 0)), png)
            newsrc = str(png.relative_to(project_dir)).replace("\\", "/")
            data["source"] = newsrc if not isinstance(src, list) else [newsrc] + src[1:]
            iw, ih = Image.open(png).size
        except ImportError:
            print(f"  ! {src0} is a PDF but PyMuPDF is not installed "
                  f"(pip install PyMuPDF) — export the page to an image, or annotate by coordinates.")
            return data
    else:
        iw, ih = Image.open(p).size
        # only OCR when there's a `find` phrase to locate — a region/focus binding needs no text search
        # (and Tesseract may be absent). page_size still comes from the image (cheap, no OCR).
        words = ocr_words(p) if any(isinstance(a, dict) and "find" in a for a in data.get("annotations", [])) else []
    data["page_size"] = [iw, ih]
    out = []
    for a in data.get("annotations", []):
        if "find" not in a:
            out.append(a); continue
        rects = locate(words, a["find"], iw, ih)
        if not rects:
            print(f"  ! could not locate {a['find']!r} on {src0} — leaving unresolved")
            out.append(a); continue
        t = a.get("type", "highlight")
        for r in rects:
            na = {k: v for k, v in a.items() if k != "find"}
            if t == "label":
                na["at"] = [round(r[0] + r[2] / 2, 4), round(r[1] + r[3] / 2, 4)]
            elif t == "underline":
                na["rect"] = [round(r[0], 4), round(r[1] + r[3], 4), round(r[2], 4)]
            else:
                na["rect"] = [round(v, 4) for v in r]
            out.append(na)
        print(f"  OK {a.get('type','highlight')}: found {a['find']!r} -> {len(rects)} rect(s)")
    data["annotations"] = out
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--project", required=True, help="project dir the source paths are relative to")
    ap.add_argument("--out", help="output spec (default: overwrite --spec)")
    args = ap.parse_args()
    spec = json.load(open(args.spec, encoding="utf-8"))
    proj = Path(args.project)
    for fr in spec.get("frames", []):
        for sc in fr.get("scenes", []):
            if sc.get("type") == "document":
                print(f"[{fr.get('id')}/{sc.get('id')}] resolving...")
                sc["data"] = resolve_scene(sc.get("data", {}), proj)
            elif sc.get("type") == "split_view" and isinstance(sc.get("data", {}).get("paper"), dict):
                print(f"[{fr.get('id')}/{sc.get('id')}] resolving split_view paper...")
                _bind_document(sc["data"]["paper"], proj)   # {document,page,focus} → {source,page_size,focus_rect}
    out = args.out or args.spec
    json.dump(spec, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("wrote", out)


if __name__ == "__main__":
    main()
