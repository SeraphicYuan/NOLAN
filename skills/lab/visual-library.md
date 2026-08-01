---
id: lab.visual-library
name: Visual Lib (not-held picture discovery tier)
description: >
  The library of pictures we do NOT hold — museum and archive collections harvested as catalog
  metadata plus a 512px thumbnail, so a search over a corpus far larger than any local library can
  answer "this image exists, here, under these terms", and one promotion edge fetches the bytes
  when a beat earns it. Covers the collection → harvest → (on-demand) caption loop, the THREE
  knowledge tiers (collection-only / shallow item / captioned item), the ROUTED retrieval (catalog
  identity for named works, CLIP over thumbnails for look), the promotion edge into the held
  Picture Library, and the invariants (the tier is opt-in on every read path, identity is
  catalog-derived never model-asserted, collection rights are sticky, coverage is stated honestly).
  Read before touching imagelib/harvest.py, the `held` tier in imagelib/catalog.py + store.py, the
  `/visual-lib` page, or the `nolan images harvest / discover / fetch / collections` commands.
kind: methodology
purpose: >
  Orient any Visual Lib task — which tier owns what, why retrieval is routed rather than blended,
  where the acquisition doors are, and which claims have honesty tests behind them.
status: active
version: 1
tier: lab
handoffs: []
uses: []
documents:
  module: src/nolan/imagelib/harvest.py
  store: src/nolan/imagelib/store.py
  page: src/nolan/webui/routes/visual_lib.py
loaded_by: []
evals:
  - scripts/eval_visuallib_recall.py
---

# Visual Lib — the not-held picture tier (`src/nolan/imagelib/`)

Two tiers, ONE catalog, ONE promotion edge — the shape the transcript library used to add a
discovery tier to the video library (`source_kind='transcript'`, `has_footage=0` in the SAME
VideoIndex) rather than forking a second store.

| tier | flag | what it is | where the bytes are |
|---|---|---|---|
| Picture Library | `held=1` | images we keep, CLIP+BGE searchable | `_library/images/files/` |
| **Visual Lib** | `held=0` | catalog metadata + a 512px thumbnail | at the institution |

Why a discovery tier for *pictures*, when a JPEG is cheap: the win is not storage. It is
**catalog-scale discovery** (the Art Institute alone publishes 61,568 public-domain artworks;
keyword search over that is as bad as keyword search over a channel's videos), **rights
decoupling** (index what you may not redistribute), and **region-addressability** (IIIF serves any
region at any size on demand — the image is a view, not a file).

## The three knowledge tiers

- **T0 collection-only** — the `collections` row: title, blurb, rights, count. Searchable before a
  single member is indexed; a hit says "this collection probably has it".
- **T1 shallow item** — what a harvest writes: the source's OWN catalog record (title, creator,
  date, medium, place) + thumbnail + stable id. No model calls. 90% of items live here forever.
- **T2 captioned item** — `harvest.describe_discovery`, **demand-driven and bounded**. Captioning
  132k items is not a plan; caption what retrieval or a human surfaced. Collection blurb, artist
  knowledge and classification are passed as context — but never the TITLE, because handing the
  model the answer makes it describe the title instead of the picture.

  The caption is **structured** (`imagelib/caption.py`, `caption_json` + `caption_schema`), and
  v1 is what survived measurement: `summary` · `subjects` · `action` · `human_presence` ·
  `panel_count` · `text_in_image` · `condition` · `mood` · `palette_words` · `uncertain[]`.
  **Half of v0 died on a 50-row validation** and must not creep back (a test enforces it):
  `focal_zone` was the centre cell 50/50; `has_border` agreed with pixel measurement 16/50,
  *worse than chance*; `open_zones` was one of two templates 38 times; `named_content` never
  once fired; `weather`/`vantage`/`time_of_day` were 78–82% constant. **The model NAMES, a
  detector LOCALISES, and nothing numeric is ever asked of a model.**

  Two rules on content: **observations, never policies** (no `usable_as` — re-captioning 60k rows
  is the expensive operation, so a policy baked into a caption costs a re-caption to change), and
  **a caption is never an identity** (`identity_source` untouched). `description` keeps holding
  the readable sentence so the BGE channel the eval measured stays unchanged.

  Verified live on real museum thumbnails: a coin came back `panel_count: pair` (the two-faces
  case v0 missed entirely) with its inscribed Latin correctly `text_in_image: depicted` rather
  than a watermark, and Van Gogh's *Bedroom* was described without being named.

