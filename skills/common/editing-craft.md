---
id: common.editing-craft
name: Editing craft
kind: craft
purpose: The editing umbrella — cutting-rhythm techniques (j-cut, shot-list, transition-in), when to use each, how to author them on the plan.
status: active
version: 1
handoffs: []
uses: []
evals: []
---

# Editing craft — the cutting-rhythm umbrella

This skill is the agent-facing catalog of **editing techniques**: how NOLAN
cuts, not what it shows. The registry of record is
`src/nolan/editing.py` (`REGISTRY`) — this document is honesty-tested against
it (`tests/test_editing.py`), so every technique listed here exists and every
technique that exists is listed here.

**The umbrella's legality gate:** narration owns duration (the sync
contract). Every technique here is duration-preserving. Techniques that
stretch or compress time — speed ramps, freeze frames, true overlap
dissolves — are deliberately absent: they would break `video ≡ narration`.
Do not improvise them; if a beat seems to need one, say so in your notes
instead of faking it.

**How to author:** editing decisions are DATA on the plan (scene fields or
project.yaml keys), never code. Malformed authoring fails the premium
eligibility gate loudly (`validate_plan_editing`), listing scene ids.

---

## j-cut

**What:** every eligible internal cut inside a section is pulled earlier
(default 12 frames ≈ 0.4s) so the next image arrives while the previous
sentence is still finishing. The audio slice moves with the picture; total
narration is byte-identical.

**When:** on by default — this is the single cheapest de-AI-tell in the
system (amateur/AI edits cut exactly on sentence pauses; editors don't).
Only cuts INTO imagery shift; a text card's reveal waits for its word cue,
so cuts into quote/title cards stay straight. Section edges never move.

**Authoring:** `j_cut_frames` in project.yaml (project scope). `0` disables;
raise toward ~18 for a languid essay, keep 8–12 for urgent pacing. You do
not author it per-cut.

## shot-list

**What:** one scene's narration window cut into several camera-toured
stills — `scene.shots = [{src, place?, weight?, caption?}]`. Each shot gets
the full still-motion treatment (energy → zoom tightness, lane alternation);
`place` aims the camera exactly like a nine-dot tray placement.

**When:** any narration span longer than ~6s over a single still reads as
static — the deconstruction corpus shows editors hold 2–4s per shot under
longer spans. Use 2–4 shots that ESCALATE or CONTRAST (wide → detail,
cause → effect), not four synonyms of the same image. `weight` gives the
key image the longest hold. Windows too small for every shot drop trailing
shots (never squeeze below ~0.8s) — order shots by importance.

**Authoring:** per scene. `src` required (project-relative or absolute
image path); `place` `[x, y]` in 0..1 optional; `weight` number > 0
(default 1); `caption` reserved.

## transition-in

**What:** how a scene ENTERS: hard `cut`, or a short opacity ramp from the
theme background — `dissolve` ≈ 0.27s, `fade` ≈ 0.47s. Executed inside the
Chapter composition; audio always starts on the cut.

**When:** the Editorial Arc pass (`nolan.tempo_plan`) authors this from the
energy arc — fade under ~0.35 energy (contemplative), dissolve to ~0.55,
cut above. Override a single scene when its landing should read softer or
harder than its energy suggests (e.g. a hard cut INTO a quiet revelation).
A section's first scene always hard-cuts — it lands on the beat anchor.
This is an entrance ramp, not a true overlap dissolve (see the legality
gate above).

**Authoring:** `scene.transition` = `cut` | `dissolve` | `fade`.

---

## Growing this umbrella

A new technique follows the module contract (CLAUDE.md): add an
`EditTechnique` entry (purpose + when_to_use + `duration_preserving`),
define the authored field, validate it in `validate_scene_editing`, execute
it in the premium render path, and document it here (the honesty test will
fail until you do). Candidates on the roadmap: match-cut suggestions,
cutaway/reaction inserts, montage acceleration (cadence ramp within the
duration budget).
