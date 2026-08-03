# Results — Phase 0 replay

Run: `D:\env\nolan\python.exe -X utf8 explore/2026-08-02-script-loop-graph/replay.py`
Read-only over `projects/*/scriptgen/`. No LLM calls, no fleet, deterministic, re-runnable.

## Corpus

Six recorded runs have a review round. **Only one iterated past round 1.**

| run | rounds | mode | style |
|---|---|---|---|
| the-diamond-illusion | **3** | auto | channel-lufei-wang-eng |
| aidebate-braid | 1 | semi | channel-lufei-wang-eng |
| attention-is-all-you-need-explainer | 1 | auto | great-books-explained |
| homer-auto | 1 | auto | great-books-explained |
| homer-braid | 1 | auto | great-books-explained |
| the-ai-debate-golden | 1 | auto | — |

That 5-of-6 figure is a finding in itself: **the review loop is, in practice, a single pass.**
Whatever policy we adopt has to work at round 1, because that is where almost every run ends.

## The one multi-round run, in full

| round | findings | h/m/l | **weighted** | draft words | human |
|---|---|---|---|---|---|
| 1 | 15 | 1/5/9 | **33** | 2,223 | 15/15 |
| 2 | 10 | 0/4/6 | **18** | 2,326 | 10/10 |
| 3 | 8 | 0/5/3 | **18** | 2,530 | **none** |

Promoted `draft-03.md`.

### Finding 1 — round 3 did no work that severity can see

Total findings fell 10 → 8, which reads as convergence. **Severity-weighted, it went 18 → 18.**
Round 3 cleared three `low` findings and *added* a `med`. A rule watching total findings calls
that progress; a rule watching weight calls it a stall. The draft also grew 204 words while
getting no better by this measure.

### Finding 2 — the loop lost its interrupt exactly when it mattered

Rounds 1 and 2 were human-gated. Round 3 — the one that shipped — was not. The run is
`mode: auto`, yet two of its three rounds *were* human-gated, so the declared mode and the
observed behaviour already disagree. The promotion decision is unrecorded and unrecoverable.

### Finding 3 — the human approves ~everything, but not always

**6 of 7 human-reviewed rounds approved 100% of findings.** The exception is real and instructive:

| run | approved | |
|---|---|---|
| aidebate-braid r1 | **9/22 = 41%** | 8 med, 13 low — a long, weak review, heavily filtered |
| every other round | 100% | |

So the interrupt is not *inherently* a rubber stamp — it discriminated hard once. But on this
evidence "human approved everything" is the norm, and a policy that treats approval as a strong
quality signal is reading noise most of the time.

## What each policy would have done

Diamond Illusion, decided with only what was knowable at each round:

| policy | after r1 | after r2 | after r3 |
|---|---|---|---|
| actual (baseline) | cont | cont | cont → promoted |
| `no_high` | cont | **STOP** | STOP |
| `no_high_or_med` | cont | cont | cont |
| `total_falling` | cont | cont | cont |
| `weighted_falling` | cont | cont | **STOP** |
| `rubber_stamp_detector` | cont | **ASK** | ASK |
| `semi_auto` | cont | cont | cont |

Three genuinely different verdicts on the same evidence:

- **`no_high` stops a round early** — saves one full draft+review cycle, ships with 4 med open
- **`weighted_falling` stops exactly where the work stopped paying** — and is the only rule that
  identifies round 3 as wasted
- **`no_high_or_med` / `semi_auto` would still be running** — by their standard the real run
  shipped *early*, with 5 med open

## Verdict

**The replay does what it was built to do.** The loop's stop decision is currently unstated, and
the candidate rules disagree materially — which means it is a real decision, not a formality.

Recommendation for the live loop (Phase 2), for a human to accept or reject:

1. **Route on severity weight, not finding count.** The recorded run is a clean demonstration
   that count hides a stall.
2. **Never promote without an interrupt.** Round 3 promoting unreviewed is a defect the graph
   should make structurally impossible, not a policy choice.
3. **Do not build much on the approval signal** until there is more of it — 6/7 rounds at 100%
   is close to no signal, and the one discriminating round is a sample of one.
4. **Optimise round 1.** Five of six runs never reach round 2, so effort spent on multi-round
   convergence is effort spent on the rare case.

## Not answered here

- Whether the graph produces a *better draft* — untestable without generation, by design
- Whether `weighted` weights (9/3/1) are right — they are a first guess, and the replay is the
  place to tune them once someone disputes a verdict
- Whether findings are comparable across archetypes — `review_archetype` is unset on 5 of 6 runs
