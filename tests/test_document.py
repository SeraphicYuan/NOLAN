"""B-P1 — document source (PDF → page images + layout map, provenance-gated). Self-contained: builds a tiny
PDF in-test with fitz, so it needs no external fixture."""
import json
from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")     # PyMuPDF; skip if the optional engine isn't installed

from nolan.document import ingest_pdf, load_document, region_bbox   # noqa: E402
from nolan.document.registry import _documents_dir                  # noqa: E402


def _make_pdf(path):
    doc = fitz.open()
    p = doc.new_page(width=612, height=792)
    p.insert_text((72, 90), "The Big Heading", fontsize=26)
    p.insert_text((72, 160), "This is a body paragraph with several ordinary words in it.", fontsize=10)
    doc.new_page(width=612, height=792).insert_text((72, 90), "Second page text here.", fontsize=10)
    doc.save(str(path))


def test_ingest_pdf_produces_pages_regions_words_and_normalized_bboxes(tmp_path):
    pdf = tmp_path / "sample.pdf"
    _make_pdf(pdf)
    out = tmp_path / "documents"
    layout = ingest_pdf(str(pdf), str(out), doc_id="samp")

    assert layout["page_count"] == 2
    assert layout["provenance"].startswith("pdf:sample.pdf#sha1:")
    p1 = layout["pages"][0]
    assert (out / "samp" / p1["image"]).exists()                    # a rendered PNG per page
    kinds = {r["kind"] for r in p1["regions"]}
    assert "heading" in kinds and "paragraph" in kinds              # 26pt line → heading, 10pt → paragraph
    assert p1["words"], "words carry their own bbox for fine targeting"
    # every bbox is NORMALIZED to the page (0..1) so targeting is resolution-independent
    for r in p1["regions"] + p1["words"]:
        assert all(0.0 <= v <= 1.0 for v in r["bbox"]), r


