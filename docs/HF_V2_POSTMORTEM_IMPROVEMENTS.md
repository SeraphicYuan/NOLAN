# HF compose-first — post-mortem improvements (handoff for nolan2)

**Source:** end-to-end cold run of `the-diamond-illusion-v2` (2026-07-25) — 9 frames / 90 scenes /
815s, authored compose-first in `kraft-paper`, rendered to `renders/video.mp4`. All 6 style-contract
gates pass (v1 failed 5). Every item below is derived from something that ACTUALLY went wrong or
was actually observed in that run — no speculative cleanup.

**STATUS 2026-07-25 — 10 of 11 landed; item 5 is REVERTED.**

| item | status | commit |
|---|---|---|
| 1 · pixel-level provenance | landed — as THREE fixes, not one | `5789f43` |
| 2 · missing media fails | landed | `5789f43` |
| 3 · kicker out of placement | landed — but see the note, `_scene_query` still reads it | `b42382d` |
| 4 · phantom `at` cues | landed — option (b), and the mechanism was not what this doc says | `1eb4e71` |
| 5 · author-time overlap check | **WITHDRAWN** — the rule it asks us to enforce does not exist | `66738e3` |
| 6 · perceptual dedup | landed — one condition, not a pHash system | `66738e3` |
| 7 · coverage/long-hold contradiction | landed — one shared registry | `5789f43` |
| 8 · `layout_lint` cries wolf | landed | `66738e3` |
| 9 · coverage reads only `pool.json` | landed — 24 gaps → 6 real | `1eb4e71` |
| 10 · document the cheap loop | landed | `66738e3` |
| 11 · incremental by default | landed — as WIRING (`--render auto`), not a usage note | `5789f43` |

**The pattern worth keeping.** Every claim in this document that was checked held — five were
verified independently before any code changed, and all five were true. What repeatedly needed
correcting was not the evidence but the **attribution of cause**: items 1, 4, 5 and 11 each named
where the symptom *appeared* rather than where the cause *lived*, and item 5's premise turned out to
be wrong outright. Implementing any of them literally would have under-fixed or, in 5's case, broken
authoring. Read an agent-written postmortem that way: trust its evidence, re-derive its causes.

Keep this file until the notes are folded into `docs/WIRING_CHECKLIST.md`; the corrections below are
the part worth keeping.

**TEMPORARY FILE.** Delete it once the items are landed (or fold the survivors into
`docs/WIRING_CHECKLIST.md` / `docs/SOTA_ROADMAP.md`).

## Ground rules for whoever implements this

- Read `docs/WIRING_CHECKLIST.md` first. Every item here that adds a rule needs its honesty test —
  *docs claim, tests enforce*. An item without a test isn't done.
- `tests/` must stay green (`~3 min`). Run the area suites named per item.
- **Concurrent agents share this tree.** Check `git status` and stage ONLY your hunks. Never `git add -A`.
- Windows python: `D:\env\nolan\python.exe -X utf8`. Never a bare `python`.

## ALREADY FIXED in the working tree (do NOT redo — verify + keep)

Both are uncommitted in `render-service/_lab_hyperframes/bridge/`:

1. `compose_extension.py` — `spotlight()` emitted BOTH halves of a centred label on the SAME
   `txt_track`, over identical windows. `assemble-index.mjs` rejects same-track time overlap, so
   **no centred spotlight had ever assembled**. The right half now drops one lane
   (`track=txt_track - 1`); halves are spatially disjoint so z-order is invisible.
2. `assemble_media.py` — `_iter_media_srcs()` only followed keys literally named `src`, so
   `newshead.image`, `timeline` events[].image, `document.source`, `gallery`/`carousel` `images`
   as BARE strings, `spotlight.subject` and `social_card.avatar` were never staged. 11 assets
   404'd and killed a 20-minute render. Now matches on the VALUE's shape
   (`^assets/….<media-ext>$`), so it is key-agnostic and new block fields work for free.

