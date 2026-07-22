"""Writers for the two project source registries (the missing create surface the Data panel needs).

Dataset + document were consume-complete but had no writer — a table could only enter the provenance-gated
registry by hand-editing index.json, and a PDF only via a bare CLI module. These test the new writers:
provenance-gating on create (mirrors the load gate), column inference, and the image->PDF document path.
"""
import io

import pytest


def test_register_dataset_is_provenance_gated_and_infers_columns(tmp_path):
    from nolan.data import (register_dataset, list_datasets, load_dataset,
                            dataset_preview, delete_dataset)
    csv = b"year,pct,name\n2020,4.4,A\n2024,12.0,B\n"
    with pytest.raises(ValueError):                                   # no provenance -> cannot register
        register_dataset(tmp_path, filename="t.csv", title="T", provenance="", table_bytes=csv)
    meta = register_dataset(tmp_path, filename="t.csv", title="Share", provenance="IEA 2024", table_bytes=csv)
    assert meta["id"] == "t"
    assert {c["name"]: c["dtype"] for c in meta["columns"]} == {"year": "int", "pct": "float", "name": "str"}
    assert [d["id"] for d in list_datasets(tmp_path)] == ["t"]
    assert load_dataset(tmp_path, "t").rows[0]["year"] == 2020        # loads through the gate, dtype coerced
    pv = dataset_preview(tmp_path, "t")
    assert pv["n_rows"] == 2 and pv["columns"][0] == "year"
    assert delete_dataset(tmp_path, "t") and list_datasets(tmp_path) == []


def test_register_dataset_rejects_a_non_table_file(tmp_path):
    from nolan.data import register_dataset
    with pytest.raises(ValueError):
        register_dataset(tmp_path, filename="x.txt", title="X", provenance="p", table_bytes=b"hi")


def test_ingest_document_accepts_an_image_and_stamps_provenance(tmp_path):
    pytest.importorskip("fitz")
    Image = pytest.importorskip("PIL.Image")
    from nolan.document import (ingest_document, list_documents,
                               document_summary, delete_document)
    buf = io.BytesIO()
    Image.new("RGB", (400, 560), "white").save(buf, format="PNG")
    lay = ingest_document(tmp_path, "scan.png", buf.getvalue())
    assert lay["page_count"] == 1 and lay["provenance"].startswith("pdf:")
    assert [d["id"] for d in list_documents(tmp_path)] == [lay["id"]]
    assert document_summary(tmp_path, lay["id"])["page_count"] == 1
    assert delete_document(tmp_path, lay["id"]) and list_documents(tmp_path) == []


def test_data_brief_surfaces_datasets_for_authoring(tmp_path):
    # the discover leg: an author must SEE what's bindable, or they invent numbers the gate then rejects
    from nolan.data import register_dataset
    from nolan.hyperframes.data_brief import data_brief
    assert data_brief(tmp_path) == ""                                # honest silence when there's nothing
    register_dataset(tmp_path, filename="gpu.csv", title="GPU", provenance="Epoch AI",
                     table_bytes=b"year,v\n2016,1.0\n2024,9.0\n", when_to_use="cost beat")
    brief = data_brief(tmp_path)
    assert "`gpu`" in brief and "dataset" in brief and "Epoch AI" in brief and "year" in brief
