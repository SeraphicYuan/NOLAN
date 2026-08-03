# The Wiring Checklist — definition of "wired"

Mandatory reading before adding any capability, umbrella, pipeline step,
block, comp, or authored plan field (CLAUDE.md routes here). Every rule
below was paid for by a real incident, and every rule names the TEST that
enforces it — because this repo's own history proves prose doesn't hold:
the module contract was already written down when `bt.shots` shipped
computed-into-the-void, and the consumer manifest drifted within twenty
minutes of its creation. **Docs claim; tests enforce. A rule without its
honesty test doesn't exist.**

## The pitfall classes (each with its incident and its test)

1. **Authored-but-unconsumed.** A decision written to an artifact that no
   render-path code reads. *Incidents:* `scene.transition` authored by
   tempo for months, `bt.shots` computed and dropped, `brief.pacing` with
   no reader, the style guide's visual language consumed only script-side.
   *Enforcement:* every authored plan field gets a `PLAN_FIELD_CONSUMERS`
   entry (src/nolan/scenes.py) and `tests/test_plan_field_audit.py`
   grep-verifies the named consumer actually references it.
   *Variant — the GATE accepts what the schema never offered.* Not "the
   schema promises a field and the block ignores it": `timeline`'s events
   schema is `{year, label?, image?, side?}` and never declares `at` at all,
   yet a hand-authored `events[].at` validated rc=0 "OK — spec validates"
   and then did nothing. Three frame workers each lost time rediscovering
   that. Diagnose which of the two it is before fixing — retro-fitting a
   consumer for an undeclared field is building an unspecified feature.
   *Enforcement:* `author.py` refuses a cue on any block outside
   `CUE_BLOCKS` and says INERT plus the exact path; `CUE_BLOCKS` is
   re-derived from the composer source, never hand-listed
   (`tests/test_block_registry.py` pins both the derivation and the
   refusal).

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
   *Incidents (diamond-v2, where the fork was invisible because both copies
   were valid):* `_GROUND_BLOCKS` was declared twice under one name —
   autoground's 6 (derived from compose.py) against metrics' `{statement,
   stat}` — so grounding a `pull_quote` credited nothing toward `coverage`
   while STILL tripping the long-ungrounded-hold advisory; the author was
   told to fix a thing the metric refused to see. Widening one copy without
   knowing the other existed is what created it. Separately `_content_time`
   and `_scene_query` each kept a private visible-text key tuple, so a
   `pull_quote`'s own `quote` was invisible to placement and the matcher
   corroborated against the scene's `kicker` — a field the catalog declares
   "design intent, not narration". *Enforcement:* `nolan/block_registry.py`
   is the one home for both sets and `tests/test_block_registry.py` asserts
   NO module re-declares them privately. Note the shape of that test: it
   hunts the literal, because the failure mode is a fork, not a wrong value
   — a test that merely checked the number would have passed on both copies.
   Effect once unforked, with no re-authoring: coverage 0.656 → 0.767, long
   ungrounded holds 11 → 2. The essay was always that well grounded; the
   metric could only see 2 of 6 block types.

5. **Catalog-blind agents.** An authoring agent whose prompt carries a
   private, hand-listed slice of the inventory. *Incidents:* no
   orchestrator skill referenced the capability catalog; slide_designer's
   embedded table lagged the block library; the evoke planner's operator
   menu was hand-written prose duplicating `when_to_use`; tempo kept a
   private transition tuple that `nolan.editing` mirrored *by comment*.
   *Enforcement, two layers:* (a) catalogs are generated from or
   honesty-tested against the registries (`tests/test_umbrella_skills.py`,
   `tests/test_editing.py`, `tests/test_treatment_pass.py`); (b) each
   catalog provably REACHES its decision points — every umbrella declares
   its consumers in `CATALOG_CONSUMERS` (src/nolan/system_map.py),
   grep-verified by `tests/test_catalog_consumers.py`. Existence isn't
   wiring; consumption is.

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

