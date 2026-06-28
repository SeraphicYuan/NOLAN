# Project-Model Unification — Design (C1)

## Problem
"A project" is represented five different ways with no shared abstraction and **no link
between the filesystem and the index DB**:

| Lens | "is a project" marker | identity | listed by |
|---|---|---|---|
| Scenes / Studio | `scene_plan.json` (or `output/scene_plan.json`) | dir path rel to `projects/` | `scan_projects()` (hub.py) |
| Script Projects | `scriptgen/meta.json` | `slug` (top-level dir) | `ScriptProjectStore.list()` |
| Agents / Orchestrator | `.orchestrator/` dir | `state.project_slug` or dir name | `dashboard.list_all_projects()` |
| Video Library | row in index-DB `projects` table | opaque `id` (+ unique `slug`) | `VideoIndex.list_projects()` |
| Picture Library | `projects/<name>/imagelib/` | project *name* string | `library_paths()` |

Consequences: `/scenes`, `/script-projects`, `/agents`, `/library` show different lists for
the same folders; `script_project_store.create()` writes the filesystem but never calls
`index.create_project`, so the DB `path`/`slug` and the FS dir don't reference each other —
they collide only by naming convention.

## Goal
One **slug-keyed `Project` abstraction** with capability flags derived from marker files, a
single discovery function, and an explicit FS-slug ↔ DB-`projects.id` link. Each page keeps
its current view by *filtering on a capability*, but from one source of truth.

## Design

### Identity
`slug` = the project directory's path **relative to `projects/`**, POSIX-normalized
(e.g. `"US Economy"`, or nested `"US Economy/segment_xyz"`). This is exactly how
`scan_projects` already names projects and how `_get_project_dir` resolves them, so it's
backward-compatible. The index-DB `projects.slug` for a top-level project equals this slug.

### `Project` (dataclass)
```
slug: str                 # path rel to projects/ (canonical id)
path: Path                # absolute project dir
name: str                 # human label (project.yaml name → slug)
# capabilities (from marker files)
has_scene_plan: bool      # scene_plan.json | output/scene_plan.json
has_script: bool          # script.md | script.json
has_scriptgen: bool       # scriptgen/meta.json (script-writing workspace)
has_orchestrator: bool    # .orchestrator/
has_segment: bool         # segment_meta.json
has_imagelib: bool        # imagelib/
# light metadata
scene_count: int          # parsed from scene_plan (0 if none)
library_project_id: str|None   # index-DB projects.id whose slug == this slug (the link)
```
`kinds` convenience: derived list like `["script","scenes","orchestrator"]` for display.

### Markers are relative to the project dir
`scriptgen/meta.json` marks the **parent** dir as a project (kind=script), not `scriptgen/`
itself. So discovery flags a directory `D` as a project if **D** contains any of:
`scene_plan.json`, `output/scene_plan.json`, `project.yaml`, `scriptgen/meta.json`,
`.orchestrator/`, `segment_meta.json`. (`imagelib/`, `assets/`, `clips/`, `source/`,
`output/`, `scriptgen/`, `.orchestrator/` are *sub-dirs of a project*, never projects, and
are not recursed into as candidates.)

### Discovery
`discover_projects(root, index=None) -> list[Project]`:
- walk `root` up to depth 3 (matches `scan_projects`), skipping `_PROJECT_SKIP_DIRS`,
  dotdirs, and the known project sub-dir names above;
- a dir with ≥1 marker becomes a `Project`; recursion still descends to find nested
  segment-output projects;
- if `index` is given, set `library_project_id = index.get_project_id_by_slug(slug)`.

`get_project(root, slug, index=None) -> Project|None` — single project by slug.

### FS ↔ DB link
- **Read:** `library_project_id` is resolved by slug match (no schema change).
- **Write (Phase 3):** when a project is created (script/orchestrator/segment), also ensure a
  DB row via `index.create_project(name, slug=slug, path=str(dir))` so videos/clips can attach
  and the link is durable. Idempotent: skip if `get_project_id_by_slug(slug)` exists.
- A `backfill` helper registers DB rows for existing FS projects lacking one.

## Rollout (each phase independently tested, backward-compatible)
- **Phase 1 — ✅ DONE:** `src/nolan/projects.py` (`Project`, `discover_projects`, `get_project`,
  `link_db_project`, capability detection). Purely additive. Tested in `tests/test_projects.py`.
- **Phase 2 — ✅ DONE (new surface):** unified `GET /api/projects` (capability-tagged, links DB by
  slug) + `nolan projects status` CLI. TestClient-tested. *Migrating the legacy per-page endpoints
  (`/scenes/api/projects`, `/api/status`, script-projects/agents/library) onto the shared discovery
  is deferred — it must preserve `scan_projects`'s exact `sections`/`has_audio` shape and needs the
  web UIs render-tested, which can't be done from WSL against the Windows-bound hub.*
- **Phase 3 — ✅ DONE:** FS↔DB linking wired into `script_projects_create` (best-effort, guarded) +
  `nolan projects backfill` to reconcile existing projects. Idempotent; roundtrip-tested with a real
  temp `VideoIndex`.

### Status summary
The unified read model, the one-list endpoint, and the FS↔DB link all exist and are tested. What
remains (deferred, lower risk now that the abstraction exists): point the four legacy listing
endpoints + `scan_projects` at `discover_projects`, and link on the orchestrator/segment/`projects
create` paths too (script-create is done; `projects backfill` covers the rest in the meantime).

## Non-goals / kept as-is
- Picture-library scope stays keyed by slug (already aligns; `imagelib/` is a project sub-dir).
- `ScriptStyleStore` (`script_styles/`) is a distinct concept (writing-craft corpus), not a project.
- No DB schema migration in Phase 1/2.

## Risks & mitigations
- **Nested-project naming** must stay identical to `scan_projects` (templates resolve by it) →
  Phase 2 keeps `scan_projects`'s exact output via the wrapper + tests asserting parity.
- **Performance** (walking `projects/` per request) is unchanged from today's `scan_projects`.
- **DB write on create** (Phase 3) is the only behavior change → idempotent + guarded + tested.
