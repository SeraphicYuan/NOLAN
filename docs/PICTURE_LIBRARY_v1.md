# Picture Library — v1

Date: 2026-06-25. A persistent, searchable, license-aware image store — the
still-image counterpart to the video library. Where acquisition (image-search
providers + link extractors) previously dumped files into ephemeral `.scratch/`,
the library warehouses them with provenance, dedup, curation, and **semantic
search**.

## Why (vs the video library)
Indexing video is expensive (download + transcribe + scene-detect), so that
library caches to avoid re-work. Images are cheap to re-fetch, so the picture
library's value is different:
- **Provenance & licensing** — store `license` + `source_url` per asset and
  filter to license-clean images (matters: DPLA/Europeana mix in lots of
  in-copyright material).
- **Persistence** — acquisition results stop evaporating into `.scratch`.
- **Dedup + reuse** — same image (by content hash) stored once, reused across projects.
- **Semantic search** — CLIP text→image: "soldiers in a trench" finds matching
  pictures across everything you've gathered.

## Architecture (`src/nolan/imagelib/`)
- `catalog.py` — `AssetCatalog`: SQLite. One row/asset: `content_hash` (dedup),
  `path`, `source`, `source_url`, `license`, `title`, `width/height`, `tags`,
  `query`, `status` (active|rejected), `added_at`. Filtered `list()` + counts.
- `embeddings.py` — `ClipEmbedder`: sentence-transformers `clip-ViT-B-32`,
  lazy-loaded. Embeds **images and text into one shared space** (so a text query
  retrieves images). Normalized for cosine.
- `store.py` — `ImageLibrary`: ties file storage + catalog + a ChromaDB `images`
  collection (manual CLIP embeddings). `add_file/add_url/add_result` (dedup by
  hash, copies into `files/<hash>`, embeds), `search` (CLIP query → Chroma →
  catalog join, active-only + license filter), `set_status` (reject also removes
  from the vector index), `list`, `stats`. `search_all()` merges global + project.

## Scopes (both inside the project tree)
- **global** → `_library/images/` (shared across projects)
- **project** → `projects/<name>/imagelib/`

Each holds `catalog.db`, `chroma/`, `files/`. Both are gitignored.

## CLI
```bash
nolan images search "steam locomotive" --scope both -p venezuela -k 12
nolan images search "anatomy" --license CC0          # license-filtered
nolan images add https://example.org/photo.jpg --source web --license CC0
nolan images add .scratch/extracted/www.gutenberg.org/manifest.json   # ingest a manifest
nolan images list --source wellcome -n 30
nolan images reject 42                                 # hide + de-index
nolan images stats
```

Acquisition → library in one step:
```bash
nolan image-search "world war 1 trench" -s wellcome --save            # -> global library
nolan image-search "favela" -s all --resolve --save --scope project -p venezuela
```

## Verified
- 10 unit tests (`tests/test_imagelib.py`): catalog dedup/list/status, store
  copy/dedup/dim-probe, **semantic search** (color-based FakeEmbedder → red image
  matches "red"), reject-removes-from-search, license filter, `add_url`, stats.
- Live CLIP end-to-end: ingested 5 Wellcome skeletons + 4 Openverse locomotives;
  "skeleton bones" → top-3 all skeletons (0.29), "railway locomotive engine" →
  top-3 all locomotives (0.30). Real text→image search confirmed across sources.

## match-broll integration (library-first)
`match_broll_v2` now searches the picture library (global + the project's, sharing
one CLIP embedder) **before** any external provider. Library candidates are
vision-scored on the *same* 0–10 scale as external hits (the scorer reads local
files); a candidate scoring ≥ `library_gate` (default 5) is copied into the
scene's `assets/broll/` and used — free, and it reuses curated/licensed assets.
Result includes `from_library` count. `use_library=True` by default.

> Thread-safety: the library is searched from match-broll's `ThreadPoolExecutor`,
> so `AssetCatalog`'s SQLite connection uses `check_same_thread=False` + an
> internal lock (it's created in one thread, read from worker threads).

## Hub UI
`/images` (card on the home page). Empty box → browse newest; type → CLIP
semantic search. Scope (global/project/both), license filter, per-tile **Reject**,
and a link to the source page. Thumbnails stream via `GET /api/images/raw`.
Endpoints: `/api/images/{search,list,raw,stats}` + `POST /api/images/{id}/reject`.

## Segment resolver integration
The asset-first `AssetResolver` (`src/nolan/segment/`) now has a **library source**:
for footage scenes, after an indexed-video segment-search miss, it CLIP-searches
the library (global + project) and uses the top still clearing `library_threshold`
(default 0.24 cosine) before escalating to external/ComfyUI. `resolved_source` is
recorded as `library(...)`. Wired via `SegmentBuilder._make_library_fn` (lazy:
loads CLIP only on the first footage scene). Uses a CLIP threshold (free/fast) —
match-broll uses vision scoring; the segment pipeline favours the cheap path.

## Promote project → global
`promote_to_global(project, asset_id)` copies a project asset's file + row +
embedding into the global library (dedup by hash). `nolan images promote <id>
-p <project>`, `POST /api/images/{id}/promote`, and a per-tile **Promote** button
(shown when a Project is set in the gallery).

## Limits / follow-ups
- First search/add loads CLIP (~600 MB download, then cached).
- Gallery ingest is URL-only; bulk **manifest** ingest stays on the CLI
  (`nolan images add <manifest.json>`).
- Resolver library matches set an absolute `matched_asset` path (not copied into
  the project) — fine locally; less portable than match-broll's project copy.

## Description-based matching (2026-06) — "video library for images"

Each asset can carry a **vision-generated description** (like the video library's
segment summaries), indexed with **BGE text embeddings** so b-roll is matched
**description ↔ description** instead of a scene intent vs a bare provider title.

- **Storage**: `catalog.assets.description` (auto-migrated) + a second ChromaDB
  collection `descriptions` (BGE `BAAI/bge-base-en-v1.5`, same model as
  `vector_search`). `ImageLibrary(describer=...)` auto-describes on ingest.
- **Generation**: `imagelib/describe.py::make_describer(config)` reuses the vision
  pipeline (`nolan.vision.describe_image`) — one provider, sync, thread-safe-ish.
- **Search**: `search_by_description` (BGE text→text), `search_hybrid`
  (0.6·description + 0.4·CLIP), `backfill_descriptions` for existing assets.
- **Unified matcher**: `external_assets.semantic_match_for_scene` —
  (1) **library-first** hybrid search (strict `library_first_gate=0.45`);
  (2) on a miss, external search → quality pre-filter → **describe + ingest** into
  the project library → re-search → accept best ≥ `sim_gate=0.30`. External search
  becomes an *ingest source*; the library grows and is reused across projects.
- **Wired in**: `match_broll_v2(semantic=True)` (default) builds the describer +
  project ingest library and runs **sequentially** (Chroma/vision aren't
  thread-safe; the describe cost caches for reuse). Hub `/api/match` accepts
  `semantic`. Tests: `tests/test_imagelib_descriptions.py`, `tests/test_semantic_match.py`.

Live: 2 b-roll scenes matched in ~26s — one via fresh ingest, one **reusing** the
other's ingested asset by description. Note: in a *sparse* library, reuse can be
loose; the strict library gate mitigates it, and `backfill_descriptions` on your
existing assets sharpens recall.
