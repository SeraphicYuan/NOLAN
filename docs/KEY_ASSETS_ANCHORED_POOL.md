# Key-Assets Anchored Pool — program plan

**Status:** in progress · started 2026-07-22 · owner: human + Claude (in-the-loop, refine-then-automate)

A **global, top-down** asset stage that runs **before** the existing per-beat acquisition
(`src/nolan/acquire/`). A senior archival/research producer reads the whole script, decomposes it
into the **hero assets** the video is *about* (named people, orgs, logos, specific works/ads,
places, events, key clips), does **consolidated, greedy research** to find + condition them, and
hands the authoring stage a typed, provenance-carrying, well-named **anchored pool** that authoring
consumes **first** — falling back to acquisition only for what heroes don't cover.

## Why (the gap)

`src/nolan/acquire/` is **local/bottom-up**: one need per beat, recall-driven, interchangeable
b-roll. It structurally cannot produce the **hero asset** — the specific, named, irreplaceable thing
(the real De Beers logo, a portrait of Ernest Oppenheimer, the 1947 "A Diamond Is Forever" ad). In
documentary production this is a separate role (the **archival/research producer** building an
**asset pull list**) done *before* editors cut b-roll. This feature gives NOLAN that role.

| | Key-Assets pool (new) | Acquisition pool (existing) |
|---|---|---|
| View | **Global / top-down** | Local / per-beat |
| Optimizes | **Precision** — the right specific thing | Recall — enough on-topic options |
| Cardinality | Few, curated, hero | Many, interchangeable |
| Failure mode | *Wrong entity* / missing | Thin / off-topic |

## Taxonomy placement (NOLAN contract)

Hybrid, per the capability-routing policy:
- **Agent + skill** (taste/synthesis): senior-editor decomposition + research/expansion.
- **LLM calls** (structured judgment): entity extraction, kind classification, slugging.
- **Deterministic code** (computable correctness): download/gate, background removal, crop/upscale,
  naming, provenance, dedup-vs-acquisition, and **the gate**.
- **Agent contract:** research output is a **PROPOSAL** (`key_assets.proposal.json`), never
  canonical. A deterministic gate promotes it to `key_assets.json`. No side-door into canonical.

Lands as: a new **organ** `src/nolan/keyassets/`, a **lab** review surface (approve the pull list
before spend), an **agent** for research, and a **registry** (kind taxonomy + processing rules).

## Locked decisions (from the director, 2026-07-22)

1. **Kinds v1:** `person` · `organization` · `logo/brand-mark` · `artifact/work` · `place` ·
   `event/moment` · `key-clip`. **No `dataset/stat`** — datasets move to the **script research
   stage** (guarantees dataset↔script alignment; feeds authoring via existing `/data` +
   `register_dataset` + `data_brief`). Key-assets is visual-hero only.
