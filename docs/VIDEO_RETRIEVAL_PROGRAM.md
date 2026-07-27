# Video retrieval program — making the library tiers safe to acquire from

**Status:** in progress (started 2026-07-27). Owner: the acquisition/library seam.
**Predecessors:** `docs/ACQUISITION_CONSOLIDATION.md` (two pools / one spine),
`skills/lab/visual-library.md` (the routed-retrieval eval this program copies).

## The problem, stated once

Wiring the transcript library into acquisition opened two doors at the same time:

1. **A very good one.** Stock APIs and web search only take keywords and only expose thin
   metadata. The library holds rich, searchable descriptions of what a video *says* and what each
   shot *shows* — material no provider will sell us and no keyword query can reach.
2. **A bad one.** A dense index is k-nearest: it returns `k` rows for *any* query, however wrong.

The program's whole job is to keep (1) and contain (2).

### What is measured, not argued

| observation | number | where |
|---|---|---|
| Tier B (keyassets → transcript lib) heroes delivered | **0** of 63 resolved files / 22 entities | audit of every `key_assets.json` on disk |
| "1975/2004 US Court Proceedings" top hit | **Watergate, 0.713** | re-run vs the 253-row library |
| "Kimberley Mine" top hit | South Dakota **gold** mine, 0.693 | same |
| genuine on-domain hit, same run | diamond machinery, 0.704 | same |
| off-domain "sushi preparation in a Tokyo restaurant" | 0.649 | segment index |
| off-domain "penguins on Antarctic sea ice" | 0.671 | segment index |
| separation on/off domain — segments | **+0.053** | 4 on / 4 off queries |
| separation on/off domain — frames | **+0.082** | same |

**Wrong answers outrank right ones across queries.** That is the finding that sets the shape of
every fix below: this is not a threshold problem, so no threshold fixes it.

### Two consequences that constrain the design

- **Every absolute floor we own has a shelf life.** For a query with no true answer, top-1
  similarity is the maximum of N draws from a background distribution, and the expected maximum
  *rises with N*. On-domain scores stay flat. `clip_lib_min_sim` 0.55, the 0.42 fit bar, the
  tail-trim — all tuned against today's corpus and all silently loosening as the library grows.
  (A per-query *relative* score does not fix this: measured, absolute separates ~3× better, and
  "penguins" scored the single highest relative confidence in the set. Dead end, closed.)
- **Growth degrades cost, not just quality.** Each off-domain candidate that clears retrieval buys
  a download, a CLIP pass, sometimes a VLM call. Even where the pixel gates hold the quality line,
  the bill scales with library size.

### The reframing that matters

Text-RAG retrieves for an LLM that can ignore bad context. **We commit**: a bad hit becomes a shot
in the video. So the target is a *decision* system with an abstain option, not a *ranking* system —
**precision@1 and abstain-rate**, not recall@10. And unlike text RAG we hold an oracle: the pixels.
The lever is not a better text retriever, it is routing an expensive pixel oracle to the right
candidates cheaply.

## The two modes (the organising idea)

Classic IR splits **topical relevance** from **known-item retrieval**. The Visual Library tier
already implements exactly this split for images (`look` vs `named`) and measured it over 19 golden
needs / 841 rows:

| system | look r@1/5/10 | named r@1/5/10 |
|---|---|---|
| **routed (shipped)** | **63.2 / 100 / 100** | **94.7 / 100 / 100** |
| CLIP (dense) only | 47.4 / 89.5 / 100 | 84.2 / 94.7 / 100 |
| identity only | 47.4 / 78.9 / 84.2 | 94.7 / 100 / 100 |
| near-equal blend | 31.6 / 78.9 / 89.5 | 84.2 / 100 / 100 |
| keyword baseline | 31.6 / 47.4 / 57.9 | **94.7 / 100 / 100** |

Plain keyword search is *already perfect* on named queries and nearly useless on look queries;
dense is the mirror image; **a near-equal blend is the worst configuration tried** — which is
precisely the 1:1 segment/frame interleave shipped in `_search_transcript_all`.

### Four need shapes on the video path

