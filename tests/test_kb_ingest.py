"""KB ingest: routing, raw-note frontmatter, and hash-dedup (offline)."""
import importlib


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("NOLAN_KB_VAULT", str(tmp_path / "vault"))
    from nolan.kb import paths
    importlib.reload(paths)                      # pick up the temp vault root
    from nolan.kb import ingest as ingest_fn, KBCatalog
    return ingest_fn, KBCatalog


def test_text_ingest_writes_raw_note(tmp_path, monkeypatch):
    ing, KBCatalog = _fresh(tmp_path, monkeypatch)
    cat = KBCatalog()
    text = "Flow cut: match the motion direction across the cut so the eye keeps moving."
    r = ing(text, source_type="text", catalog=cat)
    assert not r.deduped
    assert r.source_type == "text"
    assert r.raw_path.exists()
    body = r.raw_path.read_text(encoding="utf-8")
    assert body.startswith("---")
    assert "kb: raw" in body and "status: raw" in body and "source_type: text" in body
    assert text in body


def test_ingest_is_idempotent_by_content_hash(tmp_path, monkeypatch):
    ing, KBCatalog = _fresh(tmp_path, monkeypatch)
    cat = KBCatalog()
    text = "Smash cut: break rhythm with a sudden hard cut; kill the audio for contrast."
    r1 = ing(text, source_type="text", catalog=cat)
    r2 = ing(text, source_type="text", catalog=cat)
    assert r2.deduped and r2.id == r1.id
    assert cat.count() == 1


def test_pdf_without_pymupdf_errors_loudly(tmp_path, monkeypatch):
    ing, _ = _fresh(tmp_path, monkeypatch)
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    try:
        import fitz  # noqa: F401
    except ImportError:
        import pytest
        with pytest.raises(RuntimeError, match="PyMuPDF"):
            ing(str(pdf), source_type="file")