2. **Research = consolidate then greedily harvest.** Cluster correlated entities into a few
   **research directions** (De Beers + Rhodes + Oppenheimer + the 1947 ad + Kimberley → ONE "De
   Beers cartel" direction), research each **once**, and squeeze **every** relevant asset + fact out
   of each touch. *This clustering + greedy-harvest is the part we test/refine together.*
3. **Web search = a first-class provider** (built P0 — see below), not ad-hoc.
4. **Authoring: anchored pool first, acquisition for the gap.** Retire the invent-only faceless
   path — all videos consume the pool. Author places heroes at their named beats first; acquisition
   only fills the rest. Entity-level suppression prevents double-search (they search different
   spaces anyway).
5. **Human-in-the-loop** (`--review`) until we automate. Provenance **recorded** (fair-use regime,
   not blocking). **Reusability** into the persistent library = v2.

## Artifact schema (`key_assets.json`)

```jsonc
{
  "id": "ka_debeers_logo",
  "kind": "logo",                    // registry-validated enum
  "entity": "De Beers",
  "narrative_role": "recurring brand anchor — appears whenever the cartel is named",
  "priority": "hero" | "supporting",
  "mentions": ["s3.b2", "s7.b1"],    // beat spans → ties into coverage.py + sync.py at/anchor
  "research_direction": "de-beers-cartel",
  "research": { "summary": "...", "facts": [{"claim":"...","source_url":"...","confidence":"high"}] },
  "assets": [
    {"file": "keyassets/logo_de-beers_cutout.png", "variant": "cutout",
     "collage_ready": true, "processing": ["bg_removed:birefnet","trim"],
     "provenance": {"source_url":"...", "license":"...", "resolved_via":"wikimedia|title-match|web"}}
  ],
  "provenance": {"skill":"keyassets@1","agent":"nolanN","model":"...","date":"2026-07-22"}
}
```

## Kind registry (`keyassets/registry.py`)

Each kind carries **processing rules** + **resolution strategy**:

| kind | resolution (preferred → tail) | processing |
|---|---|---|
| person | named-work/title-match, Wikimedia, institutional → web | identity-verify (VLM); optional cutout |
| organization | Wikimedia, official → web | — |
| logo/brand-mark | Wikimedia/SVG, official → web | **cutout + trim** → collage_ready |
| artifact/work | title-match, museum/archive → web | identity-verify; crop |
| place | Wikimedia, archive, map | — |
| event/moment | archive.org, LOC, Wikimedia → web | — |
| key-clip | archive.org movies, provider video → web | trim to b-roll window |

## Stage pipeline (`src/nolan/keyassets/`)

`decompose` (LLM, global) → `consolidate` (cluster → research directions) → `research` (agent,
greedy harvest: `web_search` + authoritative providers + `extractors/` to pull real assets from
found pages) → `resolve` (canonical retrieval + `asset_gate`) → `condition` (`cutout_file(trim=True)`,
crop/upscale, **semantic naming**) → `gate` (proposal → canonical) → `manifest`
(`key_assets.json` + HERO section prepended to `capture/extracted/asset-descriptions.md`).

CLI: `nolan key-assets <comp> [--review] [--budget N]`.

## Naming (self-documenting, stable)

`keyassets/{kind}_{entity-slug}_{variant}.{ext}` — e.g. `logo_de-beers_cutout.png`,
`person_ernest-oppenheimer_portrait.png`, `clip_diamond-is-forever-ad_1947.mp4`. Videos live under
`keyassets/videos/` (the one hard `stageAssets` rule); basenames must appear verbatim in a frame's
`asset_candidates`. The `{id}_{NN}` index is *not* parsed by any consumer — semantic names are safe.

## Integration & wiring (the make-or-break)

The inventory consumer is the **authoring agent reading `asset-descriptions.md`** (no code parses
it into selections; the only deterministic consumer is `scripts/lib/assets.mjs → stageAssets()`,
which copies **named basenames** from `capture/assets{,/videos}` + `capture/keyassets{,/videos}`).

Ordering: `new_essay` → **key-assets** → `acquire_pool` → author (pool-consuming, heroes first).

- `manifest` prepends a **HERO section** to `asset-descriptions.md` (elevated, with narrative role +
  `collage_ready`/`cutout` flags), files under `capture/keyassets/`.
- Authoring (the `hf-author` skill + `.hf_kickoff.md` in `new_essay`) changes to **place
  HERO assets at named beats first** (via `sync.py` `at`/`anchor`), then fill from the acquisition
  pool. **Cutouts** flow into the `spotlight`/collage blocks (`data.src` resolved against the comp
  dir).
- **Acquisition suppression:** ~~entities satisfied by a hero are marked resolved so
  `derive_asset_needs`/the engine complement instead of re-searching.~~ **SUPERSEDED (2026-07-23):**
  the design settled on *two pools, one spine* with heroes as an **offer** — the agent picks from BOTH
  the hero pool and the b-roll pool. Re-searching a hero's entity in b-roll gives the author MORE
  options (the golden run placed De Beers as both a hero logo AND b-roll footage); suppressing it would
  shrink the palette. The only cost of not suppressing is a little redundant search budget — accepted.
- **Coverage seeding:** ~~resolved heroes feed `coverage.py` → "named but unillustrated" closes by
  construction.~~ **SUPERSEDED (2026-07-23):** `coverage.py` is an acquire-path organ and is NOT in the
  HF launch/finish path, so there is nothing to seed here. The **W5 soft `hero_coverage` report**
  (`keyassets/inventory.py` → /keyassets: which SELECTED heroes the author actually placed vs skipped)
  serves the reliability intent for the dominant HF flow — a signal, not a mechanical gate, matching the
  heroes-as-offer model. The golden run depicted all 20 heroes without coverage.py.

## Honesty test (per WIRING_CHECKLIST — docs claim, tests enforce)

Every `key_assets.json` entry appears in `asset-descriptions.md` with a **stageable basename that
exists on disk**; kind ∈ registry; cutout variants are trimmed; provenance present. Fails loud if a
hero can't be placed — kills the phantom-artifact trap (the `transition` lesson).

## Blindspots + mitigations

- **Wrong-entity / identity collisions** (a portrait of the *wrong* Oppenheimer) — the highest-stakes
  failure. Mitigate with `verify_generation` VLM identity check + institutional/title-match priority.
- **Cost/scope creep** — rank + cap the hero set; deep-research only heroes; consolidation cuts
  redundant researches.
- **Overlap with acquisition** — entity-level suppression; they search different spaces.
- **Provenance under fair use** — record source/license (powers credits; lets the human make the
  fair-use call), never blocks.

## Golden test: `projects/the-diamond-illusion/scriptgen/drafts/draft-03.md`

Hero pull-list the stage must recover (acceptance criteria):
- **People:** Cecil Rhodes, Ernest Oppenheimer (+1910 quote), Frances Gerety, Mary of Burgundy
  (1477), Edward Epstein, Jack Ogden.
- **Logos → cutout/collage:** De Beers (recurring anchor), N. W. Ayer, Lightbox, General Electric,
  Advertising Age.
- **Artifacts/works:** the 1947 "A Diamond Is Forever" ad, Star of South Africa (83 ct), the four-Cs
  grading device, vintage N.W. Ayer print ads.
- **Places:** Hopetown / Kimberley "Big Hole", Zaire, London (the Syndicate).
- **Events/clips:** 1869 rush, 1888 consolidation, 1975 divestiture, 1981 Zaire dump, 2004 GE plea,
  2025 Lightbox shutdown; vintage TV commercials, Big Hole footage, lab-grown production footage.
- **Consolidation win:** the De Beers people + company + campaign + mine collapse into ONE research
  direction.
- **Datasets (correctly OUT of scope):** 10%→post-war adoption, $23M→$2.1B sales, 90%→25% share,
  Zaire −40%, 90%-cheaper lab-grown — owned by the script-research stage.

## Phasing

- **P0 — Web-search provider ✅ DONE (2026-07-22).** `src/nolan/web_search.py` — `WebSearchProvider`
  ABC + keyless **ddgs-text baseline** + keyed upgrades (Tavily/Brave/SerpAPI) registered via
  `cfg.web_search` (`config.WebSearchConfig`, env `TAVILY_/BRAVE_/SERPAPI_API_KEY`).
  `WebSearchClient.search` (preferred-first) / `search_all` (greedy). Degrades cleanly; client-level
  error containment. `tests/test_web_search.py` (10 tests, green); live baseline verified.
- **P1 — Decompose + consolidate + `--review`** (the part we iterate on): pull-list without assets,
  tuned on draft-03.
- **P2 — Research harvest → resolve → condition → gate:** canonical assets, cutouts, `key_assets.json`.
- **P3 — Authoring + acquisition wiring ✅ DONE (2026-07-23), validated E2E:** HERO section
  (`inventory.write_hero_section`), heroes-first authoring (the `hf-author` brief), honesty test
  (`test_hero_inventory_stages_lists_and_is_honest`), and the launch wiring W1–W5 (default `key_assets`
  mode in `new_essay`; the ordered `_assets_job` heroes→pool→stage; `/keyassets` Collect button; new-essay
  form selector; the W5 soft `hero_coverage` report). Proven by a cold fleet run on draft-03: all 20 hero
  entities placed once, both hard gates green, full 13.6-min render. **Suppression + coverage seeding were
  SUPERSEDED** (see *Integration & wiring* above) — the heroes-as-offer / two-pools design moved past both.
- **P4 (later) — Reusability** into `imagelib`/KB (research an entity once, reuse).

## Open items to tune together (P1)

- Consolidation clustering approach (how aggressively correlated entities merge into directions).
- Budget knobs (hero cap, researches per script, harvest depth per touch).
- How greedy the per-touch harvest is (assets + facts squeezed per page).
