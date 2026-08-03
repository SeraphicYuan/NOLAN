# Deliverable protocol + the ship stage — program plan

**Status:** proposed · 2026-08-03 · derived from the diamond-v3 batch-edit run, a fleet-agent
post-mortem (nolan1), and a code audit of the render/QA/packaging paths.

Two halves that look separate and are not:

1. **Deliverable protocol** — where a render, its intermediates and its history live, and how you
   ask "is this file current?"
2. **The ship stage** — SRT, title, description, thumbnail: the artifacts between a finished render
   and a published video.

They join at one point: *packaging generates titles and thumbnails from a render.* If you cannot say
whether that render reflects the current specs, you can package a video you are not shipping. Half 1
is therefore a prerequisite for half 2, not a parallel nicety.

Per `docs/WIRING_CHECKLIST.md`: every step below names its consumer and its honesty test. A step
without a test is not in this plan.

---

## The evidence

Measured, not asserted.

**The deliverable has no fixed name.** `incremental.render_incremental` (incremental.py:873) defaults
to `renders/{comp}.mp4`; `finish.py:409` passes `out=renders/video.mp4`. One function, two names, no
marker saying which is the deliverable. Result across the lab:

```
aeneid-essay              3 top-level mp4s
ai-datacenter-debate-v5   4
homer-hf                  3
the-openai-debate         2
the-diamond-illusion-v3   2   (byte-identical only because an agent hand-copied)
```

**And the QA gates score the wrong one.** Both `render_gate.py:169` and `temporal_gate.py:152`:

```python
vids = sorted(rd.glob("*.mp4")); return vids[0] if vids else None
```

Alphabetically first. Almost every comp name sorts before `video`, so:

| comp | gates actually scored | deliverable |
|---|---|---|
| homer-hf | `homer-hf-sfx-preview.mp4` — **an SFX preview** | video.mp4 |
| aeneid-essay | `aeneid-essay.mp4` | video.mp4 |
| ai-datacenter-debate-v5 | `v46.mp4` | video.mp4 |
| the-openai-debate | `the-openai-debate.mp4` | video.mp4 |

The perceptual and temporal gates — the "verify like an editor" layer — have been reporting on a file
nobody ships. This is a silent **false negative**: a bad render passes because a good preview scored.
It is the single fact that makes this a defect program rather than a tidiness program.

**The staleness marker cannot answer the question.** `renders/.done` is
`{"comp": "...", "rendered": true}` — no hash, no timestamp, no filename. It is a boolean where a
comparison is needed.

**Intermediates live in the delivery directory.** `_concat.txt` and a leaked
`.captions_overlay.hf-transaction-*` sit beside the publishable file. The leak had to be cleared by
hand before a retry would work, and one from 2026-07-27 was never cleared. It leaks on the *happy*
path too — the `_concat.txt` on disk is from a successful stitch.

**Filename-as-provenance is causing a live bug.** `fit_ground_to_scene` (edit.py) derives the original
by `re.sub(r"_fit\d+s(?:_\d+)?$", "", stem)` and looks in `assets/`. When only the derivative was
staged there, the fit silently no-ops (`ground auto-fit skipped (asset not found: assets/a19_04.mp4)`).

**Provenance is unknown at publish time.** On the-diamond-illusion-v3:

```
91 assets on screen · 65 in pool.json · 26 NOT IN pool.json at all
0 of 91 carry origin_verified or caption_verified
35 are `quick-edit` derivatives with no link to an original
```

Not "clean" — *unknown*. At the last gate before public, we cannot say where 26 on-screen assets came
from.

**Two things proposed in the post-mortem already exist.** `stage_referenced_media`
(`assemble_media.py:47`) already implements capture/=store, assets/=stage — an undocumented invariant,
not a thing to build. And `frame_sig` (incremental.py:86) already hashes *what actually renders* per
frame: the manifest's hash primitive is written.

**Packaging exists and the dominant pipeline cannot reach it.** `src/nolan/packaging.py` builds
chapters, subtitles, thumbnails, titles, description and credits — and reads `scene_plan.json`, which
HF comps do not have. Same stranded-organ shape as the VLM floor (fixed 2026-08-02). Half 2 is
therefore mostly a **port**, which changes its cost materially.

---

## Scope: what is in, what is cut, and why

The request was explicitly to include only what is necessary. Six things are cut.

