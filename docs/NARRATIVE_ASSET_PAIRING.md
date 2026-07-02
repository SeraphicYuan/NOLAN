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
   - **ComfyUI generation** — when no found asset fits, *generate* it (stills, and
     eventually paired stills driven into a motion)
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
| **Trait / behavior embodiment** | a person's quality → the archetypal *activity that exemplifies it*. patience→fishing/watchmaking; precision→surgery/calligraphy; discipline→training/running; obsession→repeated practice | bridge = trait → exemplar activity; b-roll/stock search |
| **Archetypal / mythic / art-historical** | a situation → shared iconography. hubris→Icarus; rebirth→phoenix; underdog→David & Goliath; betrayal→Judas; vain power→Ozymandias/ruins; judgment→the scales | bridge = situation → iconography; strong candidate for **ComfyUI generation** |
| **Sensory / textural (synesthetic)** | a sensory *adjective* → tactile macro. "cold, calculating"→frost forming; friction→sparks; decay→rust/rot time-lapse; warmth→embers | bridge = sensory→texture; stock macro + often a slow motion |
| **Idiom literalization (wit)** | a figure of speech shown *literally*. "throwing money away"→burning cash; "drowning in debt"→underwater | bridge = detect idiom → literal scene; generate or stock |

### B. Amplification — keep the literal, make it *land* (magnitude · mechanism · place)
*(**not pure matching** — these are asset + **motion composition** via Remotion / motion library)*

| Operator | Logic → example | Build notes |
|---|---|---|
| **Scale / tangibility** | a number → a body-sized referent. "$1B"→stadiums, city blocks, grains of sand; "fills X pools" | **quantity extraction** → pick a referent → **compose with motion on the number/words** (counters, kinetic text) over/with the asset. Remotion + motion lib, not just a clip |
| **Process / mechanism analogy** | a "how it works" → a physical machine that behaves the same. overheating→boiling pot / pressure gauge; feedback loop→thermostat/snowball; bottleneck→hourglass | mechanism extraction → analogy; **clip/pictures + a motion** that shows the mechanism running |
| **Geographic anchoring** | a place / a *movement* → maps, satellite push-ins, route lines | `route-map` motion exists; bridge extracts place/route |
| **Data-as-shape** | a trend → a chart whose **silhouette mirrors the emotional arc** (rise=hope, crash=despair, the "K") | `bar-compare` / `line-chart` / `k-shape` motions exist; bridge maps the arc → chart shape |
| **Hero-literal** | sometimes the right cut *is* the actual subject, shot with reverence | restraint operator; literal search + a dignified Ken-Burns/hold |

### C. Relational — meaning from the *collision of two elements* (needs **pairs**, not single clips)
*(needs new machinery: source/**generate** two assets and drive them together in **one motion**)*

| Operator | Logic → example | Build notes |
|---|---|---|
| **Ironic counterpoint** | the image **contradicts** the words for critique/comedy. VO praises progress → a landfill | bridge inverts: "find the shot that *undercuts* this line." single-clip first; pair later |
| **Historical rhyme** | now vs then; a modern line over archival that "rhymes" (2008 line ↔ 1929) | pair a contemporary + an archival asset; temporal juxtaposition |
| **Dialectical montage (Eisenstein/Kuleshov)** | shot A + shot B → a *third* idea neither holds. workers + slaughterhouse | **pair generation + a collision motion**; the deepest, highest-ceiling operator |
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

## Status

- ✅ **Tonal/evocative** — `src/nolan/evoke_broll.py`, `/broll` page (stock + library modes,
  provider selection, period/locale gate, listwise accept / UNMATCHED). See `IMPLEMENTATION_STATUS.md`.
- ✅ **Conceptual-isomorphic** — operator #2 on `/broll` (Approach toggle). Bridge maps concept→mechanic→isomorphic carrier domain(s); scoring judges metaphor-fit + freshness (cliché-avoidance).
- 🎯 Everything else above is **designed, not built** — each is a meaty, independently
  buildable+testable feature (a new operator = bridge + aptness gate + its asset source + motion).
