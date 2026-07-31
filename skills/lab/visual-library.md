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
  132k items is not a plan; caption what retrieval or a human surfaced. The collection blurb is
  passed as context (the same trick that makes video-frame captions entity-aware by feeding them
  the transcript window).

Knowledge inherits DOWNWARD: an item with no caption still carries its collection's rights, era
and topic, and that inherited context is what makes a T1 row retrievable at all.

## The loop

```
nolan images harvest artic --limit 600 [--query "..."]   # T0 + T1, idempotent by source_ref
nolan images discover "a rainy Paris boulevard"          # routed search over the not-held tier
nolan images fetch <id>                                  # promotion: bytes + gate -> held=1
nolan images collections                                 # coverage per collection
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
- **Collections** — harvest form (source + optional Met department/theme + limit) and the
  harvested table with per-collection coverage. Long by nature, so it is a background job with
  progress, never a request.
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

## Adapters

`harvest.SOURCES` maps a source id to `{collection, items}`. Add a museum by adding one adapter —
the gate, thumbnails, identity columns and dedup are shared. Every adapter MUST yield a namespaced
`source_ref` (`artic:27992`): a not-held row keyed on a CDN url cannot survive that url rotating,
and the ref is what makes a re-crawl update instead of duplicate. `limit` means **rows indexed**,
never records fetched — one meaning across adapters, and it mattered: as "ids fetched" a request
for 12 Met rows silently delivered 2. `tests/test_visuallib.py` enforces the ref, a rights
assertion, and the `limit` contract on every registered adapter.

Shipped:

- **`artic`** — Art Institute of Chicago. Keyless, paginated 100/request, IIIF, server-side
  `is_public_domain` filter (measured: the unfiltered listing spent 11 of every 12 records on
  items we must refuse on rights). Carries real pixel dimensions, so the gate's resolution floor
  runs at index time. Cheapest adapter per row.
- **`met`** — The Metropolitan Museum of Art. Keyless, `--dept "Photographs"` or an id (see
  `MET_DEPARTMENTS`), `--query` for a themed slice. **Hands over `wikidata_qid` for free** — 8 of
  8 rows on a European Paintings probe — which is the entire justification for that column.
  Costs ONE REQUEST PER OBJECT: the listing returns ids only, and the search endpoint cannot
  substitute (probed live, `departmentId` + `isPublicDomain` + `hasImages` returns 0 results for
  whole departments — dept 19 → 0 for every query form, dept 11 → 22). Two consequences worth
  knowing before a big harvest: departments vary hugely in image coverage (European Paintings
  ~8/8, Photographs ~2/12, so the same `limit` costs 4× the requests there), and the Met
  publishes physical measurements rather than pixel dimensions, so the resolution floor lands at
  promotion (`check_file` on real bytes) instead of at index time.

Wanted next: **Library of Congress** — probed and deliberately NOT shipped yet. Its collection
endpoint returns only a 150px thumbnail and no rights per row; the richer per-item JSON is a
second request; and `/photos/?fa=partof:…` was flaky under a plain crawl. The real design
constraint: LoC is NOT uniformly public domain, yet `asset_gate.OPEN_ACCESS_SOURCES` already
trusts `loc` wholesale — so a LoC adapter must assert rights per CURATED COLLECTION
(`fsa-owi-black-and-white-negatives`, 171,074 items, no known restrictions) rather than
free-text-searching the whole institution. Write that table before writing the adapter.

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
6. **`regions` is a column and nothing writes it.** The labelled subject/face/text/watermark boxes
   are reserved and deliberately unpopulated — the column ships only because adding one to a
   populated table is the expensive part. When it shipped, the HF path had no focal point at all.
   That changed the same day: the camera umbrella (`src/nolan/camera`) landed `solve_push(target=
   (x, y))`, framed so the target stays put. **The consumer now exists; the missing half is the
   PRODUCER** — a pass that turns a picture into labelled boxes (VLM *names* the regions, a
   detector/rembg *localizes* them; never raw coordinates from prose). The test's sentinel watches
   that solver's `target` parameter, not a CSS string.

## Deliberately deferred

- **The location/region pass** — now PRODUCER-blocked, not consumer-blocked (see invariant 6).
  What remains is the region schema (`{label, kind, box, conf}`), the pass that fills it, and the
  seam from a stored region to `camera.solve`'s `target`. The first payoff is crop safety
  (`cover` decapitates a portrait in a 16:9 frame), not the zoom — and a watermark/text box is
  immediately spendable by `hyperframes/cleanup.py`, which crops those today by vision guess.
- **Wikidata entity linking.** `wikidata_qid` is a nullable column populated only when a source
  hands it over free. Full name→QID disambiguation + SPARQL joins only pay off across several
  collections; revisit at 3+, or when key-assets' per-candidate VLM verify becomes the complaint.
- **An acquisition source adapter.** Visual Lib is discovery; the acquire engine's `search_library`
  still sees only held rows. Wiring it in means promoting on selection (the transcript library's
  clip-from-url edge), not handing the engine rows with no file.