---

## P0 — ship these first

### 1. Asset provenance: gate on what is IN THE PIXELS, not the menu's caption

**Evidence.** 4 of 35 placed clips did not show what
`capture/extracted/asset-descriptions.md` claimed:

| clip | menu says | actually is |
|---|---|---|
| `ka_lab_grown_diamond_production_cvd_footage_1.mp4` | "Lab-Grown Diamond Production (CVD/HPHT)", `archive; Internet Archive` | a scraped **YouTube** upload: an "A DIAMOND IS FOREVER" card under FOLLOW/SUBSCRIBED chrome with **`@diamondtrends.net` burned in** |
| `ka_lab_grown_diamond_production_cvd_footage_1_2.mp4` | same | aerial of a **quarry** (placed on the GROWN side of a grown-vs-mined comparison → inverted the beat) |
| `a2_05.mp4` | "digital stock market ticker" | a talking head |
| `a24_06.mp4` | "man in a dark prison uniform… in a dim cell" | a hand holding a bowl of food |
| `a21_06.mp4` | "glowing red-hot metal ring… industrial machinery" | correct, but **hard-subbed with another creator's Chinese subtitles** |

Shipping #1 would have put another channel's branding in the video under a false licence tag.

**Where.** `src/nolan/acquire/judge.py` (the existing ONE-vision-call usability FLOOR) — extend, don't
add a second pass. See skill `nolan-acquire`.

**Do.**
- Add two questions to the existing VLM call, per clip (sample ~3 keyframes, not 1 — the watermark
  on `ka_lab_grown…_1` is not on frame 0):
  - `chrome`: any watermark / channel logo / subscribe-follow UI / burned-in subtitles / news lower-third?
  - `depicts`: does this actually depict `<the caption we are about to write>`? (bool + one line why)
