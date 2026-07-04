# Narrative → Asset Pairing — the operator space

*How professional editors and video-essayists connect a line of narration to what's on screen.*
This is the design map behind the evocative-b-roll engine (`src/nolan/evoke_broll.py`, `/broll`).

---

## The big idea

We did not build "tonal b-roll." We built a **general narrative→asset pairing engine**:

```
line → BRIDGE (LLM turns the line into what to look for)
     → RETRIEVE (source candidate assets)
     → GATE (keep only apt ones — e.g. period/locale)
     → ACCEPT (listwise "would an editor use this?" → matched | UNMATCHED)
```

**"Evocative / tonal" is just the first *operator* plugged into the BRIDGE.** Every other
pairing style below is another operator = a different bridge prompt + its own aptness gate.

### The evolution (the key strategic call)

Beyond simple clip-matching, the engine has to graduate from *"which clip?"* to
**"which asset(s) + what motion + how composed?"** Two consequences:

1. **Asset sourcing is multi-source**, chosen per operator:
   - **library search** (indexed video segments, BGE vectors) — built
   - **stock search** (Pexels/Pixabay/… cheap tiers) — built
   - **picture search** (stock photos / picture library / CLIP) — ✅ wired in (stills join the stock pool; scored directly)
   - **ComfyUI generation** — ✅ Krea-2 `mode=generate` (a still per metaphor); paired-stills→motion = future
2. **Composition is a first-class layer**, not an afterthought:
   - the **motion library** + **Remotion** apply the *right motion* to numbers, words,
     pictures and clips (Ken Burns, kinetic text, counters, bar/line/k-shape, pair-morphs…)
   - so an operator's output is an **asset spec + a motion spec**, not a bare URL.
   - ✅ **motion-selection layer** (`src/nolan/motion_select.py`): maps (operator + line intent + asset
     kind) → a *motivated* motion (push-in=significance, pull-out=isolation, parallax=immersion, hold=
     restraint …). Recommends the right treatment now; render effects light up as built (Ken Burns/hold/
     as-is available; parallax/atmospheric/rack-focus/blur-in/cinemagraph planned).
3. **Rhythm/tempo needs a deep link to the script** (pacing, energy, emphasis) — see D.

---

## The operators, by editorial function

For each: the mapping logic · a concrete example · who does it · how we'd build it here.

### A. Substitution — *replace* the literal subject with a stand-in that carries meaning
*(mostly "new bridge prompt" on the existing pipeline)*

| Operator | Logic → example | Build notes |
|---|---|---|
| **Tonal / emotional** ✅ *built* | line's *feeling* → mood footage. "a stranger to his own home" → cold empty shore | bridge = mood metaphors; stock+library; period/locale gate |
| **Conceptual-isomorphic** ✅ *built* | the concept's *mechanic* → a domain with the **same structure**. strategy→chess; collapse→dominoes; fragile stability→Jenga/house-of-cards; opposing forces→tug-of-war; systems→clockwork; emergent order→murmuration; inevitability→a river | bridge = "name the mechanic, find an isomorphic carrier domain" + a **conceptual-aptness** gate (fit + cliché-avoidance). Often best **generated (ComfyUI)** + a motion |
| **Trait / behavior embodiment** ✅ *built* | a person's quality → the archetypal *activity that exemplifies it*. patience→fishing/watchmaking; precision→surgery/calligraphy; discipline→training/running; obsession→repeated practice | bridge = trait → exemplar activity; b-roll/stock search |
| **Archetypal / mythic / art-historical** | a situation → shared iconography. hubris→Icarus; rebirth→phoenix; underdog→David & Goliath; betrayal→Judas; vain power→Ozymandias/ruins; judgment→the scales | bridge = situation → iconography; strong candidate for **ComfyUI generation** |
| **Masterwork raid (composition-matched sourcing)** 🔬 *evidence: Odyssey deconstruction* | a beat's *emotion/composition* → a real public-domain masterwork that fits, **even when it depicts something else**. prideful vow→*Oath of the Horatii*; crew despair→*Oedipus at Colonus*; decadent feast→*Romans of the Decadence*; a giant→Goya's *Fall of the Titans* | Discovered by deconstructing a mythology channel (`video_deconstructions/the-odyssey-explained…/breakdown.md`): of ~76 named works a large share are non-subject stand-ins picked by compositional/emotional fit — museum look at $0 art budget. Bridge = scene-type + emotion query over a **public-domain art corpus** (imagelib + extract-assets are the plumbing); `knowledge` extended from "the named asset" to "any real masterwork whose composition carries the beat". Prefer SOURCING over generating — authenticity is the point |
| **Sensory / textural (synesthetic)** | a sensory *adjective* → tactile macro. "cold, calculating"→frost forming; friction→sparks; decay→rust/rot time-lapse; warmth→embers | bridge = sensory→texture; stock macro + often a slow motion |
| **Idiom literalization (wit)** | a figure of speech shown *literally*. "throwing money away"→burning cash; "drowning in debt"→underwater | bridge = detect idiom → literal scene; generate or stock |

