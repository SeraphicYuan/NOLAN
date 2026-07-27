# The camera umbrella — Ken Burns for the compose-first HF path

**Status: SHIPPED 2026-07-26.** Everything below is implemented and test-enforced unless a line says
otherwise. Code: `src/nolan/camera/` (registry · solve · emit · select · target), wired into the
composer at `compose.py::_camera_for`, gated in `author.py`, surfaced on `/map` as the `camera`
umbrella. Tests: `tests/test_camera*.py` (75).

**What it replaced.** The dominant path had exactly one move: `media_ground` scaled an image ground
`kb[0] → kb[1]`, `ease:"none"`, about the centre, over the whole beat — and four blocks had each
hand-written their own copy of that idea, already drifted apart (`media_ground` 1.03→1.08,
`_data_ground` 1.03→1.10, `carousel` 1.05→1.16, `_layout_cell` a literal `duration:6` that froze on a
long beat and was cut mid-stride on a short one). All linear, all centred, none scaled to the beat.
`detail_zoom` was the only real camera and its coordinates were hand-guessed by the authoring agent.

Meanwhile the LEGACY Remotion path (`src/nolan/still_motion.py`) already has: subject targeting from a
rembg cutout centroid (`subject_center()`, cached in a `<image>.subject.json` sidecar), narrative-cue
treatment selection with a no-repeat rule (`select_still_treatment()`), and an energy→camera vocabulary
(`camera_tour_props`). **This program is mostly a port and an uplift, not an invention** — and it must
land as ONE registry both paths import, or it is WIRING_CHECKLIST pitfall #4 (two dialects) by
construction.

---

## Part 0 — the rules every move must obey

These are not style preferences; they are the composer's existing contracts. A move that breaks one of
them is not shippable, and each has a test named in Part 5.

1. **Seek-safe, single paused timeline.** The renderer seeks to a frame and reads state; it does not
   play. Every move is `tl.fromTo(...)` / `tl.to(...)` registered at an ABSOLUTE time with an explicit
   duration. Banned: `repeat`, `yoyo`, `Math.random()`, `Date.now()`, CSS `animation`, anything whose
   state is not a pure function of timeline progress. (Same rule the `raw` seek-lint already enforces.)
2. **Narration owns duration.** `scene.start` / `scene.dur` are written by `sync.place_scenes` from the
   word aligner. A move therefore expresses its timing as a FRACTION of `dur` — never a literal number
   of seconds. `_layout_cell`'s `duration:6` is the bug this rule exists to prevent.
3. **A cue beats a spread.** The composer's convention is `_reveal_cues(items, start)` → an author `at`
   wins, else `_reveal_times()` spreads. The camera takes the SAME treatment: an arrival cue
   (`camera.at`, else the operative-word cue `data.cue`, else `_line_cues[i]`) sets the moment the move
   LANDS. With no cue, the move spreads across the beat by the amplitude law (Part 3).
4. **Transform-only, on the ground element.** Animate `scale` / `x` / `y` / `rotation` on `#<sid>-gnd`
   (or `#<sid>-dgnd`). Never `background-position`, `width`, `top`. The ground already carries
   `data-layout-allow-overflow`, which is what keeps `layout_lint` from flagging the overscan.
