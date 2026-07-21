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