### CUT 1 — unbounded `history/<ts>-<hash>.mp4` → keep exactly one `previous.mp4`

The proposal was a content-addressed history directory. It stores a ~900 MB **derivative** when the
manifest plus spec rollback (`rollback_batch`, shipped) already makes any past cut **re-derivable**.
The actual use case is "compare the new cut against the last one before I publish," which needs one
predecessor, not N. Unbounded history is 900 MB × every render with nobody owning deletion — and a
retention policy that ships "later" does not ship.

**Keep:** `renders/previous.mp4`, rotated on each successful render. Fixed cost, trivial policy.
**Concession:** re-deriving an old cut costs a 20-25 min render, so add `hf-finish --tag <name>`,
which promotes the current deliverable to `history/<name>.mp4`. Opt-in, human-named, bounded by
intent rather than by time.

### CUT 2 — the YouTube Analytics feedback loop

Wiring the Data API means OAuth, quota management and a channel binding, for a signal that arrives
days after publish on a channel with few videos. At low N, CTR differences are noise.

**Instead:** the judge learns from **which title/thumbnail the human picked** — free, immediate, and a
stronger signal than CTR until there are ~20 videos of data. Note: `src/nolan/youtube.py` is a yt-dlp
*downloader*, not the Data API; there is no publish integration today, so this is net-new work with a
weak payoff. Revisit when the corpus justifies it.

### CUT 3 — a general "declared home for every artifact class" refactor

Correct in principle and unshippable as one program: it spans fleet-agent scratch (`D:/tmp/hfbatch/`,
owned by nobody), preview scratch, proposals and tmp. The measured pain is already addressed by
`_work/` (below) and `prune_previews` (shipped, reclaimed 20.5 GB). Record the general problem; do not
gate this program on it.

### CUT 4 — a hard provenance GATE at publish

26 of 91 placed assets are absent from `pool.json` today. A hard gate would block every publish on day
one and be disabled within a week — `WIRING_CHECKLIST` #11, a check whose failures are all false
positives, which takes its one true positive with it.

**Instead:** ship the provenance **report** plus `derived_from` (which shrinks the unknown set at the
source), measure the false-positive rate, and gate only when it is near zero.

### CUT 5 — a thumbnail concept DSL / templating language

Keep a **minimal registry** — the house module contract requires it, it is ~20 lines, and it is what
makes `/map` and the skill honest. Cut the *DSL*: no expression language, no composable layout
grammar. Four hardcoded layouts, extracted into something more general only when a fifth earns it.
Registry-first abstraction is how unused abstractions get built.

### CUT 6 — renaming `video.mp4` → `final.mp4`

`finish.py` writes it, `sfx_mix` defaults to it, the `prior_build` check reads it. The problem was
never the name; it was that a *second* name existed. Renaming costs a full consumer sweep for zero
behavioural benefit. Kill `{comp}.mp4`; leave the working name alone.

---

## Phase 1 — deliverable integrity

Fixes a live wrong-answer bug. Roughly a day. Nothing else in this plan is safe until it lands.

### 1.1 Gates resolve through the manifest, never a glob

**Problem:** `_render_mp4()` picks `sorted(glob("*.mp4"))[0]` in two modules; 4 of 5 comps score the
wrong file.
**Fix:** one shared `deliverable(comp_dir) -> Path` reading `render.json`, with a single fallback to
`video.mp4` and a **loud** warning when the manifest is absent. Both gates import it. No module keeps
a private resolver — that is the two-dialects pitfall that created this.
**Why first:** renaming while the glob survives only changes which wrong file is picked.
**Test:** grep-verify no `glob("*.mp4")` remains under `hyperframes/`; a fixture comp with a decoy
`aaa.mp4` resolves to the deliverable.

### 1.2 One deliverable name

**Fix:** `render_incremental(out=...)` becomes required (or defaults to `video.mp4`, never
`{comp}.mp4`). **Pre-flight:** enumerate callers first — see *Verify before you build*.
**Test:** after a finish, `renders/` contains exactly one `*.mp4` besides `previous.mp4`.

### 1.3 `render.json` — the manifest, absorbing `.done`

```jsonc
{ "version": 1,
  "deliverable": "video.mp4",
  "rendered_at": "2026-08-02T19:18:04",
  "mode": "incremental",
  "duration_s": 815.19,
  "sig": "sha1 of ordered frame sigs + assembled index + audio_meta",
  "frames": { "01-try-to-sell-it-back": "a3f91c2e…", "…": "…" },
  "gates": { "hf_qa": "pass", "temporal": "pass", "perceptual": "2 advisories" } }
```