def test_load_document_is_provenance_gated(tmp_path):
    pdf = tmp_path / "s.pdf"
    _make_pdf(pdf)
    out = tmp_path / "documents"
    ingest_pdf(str(pdf), str(out), doc_id="samp")

    doc = load_document(str(tmp_path), "samp")                      # comp dir → <comp>/documents
    assert doc is not None and doc.provenance
    assert region_bbox(doc, 1, "p1-b0") is not None                # a resolvable region id
    assert load_document(str(tmp_path), "nope") is None            # never ingested → None (not a silent pass)

    # a document whose layout has NO provenance is a fabrication risk → loading raises
    bad = _documents_dir(str(tmp_path)) / "bad"
    bad.mkdir(parents=True, exist_ok=True)
    (bad / "layout.json").write_text(json.dumps({"id": "bad", "pages": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_document(str(tmp_path), "bad")


def _make_pdf_with_figure(path):
    doc = fitz.open()
    p = doc.new_page(width=612, height=792)
    p.insert_text((72, 90), "Heading", fontsize=20)
    p.draw_rect(fitz.Rect(100, 220, 500, 620), color=(0, 0, 0), width=2)   # a big VECTOR rect = a figure
    doc.save(str(path))


def test_vector_figure_is_segmented(tmp_path):
    pdf = tmp_path / "f.pdf"
    _make_pdf_with_figure(pdf)
    layout = ingest_pdf(str(pdf), str(tmp_path / "documents"), doc_id="f")
    figs = [r for r in layout["pages"][0]["regions"] if r["kind"] == "figure"]
    assert figs, "a large vector drawing should be segmented as a figure region"
    b = figs[0]["bbox"]                                              # normalized, roughly the drawn rect
    assert 0.1 < b[0] < 0.3 and 0.2 < b[1] < 0.4 and b[2] > 0.6 and b[3] > 0.7


def test_region_id_annotation_resolves_to_bbox(tmp_path):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"))
    import resolve_doc_annotations as R
    pdf = tmp_path / "s.pdf"
    _make_pdf_with_figure(pdf)
    layout = ingest_pdf(str(pdf), str(tmp_path / "documents"), doc_id="samp")
    fig = next(r for r in layout["pages"][0]["regions"] if r["kind"] == "figure")
    data = {"document": "samp", "page": 1, "annotations": [{"type": "highlight", "region": fig["id"]}]}
    R._bind_document(data, tmp_path)                                # B-P2: region-id → rect (no OCR path)
    assert data.get("source", "").endswith("p001.png") and data.get("page_size")
    assert data["_document"]["provenance"].startswith("pdf:")
    a = data["annotations"][0]
    assert "rect" in a and "region" not in a, "region id should resolve to a rect and be consumed"
    x0, y0, x1, y1 = fig["bbox"]
    assert abs(a["rect"][0] - x0) < 1e-3 and abs(a["rect"][2] - (x1 - x0)) < 1e-3   # rect = [x0,y0,w,h]


def test_bp3_wave1_vo_sync_and_motions(tmp_path):
    """B-P3 Wave 1: VO-sync spine (region text → `sync` → cue), camera:region + focus_mode:lift transforms,
    read-along sweep, split_view panels. Self-contained fitz PDF + a synthetic word stream."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"))
    import resolve_doc_annotations as R
    import compose
    from nolan.hyperframes import sync
    from nolan.whisper import WordTimestamp
    pdf = tmp_path / "d.pdf"
    _make_pdf_with_figure(pdf)   # has a heading + a figure
    ingest_pdf(str(pdf), str(tmp_path / "documents"), doc_id="d")
    # find a text region to sync/highlight
    from nolan.document import load_document
    doc = load_document(str(tmp_path), "d")
    reg = next(r for r in doc.page(1)["regions"] if r.get("text"))
    fig = next(r for r in doc.page(1)["regions"] if r["kind"] == "figure")

    # VO-SYNC: bind auto-fills `sync` from the region text; the sync layer resolves it to a cue
    data = {"document": "d", "page": 1, "focus": fig["id"], "camera": "region",
            "annotations": [{"type": "highlight", "region": reg["id"], "read": True}]}
    R._bind_document(data, str(tmp_path))
    a = data["annotations"][0]
    assert a.get("sync"), "bind should auto-fill `sync` from the region text"
    assert data.get("focus_rect"), "focus region should resolve to a rect"
    words = [WordTimestamp(w, float(i), float(i) + 0.9) for i, w in enumerate(("z z z " + a["sync"]).split())]
    sc = {"id": "s1", "type": "document", "start": 0.0, "dur": 30.0, "data": data}
    assert sync._retime_doc_annotations(sc, data, words) == 1 and a["cue"] == 3.0   # fires when the text is read

    # camera:region + read-along emit their transforms
    frag, tl = compose.BLOCKS["document"]("dc", {**sc, "id": "dc"})
    joined = "\n".join(tl)
    assert 'scale:' in joined and 'transformOrigin:"0px 0px"' in joined      # region zoom
    assert any('ease:"none"' in x for x in tl)                                # read-along linear sweep

    # focus_mode:lift emits the blur + the lifted clone
    data2 = {"document": "d", "page": 1, "focus": fig["id"], "focus_mode": "lift"}
    R._bind_document(data2, str(tmp_path))
    f2, t2 = compose.BLOCKS["document"]("dl", {"id": "dl", "type": "document", "start": 0, "dur": 8, "data": data2})
    assert "dl-lift" in "".join(f2) and any("blur(" in x for x in t2)

    # split_view: paper panel + content panel
    R._bind_document(data2, str(tmp_path))   # reuse as the paper side
    sv = {"id": "sv", "type": "split_view", "start": 0, "dur": 8,
          "data": {"paper": data2, "right": {"kind": "text", "title": "T", "lines": ["a", "b"]}}}
    fsv, tsv = compose.BLOCKS["split_view"]("sv", sv)
    h = "".join(fsv)
    assert "sv-paper" in h and "sv-content" in h and "sv-div" in h


def test_bp3_wave2_evidence_annotations():
    """B-P3 Wave 2 (document-as-evidence): redaction lifts, stamp slams, strike + insertion, equation term+gloss."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"))
    import compose
    sc = {"id": "ev", "type": "document", "start": 0, "dur": 10, "data": {"source": "x.png", "page_size": [600, 800],
          "annotations": [
              {"type": "redaction", "rect": [0.2, 0.3, 0.5, 0.1], "cue": 5},
              {"type": "stamp", "at": [0.7, 0.2], "text": "CLASSIFIED", "cue": 2},
              {"type": "strike", "rect": [0.1, 0.5, 0.4, 0.03], "text": "(struck)", "cue": 3},
              {"type": "term", "rect": [0.1, 0.1, 0.15, 0.03], "gloss": "the model", "cue": 1.5}]}}
    frag, tl = compose.BLOCKS["document"]("ev", sc)
    h, j = "".join(frag), "\n".join(tl)
    assert "ev-rd1" in h and "y:-16,opacity:0" in j        # redaction bar lifts
    assert "ev-st2" in h and "CLASSIFIED" in h and "scale:1.55" in j   # stamp slam
    assert "ev-sk3" in h and "ev-ins3" in h                # strike + insertion
    assert "ev-tm4" in h and "ev-gl4" in h and "the model" in h        # term + gloss


def test_bp3_wave3_marginalia_and_pullquote():
    """B-P3 Wave 3 (polish): marginalia note + leader line; pull-quote lifts off the page (page dims)."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"))
    import compose
    sc = {"id": "w3", "type": "document", "start": 0, "dur": 10, "data": {"source": "x.png", "page_size": [600, 800],
          "annotations": [
              {"type": "margin", "rect": [0.1, 0.2, 0.3, 0.03], "text": "← key", "cue": 2},
              {"type": "pullquote", "rect": [0.1, 0.4, 0.8, 0.1], "text": "The whole thesis.", "cue": 4}]}}
    frag, tl = compose.BLOCKS["document"]("w3", sc)
    h, j = "".join(frag), "\n".join(tl)
    assert "w3-mg1" in h and "w3-mg1-ln" in h                     # marginalia note + leader line
    assert "w3-pq2" in h and "The whole thesis." in h and "opacity:0.32" in j   # pull-quote + page dim
