# skills/ — the NOLAN skill registry

NOLAN is a **hybrid** pipeline: a deterministic engine that hands off to an agent at
judgment points (plan, author, invent, edit). A **skill** is the markdown doc the agent
reads at such a handoff. Code has a compiler and tests; prose doesn't, so skills rot
silently — a catalog drifts from the blocks it documents, a load-site stops pointing at
the doc it used to inject, and nothing fails.

This registry gives skills the two things code already has and prose lacked:

1. **A verifiable binding.** Each skill declares where it's loaded and what it must stay
   in sync with; `python -m nolan.skills` lints those claims and FAILS on drift.
2. **An identity + lineage.** A stable `id`, a `kind`, and `uses`/`overrides` edges,
   emitted to `skills/index.json` for the rest of the system (and a future `/skills` UI).

## Two roots

| root | what | moved? |
|------|------|--------|
| `skills/` | relocated pipeline/agent docs — the home | yes, consolidated here |
| `.claude/skills/` | harness-invoked Claude Code skills (the runtime scans this path to make them invocable) | **no** — cataloged in place; moving breaks invocation |

A skill is **any `.md` whose frontmatter has an `id`.** Untagged `.md` are ignored, so
migration is incremental and a half-migrated tree still lints clean.

## Manifest (YAML frontmatter)

```yaml
---
id: explainer.script            # stable machine id (unique); kebab, dotted by domain
name: Explainer script authoring
kind: contract | craft | grammar | prompt | methodology
purpose: one line — what an agent uses it for
status: active | draft | deprecated
version: 1
handoffs:                       # WHERE it's invoked → lineage to the pipeline
  - { process: explainer, stage: author-script, gate: A }
uses: [explainer.scene-grammar]     # composition: skills it builds on
overrides: [scene-edit]             # skills it supersedes in its context
loaded_by: [src/nolan/fleet.py]     # code paths that inject/cite it (lintable binding)
documents: { palette: explainer }   # grammar↔code sync target (see below)
evals: [paper-quiz]                 # eval ids that exercise it
---
# … the skill body (plain markdown, Claude-Code SKILL.md compatible) …
```

`name` + `description` keep Claude-Code skill compatibility; the rest is management
metadata the harness ignores.

### kinds (each iterates differently)

| kind | example | how it's measured / improved |
|------|---------|------------------------------|
| **contract** (hard rules) | `flow/edit-contract` | violation-rate at the gate |
| **craft** (judgment) | `explainer/script` | feedback ledger + comprehension eval |
| **grammar** (lookup) | `explainer/block-catalog` | staleness lint vs the code it documents |
| **prompt** (one-shot) | `orchestrator/*` | A/B two versions on the same input |
| **methodology** (multi-phase) | `web-presentation/skill` | end-to-end gate pass-rate |

### `documents:` — the staleness invariant

Names what a `grammar` doc must stay in sync with, so drift is a failing check, not a vibe:

- `palette: <flow>` — the catalog must document every block in that flow's palette
  (`web-video-lab/flows/registry.json`). Scoped, so art-only blocks don't false-positive
  on the explainer catalog. Also flags palette blocks the library doesn't actually ship.
- `blocks: <path>` — a master catalog must mention every block under that library dir.

## Commands

```bash
python -m nolan.skills          # regenerate skills/index.json + lint (exit 1 on errors)
```

The linter: unique ids · valid kind · `uses`/`overrides` resolve to real skills ·
`loaded_by` paths exist and still reference the skill (catches dead bindings) ·
`documents` staleness. Errors fail; warnings are advisory (drift TODOs the system tracks).

## Status

34 skills across four tiers — browse them on the `/map` **Skills** tab (hierarchy, click-to-view,
last-amended + binding + coverage stats):

- **primary** — `pipeline.hyperframes`, the DOMINANT compose-first spine (bound to the `hf-finish`
  DAG; strong honesty test: must document every DAG step, in `tests/test_organ_skills.py`).
- **organ** — per-subsystem overviews `organ.{voice, acquire, asset-engine, sync, audio-mix}`; each
  declares `documents: {module: …}`. Add one and the generic honesty test covers it automatically.
- **craft** — the shared umbrella judgment (`common/*`); motion/sound/pairing/composition/editing/
  theme also declare `documents:` and are registry-synced by `tests/test_umbrella_skills.py`.
- **legacy** — retired Director/`explainer`/`art`/`flow` docs. The orphaned explainer/art/flow
  cluster is `status: deprecated` (superseded by `pipeline.hyperframes`, which `overrides` them);
  `orchestrator/*` + `flow.edit-contract` + `scene-edit` + `publish/*` stay active (still wired).

Organ/pipeline skills are authored once under `skills/<domain>/` and symlinked into
`.claude/skills/nolan-<name>/SKILL.md` so BOTH the harness auto-routes to them AND code can
`handoff()` them (`load_skills` dedups by real path). The `nolan` router table is auto-generated
(`python -m nolan.skills --emit-router`) and freshness-tested; the feedback ledger
(`record_feedback` / `skill_health`) is live.