**Warming (`warm=True`) is a BUTTON, never a default.** It downloads and PERSISTS — file on
disk, `thumb_path` on the row, CLIP vector — and it can RETIRE a row whose pixels fail the gate
(`status='rejected'`). A write hiding inside a read must not fire on every keystroke. Measured on
the live library: a NAMED query with warming took **32 s** and acquired 21 thumbnails, against
**0.5 s** without. And on a LOOK query it acquired **nothing** — look ranking is CLIP-dominant
(0.9), CLIP only knows rows that already have pixels, so the rows that need them cannot rank high
enough to earn them. **Search-driven warming cannot bootstrap look coverage; only
`backfill_pixels` can.**

Knowledge inherits DOWNWARD: an item with no caption still carries its collection's rights, era
and topic, and that inherited context is what makes a T1 row retrievable at all.

**T1 splits into two phases**, because pixels dominate the cost. `harvest(pixels=False)` /
`--no-pixels` writes the catalog record and nothing else; `ImageLibrary.backfill_pixels` /
`nolan images backfill` fetches thumbnails progressively afterwards. Benchmarked (60 records,
30 backfills, models pre-warmed): **87 ms/row** for a record + identity index against **470
ms/row** with pixels — **5.4x**, or 1.5 h against 9.6 h over the 62,035-row artic catalog. Of
Phase A's 87 ms, 78 is BGE indexing; the row write itself is 9 ms.

Retrieval consequence, from the eval: a record-only row is at FULL strength for named queries
(94.7 / 100 / 100 with no pixels at all) and materially weaker for look (47.4 vs 63.2 at rank 1).
**Pixels buy ranking, not reach.** `discovery_stats` therefore reports `pixels_pct` alongside
`described_pct`, so a records-only collection cannot read as fully indexed. The gates that need
pixels — the banner heuristic and the content-resolution floor — run in Phase B, at the moment
the pixels first exist, and a row that fails them is retired rather than left half-indexed.

## The loop

```
nolan images dump met                                    # bulk CSV, so the rights filter is offline
nolan images harvest artic --limit 600 [--query "..."]   # T0 + T1, idempotent, RESUMES by default
nolan images harvest met --dept "European Paintings" -n 500
nolan images harvest artic --restart                     # re-walk from the start (refresh, not extend)
nolan images discover "a rainy Paris boulevard"          # routed search over the not-held tier
nolan images fetch <id>                                  # promotion: bytes + gate -> held=1
nolan images collections                                 # coverage per collection, vs upstream
```

`harvest(source, ...)` → `HarvestReport` (scanned / added / refreshed / skipped_no_image /
skipped_rights / refused_gate / errors + quoted reasons). A bounded crawl that reported only its
successes would read as full coverage.

## The surface — `/visual-lib`

Its OWN page, not a tab on `/images`, for the reason `/transcripts` is not a tab on `/library`:
the two tiers answer different questions with different verbs. `/images` curates what we HOLD
(cutout, reject, shortlist, promote-to-global); this page FINDS what we don't. Folding them put
two grammars in one control strip — "license contains" and "scope" acting on one tier while
cutout/reject acted on the other. `/images` keeps a query-carrying bridge link instead of a tier
dropdown, and the page's own Fetch is the promotion edge back.

- **Search** — the routed query over not-held rows, each card carrying its score, institution,
  sticky rights, a QID badge where the source handed one over, and `Fetch`.
- **Sources** — harvest form (source + optional Met department/theme + limit) and the harvested
  table with per-collection coverage. Long by nature, so it is a background job with progress,
  never a request. Named **Sources**, not Collections: all three collections are currently
  whole-source harvests, so the old label promised curation the tier does not have. The concept
  survives — a collection is a **rights-and-provenance unit**, and when LoC lands its curated
  collections each becomes a row here with its own rights. The table shows SOURCE and COLLECTION
  as separate columns for exactly that reason, plus the upstream denominator beside the count.
- **Coverage** — what the library actually knows, with the T2 caption batch. It states that
  catalog prose does not count as a caption, so a 0%-captioned collection reads as 0%.

