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

import re
from typing import Dict, List

from .verbs import apply_query

# a column is TEMPORAL if its name (or declared unit) reads as time — a line chart over such an x auto-gets
# the sweeping time-cursor (A-P2.5), so a time series reads as time advancing without the author toggling it.
_TEMPORAL = re.compile(r"(?:^|[_\s])(year|date|time|month|quarter|day|week|decade|yr|period|era)s?(?:$|[_\s])", re.I)


def _is_temporal(col, dataset) -> bool:
    if not col:
        return False
    if _TEMPORAL.search(str(col)):
        return True
    for c in getattr(dataset, "columns", []) or []:        # dataset column metadata: a temporal dtype/unit
        if c.get("name") == col and (str(c.get("dtype", "")).lower() in ("date", "datetime", "year")
                                     or _TEMPORAL.search(str(c.get("unit", "")))):
            return True
    return False


def _num(x):
    try:
        return round(float(x), 6)
    except (TypeError, ValueError):
        return x


def _rowval(r, key, default=""):
    return r.get(key, default) if key else default


# encode keys whose VALUE names a table column (vs. literal options like prefix/suffix/source_label)
_ENCODE_COL_KEYS = ("x", "y", "label", "value", "start", "end", "text")


def _available_columns(dataset, query: Dict) -> set:
    """The column names an encode/query may legally reference: the base table columns, plus any produced
    by the query (derive adds new names; aggregate keeps group_by + the aggregated columns)."""
    rows = getattr(dataset, "rows", None) or []
    base = set(rows[0].keys()) if rows else {c.get("name") for c in (getattr(dataset, "columns", []) or [])}
    base.discard(None)
    cols = set(base)
    q = query or {}
    cols |= set((q.get("derive") or {}).keys())
    agg = q.get("aggregate") or {}
    if agg.get("group_by"):
        cols.add(agg["group_by"])
    cols |= set((agg.get("agg") or {}).keys())
    return cols


def _validate_binding(block_type: str, enc: Dict, query: Dict, dataset) -> None:
    """Fail LOUD if an encode/query references a column the dataset doesn't have — else a typo'd column
    (`yr` for `year`) silently materializes zeros/empty labels and renders a wrong-but-plausible chart
    (the 'failures are loud' invariant). No-op when we can't determine the columns (empty table)."""
    avail = _available_columns(dataset, query)
    if not avail:
        return
    refs = {}  # column-name -> where it was referenced (for the message)
    for k in _ENCODE_COL_KEYS:
        v = (enc or {}).get(k)
        if isinstance(v, str) and v:
            refs.setdefault(v, f"encode.{k}")
    for c in (enc or {}).get("columns", []) or []:      # data_table explicit column list
        if isinstance(c, str) and c:
            refs.setdefault(c, "encode.columns")
    q = query or {}
    for c in (q.get("filter") or {}):
        refs.setdefault(c, "query.filter")
    if isinstance(q.get("sort"), dict) and q["sort"].get("by"):
        refs.setdefault(q["sort"]["by"], "query.sort.by")
    if isinstance(q.get("top_n"), dict) and q["top_n"].get("by"):
        refs.setdefault(q["top_n"]["by"], "query.top_n.by")
    for c in (q.get("select") or []):
        if isinstance(c, str):
            refs.setdefault(c, "query.select")
    unknown = {c: w for c, w in refs.items() if c not in avail}
    if unknown:
        detail = ", ".join(f"{c!r} ({w})" for c, w in sorted(unknown.items()))
        raise ValueError(
            f"dataset {getattr(dataset, 'id', '?')!r}: {block_type} binding references unknown column(s): "
            f"{detail}. Available: {sorted(avail)}. Fix the encode/query column name in the spec.")


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
    if block_type == "trajectory":                          # A-P4: dataset → ordered (x,y) points
        return {"points": [{"x": _num(_rowval(r, x, 0)), "y": _num(_rowval(r, y, 0)),
                            "label": str(_rowval(r, lab))} for r in rows]}
    if block_type == "data_table":                          # A-P3: dataset → a full table (columns × rows)
        cols = enc.get("columns") or (list(rows[0].keys()) if rows and isinstance(rows[0], dict) else [])
        cols = [c for c in cols if not str(c).startswith("_")]

        def _cell(r, c):
            v = r.get(c)
            if isinstance(v, float) and not isinstance(v, bool):
                v = _num(v)
            s = str(v)
            return (s + suf) if (c == val and suf) else ((pre + s) if (c == val and pre) else s)
        return {"columns": [str(c) for c in cols], "rows": [[_cell(r, c) for c in cols] for r in rows]}
    if block_type == "bullet_list":
        text_col = enc.get("text") or lab
        return {"items": [str(_rowval(r, text_col)) for r in rows]}
    if block_type == "ledger":                              # the ledger block reads `rows` [{title, desc?, meta?}]
        title_col = enc.get("text") or lab
        out = []
        for r in rows:
            row = {"title": str(_rowval(r, title_col))}
            if val and _rowval(r, val, None) is not None:
                row["meta"] = f"{pre}{_num(_rowval(r, val))}{suf}"
            out.append(row)
        return {"rows": out}
    # generic fallback: a value/label list under `items`
    return {"items": [{"value": _num(_rowval(r, val, 0)), "label": str(_rowval(r, lab))} for r in rows]}


def resolve_scene(scene: Dict, dataset) -> Dict:
    """Fill `scene.data` from `dataset` per its query+encode; stamp `value_source` (provenance) so the number
    gate passes. Mutates + returns the scene. Keeps `_dataset` for re-resolution/provenance."""
    d = scene.setdefault("data", {})
    enc = d.get("encode", {})
    _validate_binding(scene.get("type", ""), enc, d.get("query", {}), dataset)
    rows = apply_query(dataset.rows, d.get("query", {}))
    d.update(_materialize(scene.get("type", ""), rows, enc))
    d["value_source"] = dataset.meta.get("provenance") or f"dataset:{dataset.id}"
    d["_dataset"] = {"id": dataset.id, "query": d.get("query", {}), "encode": enc}
    # A-P2.5: a LINE chart over a TEMPORAL x auto-gets the time-cursor playhead (author forces it off with
    # `data.playhead: false`, which stays present and wins here).
    if scene.get("type") == "chart" and d.get("type") == "line" and "playhead" not in d \
            and _is_temporal(enc.get("x") or enc.get("label"), dataset):
        d["playhead"] = True
    # A-P3: resolve a data_table's `highlight:{where:{col:val}}` → the matching row index + the value column,
    # so a one-line beat spotlights the exact cell it names IN CONTEXT of the whole table.
    if scene.get("type") == "data_table":
        hl = d.get("highlight") or {}
        where = hl.get("where")
        if where and "row" not in hl:
            cols = d.get("columns", [])
            for idx, r in enumerate(rows):
                if all(str(r.get(k)) == str(v) for k, v in where.items()):
                    hl["row"] = idx
                    vc = enc.get("value") or enc.get("y")
                    col = vc if vc in cols else next(iter(where))
                    if col in cols:
                        hl["col"] = cols.index(col)
                    break
            d["highlight"] = hl
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