8. **Ungated acquisition.** Any code path that downloads an external asset
   and stamps it into a plan, a shot list, or a library is an acquisition
   DOOR, and every door calls `nolan.asset_gate` (candidate check before
   download, file check after). *Incident:* `fulfill_shots_wanted` and
   `nolan assets match-broll` fetched **watermarked Alamy previews** into a
   rendered Homer beat — full-frame, banner baked in, `license: null`.
   *Enforcement:* every door is named in `ASSET_GATE_DOORS`
   (src/nolan/asset_gate.py) and `tests/test_asset_gate.py` grep-verifies
   the gate calls exist in each door's body. A new fetch path without a
   manifest entry + gate call is unshippable.

9. **Front-loaded reveals (unspread, narration-blind).** A block whose
   per-element reveals fire on a hardcoded `cue = start + LEAD + i*STEP`
   stagger crams all its content into the first ~2 seconds, then holds a
   frozen frame for the rest of a 10-15s beat — and the numbers pop *before*
   the voiceover says them, because the stagger knows nothing about
   narration. *Incident:* every data/chart/stat block (chart, stat, sankey,
   pie, funnel, quadrant, cycle, spectrum, scale, spans, venn,
   connection_board, the list blocks) revealed in 2s then read as a static
   slide for 10s — the ai-datacenter-debate acid test flagged STATIC-HOLD on
   every one. Statement blocks did NOT have the bug: their operative word is
   placed on narration time by the aligner. *Rule:* an element reveal is
   scheduled through the SHARED reveal scheduler in `compose.py`
   (`_reveal_times` / `_reveal_dur` / `_reveal_cues`), never a hand-rolled
   `start + i*step`. The scheduler (a) spreads reveals across the block's
   full window (front-loading is impossible), (b) scales each count-up/draw
   duration to fill its beat (`_reveal_dur`), and (c) reads each element's
   `_cue` so the aligner can pull a reveal onto its spoken phrase ("show it
   as you say it"). *Enforcement:*
   `render-service/_lab_hyperframes/bridge/check_reveal_sync.py` scans
   compose.py for the hardcoded-stagger anti-pattern and fails on any new
   one outside a short, justified allowlist of reading/entrance cadences
   (text lines, gallery entrance, code cascade, chat beats). A new data
   block that hand-rolls its stagger is unshippable.

9b. **Prose with nowhere to write the answer** — pitfall #9's blind spot, and
   the reason "the visual is ahead of the voice" kept coming back. #9 covers
   a LIST of elements: each carries `_cue`, so the aligner has somewhere to
   put its answer. Every other authored string had no such field, so sync
   could not pin it *even in principle* — and the guard could not see the
   problem either, because `check_reveal_sync.py` looks for a hardcoded
   *stagger* and a block that reveals everything at one fixed offset matches
   no stagger pattern. *Incident:* `pull_quote` revealed its whole quote at
   `start + 0.5`; diamond-v3 at 3:41 shows a 13-word quote complete ~3.7s
   before the narration reaches it, while `check_reveal_sync` reported OK.
   Measured across the 50 blocks: a `title` on 29 of them, `quote`+`cite`,
   `text`, `caption`, and every two-sided block's side prose (which lives one
   level down, under `left`/`right`/`paper`, where none of the layers looked).
   *Rule:* a block that reveals PROSE reads `compose._prose_cue(d, field,
   start)`, which consumes the `data._field_cues` that `sync._retime_prose`
   resolves; `sync.PROSE_FIELDS` maps each field to how far into its beat it
   may be held (a quote may wait for its words, a title may only be nudged —
   parking a title trades a lead for a headless frame). *Enforcement:*
   `tests/test_reveal_sync_contract.py` composes EVERY block twice, plain and
   with cues injected, and fails if the timeline does not move — a
   behavioural test, because a static one cannot tell `times[i]` from a
   literal (a first pass at this audit wrongly cleared `timeline`, which
   contains zero references to the cue system). Deliberate cadences are
   declared in `DELIBERATE_CADENCE` with a justification, never omitted in
   silence.