Ownership splits by RESOURCE, not by page: row-level ops stay in `routes/images_extract`
(`/api/images/discover`, `/api/images/{id}/fetch`); tier-level ops are new resources in
`routes/visual_lib` (`/api/visuallib/{sources,collections,harvest,caption}`). The source and
department pickers are served FROM `harvest.SOURCES` / `MET_DEPARTMENTS` — a menu copied into a
template by hand is the menu that rots (WIRING_CHECKLIST pitfall #5), and
`tests/test_hub_images.py` asserts the picker equals the registry. Batch bounds are parsed by
`_bounded_limit`: an explicit `0` is refused, never widened to the default — `or default` on a
falsy bound is a bounded crawl unbounding itself.

## Adapters — and the crawler contract

`harvest.SOURCES` maps a source id to a **`SourceAdapter`**: the two functions (`collection`,
`items`) plus the part that actually differs between museums — `enumeration`, `upstream_count`,
`resumable`, `publishes_pixel_dims`, `rights_model`, `notes`. It used to be a bare
`{collection, items}` dict, so HOW a source can be walked survived only as prose in a docstring,
where it was also *wrong*.

Every adapter MUST yield a namespaced `source_ref` (`artic:27992`): a not-held row keyed on a CDN
url cannot survive that url rotating, and the ref is what makes a re-crawl update instead of
duplicate. `limit` means **rows indexed**, never records fetched — one meaning across adapters,
and it mattered: as "ids fetched" a request for 12 Met rows silently delivered 2.

**`ENUMERATION`** is the registry of strategies, each with its constraint:
`bulk-listing` (uncapped, unfiltered) · `search-ranked` (**depth-capped** — the trap) ·
`bulk-dump` (download, filter offline, then fetch) · `per-object` (one request per row) ·
`curated-collection` (**rights are not uniform** — the LoC case).

Three properties every crawl now has, each with a test:

- **A resume cursor**, stored on the `collections` row and advanced *after* a row is consumed —
  re-walking is free (dedup turns it into a refresh), skipping loses rows silently. It is
  **within-page**, not per-page: a page-granular cursor never advances when `limit` is satisfied
  inside the first page, so repeated small harvests re-walk page 1 forever. A live smoke run
  caught exactly that (four runs of `limit=4` → four rows, no progress). `harvest(resume=False)`
  / `--restart` re-walks deliberately.
- **An upstream denominator** (`collections.upstream_count`, `Collection.coverage`). "841
  indexed" reads as complete; "841 of 62,035 (1.4%)" cannot. A source that cannot be asked
  reports **unknown**, never full.
- **A declared enumeration strategy**, so a job measured in hours says up front whether it is
  capped and whether it can resume. Surfaced on `/api/visuallib/sources`.

Shipped:

- **`artic`** — Art Institute of Chicago. Keyless, 100/request, IIIF, resumable, carries real
  pixel dimensions so the resolution floor runs at index time. **Enumerates via the bulk
  `/artworks` listing**, which has no depth cap (probed live to page 1,320 = 132k records in).
  A `--query` switches to `/artworks/search`, which is **hard-capped at 1,000 records** (403 at
  page 11) — fine for a themed slice, useless for coverage, and the report says so. The old
  docstring justified the search endpoint by claiming the listing "spent 11 of every 12 records"
  on rights refusals; that does not reproduce — measured 52.2% usable over 1,500 rows and 48.1%
  over a fresh 800, with per-page variance of 0%–99%. It bought ~1.9× and paid a ceiling.
  Denominator: **62,035** public-domain of 132,630 total, measured live (it was 61,568 three
  days earlier — which is why it is measured, not hardcoded).
- **`met`** — The Metropolitan Museum of Art. Keyless, `--dept "Photographs"` or an id (see
  `MET_DEPARTMENTS`), resumable by offset. **Enumerates via the bulk CSV** (`nolan images dump
  met` → 318 MB, 54 columns, 484,956 rows, parses in 3.5s). `Is Public Domain` is a column, so
  the rights filter runs **offline**: 248,472 rows (51.2%) are public domain, and the
  per-department denominator is exact (European Paintings = 2,327 PD) — a rights-filtered
  department slice the live listing cannot produce at all.

  **PHASE A READS THE CSV AND SPENDS NOTHING** (`met_csv_items`). The dump carries every field
  the catalog indexes — title 90.1%, creator 43.1%, date 96.2%, medium 99.5%, classification
  86.9%, department 100%, culture 58.1%, place 18.4%, object QID 18.7% — and the per-object
  request buys exactly one more: `primaryImage`. Phase A does not fetch pixels, so it was
  spending 248,472 requests on a url it would discard. Measured end to end: **2.5 h and zero
  requests**, against 7.6 h 8-wide and 11.4 h serially. The identity row is byte-identical.

  The trade, stated rather than buried: those rows carry `thumb_url = NULL`, so
  `ImageLibrary._resolve_missing_thumb_urls` pays the per-object request in **Phase B**, 8-wide,
  via the adapter's `resolve_image_urls` hook — for rows something has decided are worth 470 ms
  of pixel work, where it is ~11% on top rather than the whole cost. A ref the Met has no image
  for stays NULL: a real answer, so it costs one request ever, not one per backfill run. Both
  paths index the identically PD-filtered sequence, so **one cursor works across both** and a
  Phase A crawl can be continued by a pixels crawl.

  A `--query` still uses the API (the CSV has no relevance ranking). Free identity extras on the
  PD subset: tags QID 56%, **artist QID 35%**, object QID 19%. Publishes physical measurements
  rather than pixel dimensions, so the resolution floor lands at promotion (`check_file` on real
  bytes) instead of at index time.

- **`cleveland`** — Cleveland Museum of Art. Keyless, `skip`/`limit`, resumable, and the
  best-shaped of the three: a **server-side `cc0=1` filter AND full depth** (artic makes you
  choose between them), plus published pixel dimensions per derivative so the resolution floor
  runs at index time. Three fixed derivatives — `web` (~750px, thumbnailed), `print` (~2850px,
  promoted), and a multi-megabyte full TIFF deliberately ignored. Denominator probed live:
  **42,255 CC0 of 68,770**. Its listing order is not perfectly stable, so a skip-cursor
  occasionally re-sees an indexed row (1 of 4 on a resumed run) — dedup makes that a refresh,
  which is exactly why the cursor may re-walk but never skip.

## Adding a source — the seven questions

You give a URL and a sentence; this protocol answers the rest. **Probe before writing the
adapter, and write the findings down** — every one of these has a consequence that is expensive
to discover later, and the artic ceiling is what happens when the answers live in a docstring
nobody re-measured.

1. **Enumeration** — bulk listing, bulk dump, or per-object? *Is it depth-capped?* Probe a deep
   page explicitly; artic's search 403s at page 11 and that cost us 98.6% of a collection.
2. **Rights** — a per-item flag, or must rights be asserted per curated collection? Is there a
   server-side filter? Get the **denominator** while you are here.
3. **Stable id** → the `source_ref` namespace (`cleveland:94979`).
4. **Thumbnail + full-image URL** derivation — IIIF, or fixed derivatives?
5. **Pixel dimensions published?** Decides whether the resolution floor runs at index time or
   waits for promotion.
6. **Auth + rate limits** — keyless, or a key in config?
7. **Free identity extras** — Wikidata QID, ULAN, artist bios. The Met's QID is why that column
   exists; its `Artist Wikidata URL` at 35% is why the artist tier is cheap.

Then declare the answers in the `SourceAdapter` (`enumeration`, `upstream_count`, `resumable`,
`publishes_pixel_dims`, `rights_model`, `notes`) so they cannot rot back into prose.

Wanted next: **Library of Congress** — probed and deliberately NOT shipped yet. Its collection
endpoint returns only a 150px thumbnail and no rights per row; the richer per-item JSON is a
second request; and `/photos/?fa=partof:…` was flaky under a plain crawl. The real design
constraint: LoC is NOT uniformly public domain, yet `asset_gate.OPEN_ACCESS_SOURCES` already
trusts `loc` wholesale — so a LoC adapter must assert rights per CURATED COLLECTION
(`fsa-owi-black-and-white-negatives`, 171,074 items, no known restrictions) rather than
free-text-searching the whole institution. Write that table before writing the adapter.

## The four knowledge sources (and what the VLM may NOT be asked)

The organising rule: **a vision call may only produce what is in the pixels and nowhere else.**
Everything else has a cheaper, more authoritative source — and asking a model for it is not just
wasteful, it is the hallucination surface.

| source | cost | gives |
|---|---|---|
| **catalog record** | free with the crawl | title, creator, date, `medium`, `place`, `classification`, `department`, `culture`, QID, rights |
| **collection** | free, once | description, rights, era, topics — inherited down |
| **artist** (`imagelib/artists.py`) | one LLM call **per person**, cached | movement, period, style, typical subjects, palette words |
| **deterministic CV** (`nolan/pixels.py`) | free, no model | every NUMBER: content box, dead margin, aspect, shape, edge contact, luminance, contrast, saturation, quiet cells |
| **VLM caption** | one call per row, on demand | what is actually DEPICTED — and nothing else |

**Never ask the VLM for:** title/artist/date/medium/dimensions/institution (catalog) · movement/
style/period/school (artist knowledge) · rights/license (collection, sticky) · culture/geographic
origin (catalog) · **any number** (CV) · **any policy** like "is this usable as a backdrop"
(computed at read time — baking a policy into a caption means changing your mind costs a
re-caption over 60k rows).

**Artist knowledge is the cheapest win on the list** (`nolan images artists`). Movement and style
are facts about a PERSON, so asking a vision model per artwork pays N times for one answer.
Measured on the live corpus: 462 distinct creators over 1,005 attributed rows, and the **top 50
cover 48% of them — 20.1x**. Monet has 33 works and needs one call. Enrichment is ordered by
`creator_histogram` (commonest first) so a bounded budget covers the most rows, bounded by CALLS
not rows, and it never pays twice — including for a **miss**, since "not recognised" is a real
cacheable answer and re-asking is how a budget gets eaten by the same forty obscure names.
Nulls stay NULL (a model writing "unknown" into the column destroys the distinction between
"we asked and it didn't know" and "it knows this is unknown"), and none of it may touch
`identity_source` — an artist's movement is context about the maker, not a claim about which
artwork this is.

**`artist_key` folds on the same WORDS in any order, and never on a shared word.** Institutions
order names differently — "Auguste Louis Lepère" (Cleveland) and "Louis Auguste Lepère" (artic)
are one man, as are "Baiitsu Yamamoto" and "Yamamoto Baiitsu" — so the key sorts its tokens.
Measured: 19 groups covering 2,073 rows, every one a genuine duplicate. Surname matching was
measured too and **rejected**: it merged Hiroshige with **Hiroshige II and III** (father, son,
grandson), James McNeill Whistler with **Beatrix Godwin Whistler** (his wife), Ancient Roman with
Ancient Greek, and 134 distinct people under "Charles". Attributing one artist's movement and
palette to another's works is far worse than paying twice. `rekey_artists()` migrates the table
after any change to the rule, merging collisions in favour of the entry that actually knows
something. The residue is named: "Francisco José de Goya y Lucientes" and "Francisco de Goya"
have different word sets and stay separate — folding those needs entity knowledge, not string
rules (see the Wikidata deferral).

`image_kind` is **derived**, not asked: `taxonomy.image_kind()` buckets the institution's own
`classification`/`medium` into a closed vocabulary (painting, print, drawing, photograph,
sculpture, textile, ceramic, metalwork, coin, glass, furniture, book, map, object, unknown). The
VLM was measured against this and lost on every row where they disagreed. Fallthrough is
MEASURED, not assumed: **0.4% unknown** on artic's 119-value vocabulary and **2.6%** on the Met's
961-value one (248,472 rows). `nolan images rederive` recomputes it from columns already on disk —
one SQL pass, no network, no model — which is what makes the vocabulary safe to correct.

## Facets — filters change the DENOMINATOR

`catalog.list(**facets)`, `catalog.facets(field, **filters)`, `search_discovery(**facets)`,
`nolan images facets`, `/api/visuallib/facets`.

The catalog columns (`medium`, `classification`, `department`, `culture`, `place`, `image_kind`)
were populated across 97k rows and **nothing could filter on any of them** — an authored field
with no consumer, WIRING_CHECKLIST pitfall #1, in the tier's own store. This is the missing half.

Why it matters more than convenience: every other retrieval improvement is a **ranking** play —
97,625 rows, make the right one first. A filter changes the **denominator**. `creator=Hokusai AND
image_kind=print` is 481 rows, and a title search over 481 is not the same task as over 97,625.
It is also how professional image libraries actually work (facets + keyword, not embeddings),
because users usually know roughly what they want.

Measured coverage, which decides what is a usable facet: **`image_kind` 100% / 14 values** and
**`department` 100% / 30** are dropdowns; `classification` (100%, 555) and `place` (58%, 886) are
type-ahead; `creator` (70%, 8,604 folded) is search-then-filter PLUS the artist strip below;
`culture` (42%) and `movement` (31% once denormalised) are optional narrowing, never primary
navigation.

- **Exact** match on catalog vocabularies (`image_kind`, `classification`, `department`,
  `culture`, `artist_key`, `movement`); **contains** on long-tailed text (`creator`, `place`,
  `medium`, `title`).
- **An unknown filter key RAISES.** A silently-dropped filter returns a plausible wrong answer.
- **Counts come from the same `_filter_sql` as the results**, so a facet can never promise rows
  the search will not deliver. A facet never narrows by itself, or every count would be its total.
- **`year_from`/`year_to`** are parsed from `date_text` by `imagelib/dates.py` — 99% populated,
  0% filterable as prose (14,069 distinct strings). Parser characterised over every real string:
  **94.8% parsed, 4.8% correctly None** ("n.d." is a real answer), ~0.15% refused. Date filters
  **OVERLAP** rather than contain — an object dated 1830-1833 belongs in a search for 1831, and
  containment would drop every imprecisely-dated row, which is most of a museum corpus. Undated
  rows are excluded: "we don't know when" cannot answer "before 1850".
- Filters are resolved to an **id set once** and intersected with all three channels — the vector
  stores cannot join against SQLite, and a per-channel filter would drift.

### Browsing by ARTIST (`catalog.artist_facets`, `assets.artist_key`)

The corpus's most natural way in, and the one a raw `GROUP BY creator` gets wrong. Attribution is
**70% of rows / 8,604 folded artists**; the top 50 reach 23% of everything and the top 500 reach
49%, but **55% of artists have exactly one work** — so it is a top-N strip plus a contains box,
never a dropdown.

`assets.artist_key` stores `folded_artist(creator)`, derived **in `catalog.add()`** so no write
path can forget it. Two rules earned by measurement:

- **Anonymity is NULL, not an artist.** "Unknown artist" (756 rows), "Artist unknown" (442),
  "Unknown" (427) and "Unknown Maker" (126) would be four of the top six names. `_is_anonymous`
  removes the anonymity words and asks what is left: nothing or a generic job title → NULL; a
  residue that names a school → keep. That is what preserves "Unknown Florentine" and
  "Ancient Greek" (an unsigned antiquity is still attributed) while dropping the placeholders.
- **The chip's count is the click's result**, which is why it filters on `artist_key` (exact) and
  not `creator` (contains) — "Bosch" is inside "Boschaert". Display name prefers a spelling with
  **no parenthetical** over a more common one: Cleveland writes "Winslow Homer (American,
  1836-1910)" and holds more of him than artic, so plain frequency put the biography on the chip
  for three of the top twenty.

