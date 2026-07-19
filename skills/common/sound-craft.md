---
id: common.sound-craft
name: Sound craft
kind: craft
purpose: The sound umbrella — SFX cue-kinds (whoosh, impact, paper, data-punch, ambience beds …), when to fire each, how to author them as data on a scene.
status: active
version: 1
handoffs: []
uses: []
evals: []
---

# Sound craft — the SFX umbrella

The agent-facing catalog of **SFX cue-kinds**: the vocabulary of sounds NOLAN
places, and *when* to fire each. The registry of record is
`src/nolan/sound/registry.py` (`REGISTRY`) — this document is honesty-tested
against it (`tests/test_sound.py`), so every kind here exists and every kind
that exists is listed here. The curated files live in
`projects/_library/sfx/sfx.json` (the bank), each tagged with its `kind`;
`nolan.sound.resolve.resolve_cue(kind)` picks the best-rated file.

**The umbrella's legality gate.** Sound is *additive over the finished mix* —
every cue is duration-preserving (it never alters video timing and must never
touch the pre-concat clips). The real gates are: it **ducks under / lands in
the gaps of** narration, and it **measures audible**
(`audio_mix.measure_sfx_audibility`) — a cue nobody can hear is a bug.

**How to author (both pipelines).** A cue is DATA on a scene, validated by
`nolan.sound.validate_scene_sound`:
- Director plan: `scene.sfx` = `{cue: <kind>, at, gain}` (or a free `{query}`,
  or a bare string). `cue` resolves from the curated bank; `query` falls back
  to a live search.
- HyperFrames spec: `scene.data.sfx` = `[{cue, at, gain}]`, where `at` is
  scene-local seconds (the finish step resolves each via
  `nolan.sound.resolve.sfx_event_for_cue` and merges into `audio_meta.sfx[]`).

**Authoring is a pairing operator, not a sound-picker.** Each `when_to_use`
below is the *trigger* — a scene-event → cue-kind rule, computable from the
spec (scene type, reveal `cue`, transitions, stat count-ups). Fire on the
motivated moment: a cut, an operative word landing, a number, an object on
screen.

**Restraint budget.** SFX is punctuation, not wallpaper: ≤ ~1 cue per 8–10s of
the same family; hard cues land in VO gaps, never over a clause; beds duck
under VO; **analogy/emotion beats get space, not sound**; reuse one
whoosh/impact family per video so it reads as designed.

## The cue-kinds

## whoosh

A short swish that sells motion across a cut / slide-in / camera move.

**When to use:** Fire on a scene ENTER or a hard frame transition. Pre-roll ~0.4s so the sweep peaks ON the cut, not after it. The workhorse cue — but one family per video; don't whoosh every internal beat.

**Family:** transition · default gain 0.3 · ~0.4s · authored by `scene.sfx / scene.data.sfx (cue='whoosh')`.

## riser

A rising swell that builds tension into a reveal or reversal.

**When to use:** Lead INTO the turn/'Wrong.' beat or a major reveal; the swell must END on the beat (author `at` = the reveal minus the riser length). Sparingly — it's a promise; pay it off with an impact.

**Family:** one-shot · default gain 0.25 · ~2.0s · authored by `scene.sfx / scene.data.sfx (cue='riser')`.

## impact-soft

A gentle thud when a word or element lands.

**When to use:** On a statement's operative-word reveal (scene.data.cue) or a 2-4 word beat-sentence. Lands in the VO gap, never over a clause.

**Family:** one-shot · default gain 0.3 · ~0.3s · authored by `scene.sfx / scene.data.sfx (cue='impact-soft')`.

## impact-hard

A cinematic hit for a major reveal or detonation.

**When to use:** The section climax, the myth-bust 'Wrong.', the biggest number. At most a few per video — overuse cheapens every one.

**Family:** one-shot · default gain 0.4 · ~0.6s · authored by `scene.sfx / scene.data.sfx (cue='impact-hard')`.

## sub-drop

A deep sub-bass drop for weight and dread.

**When to use:** A dark/heavy beat (dark theme polarity — e.g. 'the future is broke'). Pairs well under a room-tone bed; keep it rare.

**Family:** one-shot · default gain 0.4 · ~0.8s · authored by `scene.sfx / scene.data.sfx (cue='sub-drop')`.

## stinger

A short tonal accent marking a boundary or title.

**When to use:** A chapter/frame boundary or a title card — an audible section break. Optional; skip if the whoosh already carries the cut.

**Family:** one-shot · default gain 0.3 · ~0.5s · authored by `scene.sfx / scene.data.sfx (cue='stinger')`.

## click

A UI click / tick / select.

**When to use:** A button, checkbox, cursor, or list item appearing/selected. Great to articulate staccato list reveals one item at a time.

**Family:** one-shot · default gain 0.25 · ~0.15s · authored by `scene.sfx / scene.data.sfx (cue='click')`.

## type

Keyboard typing / typewriter clatter.

