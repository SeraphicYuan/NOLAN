# Roadmap: typed sources (data + document)

Tracker for making the pool a **typed source registry** (media / data / document) so data-heavy and
paper-deep-dive essays stop hallucinating numbers and can present real data in context. Design detail:
`docs/DATA_SOURCE_DESIGN.md`. Every item follows the module contract (`docs/WIRING_CHECKLIST.md`): registry
+ authored field + executor + provenance gate + honesty test + live verify. Sizes: S≈hours, M≈half-day, L≈multi-day.

## Done (reveal-sync session, 2026-07-20/21)
- [x] Reveal-sync program (spread/anchor/ground/character, placement hardening + LIS containment, autoground)
- [x] #1 text VO-sync (`_retime_lines` → `data._line_cues`; `highlight_statement` reveals lines at the read)
- [x] #2 text reveal-character (statement entrance uses `_reveal_ease`)
- [x] #3 number-provenance SOFT guard (`_number_provenance_flags`, in `sync --report` + the finish gate)

## TRACK A — Data as a source

### A-P1 · Provenance floor (hard gate) — S — **DONE (2026-07-21)**
- [x] `value_source` authored field (element-level or scene-level `data.value_source`) exempts a number
- [x] `_number_provenance_flags` traces to (a) spoken-in-VO or (b) `value_source`; (c) dataset comes with A-P2
- [x] HARD gate: finish DAG RAISES on a fabricated number (outside the try/except so it truly blocks), with
      fix guidance + `HF_ALLOW_UNSOURCED=1` escape hatch
- [x] documented in catalog `_doc`; honesty test (fabricated fails, spoken/sourced passes); essay sankey
      hard-failed → converted to an honest bullet_list of the 5 cost categories → gate passes
- [ ] (deferred) author.py static warning — skipped as too noisy; the VO-aware sync gate is the real check

### A-P2 · Dataset source + binding resolver — L — **CORE DONE (2026-07-21)**
- [x] `datasets/` dir + `datasets/index.json` registry (`nolan/data/registry.py`)
- [x] provenance gate: `load_dataset` raises on an un-sourced table
- [x] `nolan/data/verbs.py` — **pandas-backed** (pandas 2.2.3, numpy pinned 2.2.6) curated verbs incl. time
      series (pct_change/cumsum/rolling); canonical order sort-before-derive; never mutates source
- [x] binding resolver (`nolan/data/resolve.py`): `dataset`+`query`+`encode` → chart/stat/scale/pie/sankey/
      funnel/spans/bullet_list shapes + `value_source` stamp; `nolan/hyperframes/datasets.py` writes specs,
      wired into the finish DAG (step 2a, before the gate + recompose)
- [x] A-P1 gate reads dataset-sourced numbers as legit (option c); documented in catalog `_doc`
- [x] tests (`tests/test_data_source.py`, fake data) + live essay demo: bound 03-boom/s4 electricity chart to
      an `electricity_share` dataset → numbers from cells, gate passes
- [x] (follow-up) resolver↔shape parity honesty test (caught+fixed a real ledger `items`→`rows` drift)

### A-P2.5 · Time-series motion floor — M — **CORE DONE (2026-07-21)**
- [x] the line chart already reveals points along time (`times[i]` = VO-synced `_cue` or auto-spread) — that
      IS the `along_time` behavior; the sweep makes it read as time advancing
- [x] `data.playhead` on a line chart: a vertical time-cursor sweeps left→right IN SYNC with the draw
      (transform-based, seek-safe); points/values reveal as it reaches them
- [x] documented on `chart.type` in the catalog; playhead honesty check in `check_reveal_sync`; provenance
      gate applies (a dataset-bound line passes) · live demo: essay 03-boom/s4 electricity chart → a 9-point
      line from the `electricity_share` dataset (2020–2028) with a sweeping playhead
- [x] (follow-up) value TICKER rides the cursor head (snaps to each point); playhead auto-enables for a line chart over a temporal x

### A-P3 · One-line → whole-table operator — DONE (2026-07-21)
- [x] `data_table` block: a dataset as a full table (columns × rows from real cells) with ONE cell SPOTLIGHTED
- [x] `highlight:{where:{col:val}}` → the matching row + value column (resolver); a one-line beat names a
      number, the whole series shows with that cell lit. Rendered + tests (`test_data_table_*`).