**Hash what `frame_sig` hashes, not the raw specs.** A whole-spec hash flags edits that change no
pixels (a reordered key, a comment). Per-frame sigs make staleness *actionable*: not "6 edits behind"
but **"frames 04 and 07 are stale"** — which names what to re-render.

**Absorb `.done`.** A detached `hf-finish` keys on it (finish.py:76-86). Two staleness markers is the
two-dialects pitfall; the manifest's existence *is* the completion signal.

**Test:** edit one scene → exactly that frame's sig changes and the comp reports stale; recompose with
no semantic change → sig stable.

### 1.4 `_work/` for intermediates, cleaned on failure

`renders/_work/` holds `concat.txt`, `captions_overlay.webm`, `.hf-transaction-*`. Wrapped so a failed
step wipes its own transaction dir.
**Test:** kill a caption composite mid-run; assert `renders/` top level still matches the allowlist and
a retry succeeds without hand-clearing.

### 1.5 `previous.mp4`

Rotate the prior deliverable on each successful render. Plus `--tag <name>` → `history/<name>.mp4`.
**Test:** two renders leave exactly `video.mp4` + `previous.mp4`; a third does not accumulate a fourth.

---

## Phase 2 — provenance

One fix closes two live bugs (the auto-fit no-op and the 26 unknown on-screen assets).

### 2.1 `derived_from` + `op` on pool entries

Every derivation site (`quickedit_asset`, `cleanup_asset`, `fit_ground_to_scene`, `treat_preview`)
records `{derived_from: "<source file>", op: "fit|crop|cleanup|treat", params: {...}}`. Currently 0 of
1422 entries carry it, so this is purely additive — no migration.
**Test:** a fit produces an entry whose `derived_from` resolves to a file that exists.

### 2.2 `fit_ground_to_scene` reads the index, not the filename

Ask the pool for the original instead of `re.sub`-ing a suffix off the stem. `_fit15s` stays a
human-readable convenience; it stops being the data model.
**Test:** reproduce the diamond-v3 no-op — original in `capture/assets/videos/`, only the derivative in
`assets/` — and assert the fit now resolves.

### 2.3 Quick-edit derivatives register in the pool

35 of 91 placed assets are `quick-edit` outputs and 26 placed assets are absent from `pool.json`
entirely. Route every edit-time write through `_register_pool_asset` (which already merges
idempotently).
**Test:** every asset referenced by a spec resolves to a pool entry, on a real comp.

### 2.4 Provenance report at package time (report, not gate — see CUT 4)

`package/PROVENANCE.md`: every placed asset, its source, licence, `origin_verified` /
`caption_verified`, and an explicit **UNKNOWN** count.
**Test:** a comp with a deliberately unregistered asset reports it as unknown rather than omitting it.

---

## Phase 3 — ship artifacts

### 3.1 SRT/VTT into the finish DAG

Export from `caption_groups.json` (the *shipped* caption timings, forced-aligner derived) rather than
re-transcribing. Clamp overlapping cues; floor zero-length ones. Working exporter already validated on
diamond-v3: 479 cues, 0.00 → 815.14s against an 815.19s render.
**Test:** cue count > 0, monotonic non-overlapping, last cue ends within 1s of `duration_s`.

### 3.2 Chapters from `audio_meta`

Cumulative section durations; frame titles as chapter names. YouTube requires first chapter at 0:00,
≥3 chapters, each ≥10s — assert all three.
**Test:** the three YouTube constraints, on a real comp.

### 3.3 Port packaging to the HF path

An **adapter**, not a rewrite: `packaging.build_package` currently takes `scene_plan.json`. Give it a
plan-shaped view derived from HF specs + `audio_meta` (sections, titles, script, brief) so chapters,
credits, titles and description come across unchanged.
**Test:** `build_package` runs on an HF comp and produces the same inventory keys it does for a
Director project.

### 3.4 Stale-deliverable guard

Packaging compares `render.json.sig` against the live specs and **refuses** (with `--force`) when they
differ. This is the join between the two halves: it is the reason Phase 1 comes first.
**Test:** edit a scene after rendering, run packaging, assert refusal naming the stale frames.

---

## Phase 4 — the iteration loop