10. **A gate for a rule nobody proved exists.** Before enforcing a rule,
    find the artifacts that violate it and confirm they are actually
    broken. *Incident:* a post-mortem asked for `assemble-index.mjs`'s
    "same-track time overlap is illegal" check to run at author time. No
    assembler has that check — all four copies contain zero track-overlap
    logic, and the claim traces to a COMMENT describing the top-level
    INDEX's lanes (frame sub-comps 1, captions 2, voice 10, bgm 11), not
    the tracks inside a frame's own composition; `timeline_track_too_dense`
    is a DENSITY warning, a different rule. Two detectors were wired before
    anyone checked the premise: the first blocked 13 tests, because
    adjacent scenes overlap BY DESIGN via their ~0.6s transition tails; the
    second was scoped to exactly the shape that demonstrably renders —
    `videos/_stress_spotlight` still holds the pre-fix HTML, both label
    halves on track 2 over one window, beside a finished mp4 that paints
    both. *Rule:* run the proposed detector over the corpus of SHIPPED
    artifacts BEFORE wiring it. If it fires on something that rendered
    correctly, the rule is wrong — not the artifact. *Enforcement:*
    `tests/test_author_track_overlap.py` carries the disproof and asserts
    `author.py` does NOT gate, so there is no attempt #3. A withdrawn rule
    needs its test as much as an enforced one, or it comes back.

11. **A check whose failures are all false positives.** Precision is a
    shipping requirement for a gate, not a nicety: a check people learn to
    skip takes its one true positive with it. *Incidents:* `layout_lint`'s
    only 3 errors on the diamond-v2 run were the `process` block's step
    badges, deliberately pinned to their own card's corner and verified
    correct by eye — 3 of 3 false. `nolan.acquire.coverage` reported 24
    "NOT depictable" gaps, and 18 of them (De Beers, Cecil Rhodes, Frances
    Gerety, Hopetown, the Star of South Africa…) had a collected hero and
    appear in the finished video — it read `pool.json` and not
    `key_assets.json`. *Rule:* measure a new or tightened check against
    real artifacts and report BOTH directions before shipping it — what it
    now passes AND what it still fails; a fix that only silences is a fix
    that disabled the check. *Enforcement:*
    `tests/test_layout_lint_nesting.py` (a child contained in its parent
    lints clean; a genuine 40% sibling overlap still fails) and
    `tests/test_acquire_coverage.py::test_load_pool_counts_key_asset_heroes`
    (a hero covers its subject; a genuine gap is still loud). Measured: 3
    errors → 0 with all four real advisories intact, 24 gaps → 6 all
    genuine.

12. **A refusal that is really a feature request.** A gate says "no" for two
    entirely different reasons — "you did it wrong" and "the thing you asked
    for does not exist yet" — and only the first is an agent's problem. The
    second is the more valuable signal and it evaporates by default.
    *Incident:* in one 25-comment batch edit, 3 notes (12%) asked for a
    background image on a `juxtaposition`. `data.ground` validated rc=0 and
    painted nothing; the agent worked around it by converting the scene to
    `layout` (which costs the per-line reveal styles and changes the
    typography) and the fact that 12% of human notes wanted a capability we
    did not have survived only because it happened to mention it in a retro.
    *Rule:* a capability refusal must (a) name the supported alternative, so
    the workaround is a decision rather than a rediscovery, and (b) be
    RECORDED, so the count — not one agent's memory — is what argues for
    building it. *Enforcement:* `author.py` emits a machine-readable
    `CAPABILITY-GAP` token, `nolan.hyperframes.edit.log_gap` counts it into
    `.hf_gaps.jsonl` and `list_gaps()` rolls it up across comps;
    `tests/test_hf_phantom_ground.py` pins the token, the named alternative,
    the tally, and that an ORDINARY gate failure is NOT logged as a gap.
    The loop closed once already: 3 counted asks bought `juxtaposition` a
    real `data.ground`, and that test's exemplar had to move to `diagram`.

