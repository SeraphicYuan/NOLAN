"""B-P1 — document as a first-class SOURCE.

A PDF becomes page images + a LAYOUT MAP (region bboxes), provenance-stamped, so downstream blocks can
pan / zoom / highlight REAL regions of a REAL paper instead of inventing them (the paper analogue of the
data-source layer). PyMuPDF (fitz) renders each page and extracts the text/figure geometry in one pass.
"""
from .ingest import ingest_pdf, layout_for_page          # noqa: F401
from .registry import Document, load_document, list_documents, region_bbox   # noqa: F401
