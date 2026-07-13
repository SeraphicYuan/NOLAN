"""compose.document must not KeyError on an unresolved find-annotation (holbein POST_MORTEM #6).

A `{type:highlight, find:"Death"}` on a woodcut with no text layer never gets a `rect` from
resolve_doc_annotations.py; compose used to crash at `an["rect"]`. It must skip it with a warning and
still render the resolved annotations.
"""
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COMPOSE = REPO / "render-service" / "_lab_hyperframes" / "bridge" / "compose.py"


def _compose():
    spec = importlib.util.spec_from_file_location("compose", COMPOSE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_document_skips_unresolved_annotations_without_crashing():
    compose = _compose()
    scene = {"id": "s1", "type": "document", "start": 0, "dur": 6, "data": {
        "source": "assets/page.jpg",
        "annotations": [
            {"type": "highlight", "find": "Death"},                 # unresolved -> no rect (used to KeyError)
            {"type": "underline", "rect": [0.1, 0.2, 0.3, 0.02]},   # resolved -> must render
            {"type": "label", "find": "x"},                         # missing at/text -> skipped
        ]}}
    html = compose.compose_frame("01", 6, [scene], theme="dark-botanical")   # must NOT raise
    assert "s1-ul0" in html or "s1-ul" in html          # resolved underline rendered
    assert "s1-hl" not in html                          # unresolved highlight skipped, not crashed
