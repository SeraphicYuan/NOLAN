# Video block catalog — the authoring contract

This is what a chapter-spec author (the skill's chapter agent) reads to turn a
chaptered script into a render spec. You **select a block per step, fill its
props, and choose anchors** (the word in the narration where each reveal lands).
The generator (`gen_spec.py`) resolves anchors → frames; NOLAN's Remotion renders.

## Spec format (`specs/<chapter>.spec.json`)
```json
{
  "out": "<chapter>.mp4", "theme": "bold-signal", "fps": 30,
  "audioDir": "D:/.../public/audio/<chapter>",       // mp3s, Windows path (render)
  "wavDir":   "/mnt/d/.../.tts_wav",                  // wavs, POSIX path (durations)
  "wordsCache": "web-video-lab/human-3.0/words_<chapter>_all.json",
  "steps": [
    { "block": "<BlockName>", "wav": "<chapter>_<n>", "audio": "<n>.mp3",
      "anchors": ["<word|@start|@2.5|@f0.5>", ...],   // one per reveal point
      "props": { ... block props ... } }
  ]
}
```
One step = one narration beat = one mp3. `anchors.length` must equal the block's
reveal-point count (below). The generator matches each anchor to the **first
occurrence at/after the previous anchor**, so order them as they're spoken.

### Anchor kinds
- a **word/phrase** from the narration → reveal at that word's start (use a
  distinctive content word, not "the"/"a"; first token is matched, ≥3 chars).
- `@start` → frame 0 (use for a headline/first line that's up immediately).
- `@2.5` → absolute seconds. `@f0.5` → fraction of the step's duration.

## Blocks (the library) — select by the beat's *relation*

### HeroStatement — a punchy statement / transition / punchline
Use for: a single big claim, a cold-open hook, a two-part claim→counter, a reveal.
- props: `{ kicker?, lines: [{ text, accent?, strike? }] }` (1–3 lines; `accent`
  = token accent color, `strike` = drawn strike-through, e.g. on "NPC").
- **anchors: one per line** (the word that triggers each line; `@start` for line 1).

### ListReveal — an enumerated list, one item per spoken item
Use for: "X for A, Y for B, Z for C" / any list the speaker names one-by-one.
- props: `{ title?, items: [{ label, tag }] }` (label = thing, tag = its category,
  shown in accent).
- **anchors: one per item** (the word naming each item, e.g. "Spiral","Buddhism").

### ArchetypeCards — N profiles, each a maxed trait + a crashed trait
Use for: "the X who is great at A but terrible at B" comparisons; archetypes.
- props: `{ kicker?, cards: [{ name, maxLabel, maxVal(0..1), lowLabel, lowVal(0..1),
  flaw }], closer }`.
- **anchors: one per card + one for the closer** (the word naming each profile,
  then the closing-line cue).

### WebVsBoxes — "separate boxes vs one connected web"
Use for: contrast between siloed things and an interconnected system / network.
- props: `{ kicker?, headline, boxes: [string], nodes: [string] }`.
- **anchors: 3** — [headline cue (`@start` ok), the "separate/boxes" cue, the
  "web/connected" cue].

### Timeline — before/after on an axis (old vs new)
Use for: "predates X and Y" / chronology / one anchor far from later ticks.
- props: `{ kicker?, headline, anchor: { label }, ticks: [{ label }], note,
  moneyNote }`.
- **anchors: [the old-anchor cue, one per tick, the moneyNote cue]**.

### StatCount — headline numbers that count up to their spoken word
Use for: one or more stats the speaker names ("fifteen years… five years"); each number
rolls up exactly as its word is said (via the `RollingNumber` primitive).
- props: `{ stats: [{ value, word, label, sub?, prefix?, suffix?, decimals? }], closer?, accentPhrase? }`
  (1–4 stats; `value` is a **number** — use `prefix`/`suffix` strings for display, e.g. `suffix:"+"`→
  `1,000+`, `suffix:"σ", decimals:2`→`1.95σ`; `accentPhrase` highlights a phrase in the closer).
- **anchors: the count-up is driven by each stat's `word`; use `@start` (or the first stat's word).**

### ValueLadder — a value growing across a time/sequence axis
Use for: "$1k → $2k → $4k over the years" / users / revenue / price over time. The active
milestone's number rolls to its value as spoken; widening gaps show acceleration.
- props: `{ kicker?, rungs: [{ year, amount, word }], prefix?, suffix?, axisUnit? }`
  (e.g. `prefix:"$"`, `axisUnit:"yr"`).
