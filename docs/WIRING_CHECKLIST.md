# The Wiring Checklist — definition of "wired"

Mandatory reading before adding any capability, umbrella, pipeline step,
block, comp, or authored plan field (CLAUDE.md routes here). Every rule
below was paid for by a real incident, and every rule names the TEST that
enforces it — because this repo's own history proves prose doesn't hold:
the module contract was already written down when `bt.shots` shipped
computed-into-the-void, and the consumer manifest drifted within twenty
minutes of its creation. **Docs claim; tests enforce. A rule without its
honesty test doesn't exist.**

## The seven pitfall classes (each with its incident and its test)

1. **Authored-but-unconsumed.** A decision written to an artifact that no
   render-path code reads. *Incidents:* `scene.transition` authored by
   tempo for months, `bt.shots` computed and dropped, `brief.pacing` with
   no reader, the style guide's visual language consumed only script-side.
   *Enforcement:* every authored plan field gets a `PLAN_FIELD_CONSUMERS`
   entry (src/nolan/scenes.py) and `tests/test_plan_field_audit.py`
   grep-verifies the named consumer actually references it.

2. **Capable-but-unauthored.** An executor with no spine step that spends
   it. *Incidents:* 19 motion effects and 26 themes unreachable from the
   Director; 22 of 39 blocks with no adapter — the chart the test video
   "couldn't have" existed the whole time. *Enforcement:* every umbrella
   declares its authoring surface AND executor in `UMBRELLA_WIRING`
   (src/nolan/system_map.py), grep-verified by
   `tests/test_umbrella_wiring.py`. A new umbrella without both wires
   fails on day one.

3. **Silent-skip cascade.** Exact-string matching on an open vocabulary.
   *Incident:* invented `visual_type` slugs (`stat_card`, `kinetic_text`)
   made the scheduler, slide_designer and asset engine each quietly see 0
   eligible scenes. *Enforcement:* closed vocabularies with LOUD
   normalization (`VISUAL_TYPES` + `normalize_plan_visual_types`, failing
   the step on unmappable values; `tests/test_visual_types.py` pins the
   incident slugs). New enum-like fields get the same treatment: canonical
   set + normalizer + step-level error, never a silent filter.

4. **Two dialects for one decision.** The same concept encoded in two
   places always drifts. *Incidents:* the energy→camera vocabulary lived
   in THREE modules; theme.ts had its own color table so the brief's
   accent reached blocks but not comps. *Rule:* one function/registry per
   decision, everyone imports it (`nolan.still_motion.camera_tour_props`;
   `_active-theme.json` staged for theme.ts). When you find a duplicate,
   consolidating it IS the task — don't patch one copy.

5. **Catalog-blind agents.** An authoring agent whose prompt carries a
   private, hand-listed slice of the inventory. *Incident:* no
   orchestrator skill referenced the capability catalog; slide_designer's
   embedded table lagged the block library. *Enforcement:* agent-facing
   catalogs are generated from or honesty-tested against the registries
   (`tests/test_umbrella_skills.py`, `tests/test_editing.py`,
   `tests/test_treatment_pass.py`); dispatch briefs point at
   `nolan capabilities` / `/api/map`.

6. **Unverified output.** Rendering is not verifying; each medium needs a
   measurement. *Incidents:* the whoosh that mixed clean but was inaudible
   under the duck; the spotlight glass panel invisible on dark art and
   glaring on bright stock. *Rule:* frames get LOOKED at (extract + view),
   audio gets MEASURED (`measure_sfx_audibility` after every mix), and the
   result goes in the checkpoint — "verify like an editor" means per-medium
   instruments, not a green exit code.

7. **Gates lag new vocabulary.** A new step type touches every registry
   that classifies steps — the render path is only one of them.
   *Incident:* Video steps flagged as "text escaping the frame" by the
   pre-flight because `_MEDIA_BLOCKS` predated them. *Enforcement:* every
   Chapter-hostable step name must be classified media-or-text for the
   contact gate; `tests/test_step_classification.py` fails on any
   unclassified name, so forgetting is impossible.

## The checklist (run it for every new capability)

- [ ] **Registry entry** with `purpose` + `when_to_use` + constraints
      (e.g. `duration_preserving` — the sync contract is the legality gate).
- [ ] **Authored artifact field** (scene field / project.yaml / brief.json),
      validated against the registry, with a `PLAN_FIELD_CONSUMERS` entry.
- [ ] **Executor** in the render path — and if it introduces a new step
      type, classify it in the contact gate's media/text sets.
- [ ] **Umbrella wiring** — new umbrella? Declare authoring surface +
      executor in `UMBRELLA_WIRING`; it appears in `_umbrellas()` with
      `when_to_use` per entry.
- [ ] **Catalog + skill exposure** — the umbrella skill doc covers every
      registry id (honesty-tested); dispatch briefs can reach it.
- [ ] **Honesty test** — whatever claim the docs make about this capability,
      write the test that makes the claim unable to rot.
- [ ] **Live verification** — render a probe, extract frames and LOOK;
      mix audio and MEASURE; put the result in the checkpoint/commit.

## Litmus questions at review time

"Which registry did this land in? What field authors it? Who consumes that
field? Which gate classifies it? Where does an agent learn when to use it?
Which test fails if any of those answers stops being true?"