Mirrors the script program's existing convention (`drafts/draft-NN.md` + `reviews/revision-NN.md`) —
reuse it rather than inventing a second versioning dialect.

```
package/
  package.json          inventory + provenance + which draft is CURRENT
  subtitles.srt / .vtt
  chapters.txt
  PROVENANCE.md
  drafts/draft-01.json  {titles[], description, thumbnail_briefs[]}
  reviews/review-01.md  structured critique of draft-01
  thumbnails/01-<slug>.png
  EXPORT.md             mode 2
```

**Both modes write the same tree** and differ only in whether the judge runs. If export mode wrote
elsewhere we would have recreated the `renders/` problem in a new directory.

### 4.1 Auto mode — generate → judge → revise

Stop on convergence (judge returns no blocking notes) or a round budget. Two design points decide
whether this is worth building:

- **The judge sees the script, not just the title.** A title judged alone optimises for clickbait; a
  title judged against the opening 60 seconds optimises for *retention*. Feed it the hook section and
  the chapter list.
- **Part of the rubric is computable.** ≤60 chars, no saturated phrasing (a stoplist), and
  "the promise is paid off in the first 60s" — checkable against the script. Deterministic where it
  can be, taste only where it must be.

**Test:** a deliberately clickbait title that the script does not pay off is rejected by the judge,
and a rubric item is asserted deterministic (same input → same verdict).

### 4.2 Thumbnail factory

The split that makes it real:

| stage | tool |
|---|---|
| concept (headline ≤4 words + pool asset + layout id) | LLM |
| cutout | `rembg` (installed) |
| composite + type | HyperFrames, essay theme, 1920×1080 → 1280×720 |
| score | VLM **at 168×94** |

**Judge at feed size.** Scoring a 1920px render passes designs that vanish in a mobile feed, which is
where thumbnails actually fail. Reuses the existing `render_gate` VLM.
Minimal registry: 4 layouts (missing-ticker / pushed-back / annotated-slogan / two-tags).
**Test:** the registry matches the renderable layout ids (catalog-honesty, same shape as
`test_block_registry`); a rendered thumbnail is a 16:9 PNG and downscales to 168×94 without error.

### 4.3 Export mode

One `EXPORT.md`: the "here's what I want" preamble, full script **plus a compressed beat sheet**,
chapters with real timestamps, duration, theme palette/fonts, and the top pool assets with captions.
The trap is dumping 13 minutes of raw prose and burning the model's context before it can reason about
structure — the beat sheet is what avoids it.
**Test:** `EXPORT.md` contains every section heading and the real chapter timestamps; it is one file
with no external references.

---

## Verify before you build

Unknowns that could invalidate a step. Check these first; they are cheap.

1. **Who else calls `render_incremental` without `out=`?** Decides whether 1.2 is a signature change
   or a default change.
2. **Does the hub page, `/api/hf`, or any template hardcode a render filename?** Only
   `src/nolan/hyperframes/**` was audited. A hardcoded `video.mp4` in a route is fine; a hardcoded
   `{comp}.mp4` constrains 1.2.
3. **Does `packaging.build_package` have Director-only assumptions beyond `scene_plan.json`?**
   Decides whether 3.3 is an adapter or a fork.
4. **Is `caption_groups.json` written on every finish, or only when captions are enabled?** If
   conditional, 3.1 needs a fallback to `audio_meta.voices[].words`.

---

## Sequence

| phase | why this order |
|---|---|
| **1** deliverable integrity | a live false negative in the QA layer; everything downstream reads the deliverable |
| **2** provenance | closes two live bugs with one field; shrinks the unknown set before anything gates on it |
| **3** ship artifacts | needs 1 (the stale guard) and benefits from 2 (the provenance report) |
| **4** iteration loop | needs 3's artifacts to iterate on |

Phases 1-2 are the defect work — do them even if the ship stage is deferred. Phases 3-4 are the
feature work and can be scheduled independently once 1 lands.

## Known caveats

- The gate-scoring bug means **existing perceptual/temporal QA results on multi-mp4 comps are not
  trustworthy** and should be re-run after 1.1, not treated as a baseline.
- `renders/previous.mp4` doubles steady-state disk per comp (~900 MB). Accepted deliberately as the
  bounded alternative to unbounded history.
- The thumbnail judge has no ground truth until the human picks (CUT 2). Expect its early scores to
  be weakly calibrated; the human's choice is the training signal.
