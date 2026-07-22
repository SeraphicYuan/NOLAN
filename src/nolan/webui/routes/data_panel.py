"""Project Data panel — the create + discover surface for the two provenance-gated source registries.

Datasets (`<comp>/datasets/`) and documents (`<comp>/documents/`) were consume-complete (the finish DAG
resolves + renders them) but had NO web input and were invisible to the author. This page closes that: per
composition, upload a CSV/JSON table (→ provenance-gated dataset) or a PDF/image (→ ingested document), list
what exists with a preview, and delete. Thin wrappers over the tested backends in `nolan.data` /
`nolan.document`; the same registries feed the authoring discovery block (nolan.data/document `list_*`).
"""
import asyncio

from fastapi import Body, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from nolan import data as ndata
from nolan import document as ndoc
from nolan import hyperframes as hfedit


def register(app, ctx):
    dp_template = ctx.templates_dir / "data_panel.html"

    def _guard(fn, *a, **k):
        try:
            return fn(*a, **k)
        except (FileNotFoundError, KeyError) as e:
            raise HTTPException(status_code=404, detail=str(e))
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ---- page
    @app.get("/data", response_class=HTMLResponse)
    async def data_home():
        if dp_template.exists():
            return dp_template.read_text(encoding="utf-8")
        return "<h1>Data panel template not found</h1>"

    # ---- read / discover
    @app.get("/api/data/compositions")
    async def data_compositions():
        return {"compositions": hfedit.discover_compositions()}

    @app.get("/api/data/datasets")
    async def data_datasets(comp: str = Query(...)):
        out = []
        for d in _guard(ndata.list_datasets, comp):
            out.append(_guard(ndata.dataset_preview, comp, d["id"])
                       or {"id": d["id"], "meta": d, "columns": [], "rows": [], "n_rows": 0})
        return {"comp": comp, "datasets": out}

    @app.get("/api/data/documents")
    async def data_documents(comp: str = Query(...)):
        out = [_guard(ndoc.document_summary, comp, d["id"]) or d
               for d in _guard(ndoc.list_documents, comp)]
        return {"comp": comp, "documents": out}

    @app.get("/api/data/document/image")
    async def data_document_image(comp: str = Query(...), path: str = Query(...)):
        from nolan.document.registry import _documents_dir
        base = _documents_dir(comp).resolve()
        target = (base / path).resolve()
        if base not in target.parents or not target.is_file():   # no path traversal outside documents/
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(str(target))

    # ---- write
    @app.post("/api/data/dataset/upload")
    async def data_dataset_upload(comp: str = Form(...), title: str = Form(...),
                                  provenance: str = Form(...), when_to_use: str = Form(""),
                                  grain: str = Form(""), file: UploadFile = File(...)):
        raw = await file.read()
        return await asyncio.to_thread(
            _guard, ndata.register_dataset, comp,
            filename=file.filename, title=title, provenance=provenance,
            table_bytes=raw, when_to_use=(when_to_use or None), grain=(grain or None))

    @app.post("/api/data/dataset/delete")
    async def data_dataset_delete(payload: dict = Body(...)):
        return {"deleted": _guard(ndata.delete_dataset, payload.get("comp"), payload.get("id"))}

    @app.post("/api/data/document/upload")
    async def data_document_upload(comp: str = Form(...), file: UploadFile = File(...),
                                   doc_id: str = Form("")):
        raw = await file.read()
        lay = await asyncio.to_thread(_guard, ndoc.ingest_document, comp, file.filename, raw,
                                      (doc_id or None))
        return {"id": lay["id"], "page_count": lay.get("page_count"), "provenance": lay.get("provenance")}

    @app.post("/api/data/document/delete")
    async def data_document_delete(payload: dict = Body(...)):
        return {"deleted": _guard(ndoc.delete_document, payload.get("comp"), payload.get("id"))}