### B. Amplification — keep the literal, make it *land* (magnitude · mechanism · place)
*(**not pure matching** — these are asset + **motion composition** via Remotion / motion library)*

| Operator | Logic → example | Build notes |
|---|---|---|
| **Scale / tangibility** ✅ *built* | a number → a body-sized referent. "100B stars"→grains of sand; "$1B"→stadiums/city blocks | operator #6 on /broll (Approach: Scale). Bridge = **quantity extraction** (derives a number even when implied) + a period-safe/timeless **tangible referent** → referent b-roll scored for *scale + negative space* → **StatOver** count-up composition renders the number over the footage. **First asset + motion-composition operator.** Number/caption **styled by the video THEME** (`resolveTheme`), not hardcoded |
| **Process / mechanism analogy** | a "how it works" → a physical machine that behaves the same. overheating→boiling pot / pressure gauge; feedback loop→thermostat/snowball; bottleneck→hourglass | mechanism extraction → analogy; **clip/pictures + a motion** that shows the mechanism running |
| **Geographic anchoring** | a place / a *movement* → maps, satellite push-ins, route lines | `route-map` motion exists; bridge extracts place/route |
| **Data-as-shape** | a trend → a chart whose **silhouette mirrors the emotional arc** (rise=hope, crash=despair, the "K") | `bar-compare` / `line-chart` / `k-shape` motions exist; bridge maps the arc → chart shape |
| **Hero-literal** | sometimes the right cut *is* the actual subject, shot with reverence | restraint operator; literal search + a dignified Ken-Burns/hold |

