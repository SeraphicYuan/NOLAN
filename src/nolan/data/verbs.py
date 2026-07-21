"""Curated data verbs — the shaping layer between a dataset and a block's data shape.

A `query` is a declarative dict; ops apply in a canonical order so the same query always yields the same
rows (deterministic, gate-able). Rows are list-of-dicts; internally we shape with **pandas** (robust dtype
handling, real time-series ops) but the SIGNATURE is list-of-dicts in / list-of-dicts out, so callers (the
resolver, the gate) never touch pandas.

Query grammar (all keys optional):
  {
    "filter":    {"year": [2023, 2028]} | {"pct": {">=": 5}} | {"country": "US"},
    "aggregate": {"group_by": "category", "agg": {"value": "sum"}},   # sum|mean|count|min|max
    "derive":    {"share": ["share_of_total", "value"],              # add computed columns
                  "growth": ["pct_change", "value"],                 # time-series (run AFTER sort)
                  "cum":    ["cumsum", "value"],
                  "avg3":   ["rolling_mean", "value", 3]},
    "sort":      {"by": "year"} | {"by": "value", "desc": true},
    "top_n":     {"n": 5, "by": "value"},
    "select":    ["year", "pct"],
  }
Canonical order: filter → aggregate → SORT → derive → top_n → select (sort precedes derive so a time-series
computation runs in the intended order — year-over-year on year-sorted rows).
"""
from __future__ import annotations

import math
from typing import Dict, List

import pandas as pd

_CMP = {">": "gt", ">=": "ge", "<": "lt", "<=": "le", "==": "eq", "!=": "ne"}
_AGG = {"sum", "mean", "count", "min", "max"}


def _clean(v):
    """numpy/pandas scalar → plain Python; NaN/NaT → None (JSON-safe, matches the hand-rolled backend)."""
    if v is None:
        return None
    try:
        if isinstance(v, float) and math.isnan(v):
            return None
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):                                   # numpy scalar
        v = v.item()
    if isinstance(v, float):
        return round(v, 6)
    return v


def _to_rows(df: pd.DataFrame) -> List[Dict]:
    return [{k: _clean(v) for k, v in rec.items()} for rec in df.to_dict("records")]


def _derive(df: pd.DataFrame, spec: Dict) -> pd.DataFrame:
    for new_col, expr in (spec or {}).items():
        if not isinstance(expr, list) or not expr:
            continue
        fn = expr[0]
        src = expr[1] if len(expr) > 1 else None
        s = pd.to_numeric(df[src], errors="coerce") if (src and src in df) else pd.Series([None] * len(df))
        if fn == "share_of_total":
            tot = s.sum()
            df[new_col] = (s / tot * 100).round(2) if tot else None
        elif fn == "pct_change":
            df[new_col] = (s.pct_change() * 100).round(2)
        elif fn == "delta":
            df[new_col] = s.diff().round(6)
        elif fn == "cumsum":
            df[new_col] = s.cumsum().round(6)
        elif fn == "rolling_mean":
            w = int(expr[2]) if len(expr) > 2 else 3
            df[new_col] = s.rolling(w, min_periods=1).mean().round(6)
    return df


def apply_query(rows: List[Dict], query: Dict) -> List[Dict]:
    """Apply a query to rows (list-of-dicts) → new rows. Never mutates the source."""
    df = pd.DataFrame(list(rows or []))
    q = query or {}
    if df.empty:
        return []

    if q.get("filter"):
        for col, cond in q["filter"].items():
            if col not in df:
                continue
            if isinstance(cond, dict):                       # {">=": 5}
                for op, thr in cond.items():
                    m = _CMP.get(op)
                    if m:
                        df = df[getattr(pd.to_numeric(df[col], errors="coerce"), m)(thr)]
            elif isinstance(cond, list):
                df = df[df[col].isin(cond)]
            else:
                df = df[df[col] == cond]

    if q.get("aggregate"):
        gb = q["aggregate"].get("group_by")
        agg = {c: fn for c, fn in (q["aggregate"].get("agg") or {}).items() if fn in _AGG}
        if gb and gb in df and agg:
            df = df.groupby(gb, sort=False, as_index=False).agg(agg)

    if q.get("sort", {}).get("by") in df.columns:
        s = q["sort"]
        df = df.sort_values(by=s["by"], ascending=not s.get("desc"), kind="stable")

    if q.get("derive"):
        df = df.reset_index(drop=True)
        df = _derive(df, q["derive"])

    if q.get("top_n", {}).get("by") in df.columns:
        tn = q["top_n"]
        df = df.nlargest(int(tn.get("n", 5)), tn["by"])
    elif q.get("top_n"):
        df = df.head(int(q["top_n"].get("n", 5)))

    if q.get("select"):
        cols = [c for c in q["select"] if c in df.columns]
        df = df[cols]

    return _to_rows(df)