- `chrome=true` → **reject** (never a hero, never a ground; it is someone else's branding).
- `depicts=false` → keep in the pool but rewrite the caption from what the VLM saw, and mark
  `caption_verified: false` in `pool.json` / `key_assets.json`.
- Deterministic prior, no model needed: `source` in `{clips_library, transcript_lib}` ⇒ scraped ⇒
  always run the check and always emit the `[unverified-origin]` tag into the asset menu.
  **All 4 defects came from those two sources; every `pexels_video`/`pixabay_video` clip was clean.**
- Surface the verdict as a TAG in `asset-descriptions.md` next to the existing
  `[NNNp — LOW-RES]` / `[copyrighted]` tags, so the authoring agent sees it.

**Honesty test.** `tests/test_acquire_judge.py`: a fixture clip with a synthetic watermark must be
rejected; a clip whose caption disagrees with the VLM must come back `caption_verified: false`.
Assert `clips_library`/`transcript_lib` items are never emitted without a verdict field.

> **LANDED `5789f43` — as three fixes, because the four defects came through three separate holes.**
> Extending `judge.py` alone would have fixed one of them. Splitting the evidence by source:
> - `a2_05`, `a21_06` (`clips_library`) **never reached the VLM** — a blanket "pre-captioned + curated"
>   early-return exempted the whole source. No prompt change can reach an exempted clip. Exemption removed.
> - `a24_06` (`pexels_video`) **was judged and scored `usable: 8.0`** — because `usable` rates how
>   cuttable a shot is and never asks what it depicts. Hence `depicts`, a separate question.
> - The branded hero came through `keyassets._verify_video`, a different module that asks subject-match
>   only. It now short-circuits on `chrome` BEFORE subject-match can accept a frame.
>
> `chrome` and `depicts` joined the existing fused call — no extra round-trip. `chrome` is disqualifying
> at any score: a clip can be beautiful, on-topic, 9/10 b-roll and still be another channel's property.
> That is a licensing problem, not a taste one — which is also why we stopped asserting a permissive
> licence for `clips_library`/`transcript_lib` at all. Those now read *origin unverified* until pixels
> confirm it; the old label was a claim we could not support.

### 2. A missing asset must FAIL, not warn

**Evidence.** `stage_referenced_media()` returns `{"staged": [...], "missing": [...]}` and only
*prints* `⚠ … NOT in assets/ or capture/`. First render of v2: 11 unresolved image refs, the
**style gate still printed PASS**, and the render died ~20 min later on a wall of `HTTP404`.
That is a silent cap — straight against the "failures are loud" invariant.

**Where.** `render-service/_lab_hyperframes/bridge/assemble_media.py` → `stage_referenced_media()`,
called from `main()`; the finish DAG step is `assemble-media` in `src/nolan/hyperframes/finish.py`.

**Do.** Raise on non-empty `missing` (listing every ref), so the DAG stops BEFORE the render spend.
Escape hatch `HF_ALLOW_MISSING_MEDIA=1` for a knowing exception, matching the house pattern
(`HF_ALLOW_STYLE` / `HF_ALLOW_LAG` / `HF_ALLOW_UNSOURCED`).

**Honesty test.** `tests/test_assemble_media.py`: a spec referencing a nonexistent
`assets/nope.jpg` raises; with the env var set it warns and continues.

### 3. `kicker` must not drive scene placement

**Evidence.** `src/nolan/hyperframes/sync.py:28`

```python
_VISIBLE_TEXT_KEYS = ("lines", "title", "titleHi", "kicker", "sub", "label", "quote", "headline")
```

but `bridge/catalog.json` documents `kicker` on `stat` and `bullet_list` as
*"small eyebrow label (**design intent, not narration**)"*. The matcher reads a field the schema
explicitly declares is not narration.

Cost in this run: `f04s12`'s kicker `FRANCES GERETY` matched the narration at 75.0s while the scene
was placed at 92.0s → **LAG 17.0s → HARD BLOCK** on a scene whose copy and anchor were both fine.
Working around it meant rewriting the kicker to `THE DETAIL THAT LANDS HARDEST` — i.e. distorting
design copy to appease a timing matcher.

**Do.** Drop `"kicker"` from `_VISIBLE_TEXT_KEYS` (it feeds `_scene_query`, `_content_time`,
`_content_window_time` and the lag lint). Consider dropping `titleHi` too — it is a substring of
`title`, so it double-weights whatever it highlights.

**Honesty test.** `tests/test_hf_sync.py`: a scene whose kicker names a person mentioned much
earlier, with a correct late anchor, places on the ANCHOR and raises no lag flag.

**Watch for.** `_content_time` corroboration needs `min_words=2`; removing a source of tokens may
make a few thin scenes fall back to interpolation. Check the `--report` UNRESOLVED count on
`the-diamond-illusion-v2` does not regress (it is currently 2 of 90, both interpolated to within
~1.2s of truth).

> **LANDED `b42382d` — and it is worse than "distorts design copy": the kicker MASKS real leads.**
> The root cause is one level up from `kicker`. `_content_time` read its own hand-maintained tuple
> `("kicker","title","titleHi","center","headline")` — so a `pull_quote`'s `quote`, `steps[]`,
> `events[]`, `items[]`, `left`/`right` were ALL invisible to the matcher. It then corroborated against
> whatever design copy it *could* see. Same fork-of-truth class as item 7, fixed the same way:
> `block_registry.visible_text()` walks the actual data (excluding non-narration keys, paths and enum
> values) and both matchers read it. Measured on v2: LEAD set corrected (`f05s01` was a false flag and
> dropped, `f07s01` newly caught), UNRESOLVED held at **2** — the exact non-regression check asked for.
>
> `titleHi` was deliberately KEPT. It is the operative phrase and usually the most distinctive
> narration-matching token in the scene; double-weighting it is arguably correct, and dropping both at
> once risks exactly the UNRESOLVED regression this item warns about.
>
> **Still open:** `_scene_query` (`sync.py:136`) has its own copy of the old tuple, `kicker` included,
> used whenever a scene carries no `anchor` — and that path DOES drive placement.

---

## P1 — real, well-evidenced, slightly larger

### 4. Kill the phantom `at` anchors

**Evidence.** Three frame workers independently reported the same class — `at` validates, ships,
and does nothing:

- `compose.py` `timeline()` (~line 1533) — events schedule on `start + lead + i*step`, `[None]*n`
- `compose_extension.py` `process()` (~line 1085) — same fixed spacing
- `carousel` — advances slides by `hold`, ignores `_cue`
- `juxtaposition` — panels use fixed cues (`start+0.1` / `+0.3`), never reads a side's `at`

This is the phantom-field class from `docs/WIRING_CHECKLIST.md` (and the note-edit incident): a
gate-passing but INERT field. `stat`, `annotate`, `chart`, `bullet_list`, `ledger`, `pie`,
`spectrum`, `cycle`, `comparison_table` DO consume cues today.

**Do (either, not both):**
- **(a) preferred** — route `timeline`/`process` through the shared reveal scheduler
  (`_reveal_times` / `_reveal_dur` / `_reveal_cues`), which `bridge/check_reveal_sync.py` already
  mandates for new blocks; or
- **(b)** have `author.py` **REJECT** `at` on any block that cannot consume it, naming the block.

Silent inertness is strictly the worst of the three states.

**Honesty test.** Extend `bridge/check_catalog.py` (or add `tests/test_reveal_consumers.py`): for
every block whose `data_schema` mentions `at`, assert the composed HTML/timeline actually varies
when `at` changes. That test is what stops this recurring for block #51.

> **LANDED `1eb4e71` as option (b) — and the mechanism is not what this item describes, which is what
> settled the either/or.** This reads as "the schema promises `at`, the block ignores it." It isn't:
> `timeline`'s events schema is `{year, label?, image?, side?}` — **`at` is never declared at all**. A
> hand-authored `timeline` with `events[].at` returned rc=0 "OK — spec validates". So the defect is *the
> gate accepting a field the schema never offered, which then silently does nothing*. That makes option
> (a) wrong on its face: routing `timeline`/`process` through the reveal scheduler would be building an
> undocumented feature to justify a field nobody specified.
>
> Deriving the consumer list from the composer rather than from this doc also corrected it: **`process`
> DOES read `at`** (claimed here as fixed spacing). `timeline`, `carousel` and `juxtaposition` genuinely
> do not. A wrong list here would have blocked legitimate authoring.
>
> **Preventative, not corrective.** The shipped v2 specs contain ZERO phantom cues — the three frame
> workers each stripped them once they discovered they did nothing. This changes no pixel in the
> finished video; it buys back the time three workers separately lost rediscovering the same dead end.

### 5. Run assemble-time structural checks at AUTHOR time

**Evidence.** The `spotlight` same-track overlap (fixed above) passed `author.py` cleanly and only
surfaced minutes later in `assemble-index.mjs`, after sync + recompose + sound + captions had all
run. The block had been shipped broken for every centred spotlight.

**Do.** Port `assemble-index.mjs`'s per-track time-overlap validation into `author.py`'s gate so a
frame worker sees it in ~1s. Same check, earlier door.

**Honesty test.** `tests/test_author_gate.py`: a hand-built spec with two same-track overlapping
clips exits non-zero from `author.py`.

> **WITHDRAWN — there is no such rule.** Not deferred, not descoped: the premise was checked and is
> false in every part. Two implementation attempts were made before checking it, which is the lesson.
>
> - **No assembler has the check.** All four `assemble-index.mjs` copies in the repo contain zero
>   track-overlap logic. The claim traces to a COMMENT in two of them — *"Track lanes (same-track
>   time-overlap is illegal — lint timeline_track_too_dense)"* — which describes the top-level INDEX
>   (frame sub-comps on lane 1, captions 2, voice 10, bgm 11), **not** the tracks inside a frame's own
>   composition.
> - **The rule it names is a different rule.** `timeline_track_too_dense` is a DENSITY warning about too
>   many clips on one timeline; its suggested fix is chunking into sub-compositions.
> - **The artifact that "could never assemble" is sitting in `videos/` with a rendered mp4.**
>   `_stress_spotlight` still carries the pre-fix HTML — `s1-labl` and `s1-labr`, both
>   `data-track-index="2"`, both 0.0–6.0 — next to a finished `renders/_stress_spotlight.mp4`. A frame
>   pulled from it shows BOTH label halves painted either side of the subject. `the-openai-debate`
>   likewise shipped 10 same-scene same-track collisions in its `raw` scenes and rendered.
>
> Attempt #1 gated on raw same-track overlap → 13 test failures, because adjacent scenes overlap by
> design (each scene carries a ~0.6s tail; the transitions injector ping-pongs the lanes afterwards).
> Attempt #2 proposed scoping to same-scene identical windows — which is precisely the shape the
> evidence above shows rendering correctly. Both detectors are removed; `tests/test_author_track_
> overlap.py` now records the disproof and asserts `author.py` does not gate, so there is no attempt #3.
> The false comment in `compose_extension.spotlight` (where the claim originated) is corrected in place.
>
> What survives is the general principle — a composer bug is cheapest in the composer's own gate — and
> it is already served by the phantom-cue gate (item 4) and the layout lint (item 8), which enforce
> rules that demonstrably exist.

