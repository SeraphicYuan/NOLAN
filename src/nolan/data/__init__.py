"""`nolan.data` — data as a first-class SOURCE (Track A of docs/SOURCES_ROADMAP.md).

A dataset is a small table (rows = list-of-dicts) with provenance. A data-viz scene BINDS to it by query +
encoding, and the resolver pulls REAL numbers into the block's data shape — the author never types a value,
so a chart/pie/sankey can't fabricate the data it demands (the A-P1 gate). Verbs are pure-Python (video-essay
tables are tiny); the interface is backend-agnostic, so pandas can back it later for heavy data.

  registry.load_dataset(comp, id) -> Dataset(rows, meta)   # provenance-gated
  verbs.apply_query(rows, query)  -> rows                   # filter/select/sort/top_n/aggregate/derive
  resolve.resolve_scene(scene, dataset) -> materialized block data (+ value_source provenance)
"""
from .verbs import apply_query                              # noqa: F401
from .registry import (Dataset, load_dataset, list_datasets,  # noqa: F401
                       register_dataset, delete_dataset, dataset_preview)
from .resolve import resolve_scene, resolve_cell, resolve_datasets_in_spec  # noqa: F401
