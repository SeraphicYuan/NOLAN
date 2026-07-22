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