- **anchors: one per rung (the value's spoken word, e.g. "thousand","two","ten").**

### UnlockGrid — a big value beside a grid that fills tile-by-tile
Use for: coverage / completion / "every area unlocked" / adoption — a hero value + a grid
sweeping from dim outlines to filled.
- props: `{ value?, kicker?, popWord?, captions?, gridCols?, gridRows? }`.
- **anchors: [hero-pop cue (or set `popWord`), caption-start cue].**

### Formula — a typeset math equation that writes on (KaTeX)
Use for: any real equation from a paper / derivation; single or multi-line (`\begin{aligned}`).
Renders LaTeX via KaTeX with a left-to-right write-on reveal.
- props: `{ latex, caption?, kicker? }` (`latex` is a LaTeX string; escape backslashes in JSON).
- **anchors: 1** (`@start` — the equation is up and writes on).

### DataTable — a results / comparison table that builds row-by-row
Use for: benchmark results, model comparisons, any tabular figure (e.g. a paper's results table).
Numeric columns auto-right-align with tabular figures; one row can be emphasized.
- props: `{ columns: [string], rows: [[string]], highlightRow?, caption? }`.
- **anchors: [table-in cue (`@start` ok), the highlight-row cue].**

### BarChart — count-up comparison bars
Use for: comparing a few quantities (compute, cost, size, score); bars grow + values count up,
one bar in accent. A categorical alternative to ValueLadder (which is time-series).
- props: `{ title?, bars: [{ label, value, accent? }], unit?, caption? }`.
- **anchors: [chart-in cue (`@start` ok), then one per emphasized value as spoken].**

### PaperFigure — lift the paper's OWN figure (the empirical exception)
Use for: a figure you **can't honestly redraw** — an attention heatmap, a plot of real data, a
sample output, a photo. (For formulas → Formula, tables → DataTable, simple schematics → redraw.)
Shows the lifted image on a themed *exhibit card* with a cited source; a word-synced accent box
sweeps to a region as the narration names it. Prep the asset first with `extract_figure.py`.
- props: `{ src, kicker?, source?, highlights?: [{ word, x, y, w, h, label? }] }` — `src` is an
  absolute image path (staged into `public/` by `render.mjs`); highlight `x/y/w/h` are **fractions
  (0..1) of the image box**; each box appears when its `word` is spoken.
- **anchors: 1** (`@start` — the card writes on; highlights are word-driven, not anchor-driven).

## Block-selection guide (relation → block)
| beat relation | block |
|---|---|
| statement / hook / punchline / transition | **HeroStatement** |
| enumerated list (named one-by-one) | **ListReveal** |
| headline stat(s) that count up as spoken | **StatCount** |
| a value growing over a time/sequence axis | **ValueLadder** |
| coverage / completion / a grid filling | **UnlockGrid** |
| profiles / archetypes (good-at-one, bad-at-rest) | **ArchetypeCards** |
| siloed-vs-connected / network | **WebVsBoxes** |
| before/after / predates / chronology | **Timeline** |
| a math equation / formula | **Formula** |
| a results / comparison table | **DataTable** |
| comparing a few quantities (bars) | **BarChart** |
| an un-redrawable empirical figure (heatmap, plot, photo) | **PaperFigure** (lift) |
| line / area / time-series (data you have) | **LineChart** |
| histogram / value distribution | **Distribution** |
| a value matrix / correlation / confusion grid | **Heatmap** |
| contrast / opposition / before-after / vs | **ComparisonVS** |
| land a memorable line / define a term | **PullQuote** |
| sequential steps / method / pipeline | **StepFlow** |
| kinetic per-word headline | **KineticHeadline** |
| section divider / closing card | **ChapterCard** / **EndCard** |
| a themed icon / checkmark / counter | **LottieIcon** |

## Chart tier (library-boost Wave 2 — visx/d3 geometry, frame-driven reveal)
All redraw-tier (use for data you HAVE; lift empirical figures with PaperFigure instead).
Deterministic SVG, token-themed, reveal driven by the frame/word timeline.

### LineChart — line / area over a numeric axis (PnL curves, trends, time series)
- props: `{ title?, caption?, series:[{name?,points:[{x,y}],color?}], area?, xGroup?,
  yPrefix?, ySuffix?, yDecimals?, xPrefix?, xSuffix?, xDecimals? }`.
- **anchors: 1** (`@start`); axes fade in, then the line sweeps left→right with a live readout.

### Distribution — histogram of values (return distributions, spreads)
- props: `{ title?, caption?, bins?:[{x0,x1,count}] | values?:[number], binCount?, markerX?,
  markerLabel?, highlightRange?:[lo,hi], xPrefix?, xSuffix?, xDecimals? }`.
- **anchors: 1**; bars grow staggered; `highlightRange` bars in accent, optional mean/median marker.

### Heatmap — a value matrix on a sequential color scale (correlation/confusion/tenor grids)
- props: `{ title?, caption?, values:number[][], rowLabels?, colLabels?, showValues?,
  valueDecimals?, domain?, highlightCell?:[row,col] }`.
- **anchors: 1**; cells fade in on a diagonal sweep; `highlightCell` ringed in accent (snaps to a spoken label).

## Structural / editorial tier (library-boost Wave 3)

### ComparisonVS — two-sided contrast (ours-vs-baseline, before/after, A vs B)
- props: `{ kicker?, left:{title,points?,tag?}, right:{title,points?,tag?}, verdict? }`.
- **anchors: 3** — [left cue, right cue, verdict cue]. Right = favored side (accent panel).

### PullQuote — land a line, or define a term
- props (quote): `{ mode:"quote", quote, accentPhrase?, attribution? }`;
  (definition): `{ mode:"definition", term, definition }`.
- **anchors: 2** — [quote/term cue, attribution/definition cue].

### StepFlow — numbered sequential steps (method / pipeline / algorithm)
- props: `{ kicker?, orientation?:"horizontal"|"vertical", steps:[{label,detail?}] }` (2–5).
- **anchors: one per step** (the connector draws on as each reveals).

### KineticHeadline — kinetic typography; each word punches in as spoken
- props: `{ text, accentWords?:[string], align?:"left"|"center" }`.
- **anchors: 1** (`@start`); words rise/scale/un-blur on their spoken frames.

### ChapterCard / EndCard — section divider + closer
- ChapterCard: `{ index?, title, subtitle? }` — **anchors: 2** [index cue, title cue].
- EndCard: `{ headline?, takeaways?:[string], source? }` — **anchors: [headline, then per-takeaway]**.

### LottieIcon — a themed Lottie asset (icon / checkmark / counter)
- props: `{ src, size?, caption?, loop?, monochrome? }` (`src` = abs path to a keyframed,
  transparent-bg, expression-free `.json`, staged by render.mjs; recolored to `--accent`).
- **anchors: 1**.

## Transition layer (Montage composition)
Narrated chapters use **hard cuts** (audio-safe — overlapping `<Audio>` would overlap speech).
For **silent** sequences (title/chart montages) use the `Montage` composition: set
`"composition":"Montage"` + a `"transitions":[{type,durationInFrames,direction?}]` array
(one per gap; `type`: `fade|slide|wipe|clockWipe`) + optional `"motionBlur":true`. Total
duration auto-accounts for each transition's overlap. Film grammar: cut within a topic,
fade/dissolve between topics.

## Raw / bespoke tier (the hybrid)
Library blocks cover the recurring 80%. For a **signature beat** where no library block
does it justice (the cold-open, a one-of-a-kind diagram, a number that counts as it's
spoken), author a **bespoke block** instead of forcing a generic fit.

A bespoke block is **the same thing as a library block, written fresh for this beat** —
*not a different engine*. It is a token-faithful, `Surface`-wrapped Remotion component in
the chapter's `src/blocks/` (just not listed in this catalog), referenced by name in the
spec. It renders deterministically to mp4 exactly like a library block.

**Same contract** — every block (library or bespoke) receives:
- `revealFrames: number[]` — anchor-resolved reveal points (coarse).
- `words: { text, startFrame, endFrame }[]` — the **full per-word timeline** for the step
  (step-relative frames). Bespoke blocks use this for *per-word* choreography: strike a
  word exactly as it's spoken, count a number up as "fifteen" is said, kinetic type. So a
  bespoke beat syncs to audio **tighter** than a library block, not looser.
- `durationInFrames`. `useCurrentFrame()` is step-relative.

In the spec, a bespoke step looks like any other: `{ "block": "NpcStrike", "anchors": [...],
"props": {...} }` — the only difference is the block isn't in this catalog.

**Promotion (the harvest loop).** Because a bespoke block has the identical file shape as a
library block, promoting it is mechanical: when a bespoke pattern **recurs**, lift its
hard-coded content into props, move the file into the shared library, and add a catalog
entry — now the spec author can *select* it. The **`_needsBlock`** flag is the explicit
backlog: when you fall back, add `"_needsBlock": "<name>: <what it should do>"` to that step.
Discipline: promote on recurrence (≥2–3 uses) and generalize (find the varying props);
don't accumulate near-duplicates. Reserve bespoke for the 1–2 signature beats per chapter.

### Current raw blocks
- `NpcStrike`, `SelfFeedingCurve` — content-fused narrative gags, stay bespoke.
- `AttentionFlow` (`{sentence, focus?, label?}`) and `ArchStack` (`{layers?, subLayers?, note?}`) —
  transformer-specific schematics from the paper explainer (test run 11) → stay raw.
- (`Formula`, `DataTable`, `BarChart` were promoted to the library in test run 11 — see above.)

## Theme
`theme` is one field; every block is token-faithful so all 23 skill themes apply.
