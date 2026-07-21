# Design: Data as a first-class SOURCE

Status: **proposal** (react before code). Author: reveal-sync session, 2026-07-21.
Companion to the #3 fabrication bug (`sync._number_provenance_flags`) and the reveal-sync program.

## 1. The problem

Today a project's inputs are **script + VO + a shortlist of media** (pics/clips). Numbers enter one of
two bad ways:

- **Single-number mention.** The VO says "43%" and we render one stat. We can't show the *context* (the
  table row it came from, the other categories, the trend) because the data isn't in the project.
- **Fabrication.** A block DEMANDS quantitative data the script never gave, so the author *invents* it —
  the "benefits spread / costs don't" sankey made up a `$100 → 34/24/18/14/10` breakdown. Structure real,
  numbers fake. Actively misleading.

Both are the same gap: **there is no data source of truth.** The number is either isolated or invented.

## 2. Principle (this is settled practice, not novel)

Every serious data-viz pipeline (NYT/FT/Reuters Graphics, The Pudding) and the grammar-of-graphics world
(Vega-Lite, ggplot) separate three things:

> **DATA** (the source of truth) → **ENCODING** (how a field maps to a mark) → **MARK** (the drawn shape).

NOLAN already has the marks (the 12 data-viz blocks). We are missing the **data** and the **encoding**.
The script/VO is the *narration over* the data, not the data itself. So: **add a typed DATA source; bind
blocks to it by query; never let a block hold a number that isn't traceable to a cell.**

## 3. Architecture (six parts, each a NOLAN module-contract citizen)