`movement` is denormalised DOWN from `artists.movement` (`backfill_movements`) because
`_filter_sql` is one shared WHERE-builder and teaching it a join would change every caller. It is
therefore STALE-ABLE, so `enrich_artists` calls the backfill on its way out and `nolan images
rederive` redoes it — a denormalised column with a stale consumer is the same bug as one with no
consumer. Joining on the folded key rather than the raw name is worth **24,946 → 30,207 rows**.
`normalise_movement` is not a `.lower()`: case merges only 5 of 106 strings, while the real mess
is "aestheticism, tonalism" (two in one cell), "early photography / topographic" (one written
three ways) and "none; primarily a documentarian" (not a movement). Take the first clause, refuse
the non-answers, and resolve casing by vote **with capitalisation winning first** — movements are
proper nouns, and lowercase "ukiyo-e" outvoted "Ukiyo-e" 14-10 on nothing but house style.

## Retrieval is ROUTED, not blended

A query that NAMES something is an identity question, answered from the catalog's own words
(`_disc_ident_coll`, BGE). A query about LOOK is answered by CLIP over the thumbnail
(`_disc_coll`). CLIP provably cannot discriminate named works (all 46 Holbein woodcuts cluster at
0.29–0.36 for any query), and the catalog cannot answer a description — so one channel DOMINATES
per query kind (~0.9), the other stays a small assist (~0.1), and the lexical title cover rides in
as a bonus (~0.4). The routing decision has its own stricter threshold (`_NAMED_MIN_COVER = 0.75`):
the lexical matcher admits a title at 0.5, which is right for "is this relevant" and too loose for
"is this an identity question".