**When to use:** A code block or a typewriter/char-reveal text animation — loop under the reveal window, stop when the text settles.

**Family:** loop · default gain 0.22 · ~1.0s · authored by `scene.sfx / scene.data.sfx (cue='type')`.

## notification

A message/alert pop or ding.

**When to use:** A social_card, chat bubble, phone, or alert appearing. Match the platform feel; don't stack multiples in one beat.

**Family:** one-shot · default gain 0.28 · ~0.5s · authored by `scene.sfx / scene.data.sfx (cue='notification')`.

## error-buzz

A negative buzzer / denial tone.

**When to use:** A failure, a 'no', a red-X, a rejected/void moment. Ironic-beat friendly ('approve, approve — denied').

**Family:** one-shot · default gain 0.3 · ~0.5s · authored by `scene.sfx / scene.data.sfx (cue='error-buzz')`.

## glitch

Digital corruption / distortion artifact.

**When to use:** A decode/scramble/glitch reveal style, or an AI/tech/corruption motif. Reinforces a digital-unease register; keep it purposeful.

**Family:** one-shot · default gain 0.3 · ~0.4s · authored by `scene.sfx / scene.data.sfx (cue='glitch')`.

## camera-shutter

A camera shutter snap.

**When to use:** A photo / headshot / evidence image sliding in (newshead photo). One snap per image; don't machine-gun a gallery.

**Family:** one-shot · default gain 0.28 · ~0.3s · authored by `scene.sfx / scene.data.sfx (cue='camera-shutter')`.

## paper

Page-turn / paper slide / rustle.

**When to use:** A document, newspaper, receipt, or newshead headline landing. The signature foley for 'the story broke' / filing beats.

**Family:** one-shot · default gain 0.25 · ~0.5s · authored by `scene.sfx / scene.data.sfx (cue='paper')`.

## stamp

A stamp / gavel thud.

**When to use:** Approval, a verdict, 'sealed', a label slammed on (a villain-concept label, an APPROVED/DENIED mark).

**Family:** one-shot · default gain 0.32 · ~0.4s · authored by `scene.sfx / scene.data.sfx (cue='stamp')`.

## cash

Coin / cash-register / ka-ching.

**When to use:** A money stat, a dollar figure, a transaction. Land it ON the number, not the sentence around it.

**Family:** one-shot · default gain 0.3 · ~0.6s · authored by `scene.sfx / scene.data.sfx (cue='cash')`.

## data-tick

A per-increment tick during a number count-up.

**When to use:** A stat block counting from A→B — one tick per increment across the count window, resolving into a data-punch on the final value.

**Family:** loop · default gain 0.18 · ~0.05s · authored by `scene.sfx / scene.data.sfx (cue='data-tick')`.

## data-punch

A soft impact when a stat / bar / chart lands.

**When to use:** The instant a number, bar, or chart settles on a driving beat. Already auto-authored by audio_mix for stat/chart treatments.

**Family:** one-shot · default gain 0.3 · ~0.3s · authored by `scene.sfx / scene.data.sfx (cue='data-punch')`.

## room-tone

A low interior bed to fill dead air and set place.

**When to use:** A long hold / talking-head-ish stretch (see nolan.hyperframes.relieve) so silence doesn't feel broken; or to place an interior (office, room). Always ducks under VO.

**Family:** bed · default gain 0.1 · ~8.0s · authored by `scene.sfx / scene.data.sfx (cue='room-tone')`.

## crowd-murmur

A muffled crowd / voices bed.

**When to use:** A public / market / courtroom / hype context. Low and wide, under the read; never intelligible enough to distract.

**Family:** bed · default gain 0.12 · ~8.0s · authored by `scene.sfx / scene.data.sfx (cue='crowd-murmur')`.

## tension-drone

A low, sustained suspense drone.

**When to use:** Under a dread / slow-build stretch where room-tone reads too neutral — abstract and electronic, not a place. Pairs with a sub-drop on the peak; pull it out the moment the tension breaks.

**Family:** bed · default gain 0.1 · ~8.0s · authored by `scene.sfx / scene.data.sfx (cue='tension-drone')`.

## nature-bed

An outdoor natural ambience that sets place and mood.

**When to use:** When the narration/visual evokes an outdoor setting or a natural-force metaphor. Pick the ambience by intent: rain=melancholy, sea=vast/calm, fire=tension/warmth, wind=desolation, birds=dawn/pastoral, storm=dread. (A thunderclap is an impact-hard; the rolling storm is this bed.)

**Family:** bed · default gain 0.12 · ~8.0s · authored by `scene.sfx / scene.data.sfx (cue='nature-bed')`.

## machine-hum

A mechanical / electronic environment hum.

**When to use:** A server room, data center, engine, or factory setting — the industrial underlayer (apt for data-center / infrastructure beats). Low and constant under the read.

**Family:** bed · default gain 0.1 · ~8.0s · authored by `scene.sfx / scene.data.sfx (cue='machine-hum')`.
