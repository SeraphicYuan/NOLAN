"""Document GATE honesty test (the leg the `source`-OR-`document` gate fix was missing).

author.validate_spec must accept a document scene bound EITHER by a raw page `source` OR by an ingested
`document` id (the B-P2 path resolve_documents fills `source` from), and reject a document scene bound by
neither (an empty page). Without this, the gate can silently regress to requiring `source` (breaking the
ingested-paper path) or to accepting an empty document, with a green suite.
"""
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"
sys.path.insert(0, str(BRIDGE))
import author  # noqa: E402


def _doc_errs(data):
    spec = {"frames": [{"id": "f1", "dur": 8, "scenes": [
        {"id": "s1", "type": "document", "start": 0, "dur": 8, "data": data}]}]}
    return [e for e in author.validate_spec(spec) if "document" in e and "s1" in e]


def test_document_scene_with_raw_source_passes():
    assert not _doc_errs({"source": "assets/paper_p1.png"})


def test_document_scene_with_ingested_document_id_passes():
    # the B-P2 path: resolve_documents binds `source` from the layout map at finish time, so the gate
    # must NOT demand `source` up front.
    assert not _doc_errs({"document": "attention", "page": 1})


def test_document_scene_with_neither_is_rejected():
    errs = _doc_errs({"title": "a page with no page"})
    assert errs, "a document scene bound by neither source nor document must be rejected (empty page)"


# --- D4: annotations are gated against the vocabulary compose.py renders ---

def _ann_errs(annotations):
    # bound by a document so ONLY annotation errors remain
    return _doc_errs({"document": "attention", "page": 1, "annotations": annotations})


def test_valid_annotations_pass():
    assert not _ann_errs([
        {"type": "highlight", "region": "p1-b13"},                 # region-targeted, no text needed
        {"type": "label", "at": [0.2, 0.3], "text": "note"},       # text + explicit at
        {"type": "callout", "text": "screen-fixed card"},          # screen-fixed, needs only text
        {"type": "pullquote", "region": "p1-b2"},                  # text optional (lifted from region)
    ])


def test_unknown_annotation_type_is_rejected():
    assert _ann_errs([{"type": "hilight", "region": "p1-b13"}]), "a misspelled type must be rejected, not warn-skipped"


def test_targeted_annotation_without_target_is_rejected():
    # a highlight with no region/find/rect/at can never be placed → compose would silently drop it
    assert _ann_errs([{"type": "highlight", "color": "yellow"}])


def test_text_bearing_annotation_without_text_is_rejected():
    assert _ann_errs([{"type": "label", "at": [0.2, 0.3]}])        # label needs text
    assert _ann_errs([{"type": "callout"}])                        # callout needs text
