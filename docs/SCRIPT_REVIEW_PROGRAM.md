# Script Review Program — closing the draft→official-level gap

Status: **Phase 1 SHIPPED** (2026-07-20); Phases 2–5 planned. Owner: script
pipeline. This is the tracking doc so we don't lose the thread across sessions.
Update the checkboxes as phases land; move detail into IMPLEMENTATION_STATUS.md
on completion.

**Phase 1 landed:** `scriptwriter/rubrics.py` (registry, 7 base dims + archetypes),
`scriptwriter/gate.py` (`script_gate`), `review_task`/`revise_task`, `run_script_phase`
review/revise wiring + fresh-eyes routing, `nolan scriptgen` CLI, 18 honesty/behavior
tests, validated on the-ai-debate golden case. Next: Phase 2 (composite spine).

## 0. Why this exists (the finding)

The script pipeline today is `prep → [angle gate] → draft → v3(all-in-one) →
promote_draft (A/B)`. The single transform that takes a draft from "ok" to
"official level" — a **producer review + a targeted revision round** — happens
entirely by hand, in chat, and is recorded only *after the fact* in prose.

Proof it's the missing step, in our own repo:
`projects/the-ai-debate/scriptgen/report.md` has a section literally titled
**"Producer feedback incorporated (draft-01 → draft-02)"** with 7 numbered
changes (attribution→our-voice, the "confidence trick" relabel, cut the Reid
Hoffman story, added the memory-chip thread, …). draft-01.md and draft-02.md
are both on disk. **The best edit in the run is invisible to the system.**

This program makes that round a first-class, typed, gated, learnable pipeline
stage — and fixes the structural weaknesses that make the first draft need so
much rescuing.

## 1. The three human directives shaping the design

1. **Review must carry the same context as drafting** (coherence/consistency).
   → the review executor assembles context through the *same* `ScriptContext`
   path the render side uses, enforced by a **context-parity honesty test**.
2. **Review questions are typed to the kind of script** (a 20-min business
   argument asks different questions than a 6-min art-history narrative).
   → a **rubric registry** keyed by *script archetype* (inferred default,
   human-overridable) + free-form ad-hoc questions per run.
3. **A script may carry more than one thesis, bound by a coherent macro
   structure** (chronological, hierarchical, braided, …) — not force-one-angle.
   → a **spine-structure registry**; the "angle" becomes a small structured
   *composite spine* object; prep/beatmap/review all understand it.

Plus two cross-cutting calls made with the user:
- **Two passes, gated** — `review` (diagnose-only) → human critique gate →
  `revise` (apply approved items only). Not one combined self-rewrite.
- **Fresh-eyes critic** — `review` dispatches to a *different* fleet session
  than the one that drafted (NOLAN has no auto-spawn; see §7).

## 2. How this maps onto the NOLAN module contract

Per CLAUDE.md + `docs/WIRING_CHECKLIST.md`, a new capability is not "code in the
path" — it is registry + authored field + executor + honesty test + /map +
skill. This program adds **two registries** and **one umbrella** ("script").

| Contract slot        | What we add                                                                 |
|----------------------|------------------------------------------------------------------------------|
| **Registry**         | `review_rubrics` (dimensions + archetypes) and `spine_structures`            |
| **Authored field**   | `meta.json`: `review_archetype`, `ad_hoc_questions[]`, `composite_spine{}`, `draft_session` |
| **Executor**         | `review_task` / `revise_task` builders; `run_script_phase("review"/"revise")`; deterministic `script_gate.py` |
| **Honesty test**     | context-parity; rubric-reads-real-artifact; gate step-classification; archetype-enum coverage |
| **/map surface**     | a `script` umbrella row (authoring surface = /script-projects; executor = scriptwriter phases + gate) |
| **Skill**            | `skills/common/script-craft.md` (or extend the scriptwriter skill) documenting the rubric + spine structures, honesty-tested against the registries |

An authored field with no consumer is a bug (the `transition` lesson). Every
field above names its consumer in the executor; the honesty tests pin it.

## 3. The new pipeline shape

```
prep ──[angle/spine gate]──► draft ──► [script_gate] ──► review ──[critique gate]──► revise ──► [script_gate] ──► promote → script.md
   │                              ▲                                                      │
   └──────────── (auto mode: gates auto-approve) ◄────────── loop: review↔revise until human promotes
```

- **`review`** (NEW, diagnose-only): fresh-eyes dispatch. Reads the *same*
  context as drafting (facts, beatmap, style guide, chosen draft — via
  `ScriptContext`) + the selected rubric + ad-hoc questions. Writes
  `scriptgen/reviews/review-NN.md`: per-dimension, **located** findings (beat,
  line/quote), severity, and a concrete proposed fix. **Does not touch the
  draft.** Carries provenance (rubric@ver, archetype, agent, model, draft-NN).
