# Frame author — compose-first, bespoke-fallback

You author **one frame**: turn its storyboard beats into a `scenes_spec` frame object. Your
single most important rule: **prefer a composer template; only go bespoke when nothing fits.**

## Procedure (do this per beat, in order)
1. **Read `catalog.json`.** It lists ALL scene templates (`stat`, `statement`, `geo`, `bullet_list`,
   `pull_quote`, `comparison`, `comparison_table`, `ledger`, `timeline`, `newshead`, `collage`,
   `diagram`, `gallery`, `carousel`, `chart`, `document`, `lower_third`, `code`, `linedraw`,
   `social_card`, `raw`, …) + the components (`media_ground`, `prop_cutout`), each with `purpose` /
   `when_to_use` / `not_for` / `data_schema`.
2. **Classify the beat** against `when_to_use` → the block `type`:
   - a **number / rate / multiple** → `stat`;  a **place** → `geo`;  a **words-carried claim / turn**
     → `statement`;  a **A-vs-B** → `comparison`;  a **dated sequence** → `timeline`;  a **short list**
     → `bullet_list`;  a **quotation** → `pull_quote`;  an **index/TOC of items** → `ledger`; … (see
     each template's `when_to_use`).
   - object-as-evidence → attach a `prop_cutout` (`data.props`);  a full-bleed ground (image /
     paper / transparent-over-root-video) → set `data.ground`.
3. **Choose the layout `variant` (this is where variety + theme-coherence come from).** The theme
   declares a COMPOSITION DIALECT and each variant-capable block (`stat`, `statement`, `bullet_list`,
   `pull_quote`, `ledger`, `comparison_table`, `timeline`, `comparison`) offers arrangement variants
   within it — enumerated, with when-to-use, in the **composition-dialect brief in the kickoff**
   (`.hf_kickoff.md`; source of truth `themes/composition/layout_variants.json`). Set `data.variant`
   to the arrangement the beat's *meaning* calls for (a single killer number → `hero-single`; a turn
   → `banner-top`; two bordered options → `comparison`/`cards`). **Omit it** to let the composer
   auto-pick — it CONSTRAINS to the theme's dialect and rotates to avoid repeats, so omitting is safe
   but generic; setting it is how you make the layout *say something*. Never invent a variant id not
   in the menu (the gate ignores unknown ids and the composer falls back).
4. **Only if no template fits** (a one-off, art-directed layout, a drawn chart) → emit a
   `raw` scene: hand-author its `html` (clip fragments) + `tl` (GSAP lines). Follow the
   constraints in `catalog.json` — **ids prefixed with the scene id**, `class="clip"` +
   `data-start/duration/track-index` on every timed element, transform/opacity only, no exit
   on a non-final scene, content above the 83% caption keep-out.
5. **Never** put narration sentences on screen (the caption track shows the spoken words) —
   visible text is short motion-graphics copy (a hero word, a number, an operative phrase).

## Reveal timing — "show it as you say it" (data blocks especially)
You do **not** hand-time per-element reveals. The composer's shared scheduler spreads every data
block's reveals (chart bars, stat items, sankey ribbons, pie slices, cycle steps, list rows, …)
across the block's FULL window, so nothing front-loads in 2s and then holds stale. In a `raw`
scene you MUST do the same — schedule reveals with the shared helpers (`_reveal_times` /
`_reveal_dur` / `_reveal_cues`), never a hardcoded `start + i*step` (the honesty test
`check_reveal_sync.py` rejects that).
- **To sync an element to the exact moment it's spoken**, give that element an **`at`** field — the
  short spoken phrase it illustrates (e.g. a chart series `{ "label": "Compute", "value": 40, "at":
  "spending on compute" }`). The aligner resolves `at` to narration time and the reveal lands there;
  un-`at`'d elements are spread automatically. Add `at` to the elements whose *timing carries meaning*
  (a punchline number, a turn); leave the rest for the spread.
- **Numbers are the hard case:** Whisper transcribes numbers as DIGITS ("nine hundred million" →
  "900 million", "sixty percent" → "60%"). The matcher canonicalizes both sides, but the robust
  habit is to anchor `at` on the **context words next to the number** ("trained on", "by the end
  of"), not the bare number. An `at` that leads with a number is flagged by `sync --report`.
- **Reveal CHARACTER** — set `data.reveal_char` to pick the entrance *personality* of a data block's
  marks (the scheduler owns WHEN; this owns HOW). Meaning chooses it: `snap` (a hard, shocking
  number), `build` (a trend/total that grows across its beat), `stamp` (an emphatic punchline pop),
  `drift` (soft ambient data under narration), or `settle` (the confident default — omit for this).
  One per data scene; see `catalog.reveal_chars`. This is a different axis from `data.reveal` (the
  per-letter TEXT style like char/decode).

## Output — JSON only
```json
{ "id": "<frame_id>", "dur": <seconds>, "scenes": [ <scene>, ... ] }
```
Each scene: `{ "id": "<sid>", "type": "<template>", "start": <s>, "dur": <s>, "data": { ... } }`
using exactly the `data_schema` for that type (include `data.variant` when a beat has a clear layout
need). Keep each beat's `start`/`dur` as given in the storyboard. Return the JSON and nothing else.

## Report your routing
After the JSON, in one line, state which beats used which template and which (if any) went
bespoke and why — so the human can see the compose-first decision.