5. **Never expose an edge.** Any translate must be covered by the scale that produced the overscan
   (Part 4's solver). A move that cannot reach its target without showing background must clamp AND
   report — a silent clamp is the "no silent caps" violation.
6. **Legibility is dynamic, the scrim is not.** The scrim over a ground is a fixed gradient; a push that
   drags a bright region under the text breaks contrast mid-shot. A move samples luminance at its START
   and END framing in the text band and fails the gate if either drops below the floor (this shares the
   sampler with the frosted-panel work).
7. **Track discipline.** Ground on track 0, scrim/veil on track 1, scene content on 2+. A camera adds no
   new track and no new element (except `parallax`, which adds exactly one cutout layer on track 0).
8. **One emitter.** Every move is emitted by `camera.emit()`. `media_ground`, `_data_ground`,
   `_layout_cell`, `carousel` and `detail_zoom` all call it. No block hand-writes a camera tween again.

---

## Part 1 — the move registry

Each entry: **id** · what it does · params · **sync anchor** (what in the VO it lands on) · when to use ·
guard. `needs:` marks a move that requires a capability (detection or cutout) and must degrade cleanly
when it is unavailable.

### A. Push / pull — the scale family

| id | move | params | sync anchor | when to use |
|---|---|---|---|---|
| `push-in` | scale s0→s1 about the target point | `target`, `amount`, `ease` | arrival on the operative word | the default life-giver for a still held >3s |
| `pull-out` | scale s1→s0 (starts TIGHT, widens) | `target`, `amount` | arrival on the turn word ("but", "actually", the reveal noun) | the narrative widening — "you weren't seeing the whole picture" |
| `punch-in` | a fast step push (~0.35s) then static | `target`, `amount`, `at` | the stressed word itself | emphasis on one word; NOT ambience. Max one per beat |
| `push-to-detail` | push into a BOX so it fills ~70% of frame | `box` (x,y,w,h), `fill` | arrival on the phrase naming the thing | a named logo / face / object / signature. `needs: detection` |
| `settle` | push that overshoots ~3% and eases back | `target`, `amount` | arrival at the overshoot peak | opening shot of a section; reads as an operator finding the frame. Use sparingly |

### B. Lateral — the translate family

| id | move | params | sync anchor | when to use |
|---|---|---|---|---|
| `pan-lr` / `pan-rl` | translate across the overscan | `amount`, `ease` | spread; arrival on the end phrase | wide horizontal sources; direction follows lead room, then reading order |
| `pan-down` / `pan-up` | vertical translate | `amount` | spread | TALL sources — posters, full pages, portraits. Panning a portrait sideways is the amateur tell |
| `pan-to-subject` | starts off-subject, lands on it | `target` | arrival on the naming phrase | "the camera finds it" — a person entering the argument |
| `drift` | ≤2% lateral + scale, sub-perceptual | `amount` | none (ambient) | long holds where a real push would be too much movement |
| `whip-pan` | ~0.25s blurred lateral hand-off | `direction` | the cut itself | shot-to-shot device; belongs with clip transitions, listed here for completeness |

### C. Depth — the 2.5D family (`needs: cutout`)

| id | move | params | sync anchor | when to use |
|---|---|---|---|---|
| `parallax` | sharp subject cutout pushes faster than a blurred background | `target`, `separation` | arrival on the operative word | the single biggest "looks expensive" upgrade for a still-heavy stretch |
| `parallax-pan` | same separation, lateral | `direction`, `separation` | spread | landscape / crowd / cityscape stills |
| `depth-dolly` | foreground scales, background nearly static | `separation` | arrival | approach rather than sideways travel; good on a portrait |

### D. Focus and atmosphere

| id | move | params | sync anchor | when to use |
|---|---|---|---|---|
| `rack-focus` | subject blur→sharp (true rack needs the cutout; whole-frame is the cheap version) | `from`, `to` | the revelation word | a reveal, a realisation |
| `blur-in` / `blur-out` | whole-frame blur at the entrance / exit | `amount` | scene start / end | memory, dream, "coming into focus" |
| `roll-drift` | push + 0.3–0.8° rotation | `degrees` | arrival | unease / archival ONLY. **Never a default** — a visible rotation reads as a screensaver |
| `roll-whip` | a real roll across a hard beat change | `degrees` | the beat | rare, deliberate |

### E. Document / text-aware (`needs: detection`)

| id | move | params | sync anchor | when to use |
|---|---|---|---|---|
| `read-along` | arrives on the quoted LINE as it is spoken | `phrase` | the quoted phrase's word times | the essay-specific killer — a document/ad/patent/headline the narration quotes. (12:49 of diamond-v2 is exactly this shot) |
| `scan-column` | slow vertical crawl down a column, paced to the reading | `column` | spread across the quoted span | long documents read aloud |
| `mark-and-push` | push to a region + a drawn ring/underline at the cue | `box`, `mark` | arrival on the phrase | evidence — "look at this clause" |

### F. Stillness

| id | move | when to use |
|---|---|---|
| `hold` | locked frame, no move. An iconic image at a climax, a face at the emotional peak. **A system that always moves is as monotonous as one that never does** — `hold` must be selectable and must actually get selected |

---

## Part 2 — selection policy (deterministic first, model last)

In precedence order — the first that answers, wins:

1. **Authored lock.** `data.ground.camera` (or `scene.camera`) written by a human or the authoring
   agent. Honoured verbatim. Same precedence rule `camera_tour_props` already uses for the nine-dot
   tray placement.
2. **Narrative cue.** Verb/pronoun classes read off the beat's ACTUAL aligned narration (not a
   guess): movement verbs → a lateral; widening language → `pull-out`; naming/examining → `push-in`
   or `push-to-detail`; growth → up-drift; collapse → down-drift. This is `select_still_treatment()`
   ported onto real word-aligned text.