### 6. Perceptual dedup in the pool

**Evidence.** `a1_05`, `a17_02`, `a20_05`, `a23_02` are the **same** macro-diamond shot (same
Pexels contributor, different pool ids); `a17_04`, `a19_06`, `a1_07` are the same pink-velvet
ring-box clip; `a17_06`/`a3_05` are the same white-surface clip. ~9 grounded scenes ran on ~4
distinct looks, while `media_diversity` reported **1.10** (healthy) because it counts FILENAMES.

**Do.** pHash / CLIP-embed one keyframe per pool clip at ingest; collapse near-duplicates into a
single pool entry with variants. Then `media_diversity` measures something real.

**Honesty test.** `tests/test_style_contract.py`: two byte-different files of the same shot count as
ONE distinct asset.

> **LANDED `66738e3` — one condition, not a new system.** Acquire already de-dups by `avg_hash` at
> `dedup_hamming=6`; the whole bug is `avg_hash(c.path) if c.modality == "image" else None`, which skips
> video. It now feeds the SAME average-hash a keyframe sampled at ~1.0s — not frame 0, because a hash of
> a black opening matches every other clip's black opening and would collapse the entire pool. Measured
> on the shipped v2 pool: **13 of 81 clips are near-duplicates, 68 distinct looks**, confirming the
> observation above with a number. A hash failure returns `None` (= no opinion), so a clip is never lost
> to an ffmpeg hiccup.
>
> One thing the tests taught, worth recording: the first fixture used solid colours and *failed* —
> average-hash compares each pixel to the frame mean, so ANY uniform image hashes to all-ones and black
> and white read as identical. That is a property of the hash, not of the dedup; real footage is never
> flat, but a fixture can be. Test with patterned sources.

