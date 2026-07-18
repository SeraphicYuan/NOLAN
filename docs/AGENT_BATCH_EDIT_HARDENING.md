# Agent batch-edit loop — hardening plan (3 fixes)

Derived from executing the batch-apply-on-comment flow end-to-end (the `_stress_spotlight`
and `the-openai-debate` runs, 2026-07). Each miss in those runs traces to one of three gaps.
This plan specs the three highest-ROI fixes. It follows `docs/WIRING_CHECKLIST.md`: **every new
authored field names its writer, its consumer, and its honesty test** — no phantom fields.

Grounding — the current flow and its holes:
- UI inserts a mention as **positional text** (`hf_scenes.html:1899 insert()` → `it.token`, built at
  `:1894` as `'@asset' + i`). Order = `list_assets` (videos-first, then images alpha).
- `stage_comment` (`edit.py:1295`) persists only `{id, text, scene_id, status}` → the pick-time
  binding is discarded.
- `compile_batch_brief` (`batch.py:35`) dumps raw `c['text']` into `.hf_batch_kickoff.md` → the fleet
  agent receives `@asset0` with **no resolution and no asset list**.
- `_resolve_hf_mentions` (`edit.py:787`) resolves `@assetN` **positionally** from an `assets` list the
  route passes — used ONLY by the LLM path (`revise_frame_note`), never the batch path.
- `propose_scene_edit` (`edit.py:1378`) gates via `author.py --validate-only` (schema + seek-safety
  only) and stores the proposal in `.hf_proposals.json`. The human accepts seeing **op-JSON + rationale,
  no rendered visual**.

---

## Fix 1 — Stable, persisted `@`-mentions (kill the positional-index drift)

**Problem:** `@assetN` is an array index; the tray binding is thrown away; two consumers resolve
differently; the batch path doesn't resolve at all. Reorder one asset and every `@assetN` repoints.

