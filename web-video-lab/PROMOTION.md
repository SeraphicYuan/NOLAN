# Promotion process — bespoke (raw) → library

How a one-off `raw/` block graduates into the reusable, cataloged `library/`. Kept
deliberately mechanical so it's a 2-minute, low-risk procedure — not a judgment call
every time.

## When to promote (the gate)
Promote a bespoke block only when **all three** hold:
1. **Recurrence** — the pattern is a general archetype that appears (or clearly will)
   across ≥2–3 topics: counting stats, value-over-time, grid coverage, enumerated list,
   profiles, before/after. Not a content-specific gag.
2. **Parameterizable** — its content lifts cleanly to props with **no narrative-specific
   geometry left hard-coded**.
3. **Low overlap** — it isn't a near-duplicate of an existing library block. If it nearly
   matches one, **generalize/merge into that block** instead of adding a sibling.

Otherwise: **keep it in `raw/`.** And if only a *mechanic* is reusable (not the whole
block), **harvest the mechanic** into an existing block or a primitive — don't add a
near-duplicate block. (Example: NpcStrike's terminal backdrop is a one-off → stays raw;
its strike-on-spoken-word mechanic was folded into `HeroStatement`.)

## Steps (≈ move + regenerate)
1. **Generalize** — lift hard-coded content → props; rename the file **and** its
   `export const` to a general PascalCase name; pull any shared mechanic into
   `src/primitives/` (e.g. `RollingNumber` / `useCountToWord`).
   - **Props the spec sets must be JSON-serializable** (strings / numbers / arrays) — a
     spec is JSON, so a `format: (n)=>…` callback can't be passed. Use string props like
     `prefix`/`suffix`/`axisUnit` for spec-driven formatting (keep an optional `format`
     callback only for programmatic callers). (This bit ValueLadder's `$`.)
2. **Move** — `git mv src/blocks/raw/<Old>.tsx src/blocks/library/<New>.tsx`.
   `raw/` and `library/` sit at the same depth, so the `../../Surface` /
   `../../primitives/...` imports **don't change**.
3. **Regenerate registries** — `python web-video-lab/gen_registry.py`. It rewrites
   `library/index.ts`, `raw/index.ts`, `blocks/index.ts` from the directory contents.
   **Never hand-edit those three** (that's where concurrent-edit bugs came from).
4. **Catalog** — add a `BLOCK_CATALOG.md` entry: use-when (the relation it serves),
   props, and how many anchors it needs.
5. **Specs** — update any spec whose `block` field used the old bespoke name.
6. **Verify** — re-render an affected chapter; confirm it still renders + syncs.

## Primitives layer
Shared mechanics live in `src/primitives/`. The first is `RollingNumber` /
`useCountToWord` — "roll a number to its spoken word" — which `StatCount` and
`ValueLadder` both compose from. A primitive is more valuable than any single block
(every future stat beat reuses it); promote a primitive the same way once it's reused.

## The harvest backlog
The spec author's `_needsBlock` flags + recurring bespoke blocks are the promotion
queue. Review it periodically; promote what recurs, generalize as you go, and **don't
accumulate near-duplicates** — merge into the closest existing block instead.