Measured through the real search path (`scripts/eval_visuallib_recall.py` — 19 golden author
needs over an 841-row corpus, recall@1/5/10, `ArtInstituteProvider` keyword search as baseline):

| system | look | named |
|---|---|---|
| **shipped router** | **63.2 / 100.0 / 100.0** | **94.7 / 100 / 100** |
| CLIP only | 47.4 / 89.5 / 100.0 | 84.2 / 94.7 / 100 |
| identity only | 47.4 / 78.9 / 84.2 | 94.7 / 100 / 100 |
| near-equal blend + hard title prefix | 31.6 / 78.9 / 89.5 | 84.2 / 100 / 100 |
| BASELINE provider keyword search | 31.6 / 47.4 / 57.9 | 94.7 / 100 / 100 |

Read that honestly: **the tier's win is LOOK queries** (recall@5 47.4 → 100), which is the premise
— keyword search cannot answer a description. On NAMED queries the provider's own catalog search
is already excellent and we merely match it; what we add there is that the answer is local, offline
and rights-annotated. Every intermediate row above was a version of this router that we measured
and rejected; re-run the eval after any retrieval change, and beware sweeping weights outside the
real code path (doing so overstated look@1 by 10 points until the detector threshold was found).

Adding the Met (1091 rows, two institutions — the most confusable possible distractors, same period
and genre) held: **look 68.4 / 94.7 / 94.7, named 94.7 / 100 / 100**, and 18 of the 19 look needs
land at rank ≤3. The single miss is instructive rather than alarming: "towering altarpiece of a
figure rising to heaven surrounded by upturned faces" now returns *other altarpieces* (Altdorfer,
Froment, Gaddi) ahead of the El Greco — correct answers to an under-specified query, from a corpus
that just gained 250 religious paintings. Use `--collection <id>` when you need runs to stay
comparable; the unfiltered run is the honest one.