### 7. Resolve the coverage / long-hold contradiction

**Evidence.** `src/nolan/style_contract/metrics.py:102` — `_GROUND_BLOCKS = {"statement", "stat"}`.
`pull_quote`, `ledger`, `bullet_list`, `juxtaposition`, `comparison_table` all ACCEPT a
`data.ground` (and workers dutifully added them) but `scene_media()` always scores them `none`.
So grounding them credits nothing, and they are then flagged by the "long ungrounded holds"
advisory — **11 of them in this run**. The author is told to fix a thing the metric refuses to see.

**Do.** Pick one and make it consistent: either count a real image/video ground on those blocks
toward `coverage`, or exempt ground-carrying blocks from the long-hold advisory. Note this MOVES the
coverage number, so re-baseline the gate bands in the same change.

**Honesty test.** `tests/test_style_contract.py`: a `pull_quote` with an image ground and one without
must not score identically on both `coverage` and `long_holds`.

> **LANDED `5789f43` — and it was a REGRESSION from the commit before this run, not an old wart.** Two
> constants shared one name and disagreed: `autoground._GROUND_BLOCKS` (6 blocks, derived from
> `compose.py`) and `metrics._GROUND_BLOCKS` (`{statement, stat}`). Widening the first from 2 to 6
> without noticing the second existed is what made grounding those blocks credit nothing while still
> tripping the long-hold advisory. `nolan/block_registry.py` is now the single home and both consumers
> import it.
>
> The fix that matters is not the registry — it is the honesty test asserting **no module re-declares
> the set privately**, because the failure mode was a fork, not a wrong value.
>
> **No re-baselining needed**, contrary to the caution above: coverage 0.656 → **0.767** (inside the
> dense band 0.60–0.95), long ungrounded holds 11 → **2**, with no re-authoring. Worth knowing before
> anyone loosens a gate on the strength of that number: the essay was ALWAYS this well-grounded — the
> metric could only see 2 of 6 block types.

