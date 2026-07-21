"""Pipeline integration for the dataset source (A-P2): materialize every dataset-bound data scene from its
table BEFORE the number-provenance gate + recompose, writing the real numbers + `value_source` into the
specs. Runs in the finish DAG right after word-sync.

  data.dataset + data.query + data.encode  →  data.series/items/segments + data.value_source
"""
from __future__ import annotations

import json
from pathlib import Path


def resolve_datasets(comp) -> int:
    """Resolve dataset bindings across a comp's frame specs, writing materialized data back (CRLF-preserving).
    Provenance-gated (an un-sourced dataset raises). Returns how many scenes were resolved."""
    from nolan.data import resolve_datasets_in_spec
    from nolan.hyperframes.edit import _project_dir
    pdir = Path(_project_dir(comp))
    frames = pdir / "compositions" / "frames"
    total = 0
    for sf in sorted(frames.glob("*.spec.json")):
        raw = sf.read_bytes()
        crlf = b"\r\n" in raw
        spec = json.loads(raw.decode("utf-8"))
        n = resolve_datasets_in_spec(spec, str(pdir))
        if n:
            out = (json.dumps(spec, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            if crlf:
                out = out.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            sf.write_bytes(out)
            total += n
    return total


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="nolan.hyperframes.datasets")
    ap.add_argument("comp")
    a = ap.parse_args()
    n = resolve_datasets(a.comp)
    print(f"resolved {n} dataset-bound scene(s) → real numbers materialized from cells")


if __name__ == "__main__":
    main()