- **[critique gate]** (human): findings render as cards; human edits / drops /
  adds items and approves which to apply. Auto mode: approve all. Approved set
  persisted to `reviews/review-NN.approved.json`.
- **`revise`** (NEW): reads draft + approved findings + full context; applies
  **only** approved items as targeted edits (preserve what works); runs the
  **final coherence read** (whole-script pass to smooth patched transitions and
  restore consistent voice); updates factcheck/citations/stylecheck for the
  delta; writes `drafts/draft-(NN+1).md` + `reviews/revision-NN.md` (structured
  changelog: each edit ↔ the finding it answers).
- **`script_gate.py`** (NEW, deterministic, auto after every draft/revise):
  format valid; word-count vs target (measure, don't silently enforce); every
  beat has ≥1 grounded fact; no `[needs-check]` claim shipped as certain; refrain
  present if the spine declares one; no beat silently dropped between drafts.
  **Reports loudly**; promote is still allowed over a flag (human override), but
  the flag is visible. This is the propose→gate→accept door the script side
  currently lacks.

## 4. The rubric (directive #2)

The human's 4 hand-questions, sharpened and generalized. **Base rubric (every
script)** — dims 1–4 are the human's, 5–7 are the long-form failure modes the
list implies:

1. **Figurative fitness** — every metaphor/analogy/allegory *earned, accurate,
   load-bearing*? Flag decorative / mixed / clichéd / fact-distorting ones; cut
   or replace with a stronger image drawn from the actual material.
2. **Voice ownership vs. attribution** — paraphrase and assert in *our* voice by
   default; name a source only when (a) the person/institution is prominent
   enough that the name adds authority, or (b) it's a first-person human quote
   that must stay verbatim. Flag every needless "According to X…"; rewrite as our
   own claim, fact preserved.
3. **Example strength** — each example the *clearest, most concrete instance* of
   its point? Flag weak / generic / confusing / off-target; replace sharper (from
   facts.md or newly researched).
4. **Evidential sufficiency** — *for this video's type and length,* enough
   well-chosen examples/specifics to feel substantive (not thin, not padded)?
   Name under-supported beats; research + insert well-sourced specifics **in the
   right place**; update facts.md + citations.md.
5. **Through-line & payoff** — every beat serves the spine? For a **composite
   spine**: do the threads actually braid into the declared structure, or just
   sit adjacent? Hook promise paid off; refrain/label recurs with purpose and
   lands at the close?
6. **Retention & redundancy** — mid-script sag; point made twice; beat cuttable
   without loss? (Weighted up for long-form.)
7. **Final coherence pass** — after edits, one continuous read: consistent voice,
   smooth transitions across patched sections, duration/beat structure intact.

Each dimension is a registry entry: `{id, question, when_to_use, reads:[facts|
beatmap|draft|style|citations], diagnose_only:true, severity_hint}`.

**Archetypes** layer on the base (add/re-weight dims). Seed set:
- `long-form-argument` (the AI-debate): weight #4 up; add "steelman genuinely
  present" and "every number checkable & hedged appropriately".
- `narrative-history`, `explainer`, `biography`, `personal-essay` (stubs to
  start; grow as real projects need them).

Archetype is **inferred by default** (from style_id + target_minutes + subject,
the way spine-type is already inferred) and **overridable** in the UI. Ad-hoc
questions append to the rubric for a single run.

## 5. Composite spine (directive #3)

Today `angles.md` forces one `**[CHOSEN]**`. Upgrade the angle model to a small
structured object:

```json
"composite_spine": {
  "structure": "chronological",         // from spine_structures registry
  "threads": ["thread A one-liner", "thread B one-liner"],
  "binding": "how the threads cohere into one felt through-line"
}
```

**`spine_structures` registry** (each with `when_to_use` + how it maps to
beats): `single` (today's default), `chronological`, `hierarchical` (nested
general→specific), `braided` (2–3 threads interleaved), `thesis-antithesis-
synthesis`, `parallel-cases`, `spatial-zoom`. `single` keeps today's behavior —
this is additive, not a breaking change.

Touch points:
- **prep/angles**: propose candidate *structures* alongside angles; a chosen
  spine may be one thread + `single`, or N threads + a structure.
- **angle gate UI**: pick a structure + order the threads (not just paste one
  line).
- **beatmap**: arrange beats to realize the structure (already structure-aware
  in spirit; make it explicit).
- **review dim #5**: judges whether the braid actually cohered.
- **ScriptContext**: `angle` becomes composite-aware (keep a flat `angle`
  string for back-compat; add `spine` object).