### C. Relational — meaning from the *collision of two elements* (needs **pairs**, not single clips)
*(needs new machinery: source/**generate** two assets and drive them together in **one motion**)*

| Operator | Logic → example | Build notes |
|---|---|---|
| **Ironic counterpoint** ✅ *built* | the image **contradicts** the words for critique/comedy. VO praises progress → a landfill | operator #3 on /broll (Approach: Ironic). Bridge = surface message → ironic truth → contradicting imagery; scores irony + edge |
| **Historical rhyme** | now vs then; a modern line over archival that "rhymes" (2008 line ↔ 1929) | pair a contemporary + an archival asset; temporal juxtaposition |
| **Relational / dialectical** ✅ *built* | shot A + shot B → a *third* idea neither holds. gilded excess + starving labor | operator #5 on /broll: bridge finds a dialectical PAIR → two sub-selections (side A/B) → SplitScreen collision render |
| **Before / after · time-transformation** | change → time-lapse, decay/growth, morph | **generate a pair** (before, after) → **morph/dissolve motion** |
| **Binary / VS framing** | an opposition → split-screen, tug-of-war, boxing, diverging roads | `comparison`/VS motion exists; bridge extracts the two sides |
| **Match cut / graphic match** | link two ideas by shared shape/motion across a cut. circle→sun→coin; bone→spacecraft (*2001*) | craft-level; needs shape/motion continuity matching across a pair |

### D. Rhythm & absence — the invisible craft, about *time and restraint*
*(**requires a deep link to the actual script** — pacing, energy, emphasis)*

| Operator | Logic → example | Build notes |
|---|---|---|
| **Energy / tempo matching** | footage *motion* matched to the sentence's energy. frantic line→fast cuts; reflective line→one long slow drift | needs script-level tempo/energy signal + motion intensity control |
| **The withheld image** ✅ *modeled* | sometimes the strongest cut is **no b-roll** — black, or hold on a face | this is our **UNMATCHED** — abstention as a deliberate device |
| **Recurring visual motif / leitmotif** | give a person/idea a *returning* symbol that accrues meaning across the piece | a through-line, not a per-line pairing; needs whole-script state |

---

## Two editor's principles baked into the design

1. **Operator choice = authorial voice.** Literal-illustrative reads *journalistic* (Vox);
   heavy metaphor/irony reads *authored* (Curtis, Nerdwriter). Great pieces hold one register
   and **switch operators for emphasis** — an ironic cut lands hardest amid literal ones.
2. **The gate is aptness, not availability.** Period/locale was one constraint; every operator
   has its own (conceptual fit, cliché-avoidance, register consistency).

## How each maps onto the stack

- **A** → mostly a **new bridge prompt** on today's pipeline (+ ComfyUI gen for archetypal/idiom).
- **B** → bridge **+ quantity/mechanism extraction + motion composition** (Remotion / motion lib).
- **C** → **new machinery**: source/generate **pairs** and evaluate/drive the *collision* in one motion.
- **D** → **script linkage** (tempo/energy/through-line). Absence already modeled (UNMATCHED).

## Roadmap (value-to-effort)

1. **Conceptual-isomorphic** ⭐ — most distinctive; bridge + aptness gate (+ optional gen).
2. **Scale / tangibility** — explainer workhorse; first real **asset + motion composition** operator.
3. **Ironic counterpoint** — signature voice; "find the opposite" bridge (single, then pair).
4. **Trait-embodiment** — clean bridge, very reusable.
5. **Relational / dialectical** — the operator that gives the tool a *point of view* (pairs + gen + motion).
6. **Rhythm / tempo** — the invisible finish; requires the deep script link.

**Evidence engine:** the video-deconstruction feature (`/deconstruct`, `src/nolan/deconstruct/`)
now reverse-engineers real videos into this operator vocabulary — each breakdown is field
evidence for which unbuilt operators real editors actually use, and how. First yield: the
**masterwork raid** row above (Odyssey run, 2026-07-04) plus two reusable presets — the
*accreting journey map* (progressive `route-map` pins per episode) and *two-tier titling*
(circular portrait name-card for WHO + full-screen chapter card for WHERE).

## Status

- ✅ **Tonal/evocative** — `src/nolan/evoke_broll.py`, `/broll` page (stock + library modes,
  provider selection, period/locale gate, listwise accept / UNMATCHED). See `IMPLEMENTATION_STATUS.md`.
- ✅ **Conceptual-isomorphic** — operator #2 on `/broll` (Approach toggle). Bridge maps concept→mechanic→isomorphic carrier domain(s); scoring judges metaphor-fit + freshness (cliché-avoidance).
- ✅ **Ironic counterpoint / Trait-embodiment / Relational** — operators #3/#4/#5 on `/broll`.
- ✅ **Scale / tangibility** — operator #6 on `/broll` (Approach: Scale). Bridge extracts/derives the quantity + a period-safe **tangible referent**; referent b-roll is scored for scale + negative space; the **StatOver** Remotion composition renders a theme-styled count-up over the footage (still poster or generated referent). **First asset+motion composition operator.** The count-up number and caption are styled by the video **theme** (`resolveTheme` in `theme.ts`, as counter/kinetic-text), selectable on `/broll` (dark-editorial | light | high-contrast + accent override) and via `nolan broll --theme`. Falls back to **UNMATCHED** when no number exists or stock lacks a clean referent (precision > coverage).
- 🎯 **Rhythm / tempo** (the last operator) is **designed, not built** — it needs the deep script link.


## Still-motion build TODO (step 2 render effects)

Motion-library (Remotion) effects, each keyed to a `motion_select` id; built + visually tested one by one:
1. **Motivated Ken Burns** (salient-target push/pull/pan) — ✅ built (StillMotion)
2. **Parallax / 2.5D** (via cutout/rembg subject/background) — ✅ built
3. **Atmospheric overlays** (drifting motes + vignette + grade-drift) — ✅ built (light-leak/fog: future)
4. **Rack focus** + **blur-in** (depth/cutout) — ✅ built
5. **Transitions** — ✅ built (ClipMontage / @remotion/transitions: dissolve/slide/wipe/clockWipe/cut). *match-cut* (shape/motion continuity across a cut) = advanced/future. (ffmpeg xfade unavailable here → Remotion.)
6. **Cinemagraph / image-to-video** — ⏸ TODO: ComfyUI workflow (user will provide). 

**Asset generation:** ✅ ComfyUI **Krea 2** (`krea2-style-select`) generation source — `mode=generate` makes a still per metaphor (fooocus style, default 'Fooocus Cinematic'), served at `/broll-gen/`, scored/gated/animated like any still. Auto-fallback ('when nothing fits') = future.


## QA / integration status

- **Motion library**: still-motion / split-screen / clip-montage are first-class `MotionEffect`s in `src/nolan/motion/registry.py` (executor routes them to `nolan.still_motion`); reachable by every spec-system pipeline + in `build_guide()`.
- **CLI**: `nolan broll LINE` (operators / modes / `--render`) surfaces the pairing engine + motion-pick layer.
- **WebUI smoke test**: `scripts/broll_smoke.py` (headless chromium) — asserts no JS errors and that the operator/mode/media toggles, provider load, and show/hide wiring work. GREEN.