| shape | dominant signal | abstain posture | in-repo signal that identifies it |
|---|---|---|---|
| **named / identity** — "Cecil Rhodes", "Kimberley Mine" | lexical + title | aggressive — the VLM *cannot* verify identity, so retrieval must carry it | `key_assets.json` entity `kind` |
| **era-constrained topical** — "1960s congress hearing" | dense + era-as-text | moderate | need `category`, era tokens in the query |
| **evocative / metaphorical** — "a machine grinding" | dense / CLIP-on-pixels; lexical would *hurt* | rare — anything visually apt serves | need `evocative` |
| **spoken claim** — "someone saying X" | **both channels** | moderate | quote-shaped query |

The fourth row is *not* a channel-routing rule. The frame caption fuses the transcript window into
`combined_summary` at ingest (`vision.build_frame_analysis_prompt`), so the frame index already
carries said-content. The segment channel's unique contribution is therefore **coverage** (the
ingested-but-uncaptioned subset: 253 rows, 179 captioned) and **quote timing**, not semantics.
Whether segments ever win a need that frames also cover is an open empirical question — P3 answers
it. If the answer is no, segments is a coverage tier and should be labelled one.

## Rejected, with reasons (so they don't come back)

- **SPLADE.** Its value is implicit term expansion, which is the exact mechanism that produced the
  Watergate hit — expand "court proceedings" into {trial, hearing, gavel} and the wrong answer ranks
  *higher*. Worse, BM25's most valuable property here is that it can return **zero**: zero term
  overlap is evidence of absence, the abstain signal we lack. SPLADE never returns zero by
  construction. It also optimises recall; we do not have a recall problem.
- **ColBERT / late interaction.** Its advantage grows with document length; our documents are ~5s
  ASR chunks and one-sentence captions — there is nothing for a single vector to blur. Its other
  advantage is quality-at-scale-under-latency; we have 253 videos and an offline batch. Its one
  genuine benefit (token-level survival of rare entity terms) is ~80% recoverable from FTS5 at ~1%
  of the cost, *with* the abstain signal ColBERT does not give.
- **Per-query relative scoring.** Measured and killed (see above).
- **An authored `need.kind` field.** The signal already exists (`kind` / `evocative` / `category`),
  a wrong classification is catastrophic while a weak generated query degrades gracefully, and
  adding it before a consumer exists is WIRING_CHECKLIST pitfall 1 (phantom field).

## The plan

Ordering rule: **anything that changes the candidate pool must land before the judging pass**
(labels are the expensive resource and we buy them once). Anything that only re-orders an existing
pool is measured against those same labels for free.

### P0 — eval hardening *(no new labels)*
Negative controls become a permanent fixture: known-absent needs (sushi, penguins, +2) carried in
the goldens so every future run reports **abstain rate** on them. Metric set becomes
`precision@1 · success@k · abstain@negatives`. **Done when:** `score` prints all three and the
negative goldens are in `goldens.json`.

### P1 — the lexical channel (FTS5 + BM25 + the abstain signal)
A dedicated rebuildable sidecar index (`transcript_fts.db`) over BOTH tiers with one schema:
segment rows (transcript · combined_summary · frame_description · inferred_context) and frame-caption
rows, each carrying the **video title** (the named-mode signal the dense indexes never see).
Precedents to copy: `kb/insights_store.py` (`_match_expr`, bm25 join), `sound/catalog.py`.
API returns bm25-ranked rows **and** an explicit zero-overlap verdict. Fused with dense by
`_fuse_by_rank` (RRF — already in `transcript_lib`), never concatenated.
**Done when:** an entity query returns its documentary; an off-domain query returns `[]` rather
than k rows; index coverage is reported honestly; tests enforce all three.

### P2 — shot-grid units
`_shot_window` (keyframe → next keyframe, from `detect_cuts`→`plan_shots`) is promoted out of
`acquire/context.py` into shared code and applied to **segment** hits too. Both channels then emit
the same unit — `(video_id, shot_start, shot_dur)` — which becomes the join key. Cross-tier dedup
stops being an overlap heuristic, RRF fuses on a real key, and the arbitrary `max(6.0, …)` range in
Tier B goes away. Read-time snap; no re-index.
**Done when:** a segment hit inside a known shot snaps to that shot's boundaries, and two channels
hitting one shot fuse to one candidate (test).