---

## P2 — worth doing, lower blast radius

### 8. `layout_lint` cries wolf

All 3 "errors" in this run were the `process` block's step-number badges, deliberately pinned to
each card's corner (`left:-16px; top:-16px; 44x44`) — verified correct by eye in the render. A
linter whose only failures are false positives gets ignored, which is exactly how a REAL overlap
ships. Treat a small child fully contained in / anchored to its parent's box as intentional.
Test: the `process` block lints clean; a genuine 40% overlap of two siblings still fails.

> **LANDED `66738e3`.** An ancestor/descendant pair is exempt; siblings and cousins are not. Ancestry
> is a DOM **index path** from the root, where "ancestor" is a prefix test — not `id()`, which is only
> meaningful while the tree is alive and gets reused after collection, so a stale id could silently
> pair two unrelated elements. **3 errors → 0, FAIL → OK**, with all four genuine advisories intact and
> a real 40% sibling collision still failing.

### 9. `nolan.acquire.coverage` reads only `pool.json`

It reported **24 "NOT depictable" gaps** — De Beers, Cecil Rhodes, Frances Gerety, Zaire, Lightbox,
Hopetown, the Star of South Africa… every one of which HAS a hero in `key_assets.json` and is
placed in the final video. A plan-time check that is ~80% false positives will be skipped, and the
one genuine gap with it. Make it read the key-assets pool too.

> **LANDED `1eb4e71` — the cheapest item on the list and the largest change in behaviour.** **24 gaps →
> 6**, and all 6 survivors are genuine: Jack Ogden (the quoted historian), cubic zirconia, a US
> courtroom, a mall counter. Every named false positive is gone — De Beers, Cecil Rhodes, Frances
> Gerety, Hopetown, the Star of South Africa all have heroes and are in the finished video. That is the
> difference between a check people skip and one they act on.

### 10. Document the cheap verification loop

`--no-render` + a still contact sheet is what caught item 1, and it costs ~1 min against a ~25 min
render. It should be the documented default in `skills/pipeline/hyperframes.md` and the kickoff:

```bash
# after authoring, BEFORE any render
python -X utf8 -m nolan.hyperframes.finish <comp> --no-render
# then LOOK at every clip you placed
ffmpeg -ss 1 -i <clip> -frames:v 1 ...   # tile → read the sheet
```

### 11. Use `--render incremental` by default in the edit loop