1. **`dataset` source type in the pool.** A per-project `datasets/` dir of tables (CSV/JSON/parquet) +
   a registry entry per table: `id`, `title`, `columns` (name, unit, dtype), `provenance` (source URL /
   citation / retrieved-at), `grain` (what one row is), and `when_to_use` (a human note: "US data-center
   water by year; use for the water-cost beats"). This is the "special type in the pool, well-commented"
   you described. Gated on ingest by an extension of `asset_gate` (provenance required).

2. **Binding, not typing.** A block references data by **query**, and the numbers are *pulled*:
   ```json
   {"type":"chart","data":{"dataset":"electricity_share","query":{"select":["year","pct"],
     "where":"year in [2023,2028]"},"encode":{"x":"year","y":"pct"}}}
   ```
   The author writes the *encoding* (which columns → x/y/label/value), never the values. Resolver fills
   `series`/`items`/`segments` from the table at compose time.

3. **Data-manipulation helpers** (`nolan/data/` — deterministic, **pandas-backed**). The resolver +
   authoring use a thin, pure wrapper over pandas: `select`, `filter`, `top_n`, `aggregate` (sum/mean),
   `pivot`, `share_of_total`, `delta`/`pct_change`, `normalize`, `sort`, **plus time-series: resample,
   rolling window, cumulative, year-over-year, interpolate/fill.** (Decision Q3 — pandas gives us all of it;
   we expose a *curated* verb set, not raw pandas, so the authored `query` stays declarative + gate-able.)

4. **Block adapters.** Each data-viz block declares its **required data shape** in the catalog
   (`data_shape`: chart → `[{label, value}]`; pie → shares summing to a whole; stat → a scalar; sankey →
   source + weighted targets; spans → rows with start/end). A resolver maps `(dataset, query, encode)` →
   that shape. One resolver, N blocks — the "connect to compose.py blocks" layer.

5. **Provenance gate** (deterministic — kills #3). A data-viz block's every displayed number must trace to
   a dataset cell OR be an explicitly-sourced authored value (`value_source`). The gate rejects a block
   with bare numbers that match no cell. This is the hard version of `_number_provenance_flags` (which is
   the soft, VO-based heuristic we already shipped).

6. **The "one line → whole table" operator.** Given a beat that mentions one number, retrieve the *table*
   that number lives in, and let the author present the row *in context* (peers shown, the cell
   highlighted). This is the enrichment that makes data-heavy essays deep instead of a parade of single
   stats. It's a pairing operator (like `/broll`) but for datasets: bridge the narration line → the table.

## 4. Data flow (worked example — fixes #3)

Beat: "follow the bill — the costs land on specific people" (the fabricated sankey).

- **Old:** author invents `{power:34, water:24, drone:18, land:14, jobs:10}`. Gate blind. Ships misleading.
- **New:** either (a) a `bill_costs` dataset exists → the sankey binds to it, weights are real, gate passes;
  or (b) no dataset → the number-provenance gate rejects the quantitative sankey → the author falls back to
  a **non-quantitative** block (a `connection_board`/list of the five costs with *no* fake proportions).
  Both outcomes are honest.

## 5. Module contract (so it can't rot)

- **Registry:** `datasets/index.json` (table metadata + provenance + when_to_use).
- **Authored field:** `data.dataset` + `data.query` + `data.encode` on a data-viz scene.
- **Executor:** the resolver in the compose/finish path that fills the block's data shape from the table.
- **Honesty tests:** (a) every block's `data_shape` in the catalog matches what its executor consumes;
  (b) the provenance gate — a fixture spec with a fabricated number fails; (c) resolver round-trip (a
  known table + query → the expected series).
- **Auto-surfaced** in `/map` (a new "sources" umbrella: media / data / …).

## 6. Routing (per CLAUDE.md capability policy)

- **Dataset acquisition / ingest** → deterministic parsers + a research agent (find & fetch tables, like
  the extractor registry). Provenance stamped.
- **Shaping** (select/aggregate/pivot) → deterministic helpers.
- **Which viz for this data + which cell the narration means** → LLM taste (the encoding + the bridge).
- **Provenance** → deterministic gate. No number without a cell.

## 7. SOTA references

Vega-Lite / grammar of graphics (data→encoding→mark); dbt/semantic-layer (a table + a query, not
copy-pasted numbers); data-journalism "chart from the sheet, never retype" discipline; NOLAN's own
`asset_gate` provenance model (extend it to data).

## 8. Phasing

- **P1 — provenance floor (cheap, high value):** the `value_source` field + the hard gate; keep the VO
  heuristic as the pre-gate warning. Stops fabrication immediately, no dataset infra needed.
- **P2 — dataset source + resolver:** `datasets/` + registry + `nolan/data/` helpers + the binding
  resolver for chart/stat/pie/bar (the common shapes). Bind real tables.
- **P3 — the one-line→table operator + authoring:** the pairing bridge + UI to attach a dataset to a beat.
- **P4 — richer marks from data:** sankey/spans/quadrant adapters; derived series (delta, share).

## 9. Decisions (2026-07-21)

1. **Where datasets come from — BOTH, user-supplied first.** P1/P2 assume the author drops CSV/JSON into
   `datasets/`. A research-agent acquisition path (find + fetch + provenance-stamp) comes later, on the
   same registry + gate rails as the extractor/asset pipeline.
2. **Gate strictness — HARD-BLOCK, with a precise definition of "fabricated" so it never false-blocks.**
   My recommendation (and I agree with your lean): a displayed number is **legitimate if it traces to ANY
   of** — (a) spoken in the narration (the VO says it, number-aware), (b) an explicit `value_source` note,
   or (c) a dataset cell (once P2 lands). A number with **none** of these is fabricated → **hard fail**.
   This gives true hard-block semantics *without* breaking today's essays (whose real numbers are spoken):
   the "benefits spread" sankey (34/24/18/14/10, none spoken, no source) hard-fails; the $800B/$1T spend
   chart passes because the VO says them. So we can turn the hard gate on **now** — it only bites fabrication.
   (`_number_provenance_flags` we already shipped is the (a)-only heuristic; the hard gate adds (b)+(c).)
3. **Helper scope — pandas-backed, including time series** (resample / rolling / cumulative / YoY). See §10.

## 10. Time-series data + its MOTION (the block expansion)

Time-series is not just another table shape — it has a **temporal axis, and that axis should map to the
video's time / narration.** So the reveal isn't only "spread across the window" (reveal-sync Layer 1); it's
"**advance along the time axis as the narration moves through time.**" This is a richer reveal contract and
it wants new marks. This is the "expand the data blocks meaningfully" you asked for.

**The motion vocabulary (SOTA — FT / Our World in Data / Flourish bar-chart-race / Gapminder / 3B1B):**
- **Line draw + playhead** — the line draws left→right over time; a vertical time-cursor sweeps and the
  value/label at the head updates (upgrade of today's static strokeDashoffset draw).
- **Bar-chart race** — ranked bars reorder as values change over time (the viral format); positions swap,
  the leader label ticks. New block.
- **Connected scatter / trajectory** — a point/bubble travels its path as years advance (Gapminder). New block.
- **Streamgraph / stacked-area build** — layers accumulate left→right over time. New block (or a chart mode).
- **Cumulative / running-total** — a waterfall-over-time; the total climbs (reuse the `build` reveal-char).
- **Small-multiples reveal** — a grid of mini time-series reveal one at a time.
- **Time-axis pan/zoom** — the x-window pans to follow the narration (early years → recent), reusing detail_zoom.
- **Milestone annotations** — callouts fire as the series reaches a labeled point (a spike named as it happens).
- **Value ticker** — a number t*icks along with the time cursor (reuse the count-up scheduler, time-indexed).

**Architecture (extends #4 + reveal-sync):**
- The dataset carries a **time/order column**; the block declares `x: <time>` (or is a temporal block type).
- New reveal mode **`along_time`**: the reveal scheduler advances element-by-element *along the time axis*,
  either **VO-synced** (a time-step reveals as the VO mentions that year) or **auto-paced** (the series plays
  across the scene window). This generalizes `_reveal_times` from "spread N elements" to "walk a time axis."
- New/expanded compose.py marks: `chart` line → time-aware draw+playhead; new **`bar_race`**, **`trajectory`**
  (connected scatter), **`stream`** (stacked area). Each: registry + `data_shape` + executor + honesty test +
  the provenance gate (numbers from cells).
- Reuses: count-up scheduler (ticker), detail_zoom (axis pan), annotate (milestones), `build` character.

**Phasing add-on:** P2.5 — line-draw-with-playhead + the `along_time` reveal mode (biggest bang, small).
P4 — bar_race / trajectory / stream (the new marks).
