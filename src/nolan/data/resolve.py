"""Binding resolver — turn a data-viz scene's (`dataset`, `query`, `encode`) into the block's data shape,
filled with REAL numbers from the table, and stamp provenance so the A-P1 gate sees them as sourced.

The author writes the ENCODING (which columns map to x/y/label/value), never the values. This is the
grammar-of-graphics separation: data (the table) → encoding (the mapping) → mark (the block). One resolver,
many blocks — each block type declares how rows+encode become its canonical fields.

  scene.data = {"dataset":"electricity_share",
                "query":{"filter":{"year":[2023,2028]}},
                "encode":{"x":"year","y":"pct","suffix":"%"}}
  → after resolve: scene.data.series = [{"label":"2023","value":4.4}, {"label":"2028","value":12.0}],
                    scene.data.value_source = "<dataset provenance>"   (gate passes)
"""
from __future__ import annotations

from typing import Dict, List

from .verbs import apply_query


def _num(x):
    try:
        return round(float(x), 6)
    except (TypeError, ValueError):
        return x


def _rowval(r, key, default=""):
    return r.get(key, default) if key else default


def _materialize(block_type: str, rows: List[Dict], enc: Dict) -> Dict:
    """rows + encoding → the block's canonical data fields (only the DATA fields; kicker/title etc. are
    preserved by the caller). Encoding keys per block are documented in the catalog `data_shape`."""
    x, y = enc.get("x") or enc.get("label"), enc.get("y") or enc.get("value")
    lab = enc.get("label") or enc.get("x")
    val = enc.get("value") or enc.get("y")
    pre, suf = enc.get("prefix", ""), enc.get("suffix", "")

    if block_type == "chart":
        return {"series": [{"label": str(_rowval(r, x)), "value": _num(_rowval(r, y, 0))} for r in rows]}
    if block_type in ("pie",):
        return {"segments": [{"label": str(_rowval(r, lab)), "value": _num(_rowval(r, val, 0))} for r in rows]}
    if block_type in ("stat", "scale", "spectrum"):
        items = [{"value": _num(_rowval(r, val, 0)), "label": str(_rowval(r, lab))} for r in rows]
        if pre:
            items and items[0].__setitem__("prefix", pre)
        for it in items:
            if suf:
                it["suffix"] = suf
        return {"items": items}
    if block_type == "sankey":
        targets = [{"label": str(_rowval(r, lab)), "value": _num(_rowval(r, val, 0))} for r in rows]
        total = round(sum(t["value"] for t in targets if isinstance(t["value"], (int, float))), 6)
        return {"source": {"label": enc.get("source_label", "Total"), "value": total}, "targets": targets}
    if block_type == "funnel":
        return {"stages": [{"label": str(_rowval(r, lab)), "value": _num(_rowval(r, val, 0))} for r in rows]}
    if block_type == "spans":
        return {"spans": [{"label": str(_rowval(r, lab)),
                           "start": _num(_rowval(r, enc.get("start"), 0)),
                           "end": _num(_rowval(r, enc.get("end"), 0))} for r in rows]}
    if block_type in ("bullet_list", "ledger"):
        text_col = enc.get("text") or lab
        return {"items": [str(_rowval(r, text_col)) for r in rows]}
    # generic fallback: a value/label list under `items`
    return {"items": [{"value": _num(_rowval(r, val, 0)), "label": str(_rowval(r, lab))} for r in rows]}


def resolve_scene(scene: Dict, dataset) -> Dict:
    """Fill `scene.data` from `dataset` per its query+encode; stamp `value_source` (provenance) so the number
    gate passes. Mutates + returns the scene. Keeps `_dataset` for re-resolution/provenance."""
    d = scene.setdefault("data", {})
    rows = apply_query(dataset.rows, d.get("query", {}))
    d.update(_materialize(scene.get("type", ""), rows, d.get("encode", {})))
    d["value_source"] = dataset.meta.get("provenance") or f"dataset:{dataset.id}"
    d["_dataset"] = {"id": dataset.id, "query": d.get("query", {}), "encode": d.get("encode", {})}
    return scene


def resolve_datasets_in_spec(spec: Dict, comp) -> int:
    """Walk a spec; for every scene that BINDS a dataset (`data.dataset`), load it (provenance-gated) and
    materialize the block's data from real cells. Returns how many scenes were resolved. A missing/unresolved
    dataset is left as-is (the number gate will then flag its bare numbers, if any)."""
    from .registry import load_dataset
    n = 0
    for fr in spec.get("frames", []):
        for sc in fr.get("scenes", []):
            did = (sc.get("data", {}) or {}).get("dataset")
            if not did:
                continue
            ds = load_dataset(comp, did)
            if ds is not None:
                resolve_scene(sc, ds)
                n += 1
    return n