Not a code gap — a usage one, recorded so the next agent does not repeat it. `hf-finish` defaults to
`--render whole`; this run used `whole` for all three passes, including a final pass where only
3 of 9 frames had changed. Consequences: full re-renders, and
`compositions/frames/*.clip.mp4` **never produced** — so `/hyperframes` (`edit.py:622`,
`webui/routes/hf_scenes.py:146`, which serve the newest of `<id>.preview.mp4` / `<id>.clip.mp4`)
has no cached per-frame video and must render each frame on demand.

Consider making `incremental` the DEFAULT for any run where `renders/` already has a build, and say
so in the skill.

> **LANDED `5789f43` — as WIRING, not a usage note.** `--render` gained `auto`, and `auto` is now the
> default: `whole` on a cold comp (which is a canonical baseline worth having), `incremental` once a
> build plus a clip cache exist. The two modes were never rivals — they are *first build* vs *every
> build after*. Incremental emits `compositions/frames/*.clip.mp4`, which is exactly what
> `frame_video_path` already serves, so the edit loop gets its per-frame cache as a side effect instead
> of re-rendering each frame on demand. Force either with `--render whole|incremental`.

---

## Still open after this pass (found while implementing; NOT on the original list)

1. ~~**The 12:23 pull-quote is still not flagged.**~~ **FIXED** — a quotation matcher (`sync._prose_time`
   + `block_registry.visible_strings`). Both existing matchers are frequency-based, and a quotation
   defeats both by construction: it is built from the frame's own subject words, so they recur
   (`_content_time` needs `freq==1`) and are shared with the sibling scene that restates them
   (`_content_window_time` down-weights shared tokens ×0.25, dropping it under its threshold). What they
   discard is what identifies a quotation — ORDER. `_phrase_time` already matched order but demanded an
   exact contiguous run, and the screen read *"They're valuable"* for spoken *"They're **very**
   valuable"*: one inserted word, no match. The matcher recovers ≥70% of a ≥8-token displayed string in
   order within a 2× window; length is the safety property, so it needs no frequency weighting. Measured
   across all 10 comps with aligned VO: **f09s01 now flags at lead=11.0s** (in both diamond comps),
   three other leads got more accurate estimates, lag/mis-order/hard counts unchanged, and UNRESOLVED
   held at **2 of 90**.
2. **`_scene_query` still reads `kicker`** (`sync.py:136`, its own copy of the pre-item-3 tuple), on the
   path taken whenever a scene has no `anchor`. Item 3 is half-landed until that reads the registry.
3. **43 library clips are still 360p.** Not on this list and probably the largest single quality win
   available: those sources were ingested under BOTH the old 720p cap and the stale yt-dlp, and both
   are now fixed. A re-ingest lifts the floor under every future project, not just this one.
4. **Editorially, `f09s01` is still wrong even once flagged.** Placement cannot fix a frame's FIRST
   scene (it is pinned to 0.0 — something must cover the frame from its start), and delaying the quote's
   reveal inside the scene would flash it for <1s before the scene ends. The fix is authoring: frame 09
   needs a lead-in beat carrying *"So here's where we land…"* before the quote lands.

## Known-acceptable, deliberately NOT changed (context, so nobody "fixes" them blind)

- `ka_1975_2004_us_court_proceedings_footage.mp4` is an aerial of the **Sage Gateshead (UK)**, used
  under *"could not legally set foot in America"*. Reads as generic institutional cityscape behind
  type; the pool has no US-court asset. A better asset is wanted — do not just relabel it.
- `ka_archduke_maximilian_mary_of_burg_artwork.jpg` is **Memling's Portinari diptych**, not
  Maximilian & Mary of Burgundy. The frame-4 worker correctly refused to print those names over a
  real identifiable artwork; the narration carries them. Needs a different asset to caption on screen.
- `assets/a5_05.jpg` is an **AVIF** file with a `.jpg` extension. Headless Chrome decodes it, so it
  renders — but any PIL/extension-trusting tool will trip.
