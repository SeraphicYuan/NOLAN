"""Project data -> authoring brief (the discover leg of the dataset/document sources).

Both registries were consume-complete but invisible to the author: `list_datasets`/`list_documents` had no
call sites, so an author was told they *could* bind a dataset/document but never *which ones exist* — and so
defaulted to inventing numbers (which then trip the A-P1 number gate). This surfaces a comp's registered
datasets + ingested documents into the authoring kickoff so the author BINDS real data instead.

Mirrors `layout_brief.theme_layout_brief`: a ready-to-inject markdown string, "" when there's nothing to say.
"""
from __future__ import annotations

from typing import Optional


def data_brief(comp) -> str:
    """Markdown listing a comp's datasets (with columns + a bind example) and documents (with region ids).
    Empty string when the project has neither — an honest silence (nothing to steer toward)."""
    try:
        from nolan.data import list_datasets
        datasets = list_datasets(comp)
    except Exception:
        datasets = []
    try:
        from nolan.document import list_documents, document_summary
        docs = list_documents(comp)
    except Exception:
        docs, document_summary = [], None

    if not datasets and not docs:
        return ""

    L = ["## Project data — BIND it, do not invent numbers",
         "This project has SOURCED data. A data-viz block must pull its values from a dataset (the number "
         "gate rejects hand-typed values with no `value_source`); a paper/scan is targeted by a `document` "
         "scene. Use the ids below."]

    if datasets:
        L.append("\n### Datasets — `data:{dataset, query, encode}` (the resolver fills the numbers + provenance)")
        for d in datasets:
            cols = ", ".join(f"`{c.get('name')}`:{c.get('dtype','str')}" for c in (d.get("columns") or []))
            when = f" — _{d['when_to_use']}_" if d.get("when_to_use") else ""
            L.append(f"- **`{d['id']}`** — {d.get('title', d['id'])}{when}")
            L.append(f"  - columns: {cols or '(none declared)'}  ·  source: {d.get('provenance','?')}")
            names = [c.get("name") for c in (d.get("columns") or [])]
            if len(names) >= 2:
                L.append(f'  - bind e.g. `"data":{{"type":"line","dataset":"{d["id"]}",'
                         f'"encode":{{"x":"{names[0]}","y":"{names[1]}"}}}}`')

    if docs:
        L.append("\n### Documents — `data:{document, page, annotations:[{type, region}]}` (region zoom / highlight)")
        for d in docs:
            summ = None
            if document_summary:
                try:
                    summ = document_summary(comp, d["id"])
                except Exception:
                    summ = None
            rids = ", ".join((summ or {}).get("region_ids", [])[:10]) if summ else ""
            pc = (summ or d).get("page_count", "?")
            L.append(f"- **`{d['id']}`** — {d.get('source', d['id'])} ({pc} pages)  ·  source: {d.get('provenance','?')}")
            if rids:
                L.append(f"  - target region ids: {rids}{' …' if summ and len(summ.get('region_ids', [])) > 10 else ''}")
            else:
                L.append("  - no text layer — target by `find:\"phrase\"` or an explicit rect")

    return "\n".join(L)