## 6. The learning loop (why "we can test it properly")

Every critique-gate decision (finding accepted / rejected / **human-added**) is
logged to `scriptgen/reviews/review_ledger.jsonl` and a project-wide ledger. A
distill step promotes recurring human-added findings into (a) the default rubric
or (b) **per-style priors injected at DRAFT time** — so the *first* draft
improves over time. This is the script-side twin of the existing render-side
**taste loop** (`project_taste_loop.md`: ledger→retro→tiered-prior→prompt).
Reuse that machinery where possible rather than reinventing it.

## 7. Fresh-eyes critic within NOLAN's agent model

`src/nolan/fleet.py`: the "fleet" is **manually pre-started tmux sessions**
`nolan1`–`nolan6`. No auto-spawn, no auto-naming. `_dispatch_to_tmux` send-keys
into an existing session; `current_session()` (via `$TMUX`) already guards
against self-dispatch.

- **Default (no new infra):** persist `draft_session` in meta; `review`
  dispatches to a *different* live fleet session. Gives fresh-eyes critique
  today. If only one session is alive, warn + allow (degraded, not blocked).
- **Optional dependency (needs the user):** true auto-spawn of a fresh,
  uniquely-named agent per review. Not built until the user specifies how they
  want sessions spawned/named. Tracked as an open item, not a blocker.

## 8. Critical-review findings this program also fixes

(From the pipeline/UI review that motivated this doc — kept here so they're not
lost.)

- **No deterministic gate on drafts** (violates the propose→gate→accept
  contract) → `script_gate.py` (§3).
- **Critic = author** (v3 drafts + self-checks in one context) → separate
  `review` dispatch (§3, §7).
- **Context assembled twice, drift-prone** (`ScriptContext` unused by the
  scriptwriter; beatmap writes `**Spine + arc**` but ScriptContext regexes
  `**Angle (spine):**`) → route all context through `ScriptContext`; fix the
  header/regex contract; context-parity test.
- **No feedback capture / no learning** → the ledger + distill (§6).
- **UI: angle gate is copy-paste** → selectable angle/structure cards.
- **UI: no draft compare** → draft-NN diff view.
- **UI: no pipeline state** → visible state machine (New → Grounded → Angled →
  Drafted → Reviewed → Revised → Promoted) + per-phase status.
- **UI: no home for review** → rubric/archetype selector, ad-hoc question box,
  rendered critique cards, "Revise with approved" action.
- **UI: baseline writer exposed** → move behind an advanced flag.

## 9. Implementation phases

### Phase 1 — Vertical slice (CLI-first, validate on the golden case) ✅ SHIPPED
Goal: a working, testable `review → [gate] → revise` loop for one archetype,
proven against `the-ai-debate` draft-01 → draft-02.

- [x] `scriptwriter/rubrics.py` — rubric registry: base 7 dims +
      `long-form-argument` (+narrative-history/biography/explainer/general);
      `infer_archetype(meta)`; `get_rubric`; renderers.
- [x] `scriptwriter/tasks.py` — `review_task(slug, store)` and
      `revise_task(slug, store)` builders; shared `_context_inputs_block`;
      `_DRAFT_INPUTS`/`_REVIEW_INPUTS` parity contract.
- [x] `scriptwriter/store.py` — reviews/ dir + paths; `review_archetype`,
      `ad_hoc_questions`, `draft_session` in meta; `current_draft` (seeds from
      script.md), `next_draft_number`, `list_reviews`, `resolve_archetype`.
- [x] `scriptwriter/gate.py` — deterministic `script_gate` (§3); `gate_text`
      (pure) + `run_gate`; grounding via beatmap covers w/ corpus fallback.
- [x] `operations.run_script_phase` — `review` / `revise` phases; route
      `review` to a non-drafting fleet session (`_pick_reviewer_session`);
      record `draft_session`. Route accepts the new phases.
- [x] CLI: `nolan scriptgen review|revise|gate|archetype <slug>`.
- [x] **Honesty tests** (`tests/test_script_review.py`, 18): context-parity
      (review inputs ⊇ draft inputs + every input in the brief); gate reports
      exactly its declared doors; every archetype keeps the four core questions.
- [x] **Golden case**: gate on the-ai-debate auto-caught the +22% length overrun
      and the 5 needs-check flags the producer had found by hand; review brief
      renders the typed rubric with the producer's four questions as dims 2–4/1.
