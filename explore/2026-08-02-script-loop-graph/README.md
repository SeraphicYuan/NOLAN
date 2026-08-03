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
| `policies.py` | eight candidate stop rules; `severity_floor` is **the chosen one** |
| `replay.py` | drives recorded runs through every policy; read-only |
| `test_policies.py` | pins the three chosen constants to the rounds they were decided from |
| `fleet_kinds.py` | **Phase 1** — ephemeral named fleets: kinds, atomic reserve, ceiling, reap |
| `probe_fleet.py` | exercises the lifecycle against real tmux with **no Claude agent spent** |
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

## Phase 1 — fleet lifecycle (done, `fleet_kinds.py`)

Ephemeral by default: **reserve → dispatch → await the artifact → release.** Warm pooling across
rounds is deliberately not built; the loop's state lives in files, so a warm agent buys little
and costs a lifecycle that can leak.

Four things `nolan.fleet` does not have, each of which the script loop needs:

- **Kinds.** `AGENT_PREFIX` is a module constant and `dispatch()` takes `plan_path`/`scene_ids`.
  A script worker shares none of that vocabulary.
- **Atomic reservation.** `next_session_name()` reads the live list and returns a name; the
  caller then creates it. Two callers racing get the SAME name and one silently loses its agent.
  Here **tmux is the lock** — `new-session` fails if the name exists, so the create *is* the
  reservation and a collision retries.
- **A concurrency ceiling.** Nothing refuses the eleventh agent today. Each is a billing session.
- **A completion signal that survives the agent.** `fleet` waits on the agent writing its own
  status; that is a promise it may not keep. Here the caller supplies a predicate over the
  artifact it actually wants — true whether the agent reported success, crashed after writing, or
  never wrote a status at all.

`await_done` distinguishes **`died`** from **`timeout`** deliberately: one means the work will
never arrive, the other means it might still. It also re-checks the predicate *after* seeing the
session gone, so an agent that wrote the artifact and exited is a success, not a death.

Verified against real tmux via `probe_fleet.py` — atomic naming, ceiling refusal, artifact-based
completion, death-vs-timeout, and staleness reaping — with **no Claude agent spawned**, the same
reason Phase 0 replays recorded runs instead of generating new ones.

### Two defects found on the way

- **`nolan.fleet._tmux` uses a fixed 8-second timeout, and a cold WSL boot exceeds it.** Measured
  here: warm, `wsl.exe tmux -V` is 0.09–0.58s; cold, it times out. So the first fleet call after
  the machine has been idle fails and every call after it succeeds — an intermittent that
  self-conceals on retry, which is the worst shape for the unattended loop Phase 2 will be.
  Worked around in `ensure_tmux()`; **must be fixed in `nolan.fleet` at promotion**.
- **Six stale `nolan1..6` status files** sit on the board with `session_alive: False`. The
  `nolan-run-*` reaper does not cover the long-lived namespace, so the fleet panel shows ghosts.

## Where it goes

Undecided. Promotion target would be `src/nolan/scriptwriter/` (policy + state) with the graph
itself somewhere under the pipeline. Not promoted until a human has picked a stop policy from the
`RESULTS.md` table — the harness deliberately ships none as default.
