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
- [ ] (follow-up) formal per-block `data_shape` field in the catalog + a resolver↔shape parity honesty test

### A-P2.5 · Time-series motion floor — M — **CORE DONE (2026-07-21)**
- [x] the line chart already reveals points along time (`times[i]` = VO-synced `_cue` or auto-spread) — that
      IS the `along_time` behavior; the sweep makes it read as time advancing
- [x] `data.playhead` on a line chart: a vertical time-cursor sweeps left→right IN SYNC with the draw
      (transform-based, seek-safe); points/values reveal as it reaches them
- [x] documented on `chart.type` in the catalog; playhead honesty check in `check_reveal_sync`; provenance
      gate applies (a dataset-bound line passes) · live demo: essay 03-boom/s4 electricity chart → a 9-point
      line from the `electricity_share` dataset (2020–2028) with a sweeping playhead
- [ ] (follow-up) value TICKER at the head; auto-enable playhead for line charts bound to a time dataset

### A-P3 · One-line → whole-table operator + authoring — M
- [ ] pairing operator: narration line → the dataset table (present the row IN CONTEXT, cell highlighted)
- [ ] authoring flow to attach a dataset to a beat · verify: one-number beat renders the full table

### A-P4 · New time-series marks — L
- [ ] `bar_race` · `trajectory` (connected scatter) · `stream` (stacked area) [opt: streamgraph, small-multiples, milestones]
- [ ] each: registry + data_shape + executor + honesty test + provenance gate (reuse ticker/detail_zoom/annotate/build)

## TRACK B — Paper / document as a source

### B-P0 · Sample videos (user) → pin the motion set — GATE
- [ ] user sends 2–3 reference clips → lock the block/motion list

### B-P1 · Document source — L
- [ ] `document` pool type: PDF → page images + LAYOUT MAP (bboxes for paragraph/figure/equation/word)
- [ ] registry + provenance

### B-P2 · Region targeting + paper block family — L
- [ ] region targeting (reference paragraph/figure/word by id → pan/zoom/highlight)
- [ ] `document`/`paper` block: page-as-ground + scroll/page-turn/zoom-to-region + VO-synced highlight (reuse `_line_cues`)
- [ ] reuse detail_zoom / annotate / spotlight / pull_quote

### B-P3 · Full motion set — M–L (from samples)
- [ ] figure extraction · equation term-by-term · citation web (connection_board) · side-by-side · redaction · track-changes · title hero

## Cross-cutting
- [ ] unify media/data/document under a "sources" umbrella in `/map`; blocks become source-aware

## Order
A-P1 → A-P2 → A-P2.5 → B-P1 → B-P2 → A-P3 → A-P4 → B-P3 (interleave Track B once samples arrive).
