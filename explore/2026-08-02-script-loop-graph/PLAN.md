# Phase 3 — plan

Everything below is a consequence of something Phase 2 measured. No item is here because it
seemed like good practice.

## The eight items

| # | what | why (the evidence) | lands in |
|---|---|---|---|
| **P1** | Provenance on every judge output | A 17-vs-99 gap took git archaeology to explain, and the cause was partly an output-contract change. Nothing records who was asking. | production |
| **P2** | Judge redesign — pairwise | Draft-02 was **better** and scored **worse** (99→117). Finding-count rewards vagueness: an assertion has no surface area, an argument does. | production |
| **P3** | Split computable from judged | Timecodes all collapsed to `[0:00]`; declared `8:00` vs computed `10:03`. Both are arithmetic and neither should reach a model. The loop also never consulted the gate at all. | production |
| **P4** | Word budget, 5% wiggle | The revise pass added **+192 words** to a draft already 40% over, while pacing was one of the `high` findings it was told to fix. | production |
| **P5** | Persistence, not fix-rate | 23 findings → 7 fixed / **11 persisted** / 8 new. A finding can vanish for innocent reasons; one that SURVIVES a pass aimed at it cannot. | explore |
| **P6** | Revert · retry smaller · max rounds | After a regressing round both `continue` and `stop` are wrong. Replay could never find this — recorded runs only improve. | explore |
| **P7** | Archetype required, params recorded | `review_archetype: None` on 5 of 6 runs → fell back to `general`, which **lacks `steelman-present`**. A Homer essay rebutting a forgery claim never got the steelman critique. | production |
| **P8** | Validate on ≥3 drafts, ≥2 styles | Every conclusion so far rests on one Homer script. | explore |

## Design decisions taken in discussion

**P5 — persistence, not resolution.** A finding disappearing is ambiguous (fixed / text cut /
judge silent). A finding at the same `(dim, beat)` present in round N *and* N+1 is not: a pass
aimed at it failed. Survives 1 → note. Survives 2 → **escalate to a human**, same shape as the
`hf-edit` capability-gap ledger.

**P6 — "retry smaller" means a smaller CHANGE SET, not a smaller draft.** On regression: revert to
draft N-1, re-revise with **highs only**, re-judge. If the small set converges where 23-at-once
regressed, the cap becomes policy. If it also regresses, the revise pass itself is the problem —
a more valuable finding.

**Max rounds = 4**, with `max_rounds_reached` as its own terminal state. Not success, not failure;
recorded so a run that hit the ceiling never reads like one that converged.

**Out of scope:** downstream. The pipeline starts at the script; VO takes what it is given.

## Order, and why

Dependency-first, cheapest-first inside that:

1. **P1 provenance** — everything after it is a measurement, and an unstamped measurement is
   what wasted time in Phase 2.
2. **P3 deterministic checks** — standalone, free, and removes work from the judge before the
   judge is redesigned.
3. **P7 archetype** — small, and changes what the judge is even asked.
4. **P4 word budget** — one constraint in one brief.
5. **P2 pairwise judge** — the big one; benefits from 1/3/7 being settled.
6. **P5 persistence** + **P6 loop control** — the graph's own logic.
7. **P8 validation** — last, because it measures everything above.

## Split: production vs explore

Prompt, gate and rubric changes (P1, P2, P3, P4, P7) are **production improvements that stand on
their own merit** — they make any run better whether or not a graph ever drives it. Graph control
(P5, P6) stays in `explore/` until it has earned promotion. P8 is a run, not code.
