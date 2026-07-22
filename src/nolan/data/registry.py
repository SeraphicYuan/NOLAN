"""Dataset registry + loader (provenance-gated).

A project keeps its data under `<comp>/datasets/`: an `index.json` of metadata + the table files (CSV/JSON).
Loading is PROVENANCE-GATED — a dataset with no `provenance` cannot register (mirrors `asset_gate`: an
un-sourced number is exactly the fabrication A-P1 blocks). The loader coerces column dtypes so downstream
verbs get real numbers.

index.json shape:
  {
    "electricity_share": {
      "title": "US data-center share of US electricity",
      "file": "electricity_share.csv",
      "columns": [{"name":"year","dtype":"int"}, {"name":"pct","unit":"%","dtype":"float"}],
      "provenance": "IEA Electricity 2024, table 3",   # REQUIRED — no provenance, no dataset
      "grain": "one row per calendar year",
      "when_to_use": "the electricity-cost beats"
    }
  }
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Dataset:
    id: str
    rows: List[Dict]
    meta: Dict = field(default_factory=dict)

    @property
    def provenance(self) -> str:
        return self.meta.get("provenance", "")

    @property
    def columns(self) -> List[Dict]:
        return self.meta.get("columns", [])


def _datasets_dir(comp) -> Path:
    p = Path(comp)
    if (p / "datasets").exists():
        return p / "datasets"
    try:
        from nolan.hyperframes.edit import _project_dir
        return Path(_project_dir(comp)) / "datasets"
    except Exception:
        return p / "datasets"


def _index(comp) -> Dict:
    idx = _datasets_dir(comp) / "index.json"
    if not idx.exists():
        return {}
    return json.loads(idx.read_text(encoding="utf-8"))


def list_datasets(comp) -> List[Dict]:
    """Every registered dataset's metadata (for authoring — what tables exist + when_to_use)."""
    return [{"id": k, **v} for k, v in _index(comp).items()]


_COERCE = {"int": lambda x: int(float(x)), "float": lambda x: float(x), "str": str}


def _load_table(path: Path, columns: List[Dict]) -> List[Dict]:
    dtypes = {c["name"]: c.get("dtype", "str") for c in (columns or [])}
    if path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        rows = raw if isinstance(raw, list) else (raw.get("rows") or [])
    else:                                                   # csv
        with path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        row = {}
        for k, v in r.items():
            fn = _COERCE.get(dtypes.get(k, "str"))
            try:
                row[k] = fn(v) if (fn and v not in (None, "")) else v
            except (TypeError, ValueError):
                row[k] = v
        out.append(row)
    return out


def load_dataset(comp, dataset_id: str) -> Optional[Dataset]:
    """Load a dataset by id from the project registry. Provenance-gated: raises if the dataset has no
    `provenance` (an un-sourced table is the fabrication the number gate exists to stop). Returns None if
    the id isn't registered (caller decides — the gate treats an unresolved binding as unsourced)."""
    meta = _index(comp).get(dataset_id)
    if not meta:
        return None
    if not str(meta.get("provenance", "")).strip():
        raise ValueError(f"dataset {dataset_id!r} has no `provenance` — an un-sourced table cannot register "
                         f"(add a citation/source to datasets/index.json).")
    f = meta.get("file")
    if not f:
        raise ValueError(f"dataset {dataset_id!r} has no `file`.")
    path = _datasets_dir(comp) / f
    if not path.exists():
        raise FileNotFoundError(f"dataset {dataset_id!r} file not found: {path}")
    return Dataset(id=dataset_id, rows=_load_table(path, meta.get("columns", [])), meta=meta)


# --- authoring/UI writers (the missing create + discover surface for the provenance-gated registry) ---

def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")
    return s or "dataset"


def _guess_dtype(values) -> str:
    """Best-effort column dtype from sampled cell values (int < float < str). Coercion in _load_table is
    try/except, so a wrong guess degrades to the raw string rather than crashing."""
    seen = set()
    for v in values:
        if v in (None, ""):
            continue
        sv = str(v).strip()
        try:
            int(sv); seen.add("int"); continue
        except ValueError:
            pass
        try:
            float(sv); seen.add("float"); continue
        except ValueError:
            seen.add("str")
    if not seen or "str" in seen:
        return "str"
    return "float" if "float" in seen else "int"


def _infer_columns(rows: List[Dict]) -> List[Dict]:
    if not rows:
        return []
    return [{"name": k, "dtype": _guess_dtype([r.get(k) for r in rows[:200]])}
            for k in rows[0].keys()]


def register_dataset(comp, *, filename: str, title: str, provenance: str,
                     table_bytes: Optional[bytes] = None, table_path=None,
                     dataset_id: Optional[str] = None, columns: Optional[List[Dict]] = None,
                     when_to_use: Optional[str] = None, grain: Optional[str] = None) -> Dict:
    """Write a table file into ``<comp>/datasets/`` and register it in ``index.json``. PROVENANCE-GATED —
    an un-sourced table cannot register (mirrors :func:`load_dataset`). Columns are inferred from the
    table if not given. Validates the table parses + loads through the gate before returning its metadata.
    """
    if not str(provenance or "").strip():
        raise ValueError("a dataset needs `provenance` (a citation/source) — an un-sourced table cannot "
                         "register (the fabrication the number gate exists to stop)")
    if table_bytes is None:
        if not table_path:
            raise ValueError("register_dataset needs table_bytes or table_path")
        table_bytes = Path(table_path).read_bytes()
    fn = Path(filename).name
    if Path(fn).suffix.lower() not in (".csv", ".json"):
        raise ValueError(f"unsupported table {fn!r} — use a .csv or .json file")
    ddir = _datasets_dir(comp)
    ddir.mkdir(parents=True, exist_ok=True)
    did = _slug(dataset_id or Path(fn).stem or title)
    (ddir / fn).write_bytes(table_bytes)
    try:
        if not columns:
            rows = _load_table(ddir / fn, [])
            if not rows:
                raise ValueError(f"table {fn!r} has no rows")
            columns = _infer_columns(rows)
    except Exception:
        (ddir / fn).unlink(missing_ok=True)                 # don't leave an orphan table on a bad parse
        raise
    meta = {"title": title or did, "file": fn, "columns": columns, "provenance": provenance.strip()}
    if when_to_use:
        meta["when_to_use"] = when_to_use
    if grain:
        meta["grain"] = grain
    idx = _index(comp)
    idx[did] = meta
    (ddir / "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    load_dataset(comp, did)                                  # final gate: it must load through the provenance gate
    return {"id": did, **meta}


def delete_dataset(comp, dataset_id: str) -> bool:
    """Remove a dataset from the registry (and its table file if no other entry references it)."""
    idx = _index(comp)
    meta = idx.pop(dataset_id, None)
    if meta is None:
        return False
    ddir = _datasets_dir(comp)
    f = meta.get("file")
    if f and (ddir / f).exists() and not any(m.get("file") == f for m in idx.values()):
        (ddir / f).unlink()
    (ddir / "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def dataset_preview(comp, dataset_id: str, n: int = 8) -> Optional[Dict]:
    """A dataset's metadata + first ``n`` rows as a table (for a UI panel / authoring discovery)."""
    ds = load_dataset(comp, dataset_id)
    if ds is None:
        return None
    cols = [c["name"] for c in (ds.meta.get("columns") or [])] or (list(ds.rows[0].keys()) if ds.rows else [])
    return {"id": ds.id, "meta": ds.meta, "columns": cols, "n_rows": len(ds.rows),
            "rows": [[r.get(c, "") for c in cols] for r in ds.rows[:n]]}