13. **A field whose meaning depends on a sibling.** The inverse of #1:
    not an authored field with no consumer, but a consumed field whose
    correctness is silently voided by a change to a neighbour. *Incident:*
    swapping `annotate.data.src` invalidates every `callouts[].x/y` — a
    regenerated image moved the subject ~14% up the frame and a leader line
    would have pointed at empty water. Nothing anywhere says so; it was
    caught by eye. *Rule:* when a field's meaning is relative to another
    (coordinates to an image, region rects to a page, pins to a map, zones
    to a cutout), the dependency is part of the contract — a change to the
    anchor without a change to the dependents is a gate failure, not a
    judgement call. *Enforcement:* NOT YET BUILT — this class is documented
    ahead of its test on purpose, because the next capability that carries
    relative coordinates should ship with the check rather than rediscover
    the incident. A rule without its honesty test does not exist; treat this
    entry as the specification for the test, and delete this sentence when
    it lands.

## The checklist (run it for every new capability)

- [ ] **Registry entry** with `purpose` + `when_to_use` + constraints
      (e.g. `duration_preserving` — the sync contract is the legality gate).
- [ ] **Authored artifact field** (scene field / project.yaml / brief.json),
      validated against the registry, with a `PLAN_FIELD_CONSUMERS` entry.
- [ ] **Executor** in the render path — and if it introduces a new step
      type, classify it in the contact gate's media/text sets.
- [ ] **Synced reveals** — a `compose.py` block schedules every per-element
      reveal through the shared scheduler (`_reveal_times`/`_reveal_dur`/
      `_reveal_cues`), never a hardcoded `start + i*step` (else it reads
      stale and pops before the VO). `check_reveal_sync.py` enforces it.
- [ ] **Umbrella wiring** — new umbrella? Declare authoring surface +
      executor in `UMBRELLA_WIRING`; it appears in `_umbrellas()` with
      `when_to_use` per entry.
- [ ] **Catalog + skill exposure** — the umbrella skill doc covers every
      registry id (honesty-tested); dispatch briefs can reach it.
- [ ] **Characterised gate** — a new or tightened check is run over the
      EXISTING corpus of shipped artifacts before it is wired, and both
      directions are reported (what it passes, what it fails). A rule that
      fires on output that shipped and rendered correctly is a wrong rule.
- [ ] **Honesty test** — whatever claim the docs make about this capability,
      write the test that makes the claim unable to rot.
- [ ] **Live verification** — render a probe, extract frames and LOOK;
      mix audio and MEASURE; put the result in the checkpoint/commit.

## Reading a post-mortem (an agent's, or your own)

**Trust the evidence; re-derive the cause.** On the diamond-v2 cold run
every claim that was checked held — five verified independently before any
code changed, all five true. What needed correcting was the ATTRIBUTION:
four of eleven items named where the symptom appeared rather than where the
cause lived, and one item's premise was false outright. "Extend `judge.py`"
was three holes in three modules (a whole source exempted from the VLM; a
`usable` score that rates cuttability and never asks what the clip depicts;
a hero path that asks subject-match only). "The block ignores `at`" was the
gate accepting an undeclared field. "Use incremental renders" read as a
usage note and was missing wiring. Implementing any of them literally would
have under-fixed, and item 5 would have broken authoring. Split the
evidence by source before believing a single cause, and characterise the
proposed rule against real artifacts (class 10) before writing it down.

## Litmus questions at review time

"Which registry did this land in? What field authors it? Who consumes that
field? Which gate classifies it? Where does an agent learn when to use it?
Which test fails if any of those answers stops being true?"