- [x] **Live golden run (2026-07-20)**: spawned a fresh agent (`nolan-gold`, via
      the ATHENA recipe: `tmux new-session -d … -c <repo>` → `claude
      --dangerously-skip-permissions` → poll boot → dispatch), ran review+revise
      blind on an isolated draft-01 clone (`the-ai-debate-golden`, answer key
      removed). The `long-form-argument` critic produced 16 located findings and
      independently rediscovered the producer's 3 biggest manual draft-02 moves
      (memory-chip thread, de-attribute Marcus, specify "too big to fail") + real
      additions the human missed (Galloway date error, ~5%-pay hole, MS/Claude-Code
      trap, Amazon/Uber steelman gap). Revise applied all 16, grounded new claims
      ([S11] + factcheck/citations/stylecheck), did the coherence read, and flagged
      the +4-5min overrun loudly (no silent cut). Divergence worth a rubric tweak:
      machine was conservative on voice-ownership (Marcus 5→4) vs the human's 5→0.

### Phase 2 — Composite spine  ✅ SHIPPED (2026-07-20)
- [x] `scriptwriter/spine_structures.py` registry (single/chronological/hierarchical/
      braided/thesis-antithesis-synthesis/parallel-cases/spatial-zoom, each with
      `when_to_use` + `beat_guidance` + thread bounds); `composite_spine` in meta +
      `store.set_composite_spine` (validated).
- [x] prep/angles builder offers the structures menu; beatmap builder injects the
      chosen structure's arrangement guidance + threads (`_beatmap_block(…, spine)`).
- [x] `ScriptContext` composite-aware (`spine` field, flat `angle` back-compat/synthesis,
      structure surfaced in `brief()`); also fixed the `**Spine + arc:**` regex drift.
- [x] review dim #5 already braid-aware (Phase 1).
- [x] API `POST /api/script-projects/{slug}/spine` + CLI `nolan scriptgen spine`.
- [x] tests (`tests/test_spine_structures.py`, 8): enum coverage, thread-bound validation,
      `single`==today back-compat, store round-trip, ScriptContext surfacing.
- Deferred to Phase 3: the angle-gate UI to pick a structure + order threads (cards).

### Phase 5 (partial) — Agent spawn + fleet console  ✅ SHIPPED (2026-07-20)
- [x] `fleet.spawn/kill/detect_status/capture_pane/fleet_detailed/next_session_name`
      (ATHENA recipe, WSL-routed); live spawn→idle→kill verified.
- [x] `/sessions` page + `routes/sessions.py` (list/spawn/kill/peek) + nav entry.
- [x] tests (`tests/test_fleet_spawn.py`, 4) + TestClient route smoke.
- Note: hub restart required to serve the new `/sessions` route + nav link live.

### Phase 3 — UI (make it operable & obvious)  ✅ SHIPPED (2026-07-20)
- [x] Pipeline state machine surfaced on /script-projects (`store._pipeline_state`,
      7-step stepper).
- [x] Spine picker in the angle panel (structure dropdown + threads + binding, via
      `POST /spine`); angle textarea retained.
- [x] Review panel: archetype selector + ad-hoc question box (`/review-config`),
      "🔍 Review draft", critique cards with per-finding checkboxes, "Approve selected →
      Revise" (`/review/{n}` + `/review/{n}/approve` → dispatch revise).
- [x] Draft compare (client LCS diff) + gate badges (`GET /gate`).
- [x] Baseline writer moved behind an Advanced `<details>`.
- [x] Verified in a real browser (Playwright): stepper/findings/gate/spine all render,
      zero console errors.
- Deferred: angle *cards* parsed from angles.md (still paste-the-thesis); add-a-finding
  in the critique gate.

### Phase 4 — Learning loop  ✅ SHIPPED (2026-07-20)
- [x] `scriptwriter/ledger.py` — `_script_review_ledger.jsonl` captured at the critique
      gate (`/review/{n}/approve` → `record_review_decision`): approved vs rejected findings
      (by dim/severity) + the ad-hoc questions, per archetype/style.
- [x] `distill` (per-dim approve rates + recurring ad-hoc) + `draft_priors` injected into
      the DRAFT task (`_draft_v3_block`) — first drafts pre-empt what producers keep asking.
- [x] CLI `nolan scriptgen ledger`; tests `tests/test_script_ledger.py` (5).
- Deferred: the formal A/B lift harness (first-draft-only vs +1 round, scored).

### Phase 5 — Auto-spawn critic (optional, needs user input)
- [ ] Only if the user specifies session spawn/naming; otherwise the §7 default
      stands.

## 10. Definition of done (Phase 1)
Running `nolan script review <slug>` then `nolan script revise <slug>` on a
drafted project produces a located critique, a human-inspectable approved set, a
new numbered draft that applies only approved items and passes `script_gate`,
and a revision changelog — with the golden test on the-ai-debate demonstrating
the machine reproduces the substance of the human's draft-01→draft-02 round.