### A-P4 · New time-series marks — DONE (2026-07-21)
- [x] `trajectory` (connected scatter — path through 2-D over time; dataset-bound via encode x/y/label),
      `stream` (stacked area / streamgraph — composition over time, left→right sweep), `bar_race` (ranked
      bars that grow + REORDER across steps with a period ticker) — all in compose_extension.py
- [x] each: catalog entry (+fn) + REQUIRED + _DATAVIZ provenance gate + honesty test; all rendered + looked at
- [ ] (follow-up) dataset-pivot binding for stream/bar_race (category × step); milestones/small-multiples

## TRACK B — Paper / document as a source

### B-P0 · Sample videos (user) → pin the motion set — GATE
- [ ] user sends 2–3 reference clips → lock the block/motion list

### B-P1 · Document source — CORE DONE (2026-07-21)
- [x] `nolan/document/ingest.py` (PyMuPDF/fitz): PDF → a rendered PNG per page + a LAYOUT MAP of regions
      (heading / paragraph / figure(raster) / word) with NORMALIZED bboxes (0..1, resolution-independent)
- [x] `nolan/document/registry.py`: provenance-gated registry (raises on an un-sourced document — the paper
      analogue of the A-P1 number gate), `list_documents`, `region_bbox` lookup (the B-P2 targeting hook)
- [x] honesty test (`tests/test_document.py`, self-contained fitz PDF) + live verify on the Attention paper
      (15 pages, 538 regions, 6069 words; bbox overlay confirmed the map aligns to the render)
- [ ] (B-P2) VECTOR-drawn figures aren't segmented yet (only raster image blocks); equation regions deferred
- [ ] (follow-up) `nolan document ingest` CLI command in cli_legacy; a `document` POOL type surfaced in /pool

### B-P2 · Region targeting + paper block family — CORE DONE (2026-07-21)
- [x] REGION-ID targeting: `{region:"p3-fig0"}` on a document annotation → rect from the B-P1 layout map
      (`resolve_doc_annotations._bind_document`); the stable-id path (robust vs an ambiguous `find`, and the
      ONLY way to target a FIGURE) — complements the existing text-`find` resolution
- [x] VECTOR-figure segmentation in ingest (cluster drawings) — verified it bounds Figure 1 (the Transformer)
- [x] `data.document`+`data.page` bind the rendered page as `source` + page_size + provenance; catalog fields
      + honesty tests (`tests/test_document.py`)
- [x] reuses the existing `document` block's highlight/underline/label/callout/caption + camera(push/scroll)
- [ ] (follow-up) a dedicated zoom-TO-region camera; equation regions; a `document` POOL surface in /pool

### B-P3 · Full motion set — WAVE 1 DONE (2026-07-21; B-P0 clips received)
Wave 1 (core paper-explainer kit) — all rendered on the Attention paper:
- [x] highlight a sentence (region-id) + **VO-SYNC spine** (`_retime_doc_annotations`: a region's text →
      `sync` → cue, so annotations fire ON the spoken word — the 'read to you' feel)
- [x] `camera:"region"` + `focus:<region-id>` (zoom into a region) · `focus_mode:"lift"` (crop → enlarge
      centre-screen → BLUR+DIM the page behind — the "portion lifts out" move)
- [x] read-along (a highlight sweeps across a paragraph at reading pace) · `split_view` block (a document
      region ∥ any content — clip/text/stat, the paper scrolls to its region)
Wave 2 (document-as-EVIDENCE) — all rendered on the Attention paper:
- [x] redaction (a black bar over text that LIFTS to reveal) · stamp (APPROVED/CLASSIFIED slams on)
- [x] strike (TRACK-CHANGES strikethrough + green insertion) · term (EQUATION term-by-term: highlight+gloss)
Wave 3 next:
- [x] Wave 1 above; figure extraction done (B-P1/B-P2)
- [ ] citation web → reuse `connection_board`; side-by-side → `comparison`; title hero → `hero` (blocks EXIST;
      the paper-specific MOTION/pacing needs the reference clips to pin)
- [ ] equation term-by-term · redaction · track-changes — new motion, BLOCKED on B-P0 samples

## Cross-cutting
- [x] unified media/data/document under a "sources" umbrella in `/map` (`nolan/sources.py` SOURCES registry +
      system_map wiring/consumer manifests, honesty-tested) — every source is provenance-gated

## Order
A-P1 ✓ → A-P2 ✓ → A-P2.5 ✓ → B-P1 ✓ → B-P2 ✓ → A-P3 ✓ → A-P4 ✓ → cross-cutting ✓ → **B-P3 remains, gated on B-P0 reference clips**.