**Data model (the one new field):** add `mentions` to a staged comment.
```jsonc
// meta.comments[i]  (frame spec — lossless, survives round-trips)
{ "id": "c1", "text": "... background use @bg-s08n37 ...", "scene_id": "f08s03", "status": "open",
  "mentions": [
    { "token": "@bg-s08n37", "type": "asset", "ref": "assets/videos/s08n37_01.mp4", "label": "s08n37 · video" }
  ] }
```
- `token` — the exact string in `text` (for chip rendering + resolver matching). **Human-readable and
  stable**, not positional (e.g. derived from the asset's pool id / stem, deduped).
- `type` — `asset | scene | reveal | transition | pool | clip | vo`.
- `ref` — the **stable identifier**: asset path (or pool id) / scene id / vocab name / pool-bin id / …
- `label` — display text for the picker + review UI.

**Writer → consumer wiring (must both exist — the phantom-field rule):**

| Layer | File · fn | Change |
|---|---|---|
| WRITE (UI) | `hf_scenes.html` `candidates()`/`insert()` | tray item carries `{token, type, ref, label}`; `insert()` inserts a **stable** token AND pushes the binding to a per-field `pendingMentions` map keyed by token |
| WRITE (route) | `hf_scenes.py:416` `POST /api/hf/frame/comment` | accept `payload["mentions"]`; pass through |
| WRITE (store) | `edit.py:1295` `stage_comment(..., mentions=None)` | persist `mentions` on the comment (default `[]`) |
| READ (batch) | `batch.py:35` `compile_batch_brief` | for each comment, append a **RESOLVED MENTIONS** block (`@token → <ref> (type)`) so the agent gets paths, not `@asset0` |
| READ (LLM) | `edit.py:787` `_resolve_hf_mentions` | resolve from `comment.mentions` first; fall back to positional `assets[N]` only when a token has no binding |

**Token strategy:** stop emitting `@asset0`. Emit `@` + a stable slug (the pool id or asset stem,
deduped: `@s08n37`, `@s08n37-2`). The `mentions` array is the source of truth; text token is display +
match key. Extends cleanly to the typed grammar you asked about (`@vid` / `@pic` / `@pool` / `@clip` /
`@vo`) — same `{type, ref}` shape, different picker filter.

**Back-compat (loud, not silent):** a bare `@assetN` with no `mentions` binding still resolves
positionally, but `compile_batch_brief` stamps it `@assetN → ⚠ UNBOUND (positional, may drift)` in the
kickoff so the agent (and human) see the ambiguity instead of guessing. Old comments keep working.

**Honesty tests** (`tests/test_hyperframes_edit.py`):
- `stage_comment(mentions=[…])` → reload → `mentions` intact (lossless round-trip).
- `compile_batch_brief` output for a comment-with-mentions contains the resolved `ref` (path), not the
  raw `@token`; and for an unbound `@assetN`, contains the `⚠ UNBOUND` marker.
- `_resolve_hf_mentions` prefers `comment.mentions[ref]` over positional; positional only on miss.

**Effort:** M (UI ~1/2 day incl. the chip; backend + tests ~1 day). **This is the fix that closes your
`@asset0` bug.**

---

## Fix 2 — A rendered preview on every proposal (stop accepting blind)

**Problem:** the reviewer approves a proposal from op-JSON + rationale; I had to build throwaway probe
comps to actually *look*. `author.py --validate-only` builds nothing, so there's no image to show.

**Design — lazy render on view (don't pre-render proposals nobody opens):**
- New route `GET /api/hf/proposal/preview?comp=&id=[&at=]` →
  1. load the proposal; deep-copy the target frame spec; `_apply_ops(trial, prop.ops)` (the exact
     `propose_scene_edit` trial).
  2. build the trial frame HTML to a **scratch** dir via `author.py --out-dir` (never canonical), copy
     `assets/` + `assets/cutouts/` so paths resolve (the probe mechanism, proven this session).
  3. `npx hyperframes snapshot` at `at` = the edited scene's `start + 0.6*dur` (reveals settled), or a
     caller-supplied timecode.
  4. cache the PNG under `compositions/_preview/_proposals/<id>@<t>.png`; return it (or 202 while
     building). Invalidate on proposal mutation.
- **Reuse:** `_scaffold_preview` + `snapshot_frame` already do steps 2–3; factor a `snapshot_trial(comp,
  frame_id, trial_spec, at)` helper so both canonical snapshot and proposal preview share it.
- **Canonical-safe:** operates entirely on a copy + scratch dir; `propose_scene_edit` and the canonical
  spec are untouched (assert in the test).

**Wiring:**

| Layer | File | Change |
|---|---|---|
| RENDER | `edit.py` | new `snapshot_trial(...)`; new `proposal_preview(comp, proposal_id, at=None)` |
| SERVE | `hf_scenes.py` (near `:469`) | `GET /api/hf/proposal/preview` |
| SHOW | `hf_scenes.html` proposal review (`#activity-proposals`, the render at `:730`) | lazy `<img>` per proposal (spinner → thumbnail); reuse the effect-proposal modal pattern at `:584` |

**Cost:** ~5–15s headless render per *viewed* proposal (lazy → only what's opened). Cache keyed by
`(proposal_id, at)`. For multi-scene frames, snapshot the edited scene's window, not the whole beat.

**Honesty tests** (`tests/test_hyperframes_edit.py`):
- `proposal_preview` for a known proposal returns an existing PNG of the right dimensions.
- canonical spec byte-identical before/after `proposal_preview` (no side effects).
- a proposal whose ops reference a missing asset still returns a preview (renders the broken state) —
  so the human *sees* the breakage rather than discovering it post-accept.

**Effort:** M (the snapshot-trial helper is the bulk; route + UI thumbnail small). **Highest
review-confidence ROI.**

---

## Fix 3 — Extract the note into a requirement checklist the agent must answer

**Problem:** a note like *"cutouts L/R + lower-thirds + **kinetic** + bg=@asset0"* is ~6 requirements;
nothing decomposed it or checked coverage, so "kinetic" silently became "some motion." Self-report in
prose hides misses.

**Design — extract at dispatch, answer at propose, surface at review:**
- **Extract (dispatch, `batch.py`):** a cheap structured LLM call (qwen via OpenRouter — capability
  routing: "cheap structured judgment") turns each comment's `text` into
  `requirements: [{id, text}]` (atomic, checkable). Persist on the comment (`meta.comments[i].requirements`)
  and render them in the kickoff as an explicit checklist. Deterministic fallback if the LLM is
  unavailable: 1 requirement = the whole note (never blocks).
- **Answer (agent, `propose_scene_edit`):** add an optional `requirements` arg → stored on the proposal
  as `[{req_id, status: met|partial|unmet|deferred, note}]`. The kickoff instructs the agent to map its
  ops to each requirement and mark status (a `deferred`/`unmet` is a first-class, honest signal — like
  the capability-gap pattern, not a failure to hide).
- **Surface (review UI):** the proposal card shows the checklist with ✓/◐/✗/⏸ per requirement; any
  `unmet`/`partial` is a **pre-accept warning banner**. This is advisory (coverage is judgment), but it
  turns a silent miss into a visible one — it would have flagged the missing kinetic text.

**Wiring:**

| Layer | File · fn | Change |
|---|---|---|
| EXTRACT | `batch.py` `compile_batch_brief` | LLM → `comment.requirements`; render checklist into kickoff |
| ANSWER | `edit.py:1378` `propose_scene_edit(..., requirements=None)` | store coverage on the proposal |
| SURFACE | `hf_scenes.html` proposal review + `GET /api/hf/proposals` | show checklist + unmet-warning |

**Honesty tests:**
- `compile_batch_brief` with a stub LLM extracts N requirements into the kickoff; with the LLM
  unavailable, falls back to 1 (no crash).
- a proposal carrying `requirements` round-trips; `list_proposals` returns coverage; an `unmet` item is
  flagged by the review payload.

**Effort:** M–L (LLM extraction + prompt tuning is the variable part; the plumbing is small).

---

## Sequencing, risk, and what to skip

**Order:** Fix 1 → Fix 2 → Fix 3.
- Fix 1 is the correctness bug (your `@asset0` issue) and unblocks the typed-grammar / tray UX you want
  next; do it first.
- Fix 2 is independent and pure upside (no data-model change); ship it second for immediate review
  confidence.
- Fix 3 depends on nothing but is the most LLM-taste-sensitive; do it last so prompt iteration doesn't
  block the deterministic wins.

**Risks / watch-items:**
- *Fix 1 migration:* old comments have no `mentions` — the positional fallback + `⚠ UNBOUND` marker
  keeps them working and honest. No data migration needed (lossless spec).
- *Fix 2 perf:* keep it lazy + cached; never pre-render on `propose`. Snapshot the scene window, not
  the 159s beat.
- *Fix 3 over-trust:* coverage is agent self-report — keep it **advisory** (a warning, never a hard
  accept-block), or it becomes a gate that lies (the phantom-gate trap).

**Explicitly out of scope (deferred):** the full typed-grammar picker (`@[vid]` category tray) is the
natural follow-on to Fix 1 but is UI-heavy — spec it separately once Fix 1's `{type, ref}` model lands.
Agent-authored-asset provenance (source URL / license stamping for fetched photos) is real but distinct
from these three; track it against the existing `asset_provenance_gate`.

**Docs to update on landing:** `IMPLEMENTATION_STATUS.md` (CRLF), and add the three new comment/proposal
fields to `docs/WIRING_CHECKLIST.md`'s field-consumer table.
