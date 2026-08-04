# Results

> ## ⚠ CORRECTION (Phase 2, 2026-08-02) — the Phase 0 trend analysis below is INVALID
>
> Phase 2 ran a calibration: **the same draft, judged twice.**
>
> | draft-01, 1,364 words | findings | h/m/l | weighted |
> |---|---|---|---|
> | judged in the original run | 9 | 0/4/5 | **17** |
> | judged fresh today | 23 | 6/14/3 | **99** |
>
> **5.8× on weighted severity. Zero high findings versus six.** The gap is uniform across all six
> dimensions (throughline-payoff 1→5, voice-ownership 0→2, evidential-sufficiency 1→4), which
> rules out any explanation about the draft and leaves only one: **an LLM judge's absolute scores
> are not comparable across sessions.**
>
> What that breaks, specifically:
>
> - **The headline finding below** — "Diamond Illusion round 3 did no work severity can see,
>   18 → 18" — compared three readings from three different judges. It is not evidence of a
>   stalled round. I stated it as a measurement; it was noise.
> - **`weighted_falling`** and **`MIN_GAIN`** both compare scores across rounds. Unusable as built.
> - **The absolute floor** (15 or 20) is meaningless when the same draft reads 17 or 99.
> - **Even `high == 0`** — the rule I was most confident in — flipped from 0 to 6 on one draft.
>
> So the agreed policy (`0 high · floor 15 · gain > 3`) rests on an unsound measurement basis and
> **should not be promoted.** Nothing was built on it, which is the point of having found this for
> the price of two agent runs (~15 minutes) rather than after wiring a graph around it.
>
> **Where this points.** Absolute scoring is the wrong instrument. The candidates:
> 1. **Pairwise, in ONE session** — show the judge draft N-1 and draft N and ask "did this improve,
>    and what still blocks?" A comparison inside one context needs no cross-session calibration.
>    Cheapest and most promising.
> 2. **`gate.py`** — the deterministic checks (format, word-count, beat-grounding, needs-check,
>    beat-continuity) are stable by construction and already exist. Untapped as a routing signal.
> 3. Multi-judge median, or an anchor set for normalising a session. Both expensive.
>
> The replay harness, the state model and the fleet lifecycle all stand — only the severity metric
> is discredited. Re-run the comparison once a stable metric exists.

# Phase 0 replay

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

## DECIDED — `severity_floor`, 2026-08-02

Chosen jointly after seeing the table below. Three rules, priority-ordered:

1. **`high == 0`** — a high-severity finding is never shippable. Two runs promoted with one open.
2. **weighted severity ≤ 15** at any round → stop.
3. **a round must move weighted severity by MORE than 3** to justify another.

**The floor is set so it almost never fires, and that is deliberate.** The lowest round-1 score
in any recorded run is 17, so 15 fires on none of them. A floor tight enough to fire (20 would
stop `homer-auto` at 17 and `homer-braid` at 20) is a floor fitted to six unlabelled points. So
the floor is a safety valve for a genuinely clean first draft and **`MIN_GAIN` is the real
terminator**.

Cost, stated rather than discovered: a marginal-gain rule needs two rounds to see a trend, so
**every run now does at least two** where five of six historically did one. That roughly doubles
loop cost and buys erring toward polish rather than toward shipping early — the safer direction
while the thresholds are this unproven. Revisit when runs carry quality labels.

Behaviour on the recorded corpus:

| run | r | h/m/l | wt | decision |
|---|---|---|---|---|
| aidebate-braid | 1 | 1/8/13 | 46 | cont — high open |
| attention | 1 | 1/5/5 | 29 | cont — high open |
| homer-auto | 1 | 0/4/5 | 17 | cont — above floor |
| homer-braid | 1 | 0/5/5 | 20 | cont — above floor |
| the-ai-debate-golden | 1 | 0/8/8 | 32 | cont — above floor |
| the-diamond-illusion | 1 | 1/5/9 | 33 | cont — high open |
| the-diamond-illusion | 2 | 0/4/6 | 18 | cont — above floor |
| the-diamond-illusion | 3 | 0/5/3 | 18 | **STOP** — gain 0, not >3 |

## Not a policy: promotion must require a human

Round 3 promoted with no human review. **No stop rule can fix that** — it is a missing edge, not
a wrong threshold. In the graph, promotion must be a node that cannot be routed past without an
interrupt. Recorded here so it is built as an invariant in Phase 1/2 rather than encoded as a
policy someone can swap out.

## Verdict

**The replay does what it was built to do.** The loop's stop decision was unstated, and the
candidate rules disagree materially — which made it a real decision rather than a formality.

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