### P3 — extend the pool, then judge once
Add the lexical and fused arms to `CHANNELS`, re-extract (the pool grows), then judge with a
**pixel-based VLM judge**: a still extracted at each candidate's timestamp *by the same method for
both channels*, caption **withheld**, one shot at a time (position bias). The circularity this
avoids is specific: the frame channel retrieves by BGE-over-gemma-caption, so a caption-reading
judge would score that channel with its own scoring function. A **25-row human calibration sample**
follows; judge-human agreement is reported with the results. Named-slice numbers are labelled
**provisional** — a VLM can read era from a still but cannot assert *"this is the Kimberley mine"*
(identity is catalog-derived, never model-asserted).
**Done when:** all arms scored on shared labels, with the agreement number stated.

### P4 — the pairwise rerank / abstain rung
The cascade today is `weak retrieval → expensive download → CLIP-on-pixels → VLM`. There is no
cheap rung between retrieval and download, which is why growth degrades the bill. Insert a pairwise
relevance judgement over the pooled top-N (title · caption · transcript), returning a graded score
**and an abstain**. LLM-rerank first — we already run one on the library-growth path, it is off-box,
and a local cross-encoder would add contention to a GPU lock already shared by ComfyUI and
OmniVoice; swap in `bge-reranker` only if volume makes the API cost bite.
**Why this specifically:** a bi-encoder top-1 is a max-of-N statistic and therefore drifts with
corpus size; a pairwise score is per-pair and **does not**. This is the answer to "every threshold
expires" that relative scoring failed to be.
**Done when:** measured on P3's labels — precision@1 lift and downloads-avoided, both reported.

### P5 — route, don't blend (+ the project-topic prior)
Replace the 1:1 interleave with the four-mode routing above, weights taken from the eval rather
than from taste. Two query forms are *generated* per need (an identity string and a look string)
rather than one being classified — a weak generated query degrades gracefully, a wrong label flips
the whole need to the wrong channel. Abstain (P4) is what makes hard routing safe: a misroute
becomes "found nothing" instead of "wrong shot".
**The project-topic prior** (`topic_cluster` over the persisted `title_vectors.npz` — free): boost
segments whose **parent video** is topically near the project brief. A **prior, never a gate** —
good b-roll is frequently off-topic by design (a chess game for "strategy"), and a hard topical
scope would prune exactly the evocative hits that currently work. Same shape as the title bonus
already in the shipped image router.
**Done when:** routed beats blend on the eval, per mode, and the prior is shown not to hurt the
evocative slice.

### P6 — Tier B rework (keyassets)
Today a miss is expensive (download + VLM video call per candidate, on the hardest entities) and
confidently wrong. Rework to **identity-anchored retrieval with a cheap honest miss**: match the
entity against video titles and the lexical index; when nothing matches, return nothing immediately
at zero cost. The strict VLM gate stays — it is the only part that has been working.
**Done when:** an entity with no library match resolves with **zero downloads**, and the tier
reports what it skipped (no silent caps).

### P7 — index enrichment: on-screen text
`transcript_frames.py:625` claims the caption captures "OCR/entities". It does not:
`build_frame_analysis_prompt` asks for people, location, objects, story, `asset_type` and `shot` —
**never on-screen text**. Archival footage is full of burned-in names, chyrons, title cards and
signage: identity evidence, in the pixels, currently discarded (we even already locate chyrons in
`clean_media_inplace`). Adding it improves the dense channel, the lexical channel and the named mode
at once. Deliberately **after P3**, because a re-caption pass shifts every absolute number; the
eval is re-scored after.

### P8 — PARKED for discussion: the Visual Library as an acquisition source
Wiring Visual Lib into keyassets + acquire will hit the same k-nearest disease, but with real
nuances that deserve their own design pass rather than a copy of this one:
- identity is **stronger** there — catalog title/creator/date are authoritative, not model-asserted;
- the **era filter that died here may live there** (archive.org `year` is 8% populated; museum
  `date_text` is not);
- a cheap pixel gate already exists **pre-promotion** (the harvested 512px thumbnail), so the
  expensive rung sits in a different place in the cascade;
- `held=0` means the failure mode is a wasted *promotion*, not a wasted download;
- known false-fire: `banner_suspect` on museum object photography.
Open after P6.

## Invariants this program must not break

- **No silent caps** — every bound reports what it dropped (the tail-trim, the rerank, the prior).
- **Identity is catalog-derived, never model-asserted.**
- **Proposals behind deterministic gates** — an LLM rerank is a proposal; the pixel gates decide.
- **Docs claim, tests enforce** — each phase lands with the honesty test that makes its claim real.