## Invariants (each has a test)

1. **The tier is OPT-IN on every read path.** `catalog.list(held=1)` is the default; the discovery
   vectors live in their own chroma collections. A not-held row has no file, so leaking one into
   the acquisition engine's library source is a FileNotFoundError traded for an unusable hit.
2. **Identity is catalog-derived, never model-asserted.** `identity_source` vs
   `description_source` are separate columns because only one may ever be a guess: a caption is a
   reading of the picture, an identity is a claim about *which* picture it is. A VLM naming an
   artwork is a hallucination that becomes a factual error on screen (the Alamy/named-work lesson).
3. **Collection rights are sticky.** `upsert_collection` overwrites only what the caller asserts
   (ported from the re-caption that silently re-labelled a Prelinger PD film as copyrighted).
4. **Coverage is honest.** `described_count` counts MODEL descriptions only — catalog prose is on
   every row, so counting it would report a 0%-captioned collection as complete.
5. **Both fetches are acquisition doors.** `add_discovery` (thumbnail) and `promote_to_held` (full
   image) are in `ASSET_GATE_DOORS`. An un-gated discovery tier is a laundering route around the
   gate `add_url` applies to held assets.
5b. **The resolution floor judges CONTENT, not the file** (`nolan/pixels.py`, `tests/test_pixels.py`).
   Museum object photography is an object on a plain sweep, so the file routinely overstates the
   asset: measured over the live corpus, 22% of rows carry ≥5% dead margin on some side and coins
   run 29–32%, which makes a 3000x1511 coin photo at 31% content a **2197x644** asset. The gate was
   admitting those as archival-grade. `add_discovery` now measures the stored thumbnail and scales
   the content share onto the catalog's declared dimensions; `asset_gate.check_file` does the same
   on real bytes. It REFUSES rather than flags, because cropping cannot create pixels. Characterised
   before wiring (checklist #10/#11): **7 of 841** discovery rows and **1 of 46** held rows newly
   refused, every content box inspected by eye, 834 still passing. Rows from a source that
   publishes no pixel dimensions (the Met — physical size only) are unaffected.
6. **`regions` is now PRODUCED** (`nolan/regions.py`, `ImageLibrary.locate_subjects`). It shipped
   as an unpopulated column, was consumer-blocked until the camera umbrella landed
   `solve_push(target=(x,y))`, then producer-blocked — and the producer had to be a DETECTOR:
   asked for a focal cell, a VLM answered middle-centre on **50 of 50** rows. Two tiers: `energy`
   (gradient mass inside the measured content box — no model, ~2 ms, the default) and `matting`
   (rembg/U2Net, accurate, ~170 MB). `focal_point()` is the seam to the solver and **returns None
   below a confidence floor** — pushing on a badly-located target is worse than pushing on the
   centre, because the move looks deliberate either way. `crop_safe()` is the first payoff: a
   16:9 `cover` on a tall portrait is how you decapitate someone.
   Characterised on 24 real rows spanning every kind — 17 located with tight boxes, 7 declined,
   every decline a genuinely full-bleed composition. **Known limitation:** on a `panel_count:
   pair` row (a coin showing both faces) the box spans both, so its centre lands in the ground
   between them; a caller holding that caption field should target one panel.

## Deliberately deferred

- **Indexing RESTRICTED rows (`is_public_domain: false`) as a rights-flagged tier.** Today all
  three adapters DROP them — `report.skipped_rights += 1; continue` — so no row and no flag
  exists. The need is real: a search for *Nighthawks* returns nothing, and "we hold no picture of
  it" is indistinguishable from "it exists, it is Hopper, it is in copyright until 2038, stop
  looking."

  **Deferred because it is the wrong SHAPE, not because the need is fake.** It is an on-demand
  question — it arises rarely, for one named thing someone just searched for — and pre-indexing
  ~70k unusable rows to have the answer waiting is the same trade this tier already rejected when
  it chose demand-driven captioning over captioning 132k items. The live answer costs ONE request
  (`is_public_domain` on a title search, ~200ms).

  The argument that settles it: **NOLAN has no licensing path.** The rights posture is
  open-access-only, so there is no workflow where you see a restricted artwork and buy it. The
  information can change what you UNDERSTAND but never what you DO, and diagnostics do not justify
  doubling a corpus. It also adds a second orthogonal "look but never use" axis on top of
  `held=0`, doubling the ways a future acquisition path can leak — the exact direction of the
  incident this gate was built after.

  **REVISIT IF A LICENSING PATH APPEARS.** That is the trigger; the reasoning above collapses the
  moment a restricted artwork becomes something you can act on. The design, so it is not
  re-derived: a real `rights_status` column (`open` / `restricted` / `unknown`) rather than
  inferring from a collection label; those rows **excluded by default from every read path**, the
  way `held=0` already is; and a SEPARATE collection, so the existing CC0 assertion stays true.
  Cost ≈ 2x rows and 2x identity embeddings (132k vs 62k for artic), plus a re-crawl to backfill.

  The cheap interim, if the confusion ever bites in practice: when a NAMED query returns nothing,
  ask the source live and report "exists, restricted" — ~30 lines, no storage, no leak surface.
- **Text / watermark / face regions.** The `subject` label is produced; the rest of
  `REGION_LABELS` is still reserved. A watermark box would be immediately spendable by
  `hyperframes/cleanup.py`, which now has a measured *matte* detector (`detect_matte`) but still
  crops logos and caption bands by heuristic + optional vision confirm.
- **Wikidata entity linking.** `wikidata_qid` is a nullable column populated only when a source
  hands it over free. Full name→QID disambiguation + SPARQL joins only pay off across several
  collections; revisit at 3+, or when key-assets' per-candidate VLM verify becomes the complaint.
- **An acquisition source adapter.** Visual Lib is discovery; the acquire engine's `search_library`
  still sees only held rows. Wiring it in means promoting on selection (the transcript library's
  clip-from-url edge), not handing the engine rows with no file.
