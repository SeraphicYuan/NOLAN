# Web-Video-Presentation × NOLAN — discussion insights

Reference notes from the design discussion. Captures *why* and *what we decided*, so
we don't re-derive it. The experiment lives here in `web-video-lab/` (sandbox).

## What this is
- **web-video-presentation** (ConardLi/garden-skills) — sibling of the beautiful-article
  skill we promoted into NOLAN. Turns a script into a click-or-auto-driven **16:9 web
  "video"**: chapters = pure functions of a global `step`; `narrations.ts` is the single
  source of truth for step count + narration; provider-agnostic TTS; `?auto=1` plays the
  deck (advancing on each clip's audio `ended`) so you screen-record it to mp4.
- Light stack: Vite + React + TS, ~6 hand-rolled hooks (no framework), themed via CSS tokens.

## Decisions
1. **Keep it OUT of NOLAN for now.** Sandbox folder (`web-video-lab/`) that *uses* NOLAN as a
   read-only library (OmniVoice TTS, scriptwriter, headless-Chrome/ffmpeg). **Dependency is
   one-way: lab → NOLAN. Do not edit `src/nolan/` at this stage.** If it earns its way in,
   "promote into NOLAN" is a separate later decision (like beautiful-article was).
2. **It's a narrower medium than NOLAN** — the *express lane* for **text/data/explainer
   content with no footage** (keynote, tech review, talk/product demo, concept explainer).
   Complements NOLAN's heavy asset lane; doesn't compete with it.

## Structural insight (skill ≈ NOLAN's segment model)
- Isomorphic tree: **chapter ≈ scene/section**, **step ≈ segment/beat**, `narrations[i]` ≈
  segment narration, the `if(step===N)` JSX ≈ the segment's resolved visual.
- The real axis of difference is **NOT asset-vs-code** (NOLAN already does coded animation via
  its scene-template/effect library). It's **template-library-driven (NOLAN) vs
  bespoke-per-beat-generative (skill)**. That one choice cascades into:
  - **Granularity** — asset/template-paced = coarse (1–3 sentences/segment); idea-paced coded
    reveal = fine (≈half-sentence/beat). Coupled to the fill, not an independent knob.
  - **Sync** — NOLAN = word-level **timeline alignment** (needs forced-alignment, can drift).
    Skill = **audio-event-driven**: each step owns its mp3, auto-advance on `ended` (+200ms),
    no global clock. "Visual is master, audio paces it" — sidesteps alignment/drift. **Worth
    testing as a possibly-better model for the asset-lite case.**
- So: **isomorphic in structure, divergent in execution — and the divergences are caused by
  the resolver choice, not independent.**

## The "react engine"
- Not a framework — a ~15 KB convention: `Stage` (fixed 1920×1080 + `transform: scale`),
  `useStepper` (one cursor, no timer), `useAudioPlayer`/`useAutoMode`.
- NOLAN uses React for video too (**Remotion** = `(frame)⇒JSX`, deterministic headless render).
  This skill is `(step)⇒JSX` **live in a browser, advanced by audio, captured by recording** —
  a different paradigm NOLAN does **not** currently have.

## Integration seams where NOLAN adds value (the standalone skill lacks)
- **TTS:** the skill's provider contract is one shell fn `tts_synthesize <text> <out.mp3>
  <voice>`. NOLAN's `OmniVoiceTTS` (local, zero-shot **voice cloning**, no API key) plugs in as
  `tts-providers/omnivoice.sh` in ~30 lines. Only coupling = `public/audio/<id>/<step>.mp3`
  (1-indexed). Replaces paid MiniMax/OpenAI/ElevenLabs.
- **Recording:** the skill has **no programmatic capture** (manual screen-record only). NOLAN
  has headless Chrome + render-service + ffmpeg → a `?auto=1` → mp4 driver (Playwright/CDP
  screencast muxed with the per-step mp3s). **This is the novel risk to de-risk.**
- **Deeper (future):** render the same chapters via NOLAN **Remotion** deterministically →
  no screen-record at all. Destination, not start.

## Architecture to reduce agent burden — the determinism gradient
The skill is currently **all-Raw** (every beat bespoke). Add lower, more-deterministic layers
(mirrors the article skill's `figure → primitives → Raw` tiering, which cut section code
**−58%** and authoring **~190k→71k tokens**):

| Layer | Fixes | Determinism | Status |
|---|---|---|---|
| **Theme** | look (color/type/space) | full (token packs) | exists, ~20 |
| **Blocks** | reusable animated components | parameterized data-prop | **build it** |
| **Chains** | proven block-sequences per beat-type | semi (defaults) | advanced |
| **Raw** | the one signature beat | bespoke (agent) | exists |

- **The skill already validates this at the style layer** — it offloads aesthetics to themes so
  the agent only invents motion+layout. We extend the same offloading to *structure* (blocks)
  and *composition* (chains). The author resisted this (anti-template), but our article work
  already showed it pays off.
- **Blocks must be step-aware** — a block declares "K steps consumed + what each reveals."
  Composing blocks then **auto-derives `narrations.length` + narration slots**, *reinforcing*
  the skill's single-source-of-truth instead of fighting it.
- **Chains = productize the skill's existing relation-prefixes** (`反差对照`/contrast,
  `递进列表`/list, `金句`/punchline, stat, process) + its "relation→action decision tree" into
  `beat-relation → block-sequence` **defaults the agent can override** (never mandates — else it
  degrades to a translation machine).
- **Design rule:** *determinism in the plumbing (layout / step-choreography / timing),
  expressiveness in theme + Raw.* That's how you get the token savings **without** samey output.
- **Economic premise:** the block/chain library is what makes the express lane actually
  *express* — without it, bespoke-per-beat coding can cost as much as the heavy pipeline,
  defeating the point.

## Build approach
- **Harvest, don't invent.** Run the first few presentations bespoke-first, then mine the
  recurring beat-shapes into blocks (the relation-buckets are a prior). The article figures
  earned their keep by collapsing ~90% of bespoke Raw into 6 recurring shapes — same here.
- **Design blocks for both backends** (web-playback now, NOLAN-Remotion later) so a good block
  is portable — it becomes the concrete shared substrate for an eventual "one scene_plan, two
  render lanes (heavy asset-mp4 / express web), or mixed per-segment."

## NOLAN convergence / payoff (even without merging)
- The block library is the **same kind of asset as NOLAN's scene-template library** → the bridge
  to "one model, two lanes." Plus a virtuous loop via CLAUDE.md's **"Promote Techniques to
  NOLAN"** workflow: great sandbox blocks → promoted into NOLAN's reusable scene templates.

## Open questions / next
- Seed blocks up-front vs **harvest** after 2–3 bespoke runs (leaning harvest).
- First test: **HUMAN 3.0** (Dan Koe), a *portion* of chapters — scaffold + author a couple
  chapters bespoke, then probe: OmniVoice provider, audio-event sync, headless record.

---

## Test run 1 — HUMAN 3.0 (portion) — results
Workspace: `web-video-lab/human-3.0/`. 2 chapters (`hook`, `one-map`), 12 steps, theme
`bold-signal`, authored by **2 parallel sub-agents** (skill mode C). Scaffold + `tsc` + `vite
build` all clean in WSL (node 22). 12 step screenshots in `presentation/dist/_shots/`.

**What worked — output quality is real.** Designed-deck quality, content-driven motion:
`NPC` struck-through over a faint daily-loop terminal; "Level 100 / map unlocked" grid; a
sealed-boxes→interconnected-web SVG diagram; dual stat-bars (one maxed, one crashed) for the
broken archetypes. The `bold-signal` theme held visual unity across **both** chapters.

**Key finding — validates the determinism-gradient thesis.** Parallel bespoke authoring
**diverged on the axis nothing pinned**: on-screen **language**. ch1 → English (6 CJK chars),
ch2 → Chinese (290 CJK chars) — the skill's Chinese-origin example biased ch2 toward `serif-cn`.
The *look* stayed consistent (theme tokens = deterministic floor held); everything **not**
pinned by a deterministic layer drifted. Direct evidence for: (a) cheap fix = explicit
constraints in the chapter brief (e.g. "on-screen language = English"); (b) real fix = a
**block layer** that pins structure/idiom so the agent can't drift it. Theme alone unifies
style, not language/structure.

**Headless-capture seam (probed).** `file://` fails — the scaffold loads ES-module scripts,
which Chrome blocks over `file://` (the article skill only worked there because it inlines
single-file). **Served HTTP + Windows-Chrome `--screenshot` works**, bridged by WSL2 localhost
forwarding (default NAT otherwise isolates WSL↔Windows). Added a lab-only `?c=&s=` deep-link
(`main.tsx`, keyed to `useStepper`'s STORAGE_KEY) + `base:'./'` to target any step. So a
headless **recorder** is feasible here, but needs a served URL + the deep-link, not `file://`.

## Test run 2 — OmniVoice narration + narrated mp4 (the two integration seams)
Built on run 1's `web-video-lab/human-3.0/`. Tools: `synth_omnivoice.py`, `build_narrated_video.sh`.

**Seam 1 — OmniVoice TTS plugged in (proven).** `synth_omnivoice.py` drives NOLAN's
`nolan.tts.OmniVoiceTTS` (read-only) on the **RTX 4090** in the dedicated CUDA env, cloning
`voices/shakespeare-narrator/sample.wav`, and synthesized **all 12 segments** straight into the
skill's `public/audio/<chapter>/<step>.mp3` (1-indexed) layout. So NOLAN's local zero-shot
voice-cloning *is* the skill's TTS engine — no API keys, no MiniMax/OpenAI. The skill-native
form is a ~30-line `tts-providers/omnivoice.sh`; we ran the **batch** path (one model load) since
the per-segment contract would reload the model 12×.

**Seam 2 — narrated mp4, built headlessly (proven).** `build_narrated_video.sh` reads each
step's mp3 duration and holds that step's frame for exactly that long, then muxes the
concatenated narration → `human-3.0_narrated.mp4` (h264+aac, **135 s, 4.3 MB**, mean −16 dB
speech). This **reproduces the skill's audio-event sync deterministically** ("step lasts as long
as its clip") and — crucially — **without a manual screen-record**: the exact NOLAN value-add
over the standalone skill (whose only output path is human screen-capture). OmniVoice durations
tracked the script estimates well (hook 62.5 s, one-map 68.2 s).

**Still open — in-step MOTION capture.** The mp4 is *stills-per-step* (settled frame held for the
narration); the CSS entry animations within a step aren't captured. Two ways to add motion
headlessly, both feasible here, neither yet built: (a) sample frames per step via Chrome
`--screenshot --virtual-time-budget=T` over the proven HTTP path (deterministic, ~dozens of
launches/step); (b) CDP `Page.startScreencast` (needs WSL→Windows-chrome debug-port reachability,
untested under NAT). This is the "headless recorder" the insights flagged as *must-build*.

**Net for the experiment:** both NOLAN-leverage seams (voice + render-to-mp4) work; the express
lane already produces a real narrated video deterministically. Remaining polish = in-step motion.

## Fix — on-screen language enforcement (skill change)
Run 1's language drift (ch1 EN, ch2 ZH) was fixed at the **root**, not patched per-prompt — the
proper fix the divergence argued for:
- **Detect**: `detect_lang.py` (dependency-free; counts CJK per-char but Latin per word-run so
  `10 hanzi` isn't out-voted by the letters of 3 English words). `script.md` → `en`.
- **Declare**: `outline.md` header now carries `On-screen language: English (en)`.
- **Enforce in the skill copy** (`web-video-lab/skill/`): a hard rule in **CHAPTER-CRAFT.md**
  («屏幕语言 / On-screen language» — on-screen text = the article's language; the example is
  illustrative, never inherit it; checked in the completion self-check), a Phase-1.2 step in
  **SKILL.md** (detect + declare + pass to every chapter agent), and a ⚠️ warning atop the
  bundled **example chapter** (the bias source). ch2 re-authored to English (0 CJK).
- **Lesson restated**: theme tokens pin *style*, not *language/structure* — anything a
  deterministic layer doesn't pin will drift under parallel authoring. This is the first
  concrete pull toward the **block layer** (pin idiom/structure so agents can't drift it).

## Test run 3 — "compute, don't capture": word-timestamp-driven Remotion block
The screenshot/virtual-time capture was the wrong paradigm (observe an independently-timed CSS
animation, retrofit sync). Right paradigm: **audio word-timeline is master; motion is a computed
function of it; render deterministically.** Probed it end-to-end.

- **Per-word timestamps** from the OmniVoice wav via NOLAN's `whisper.transcribe_words`
  (`word_timestamps.py`; CPU — GPU whisper hit a missing-cuBLAS dll in this env). The model-list
  step → reveal schedule: Spiral 0.00s · Buddhism 2.18s · Red Pill 4.98s · eCommerce 7.44s.
- **`ListReveal` block** (parameterized, step-aware): `{items, revealFrames[], audioSrc}` — each
  item springs in at `frame - revealFrames[i]`, `<Audio>` muxed. Rendered via **NOLAN's existing
  Remotion pipeline** (`render-service` v4.0.404 + its `node_modules`, the `render.mjs`/job-JSON
  contract) — touching no existing NOLAN file (additive `render-service/_lab_listreveal/`, mirrored
  to `web-video-lab/remotion-probe/`, both removable). Output: `listreveal.mp4` (h264+aac, 12.4s).
- **Verified**: at 3.5s only items 1–2 are present (item 2 appears exactly on the word "Buddhism");
  at 9.5s all four, each on its spoken cue. **Word-accurate, deterministic, zero screenshots.**
- **The convergence, now concrete**: NOLAN *already has* the deterministic timeline renderer
  (Remotion in render-service, with a block library: KineticText/BarCompare/AnnotateStat/…). The
  express lane "done right" = feed NOLAN's Remotion **coded blocks + word timestamps**, exactly how
  its main video pipeline composites assets on a timeline. Express lane ≈ main pipeline with
  code-motion blocks instead of matched b-roll.
- **Theme faithfulness (the 23-theme library carries into Remotion)**: the block was rewritten to
  use **only the skill's semantic tokens** (`--surface/--text/--accent/--rule/--font-*/--t-*/
  --space-*` + the `.stage-frame::after` surface-pattern overlay), and `render.mjs` stages the
  chosen `skill/themes/<id>/tokens.css` (+ loads its Google fonts) per job. **Proven by swapping one
  field**: the identical block + identical motion rendered as **bold-signal** (dark gradient, Archivo
  Black, hot orange) and **paper-press** (light cream + multiply paper texture, Instrument Serif,
  warm red) — colors, surface decoration, fonts, type scale all swapped, zero code change. So the
  skill's theme library (+ figure/block library) is a **shared asset across both renderers** (browser
  playback AND Remotion-to-mp4), bound by one token contract. *(Remaining: load the active theme's
  font list generically — here we preloaded the two demoed themes' fonts.)*

## Library leverage (web research)
For word-timestamp-driven, React-based, deterministic mp4, runnable locally:
- **Alignment**: **WhisperX** (forced alignment seeded with our known script = highest accuracy)
  or `@remotion/install-whisper-cpp --dtw` (keeps it all in Node). faster-whisper (NOLAN's, native
  word ts) is the quick path — used here.
- **Renderer**: **Remotion** (NOLAN already runs it). ⚠️ **License**: free for individuals /
  non-profits / for-profit teams ≤3; **4+ in a for-profit org → paid** (Creators $25/seat/mo, etc.).
  MIT fallback = **Revideo**. Flag for if NOLAN ships to a bigger team.
- **Free helpers**: `@remotion/captions` (`createTikTokStyleCaptions`, `Caption{text,startMs,endMs}`
  = our normalized handoff), `@remotion/media-utils` (`getAudioData`, `visualizeAudio`),
  `interpolate`/`spring`/`TransitionSeries`. Official **`template-tiktok`** = whisper→word-captions→
  animated, the closest reference to clone. We build only: the OmniVoice→aligner glue + the mapping
  from `Caption[].startMs` into each block's reveal schedule.

## Test run 4 — a WHOLE chapter through NOLAN's Remotion (block library + driver)
Built `render-service/_lab_chapter/` (mirrored to `web-video-lab/remotion-probe/chapter/`).
Rendered the full **one-map** chapter (6 steps) to `one-map_chapter.mp4` — **68 s, 2048 frames,
h264+aac**, deterministic, no screenshots.
- **Block library** (token-faithful, step-aware, `revealFrames`-driven, wrapped in a shared
  `Surface`): `ListReveal`, `HeroStatement`, `WebVsBoxes` (sealed-boxes→connected-web SVG, the
  signature diagram), `ArchetypeCards` (dual maxed/crashed stat bars), `Timeline` (Greek-Philosophy→
  Internet/AI axis + struck "money"). 4 of them built by parallel sub-agents off the `ListReveal`
  reference + token cheatsheet.
- **Driver** (`Chapter.tsx`): a Remotion `<Series>` — one `Series.Sequence` per step with its
  narration `<Audio>`; `useCurrentFrame()` is step-relative, so each block's `revealFrames` (from
  that step's word timestamps) line up with the spoken words automatically. `render.mjs` stages the
  theme + each step's mp3; composition length = sum of step durations.
- **Word-synced**: each step's `revealFrames` derived from `whisper.transcribe_words` per step
  (e.g. step 4 boxes on "classes" @3.22 → web on "web" @4.74).
- **Theme-faithful + swappable**: every block uses only `--tokens`; `"theme"` is one job field.
- **Honest gaps / next**: (1) `revealFrames` were hand-mapped in the spec — the real automation is a
  **spec generator**: (chapter steps + word-timestamps) → which words map to which sub-items → job
  JSON. (2) Per-theme font loading (currently the demoed set). (3) It's a *library-block* rendition —
  cleaner/more uniform than the bespoke browser chapters; that's the library-vs-bespoke tradeoff (and
  the point). The probe folders are additive under `render-service/` and removable.

## Test run 5 — spec generator (data-driven, no hand-tuned frames)
`gen_spec.py` + `specs/one-map.spec.json`. The author writes per step: block + props + **anchors**
(a word/phrase per reveal point, e.g. `["Spiral","Buddhism","Red","commerce"]`, or `@start` / `@2.5s`
/ `@f0.5`). The generator resolves each anchor against that step's word timestamps → exact reveal
frame, reads wav durations, and emits the render job. **Validated**: regenerated one-map → reveals
land on the actual spoken word (`classes`@97, `businessman`@145, `money`@301) — *more* accurate than
my earlier hand-tuning — rendered identically (2048f). Bug found+fixed: tiny words ("a","i") were
matching as substrings of long anchors → now require exact-match or both-tokens≥3-chars. So a chapter
now renders **from data** (anchors + timestamps), no frame math.

## Improvement roadmap (skill × NOLAN × third-party) — from the HUMAN 3.0 test
**Author** (script→plan): the **skill** is the brain — its relation-prefixes (contrast/list/stat/
punchline) + "relation→action decision tree" should *select the block* and emit the anchor spec, so
the skill's chapter agent authors `{block, props, anchors}` (closing the only manual step left).
The skill's **figure taxonomy** (StepFlow/HubSpoke/CompareCards/VersusPair/CardGrid/ProportionBar/
Timeline/Stat/PullQuote) = the block library to port. **Align**: upgrade NOLAN's faster-whisper →
**WhisperX** forced alignment (we have the script → sub-100ms, near per-char); fix the GPU cuBLAS
dll. **Blocks/render**: reuse **NOLAN's existing remotion-lib blocks** (BarCompare/KineticText/
AnnotateStat/RouteMap…) + register ours in its `registry.json`; eventually drive via NOLAN's
render-service job server instead of the lab folder. **Third-party (all `@remotion/*` = same license
we already carry)**: `@remotion/transitions` TransitionSeries (kill hard-cuts) · `@remotion/paths`
evolvePath + `@remotion/shapes` (trivialize edge-draw/strike-through) · `@remotion/layout-utils`
fitText (headline-overflow safety) · `@remotion/captions` (word-synced subtitles straight from our
timestamps) · `@remotion/fonts` (per-theme font loading — closes that gap) · `@remotion/lottie` (play
NOLAN's Lottie library) · **d3-force** (auto graph layout for WebVsBoxes, run to fixed ticks offline =
deterministic) · **roughjs**+seed (scribble themes). Cross-cutting rule for deterministic headless
render: fixed seeds / fixed sim-ticks / font-load-gating everywhere.

## Test run 6 — loop closed: the skill authors the spec (fresh `hook` chapter)
`BLOCK_CATALOG.md` is the authoring contract (spec format + each block's props +
anchor-count + a relation→block selection guide). A spec-author agent — given ONLY the
hook script + the catalog — wrote `specs/hook.spec.json`: it **selected a block per beat**
(HeroStatement / ListReveal), **filled props** (even adding editorial tags Mind→Intellect…),
**picked anchor words** from the narration, and **flagged the two gaps** (`_needsBlock:
BigStat` for the "Level 100 grid" and "15yrs/5yrs" beats) instead of forcing a bad fit — exactly
the harvest-the-gap behavior the catalog prescribes. Then `gen_spec.py` → render → **`hook_chapter.mp4`,
62.6 s, word-synced, deterministic** (one transient Remotion tab `ProtocolError` but the mp4
completed clean — add render retries later).

**The express lane is now end-to-end automatic:**
`essay → (skill/agent: script + outline) → (agent: block+anchor spec, per BLOCK_CATALOG) →
gen_spec (word-timestamps → frames) → NOLAN Remotion (token-faithful blocks, 23 themes) → mp4`.
The only human input is the source; everything else is data-driven, reusing the skill's brain +
themes + figure taxonomy and NOLAN's Remotion + TTS + whisper. Remaining growth is *additive*: build
the flagged blocks (BigStat…), adopt the `@remotion/*` upgrades (transitions/paths/fitText/captions/
fonts), WhisperX alignment, and fold the lab into NOLAN's render-service proper.

## Test run 7 — the HYBRID (library blocks + Raw bespoke tier), tested on HUMAN 3.0 hook
The honest review concluded the right end-state is a hybrid: library blocks for the recurring 80%,
a **Raw/bespoke tier** for signature beats — *same engine* (Remotion), so it stays one deterministic
render. Implemented properly and tested.
- **Contract change**: `gen_spec` now emits, per step, the **full per-word timeline**
  `words:[{text,startFrame,endFrame}]` alongside `revealFrames`; the `Chapter` driver passes both to
  every block. Library blocks use `revealFrames`; **bespoke blocks use `words` for per-word
  choreography** (so bespoke syncs *tighter*, not looser). `BLOCK_CATALOG.md` gained the Raw-tier +
  promotion section.
- **Bespoke ≡ library file shape** — a bespoke block is just a token-faithful, `Surface`-wrapped
  Remotion component written fresh for one beat, in the same registry. *Not a different engine.*
- **Test (hook chapter, 3 library + 3 bespoke, one 62.6s mp4):** the 3 monotonous fallback
  `HeroStatement`s were replaced by bespoke signature beats, **visibly richer**:
  - `NpcStrike` — "NPC" accent-boxed, a strike-through **drawn across it exactly as the word "NPC"
    is spoken**, over a scrolling "someone-else's-script" terminal backdrop.
  - `LevelUnlock` — "LVL 100" + an 8×4 map grid **unlocking tile-by-tile** (diagonal sweep).
  - `YearsStat` — two numbers **counting 0→15 / 0→5 timed to the spoken words** "fifteen"/"five"
    (caught a frame mid-tick showing "4" → proof the count rides the word).
  Interleaved with library `ListReveal`×2 + `HeroStatement`, all token-faithful + theme-swappable.
- **Promotion path live**: `LevelUnlock`/`YearsStat` are the obvious generalizations of the earlier
  `_needsBlock` flags (BigStat/MapGrid) — authored bespoke now, ready to graduate to the library.
- **Last automation left**: the spec-author agent itself deciding *per signature beat* to author a
  bespoke block (vs only flagging `_needsBlock`) — here I orchestrated the 3 bespoke authors directly.
  Also: clean up the registry into `library/` (cataloged) vs chapter-local `raw/` (bespoke) for tidy
  promotion. Net: the hybrid delivers the skill's ceiling on hero beats + the pipeline's determinism/
  word-sync/cheap-at-scale everywhere else, in one engine.

## Gaps closed + timing (per ~62 s chapter, RTX 4090, single-machine)
**Gap 2 — structure:** blocks split into `src/blocks/library/` (cataloged) vs `raw/` (bespoke);
`BLOCKS = {...LIBRARY, ...RAW}`. Promotion = move a file `raw/→library/`. Re-rendered clean.
**Gap 1 — agent decides bespoke:** `SPEC_AUTHORING.md` codifies the per-beat *library-or-bespoke*
call; the agent emits a `bespoke:{brief}` (visual + word(s) to sync) instead of only flagging
`_needsBlock`; the orchestrator spawns block-authors from briefs. Demonstrated: a spec agent, from
the script alone, independently chose the **same 3 bespoke / 3 library** split and wrote the briefs.

**Measured wall-clock (deterministic stages):** TTS (OmniVoice, 6 seg, incl ~10 s one-time model
load) **18 s** · alignment (whisper **CPU** 11 s; ~2–3 s on GPU once cuBLAS is fixed) · `gen_spec`
**<1 s** · **render (Remotion, 1876 f @1080p) 37 s = 0.6× realtime, ~51 fps.**
- **Render only:** 0.6× realtime.
- **Full deterministic** (tts+align+gen+render): ~66 s ≈ **1× realtime**.
- **Library-only chapter** (mature library, no new bespoke): +~50 s spec authoring = **~2 min (~1.9×)**.
- **Hybrid w/ 3 NEW bespoke** (first time): +~50 s spec +~105 s (3 block-authors in parallel) =
  **~3.7 min (~3.5×)**; sequential ~5.5 min.
- **Key dynamic:** bespoke authoring is a **one-time cost per pattern** (promote → library → free
  next time), so per-video cost decays toward the ~2 min library number as the library matures.
  Token cost similarly: ~25–30k (library chapter) vs ~100–120k (chapter that builds 3 bespoke).
- Caveats: render is parallelizable (cores/cloud); GPU whisper shaves ~8 s; TTS model-load amortizes
  across chapters; agent latency varies. Full video ≈ linear in chapters.

## Test run 8 — fresh end-to-end hybrid (compound interest) + a real bug it caught
Ran the WHOLE loop on a brand-new 6-beat script the pipeline had never seen: TTS (OmniVoice) →
whisper align → **spec author decided 4 library + 2 bespoke** (`SelfFeedingCurve`, `CompoundLadder`)
and wrote per-word sync briefs → 2 block-author agents built them from the briefs → `gen_spec` →
render → `compound.mp4` (39.4 s, render **23.5 s = 0.6× realtime**, same as before). Both bespoke
blocks rendered beautifully (a principal bar + feedback loop-arrow; a "$10,000 after 30 years" hero
over a widening-gap money ladder).
- **The test did its job — caught a genuine robustness bug** the curated HUMAN 3.0 runs hadn't:
  whisper transcribes spoken numbers as **digits** ("becomes 2,000 in 9 years"), so the word-form
  anchors "two"/"Four"/"Ten" didn't match → `gen_spec` fell back to evenly-spaced frames → the
  ladder's rungs + count-up lost their audio sync (right visual, wrong timing).
- **Fixed:** added number-word↔digit normalization to the matcher (`two`↔`2`, `ten`↔`10`, `thousand`↔
  `1000`…). Re-gen → reveals corrected to `[8,77,151,214]` (landing on the spoken 2/4/10), re-render →
  verified: at t=17.5 s only $1,000+$2,000 are up (staggered) and the hero rolls "$1,278 → $2,000"
  exactly as "two thousand" is said. Sync restored.
- **Verdict:** the hybrid pipeline works as expected end-to-end on unseen content — same render speed,
  the agent makes sane library/bespoke calls, bespoke blocks build from briefs and render clean — and
  the e2e test surfaced + closed a real edge case (number normalization) that curated tests missed.
  (`SelfFeedingCurve`/`CompoundLadder` are now promotion candidates → generic `GrowthCurve`/`MoneyLadder`.)

## Test run 9 — the FINAL video, with everything (audio + word-synced subtitles)
Added a `Captions` overlay (`src/Captions.tsx`) — a token-faithful karaoke subtitle band driven by
the per-word timeline already flowing through the driver; toggled by a `captions:true` job flag
(threaded spec → `gen_spec` → `render.mjs` → `Chapter`). Rendered **both HUMAN 3.0 chapters with
captions** (hook hybrid: 3 bespoke + 3 library; one-map: 5 library) and concatenated →
**`human-3.0_final.mp4` — 2:11, 1920×1080 h264+aac, 9.7 MB.** A complete piece with **everything**:
themed library + bespoke blocks, word-synced motion, narration audio, and a subtitle band whose
current word lights in `--accent` exactly as spoken (verified in-sync with the block above it).
- **Honest polish item:** captions use whisper's transcript tokens (lowercase, no sentence
  punctuation). The fix is to align the *known script* text to the word timings (WhisperX
  forced-alignment, already on the roadmap) so subtitles carry proper casing/punctuation.
- Net: the express-lane pipeline now emits a finished, shareable mp4 — motion + audio + subtitles —
  fully data-driven from a script, deterministic, themed, no human in the loop.

## Test run 10 — first promotions + a streamlined promotion process
Reviewed the 5 bespoke blocks for promotion. Verdict: promote the general+recurring+parameterizable
ones, keep the content-fused gags bespoke, harvest mechanics into existing blocks.
- **Promoted** (raw → `library/`): `YearsStat → StatCount`, `CompoundLadder → ValueLadder`,
  `LevelUnlock → UnlockGrid` (all generalized: de-themed defaults, props for content).
- **Harvested a primitive**: `src/primitives/RollingNumber.tsx` (`useCountToWord` — "roll a number
  to its spoken word") — StatCount + ValueLadder both compose from it (the mechanic, not the block,
  is the reusable atom).
- **Folded a mechanic**: NpcStrike's *strike-a-word-as-spoken* → into library `HeroStatement`
  (additive `strikeWord`); the terminal-backdrop gag stays bespoke. `SelfFeedingCurve` stays bespoke
  (too content-fused). RAW is now just NpcStrike + SelfFeedingCurve.
- **Streamlined the PROCESS** (the meta-ask): `gen_registry.py` auto-builds the 3 index files from
  the directory contents, so **promotion = `mv raw/X.tsx library/Y.tsx` + regenerate** (kills the
  hand-edited-index concurrent-edit bug). `PROMOTION.md` documents the gate (recurrence +
  parameterizable + low-overlap) and the 6 steps. `BLOCK_CATALOG.md` gained the 3 entries + selection
  rows. Library is now **8 blocks, RAW 2**.
- **A real lesson surfaced + recorded**: spec-settable props must be **JSON-serializable** — a
  `format:(n)=>…` callback can't ride a JSON spec, so ValueLadder gained string `prefix`/`suffix`
  props (the `$` now comes from the spec). Noted in PROMOTION.md.
- **Verified**: re-rendered hook (now StatCount/UnlockGrid) + compound (now ValueLadder) clean;
  StatCount counts via the primitive, ValueLadder shows `$2,000` (prefix) on a `yr` axis. Equivalent
  to the bespoke originals, now reusable.

## Test run 11 — a research PAPER explainer ("Attention Is All You Need", blueprint theme)
First non-narrative source: arXiv 1706.03762 → a ~1:41, 10-beat storytelling explainer carrying the
paper's real **formulas, results table, and compute chart**. Validates the hybrid on technical content.
- **5 new bespoke blocks**, built in parallel, all token-faithful + `Surface`-wrapped + same
  `revealFrames`/`words`/`durationInFrames` contract: `Formula` (KaTeX), `AttentionFlow`
  (all-to-all self-attention web over word-chips), `ArchStack` (encoder/decoder schematic with
  residual wrap-arrows + dashed K·V link), `DataTable` (row-by-row results table, highlight row),
  `BarChart` (count-up comparison bars).
- **KaTeX renders through Remotion cleanly** — the main risk. `katex.renderToString(latex,{displayMode})`
  → `dangerouslySetInnerHTML`, with a `clipPath` write-on reveal. Display fractions, √, super/subscripts,
  and **multi-line `\begin{aligned}`** (the sin/cos positional-encoding pair) all typeset correctly at
  1080p. KaTeX `^0.17.0` installed **lab-local** (`render-service/_lab_chapter/`, render-service untouched).
  Needed `IBMPlexMono`/`IBMPlexSans` added to `index.tsx` for the blueprint theme.
- **Caption fidelity fix (pipeline-wide):** captions were whisper-derived for timing, so technical
  tokens garbled on screen ("BLEU"→"BLU", "28.4"→"28 .4", "two"→"2") even though the audio was correct.
  Fix: `gen_spec.py` now **carries the authoritative script spelling onto whisper's timing** —
  `difflib.SequenceMatcher` aligns canonicalized token streams; equal runs map 1:1 (exact timing),
  rewritten runs distribute the script tokens across that run's time span. Emits a separate
  `captionWords` (whisper `words` left untouched so block choreography is unchanged); the driver feeds
  `captionWords ?? words` to the subtitle band. Spec gains an optional `segments` path. Captions now read
  "Twenty-eight point four **BLEU** …" with karaoke timing intact. Insight: **whisper for timing, script
  for spelling** — never show the transcript as text when the script exists.
- **Promoted `Formula`, `DataTable`, `BarChart` → library** (universal technical archetypes — any
  paper/data explainer reuses them; already fully prop-driven, names unchanged so the spec needed no
  edit). Catalog gained 3 entries + selection rows. `AttentionFlow` + `ArchStack` are
  transformer-specific → stay raw. **Library is now 11 blocks, RAW 4.** Re-rendered post-promotion:
  Formula/DataTable resolve from `library/` and render identically (the `../../Surface` imports are
  unchanged since raw/ and library/ sit at the same depth).

## Test run 12 — the LIFT-AND-PLACE tier (`PaperFigure`): the paper's own figure, narrated
The one honesty gap in "redraw everything": some figures are **empirical artifacts** (attention
heatmaps, plots of real data, sample outputs) — redrawing them = *fabricating data*. So a new tier
**lifts the paper's own image** instead. Decision rule: **"could I regenerate this exactly from
symbols/numbers I have?"** Yes → redraw (Formula/DataTable/BarChart, on-theme). No → lift.
- **`extract_figure.py`** (new, arxiv-HTML aware): arXiv HTML stores figures as separate `<img>`
  assets, so extraction = find the figure's img → download → trim near-white margins (→ optional
  matte-to-transparent). One command pulled Fig 3 (the "making…more difficult" long-distance
  dependency heatmap).
- **`PaperFigure` library block**: places the image on a themed **"exhibit card"** — a light specimen
  panel framed by the theme's rule/accent + a **cited source** ("Fig. 3 · Vaswani et al., 2017") +
  themed kicker. This *sidesteps the matte-to-transparent trap*: a light-ink figure matted onto a dark
  theme goes invisible, so we don't fight the white bg — we frame it as a deliberate pinned specimen,
  which reads intentionally on any of the 23 themes.
- **Signature motion = "compute, don't capture" on a borrowed asset.** The figure is static, but a
  **word-synced accent highlight** sweeps to a region (fractional coords) exactly as the narration
  names it — verified: a "READS" box lands on the *making* column at 4.36 s, an "ATTENDS ACROSS" box
  pops onto the *more difficult* cells at 9.54 s, tracking the karaoke caption. The lifted figure
  becomes an exhibit we *narrate*, not a paste. (`render.mjs` stages `props.src` images like it stages
  audio.) Demo: `transformer/final/figure-lift-demo.mp4`.
- **How it fits the gradient**: a library block fed by an asset-prep step (extract+trim alongside
  TTS/whisper) — purely additive, nothing existing changed. **Library is now 13 blocks.**
- **Honest limits**: arxiv figures are low-res (Fig 3 is 595 px, ~2× upscale → slightly soft but
  legible); matte-to-transparent only suits figures with their own dark/colored fill (line-art on
  white needs the exhibit card or inversion); PDF-only sources would need pymupdf/pdffigures2 (HTML
  was trivial). Reserve lift for *un-redrawable* figures — redraw stays better wherever it's honest.

## Test run 13 — a NEW input format (MinerU parsed folder) + a NEW domain (finance)
Tested on a J.P. Morgan equity-derivatives report ("Thinking Outside the Box for Tail Trading"),
parsed by **MinerU** into `content.md` + `images/<hash>.jpg` + `metadata.json` — a different shape from
arXiv HTML, and a non-ML domain full of empirical charts (PnL curves, return distributions). Both
goals met: the pipeline worked, and we taught it the new format.
- **MinerU adapter** (purpose 2): `extract_figure.py` gained a `--md` mode + `--list` catalog. MinerU's
  convention is `![](images/<hash>.jpg)` followed by a `Figure N: caption` (and optional `Source:`)
  line, so `mineru_figures()` walks the markdown → `{figure, image, caption, source}` doc-ordered. The
  catalog (38 figures) is what the chapter agent reads to choose which to lift; images are already
  extracted, so "extraction" is just copy+trim. (Gotcha: the Windows python prints smart quotes in the
  console codepage → mangled on a `>` redirect; fixed by writing the JSON file directly as utf-8 via
  `--out`.)
- **Workflow ran end-to-end** (purpose 1): chapter agent read content.md + catalog → authored a 6-beat
  arc (segments.json + spec.json), choosing **redraw vs lift** correctly — StatCount for the signal
  stats (1,000+ inversions, 1.95σ), ListReveal for the 3 pillars (Delta/Gamma/Vega), **PaperFigure to
  lift Fig 1** (the stacked PnL backtest — un-redrawable), DataTable for the Fig 38 overlay comparison,
  HeroStatement hook + punchline. Then TTS → align → gen_spec → render (theme `midnight-press`). All
  agent numbers **verified against the paper** (Fig 38: returns 12.5→17.1%, Sharpe 0.69→1.11, worst-1D
  −12→−5%, MaxDD −38.2→−17.6% — all exact).
- **A real block bug it surfaced + a generalization**: StatCount fed its `value` straight into
  `interpolate`'s output range, so the agent's string values ("1,000+", "1.95σ") crashed it
  ("outputRange must contain only numbers" at the count-up). Fix (same lesson as ValueLadder's `$`):
  **numeric `value` + JSON-serializable `prefix`/`suffix`/`decimals`**; `useCountToWord` gained a
  `decimals` option so non-integers count cleanly (1.95 ticks to two places), and StatCount formats with
  grouping (`1,000+`) + suffix (`1.95σ`). Verified: both stats count up correctly on their spoken words.
- **Generality confirmed**: a finance report on a serif/dark editorial theme rendered as cleanly as the
  ML papers on blueprint — same blocks, same contract. PaperFigure's 2020-tail-event highlight bracketed
  the exact step-up after one coord tune. Demo: `tailtrading/final/tail-trading-explainer.mp4` (2:47).
- **Verified**: every beat frame-checked — all three KaTeX formulas, the attention web, the
  encoder/decoder schematic, the highlighted BLEU table, the compute bars, both hero cards. Final
  `attention-explainer.mp4` (h264+aac, faststart) in `web-video-lab/transformer/final/`.

## Library boost (3 waves) — leverage existing libs as GENERATORS, never runtimes
Acted on the web-research roadmap (`LIBRARY_BOOST.md`). Governing rule from all 4 streams:
adopt libraries as geometry/math/asset *generators* and keep driving every reveal from the
Remotion frame ourselves — anything that animates on wall-clock time (react-spring, Framer
runtime, GSAP ticker, CSS keyframes, expression-Lottie) breaks headless determinism. **Library
grew 13 → 22 blocks.**
- **Wave 1 — theme tokens + PaperFigure**: added (additive, to `base.css`, inherited by all 23
  themes) M3 motion tiers (`--dur-*`/`--ease-decel|accel`), an elevation scale (`--elev-0..5`),
  a **color-mix-derived accent ramp** (`--accent-fill/-border/-hover/-subtle`, `--surface-tint`)
  so every theme gets fill/border/hover off its own `--accent` with no per-file edits, and
  composite line-heights. New `primitives/annotate.tsx`: `useKenBurns` (zoom-to-region),
  `Spotlight` (SVG-mask dim-the-rest), `SketchBox` (seeded rough.js draw-on). PaperFigure now
  **guides the read** — spotlight dims around the spoken region (verified on the tail-trading PnL
  figure). roughjs installed lab-local.
- **Wave 2 — chart tier (the highest-leverage bet)**: visx + d3 generators, frame-driven. New
  `primitives/chart.tsx` (`Axis`, `SweepClip`, `sweepProgress`, `fmtNum`) + blocks **LineChart**
  (area+line, left→right sweep, live readout), **Distribution** (histogram, highlight range,
  mean marker), **Heatmap** (color-mix sequential scale, diagonal sweep, highlight cell). All
  verified rendering. This ends the hand-rolling of every chart (the DataTable/StatCount toil).
- **Wave 3 — transitions + structural blocks + lottie + eval**: new blocks **ComparisonVS,
  PullQuote, StepFlow, KineticHeadline, ChapterCard, EndCard, LottieIcon** (built in parallel,
  same contract); a **transition layer** — a separate `Montage` composition using
  `@remotion/transitions` (fade/slide/wipe/clockWipe) + `@remotion/motion-blur`, kept OUT of the
  narrated Chapter (hard cuts stay audio-safe; overlapping `<Audio>` would overlap speech).
  Verified a 7-block, 4-transition montage (616 frames, overlap math correct). LottieIcon
  recolors assets to theme tokens via getComputedStyle + lottie-colorify (intake rule: keyframed,
  transparent-bg, expression-free). Authoring/eval captured in `SCENE_GRAMMAR.md` (section scene
  taxonomy, audio-as-master-clock, Entrance/Emphasis/Exit, PaperQuiz comprehension harness spec).
- **Tooling**: `gen_registry.py` now registers MULTIPLE exports per file (ChapterCard+EndCard).
  `render.mjs` selects composition (`Chapter`|`Montage`) and stages figure/lottie assets.
  Deps installed lab-local (render-service untouched): visx, d3-array, roughjs, flubber,
  @remotion/transitions|motion-blur|lottie, lottie-web, lottie-colorify.
