---
status: active
---

# script-loop-graph — can the script review loop be an agent graph?

Started 2026-08-02. Protocol borrowed verbatim from `HERMES/explore/`.

## The question

The script-review loop (`nolan.scriptwriter`) is NOLAN's most graph-shaped subsystem: it cycles
draft → judge → human-approve → revise, carries rich typed inputs (style, archetype, spine,
sources, ad-hoc questions), has a deterministic gate separate from the LLM judge, and already
writes a cross-project learning ledger.

**But it has no stated termination condition.** Whether to revise again, stop, or ask a human is
currently decided implicitly, round by round, and nowhere recorded.

So, in order:

1. **Phase 0 (this) — what SHOULD the loop have decided?** Replay recorded runs against several
   candidate stop policies. No LLM, no fleet, read-only, deterministic. Produces the benchmark.
2. **Phase 1 — fleet lifecycle.** Generic fleet *kinds* + pooling on top of `nolan.fleet`, so a
   script-loop can spawn/manage/reap its own `nolan-script-*` agents.
3. **Phase 2 — live loop.** The graph drives the fleet for real.

Deliberately NOT starting with LangGraph. Phase 0's job is to get the state shape and the routing
rules right on their merits; if they are right, porting is mechanical and the framework earns its
keep on checkpointing and interrupts in Phase 2. Writing a `StateGraph` on day one would bend the
design to fit the tool before anyone knows what the design is.

**Dependency note, measured:** `pip install --dry-run langgraph` into the `nolan` env adds 16
packages and touches **none** of NOLAN's pins — no numpy, no Pillow, no pydantic bump. The
`mas`-style env split that math-animation forced does **not** apply here. So adopting it later is
cheap; that is a reason to defer the decision, not to rush it.

## Files

| file | what |
|---|---|
| `state.py` | `LoopState` / `RoundState` — references and control data, never draft text |
| `policies.py` | seven candidate stop rules, each a pure function of state |
| `replay.py` | drives recorded runs through every policy; read-only |
| `RESULTS.md` | **the verdict** |

## Run it

```
D:\env\nolan\python.exe -X utf8 explore/2026-08-02-script-loop-graph/replay.py
D:\env\nolan\python.exe -X utf8 explore/2026-08-02-script-loop-graph/replay.py the-diamond-illusion
```

## Verdict so far

See `RESULTS.md`. Headlines:

- **Round 3 of the Diamond Illusion did no work severity can see** — total findings 10 → 8 looks
  like convergence, severity-weighted it is 18 → 18 (three `low` cleared, one `med` added), and
  the draft grew 204 words. A count-based stop rule cannot see this; a weighted one can.
- **The loop lost its interrupt exactly when it mattered** — rounds 1 and 2 were human-gated,
  round 3 (the one promoted) was not.
- **5 of 6 recorded runs never reached round 2.** In practice this is a single-pass loop, so the
  policy has to be right at round 1.
- **6 of 7 human-reviewed rounds approved 100% of findings** (the exception, `aidebate-braid` at
  9/22, shows the human *can* discriminate). Approval is close to no signal today.

## Where it goes

Undecided. Promotion target would be `src/nolan/scriptwriter/` (policy + state) with the graph
itself somewhere under the pipeline. Not promoted until a human has picked a stop policy from the
`RESULTS.md` table — the harness deliberately ships none as default.
