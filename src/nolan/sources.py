"""The SOURCES umbrella — the typed inputs a scene can be BUILT FROM.

Unifies the three source kinds under one code-backed catalog so a block is source-aware and every
number/region traces to a REAL source (the A-P1 / B-P1 provenance principle — an un-sourced number or an
un-ingested document is a fabrication risk that a gate rejects):

  media     — images / video / bg-removed cutouts (the pool + stock/gen), the visual evidence layer
  data      — a provenance-gated DATASET → a data-viz block's cells (grammar-of-graphics: table→encode→mark)
  document  — a PDF → page images + a region LAYOUT MAP (heading/paragraph/figure/word), provenance-stamped

The data + document REGISTRIES (`nolan.data.registry`, `nolan.document.registry`) are the executors; the
resolvers (`nolan.data.resolve`, `resolve_doc_annotations`) bind an authored reference to real cells/regions.
"""
from __future__ import annotations

from typing import Dict, List

SOURCES: List[Dict] = [
    {"id": "media",
     "purpose": "Images / video / bg-removed cutouts from the pool or stock/gen — the visual evidence layer.",
     "when_to_use": "Any visual evidence: a photo, a clip, a prop cutout, a full-bleed ground.",
     "authored_field": "data.ground / data.src / data.props",
     "provenance": "asset_gate (license + identity)"},
    {"id": "data",
     "purpose": "A provenance-gated DATASET → a data-viz block's cells (table → encode → mark).",
     "when_to_use": "A chart/stat/table/pie/… whose numbers must be REAL, not invented — bind "
                    "data.dataset+query+encode and the resolver fills the cells + stamps value_source.",
     "authored_field": "data.dataset / query / encode",
     "provenance": "value_source (spoken | value_source | dataset cell — A-P1 gate)"},
    {"id": "document",
     "purpose": "A PDF → page images + a region LAYOUT MAP (heading/paragraph/figure/word), provenance-stamped.",
     "when_to_use": "A beat built around a REAL page — quote/annotate a paper, zoom to a figure by region id.",
     "authored_field": "data.document / page / annotations[].region",
     "provenance": "document provenance (source PDF + content hash — B-P1 gate)"},
]