3. **Source shape.** Aspect decides the axis: a tall source gets `pan-down`, never `pan-lr`. A source
   barely wider than 16:9 has no room to pan and gets a push.
4. **Duration band.** The amplitude law (Part 3) picks the size and speed; a very short beat (<3s)
   collapses to `punch-in` or `hold` because there is no room for a considered move.
5. **No-repeat.** A hard alternation against the previous still's FAMILY (push / lateral / depth /
   focus / hold), ported from `select_still_treatment`'s rule. Two identical consecutive moves read as
   a template, not a camera.
6. **Targeting.** Where a target is needed and detection is available, use it; else centre with lane
   alternation (`camera_tour_props`' existing fallback). Never break over a missing detection.

---

## Part 3 — the amplitude law (why long holds feel dead today)

Apparent speed, not scale delta, is what the eye judges. Hold it roughly constant at **0.6–0.9 % of
frame height per second** and derive everything else:

```
Δscale = clamp(0.035 + 0.0045 · dur, 0.05, 0.16)      # 4s → ~0.053, 16s → ~0.107, capped
Δpan   = clamp(0.02  + 0.004  · dur, 0.03, 0.14)      # as a fraction of the overscan available
ease   = "power1.inOut"   (arrival cue present → "power2.out", so it settles ON the word)
```

Today every beat gets a constant `1.02 → 1.12` regardless of length — which is precisely why a 16s hold
reads as static and a 4s beat reads as jumpy. `ease:"none"` (linear) is the PowerPoint tell; a real
camera accelerates and settles.

---

## Part 4 — the safe-transform solver (one helper, one class of bug killed)

```
camera.solve(img_w, img_h, canvas=16:9, target=(tx,ty), scale=s, pan=(dx,dy))
    → {x0,y0,s0} → {x1,y1,s1}, plus `clamped: [...]` naming anything it had to limit
```

Rules it enforces:

- **Cover first.** The image is `background-size: cover`; the overscan available on each axis is
  `(cover_w − canvas_w)/2` etc. A pan may only consume overscan that exists.
- **Scale to afford the pan.** A requested translate that exceeds the overscan raises `s` (to a cap of
  1.35 — beyond that a 1080p source visibly softens), and if the cap is not enough the pan is CLAMPED
  and reported in `clamped`.
- **Target reachability.** Centring `target` at scale `s` may be impossible near an edge; clamp the
  framing, not the image, and report it.
- **Resolution floor.** `s × min(img_w, img_h) ≥ canvas` at every keyframe, else the move upscales past
  source resolution — refuse and fall back to `hold` with a loud reason. (Directly relevant: ~10 library
  sources are still 360p.)

Nothing here needs a model. It is the difference between "a Ken Burns feature" and "black edges in
someone's finished video".

---

## Part 5 — wiring (module contract, per `docs/WIRING_CHECKLIST.md`)

| piece | where |
|---|---|
| **registry** | `src/nolan/camera/registry.py` — every id above with `purpose`, `when_to_use`, `constraints` (`seek_safe`, `duration_preserving`, `needs_cutout`, `needs_detection`) |
| **authored field** | `data.ground.camera` (+ `scene.camera`), validated against the registry by `author.py`; declared in `catalog.json` |
| **executor** | `camera.emit(sid, spec, start, dur)` → GSAP lines. Called by `media_ground`, `_data_ground`, `_layout_cell`, `carousel`, `detail_zoom` — the ONE emitter |
| **detection** | `camera/target.py` — rembg centroid (port `subject_center`) + the VLM box lane (`OllamaVision`, `qwen3-vl:8b`, already our default local vision model), cached in a `<image>.camera.json` sidecar. Fail-soft to centre |
| **catalog + skill** | the move table auto-emitted into the authoring catalog and the craft skill, honesty-tested against the registry |

**Honesty tests (a rule without one does not exist):**

1. every registry id is actually emitted by `camera.emit` (no phantom moves);
2. no camera tween carries a literal duration — every one is a fraction of `dur` (kills the `duration:6`
   class, and is the test `_layout_cell` would have failed);
3. property test over aspect × target × scale: the solver NEVER produces a framing that exposes an edge,
   and anything it limits appears in `clamped`;
4. seek-safety lint on emitted lines (no `repeat`/`yoyo`/`random`/`Date.now`);
5. alternation: two consecutive stills never get the same move family;
6. `hold` is reachable and is chosen on the beats the policy says it should be;
7. a move whose detection is missing degrades to centre/`hold` and says so — it never breaks the render.

---

## Part 6 — why detection needs the VLM and not just rembg

`subject_center()` returns the CENTROID of the rembg foreground mask. For a single subject that is
exactly right. For your "one or two people" case it aims at the GAP BETWEEN THEM, and for any image it
cannot answer *which* subject this sentence is about — a logo, a face in a crowd, the clause in a
contract. That is the argument for the VLM lane: not detection, **relevance**. One local
`qwen3-vl:8b` call per still, given the beat's narration, returning normalized boxes plus which box the
beat is about; cached in a sidecar exactly like `subject_center` already does, so re-renders never
re-run it.

Order of implementation, cheapest-first: solver + amplitude law + eases (no model, fixes the dead holds
today) → alternation + narrative cues → rembg targeting → VLM targeting → parallax/rack-focus → the
document family.


---

## What shipped, and the decisions that only surfaced in the building

**The amplitude law reaches real beats only because `kb` stopped governing.** Every `kb` in the tree is
an authoring default — `[1.02, 1.1]` on nine frames of diamond-v2 alone — never a tuned value. Honouring
it as an explicit amount would have left a 16s hold travelling the same 8% as a 4s beat, which is the
dead-hold complaint this module exists to answer. `kb` now decides WHETHER a ground moves; the law
decides how far; `camera.amount` is the deliberate override.

**`drift` is the alternation partner, not a duration default.** The first cut defaulted long beats to
`drift` (2%), which gave a 14.4s beat *less* travel than a 4.8s one — the same bug wearing a new hat.
A long hold is exactly where a slow, large push belongs.

**The upscale tolerance is a design decision, not a constant.** At the 2% I first wrote, a 1920x1080
stock still — the most common asset shape in the pool — could take no push at all, and the feature
would have switched itself off across most of a real project. 18% is the band where a still holds up,
and it still catches the 360p library sources by a wide margin (they need ~3x).

**…and 18% was still the wrong QUESTION** (found by rendering three real frames, below). It compared
the TOTAL upscale against a small tolerance and charged all of it to the camera — but a ground is
already scaled to cover the frame whether a camera exists or not. Measured on the diamond-v2 pool: 30
of 47 image assets are narrower than the canvas, median width 1179px, and the static ground already
pays a median 1.82x (max 5.68x), so **31 of 47 were over the "tolerance" while standing perfectly
still**. The floor now asks what the camera ADDS against a genuine mush threshold (`MUSH_FACTOR`
2.6x total): 7 of 10 grounds move where 3 did, and every hold names a source that really is too small.

**Alternation state is per FRAME.** It began as a module global carried across frames, which would have
made a frame's camera depend on which frames happened to be composed before it — and the incremental
renderer composes only the ones that changed. `compose_frame` resets it.

**`backdrop-filter` and the sub-composition topology** were verified in headless Chrome before the
glass panel work leaned on them; the camera's own seek-safety is verified by emitting every registered
move and asserting no `repeat`/`yoyo`/`random` and an absolute time on every tween.

### Fixed straight after the first commit (each was mine)

- **A deliberate `hold` read as FROZEN to `temporal_gate`** — WIRING_CHECKLIST pitfall #7, a gate lagging
  new vocabulary. The camera now RECORDS its decision (`data-camera` / `data-camera-why` on the ground)
  and the gate reads it: a hold the camera CHOSE is exempt and carries its reason, a scene frozen with no
  decision behind it still fails, and `camera="push-in"` with zero measured motion still fails — that is
  the move failing to reach the pixels, exactly what the gate is for.
- **The solver's `notes` went nowhere.** It reported clamps, degrades and holds into a variable nobody
  read, which is a silent cap with extra steps. They now land on the element and in a per-frame log.
- **`camera.at` was read but never declared** — the "gate accepts what the schema never offered" class
  from the diamond-v2 post-mortem, committed by me two hours after writing that post-mortem up. Declared.
- **Default targeting was rembg**, ~20s cold per asset, wanted for nearly every image ground: minutes
  added to a compose that takes seconds. The default is now a contrast centroid on a 64px thumbnail
  (~10ms); rembg is `precise=True` and the matte path for parallax/rack-focus, where the matte IS the
  product.
- **The emitter dispatch lived in the composer seam** (which emitter for which move). That is registry
  knowledge, and a second consumer would have had to duplicate it — pitfall #4 inside the module built
  to prevent it. Moved to `camera.emit_for`.
- **`detail_zoom` — the one block that IS a camera — was not using the module**, and the first version of
  the honesty test matched only `gnd|dgnd|-img`, so it slipped through on a `-cam` selector with a literal
  0.95s leg. Its legs are now a fraction of the stop's dwell, and the test covers every media selector.

### Found by rendering three real frames (f03 / f04 / f09, with their VO)

Frames rather than the whole video because all of it lives at the frame level and a frame renders in
minutes against ~25. Three things confirmed — the process steps land 2.4s apart instead of piling up,
the 12:49 card reads at 56% glass tint, and the long-axis pan reveals 561px of an ad that cover-fit was
cropping — and three defects came back:

- **The resolution floor was measuring the wrong thing** (above). The biggest single finding, and only
  measurement on a real pool could have produced it.
- **A long-axis pan frames the FILE, so it travelled across the source's own border.** That ad is a
  PHOTOGRAPH of the 1947 page, lying on black, shot askew: 7.7% black on the left, 11.8% on the right.
  The first fix was a symmetric 6% overscan — the right instinct with an invented number, which cannot
  remove 11.8% on one side and quietly crops real picture on a source with no border at all. The
  geometry now solves against a MEASURED content box (`target.content_box`, a purity-gated edge scan;
  a naive percentile fires on 40 of 47 assets, the purity gate on the 14 that genuinely have one).
  What remains is the tilt wedge — no axis-aligned crop removes that, and **deskewing the asset is the
  fix**; it belongs to asset cleanup, not to the camera.
- **A number-carrying element anchored on its LABEL, not its number** — a sync-organ defect the camera
  surfaced. "only ten percent" is spoken at 20.52; the item's label ("had a diamond in them") at 22.68,
  so the gauge arc drew 2.2s after the figure it illustrates. `sync._value_time` now prefers the
  number's spoken time, searched only inside the scene and only BEFORE the label, so a false match can
  never push a reveal later than what it already had.

And one misdiagnosis worth keeping: a frame render came back **black**, and the conclusion "a track-0
clip renders outside the `#root` scope where the theme tokens live" was wrong. The shipped video
disproved it (`diagram` and `geo` both put themed backgrounds on track 0 and render fine); the real
cause was the probe harness, whose mount div omitted the `data-composition-id` production sets, so the
runtime never scoped the sub-composition's CSS. Reproduce a render the way production assembles it, or
the render lies to you. (`tests/test_ground_parity.py` keeps the lesson.)

### Not yet built (named so nobody assumes otherwise)

- `read-along` and `scan-column` resolve their region through the VLM box lane, but nothing yet maps a
  quoted phrase to a line box via OCR — the box comes from the model's own reading of the narration.
  Word-level *arrival* works; per-line crawl pacing does not.
- `settle`, `roll-drift` and `pan-to-subject` are registered, executable and reachable, but the
  selector never picks them on its own — they are authored moves for now.
- **`geo`'s map camera** (`-plane` / `-world`) still hand-writes its tweens with literal durations. It
  moves in projection space between locations, which the registry does not model — a real port, not a
  rename. `tests/test_camera_compose.py` declares it as the one exception and will FAIL if someone ports
  it without updating this list.
- The legacy Remotion path still has its own `still_motion.py` vocabulary. It was left in place
  deliberately (that path is LEGACY for essays); porting it to import this registry is the remaining
  step that would close pitfall #4 completely.
