# CLAUDE.md — NOLAN operating manual

This file is loaded into EVERY session. It is the contract; details live in
the linked docs. Radically updated 2026-07-05 after the architecture
consolidation.

## What NOLAN is

Automate video-essay making: **script → authored plan → asset/motion/effect/
words/charts/tempo/voiceover matching → render**, with the human in the loop
at any artifact they choose to edit. Target: high-quality YouTube video
essays across topics and styles.

- `ARCHITECTURE.md` — the living map of the system (read it before touching
  pipeline/engine code; update it when a contract changes).
- `/map` on the hub (port 8011) — the LIVE introspected catalog: spine,
  organs, labs, skills, surfaces, health. `docs/SOTA_ROADMAP.md` — the craft
  roadmap. `IMPLEMENTATION_STATUS.md` — the change journal.

## The taxonomy (place new code deliberately)

- **SPINE** — the 10 Director steps (`orchestrator/director.py`
  PIPELINE_STEPS). Ordered, checkpointed, artifact-producing, resumable.
- **ORGANS** — engines steps call (asset_engine, voice_pipeline, audio_mix,
  layout_blocks, premium_render, motion/, render_dispatch, …). Standalone
  modules, no UI, injectable tiers, honest failures.
- **LABS** — human exploration tools that FEED artifacts (script/video
  styles, deconstruct, clips→motion promotion, broll lab, library/ingest).
  Labs never write pipeline artifacts except through explicit handoffs.
- **SKILLS + AGENTS** — the hybrid half (see policy below). Skills are the
  typed registry in `skills/index.json`; agents are the tmux fleet
  (nolan1–6) dispatched for open-ended work.

## Capability routing policy (apply to every new feature)

- **Deterministic code** where correctness is computable: timing, mixing,
  gating, matching thresholds, assembly, contracts.
- **LLM API calls** (qwen via OpenRouter etc.) for cheap structured
  judgment: bridging, scoring, describing, classification.
- **Agent + skill** for open-ended synthesis and taste: script voice, scene
  design, effect design, refinement from human comments.
- **The agent contract:** an agent's output is a PROPOSAL artifact that
  passes a deterministic gate before becoming canonical (draft → validate →
  accept). Never give agents side-doors into canonical artifacts.
- Agent-authored artifacts carry provenance: skill@version, agent, model,
  date, input reference.

## The module contract (every new craft capability)

Capabilities group under UMBRELLAS (editing, motion, pairing, themes,
blocks, sound). A new capability is not "code in the render path" — it
lands as: (a) a **registry entry** with purpose + when_to_use + constraints
(e.g. duration_preserving); (b) an **authored artifact field** validated
against that registry; (c) an **executor** in the render path; (d) auto-
surfaced in `/map` and the umbrella's skill (honesty-tested against the
registry so catalogs can't rot). An authored field with no consumer is a
bug (the `transition` lesson). Gold standard: `nolan/motion/registry.py`;
editing umbrella: `nolan/editing.py`.

**MANDATORY before wiring any new capability, step type, block, or
authored field: read `docs/WIRING_CHECKLIST.md`** — the seven pitfall
classes (each incident-derived) and the definition of "wired". Meta-rule:
docs claim, tests enforce — a rule without its honesty test doesn't exist
(PLAN_FIELD_CONSUMERS, UMBRELLA_WIRING, step classification, catalog
coverage all have one; your new thing does too, or it isn't done).

## Non-negotiable invariants

- **scene_plan.json is lossless** (schema v2): unknown keys survive every
  round-trip (Scene.extra / ScenePlan.meta). Never strip what you don't know.
- **Narration owns duration**: per-section VO wavs
  (assets/voiceover/_work/sec_*.wav) are THE beat anchors; video ≡ narration.
- **Failures are loud**: non-zero exits, error states in step history, no
  silent caps, no rc-0-on-failure. If a feature bounds coverage, it reports
  what it dropped.
- **Verify like an editor**: after rendering anything, extract frames and
  LOOK at them; after audio work, measure it (band RMS, duration deltas).

## Environment

- Conda env `nolan`: python `D:\env\nolan\python.exe`, pip
  `D:\env\nolan\Scripts\pip.exe`. No system python, no new venvs.
- **Always `python -X utf8`** — cp1252 crashes corrupt scene detection and
  break → · characters.
- Stay inside `D:\ClaudeProjects\NOLAN`. Ask before touching anything
  outside.
- Ports: hub 8011 (NEVER 8001 — SPARTA owns it), render-service 3010,
  ComfyUI 8080 (Windows-only reachable). Hub restart: find the python.exe
  PID on 127.0.0.1:8011 via netstat, taskkill it (NEVER the tailscaled PID
  also on 8011), relaunch `D:\tmp\start_hub.cmd` detached.
- Node (render-service) runs Windows-side; render.mjs/still.mjs bundle per
  invocation — TSX edits take effect on the next render, no build step.
  stage.mjs needs ABSOLUTE media paths (node CWD = render-service/).
- Default Gemini model: `gemini-3-flash-preview`.

## Working discipline

- **Concurrent agents share this tree.** Before staging: check `git status`
  and per-file hunk maps; stage ONLY your hunks (surgical `git apply
  --cached` with a hunk filter when a file is shared). Never `git add -A`.
  Commit to master; no branches. Land or leave others' WIP explicitly —
  never mix it silently into your commits.
- **CRLF files exist** (cli_legacy shim history, IMPLEMENTATION_STATUS.md,
  webui/operations.py, some templates/skills). Edit with the Edit tool, or
  in python read with `newline=''`, preserve `\r\n` on write. Check with
  `file` before scripted edits.
- **Think before coding; simplicity first; surgical changes; goal-driven
  execution** (state "done" criteria up front; verify before reporting).
  Full rigor for features/fixes/refactors; light touch for typos/configs.
- **QA loop**: run it, look at the output, fix, repeat. Do not report
  success without evidence. Tests to run by area: `scripts/test_e2e_smoke.py`
  (render/assemble chain — THE net), `scripts/test_director_steps.py`
  (pipeline sequencing), `tests/` pytest suites per module (asset engine,
  premium, audio_mix, budgets, system_map honesty, hub_*). The full
  `tests/` suite runs clean (~3 min).
- **UI wiring discipline**: every control states which artifact field it
  writes and which consumer reads it — a control that can't answer that gets
  removed. UI edit grammar: artifact → view → edit → show what re-runs →
  re-run.
- Update docs after features: IMPLEMENTATION_STATUS.md entry (CRLF!),
  ARCHITECTURE.md if a contract changed.

## Notification rule

Before asking for user approval on any action, play the alert:
`powershell -c "[console]::beep(1000,200); [console]::beep(1200,200); [console]::beep(1500,300)"`
Check `.claude/settings.local.json` permissions first; only ask if not
covered.
