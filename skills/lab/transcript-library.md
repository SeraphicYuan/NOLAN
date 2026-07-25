---
id: lab.transcript-library
name: Transcript library (discovery tier + topic search)
description: >
  The library of what other people's videos SAY and SHOW — YouTube channels and archive.org
  collections surveyed and transcript-indexed cheaply (no download), then visually captioned per
  keyframe by the VLM, so a topic search can answer "which video, and roughly when". Covers the
  survey → curate → ingest → caption loop, the THREE-TIER on-demand topic search (ingested /
  surveyed / global archive.org) with its persisted title-vector index, the LLM re-rank and its
  memory, and the broadening organ that proposes subjects the library lacks. Read before touching
  transcript_lib / transcript_vectors / transcript_memory / transcript_broaden / archive_source, the
  /transcripts page, or anything that grows the footage library by topic.
kind: methodology
purpose: >
  Orient any transcript-library task — what each sidecar owns, why the ranking is recomputed while
  the LLM's output is remembered, and the invariants (provenance is sticky, unknown duration is kept,
  no silent caps).
status: active
version: 1
tier: lab
handoffs: []
uses: []
documents:
  module: src/nolan/transcript_lib.py
loaded_by: []
evals: []
---

# Transcript library — the discovery tier (`src/nolan/transcript_*.py`)

A cheap, searchable index of OTHER people's videos: channel/collection surveys (titles only, no
download) → transcript ingest → per-keyframe VLM captions. It answers *which video, and roughly
when*, and feeds the acquire engine real footage with honest copyright provenance.

## The modules

| module | owns |
|---|---|
| `transcript_lib.py` | surveys, ingest, catalog sidecar, search, the 3-tier topic search, clustering |
| `transcript_vectors.py` | the PERSISTED BGE title-vector index over the surveyed corpus |
| `transcript_memory.py` | what the LLM decided (expansions, judgements) + what the human accepted |
| `transcript_broaden.py` | "X more videos, on subjects I don't have" — LLM topics → picks |
| `transcript_frames.py` | the visual tier: keyframes, VLM captions, CLIP visual search |
| `archive_source.py` | archive.org adapter — collection survey AND the global search |

## The three tiers of a topic search

1. **ingested-but-uncaptioned** — vector search over transcript SEGMENTS → action `caption`.
2. **surveyed-but-not-ingested** — BGE over the persisted title index → `ingest+caption`.
3. **global archive.org** — `archive_source.search_items`, for subjects the added sources don't
   cover at all → `ingest+caption`.

Their scores are on different scales (segment cosine vs title cosine), so they are fused by RANK
(`_fuse_by_rank`, RRF) — never concatenated. `_rrf_fuse` in the same module exists for the same
reason on the said/shown blend.

## Invariants (each one is incident-derived)

- **Provenance is sticky.** `record_transcript`'s `kind` / `copyright_free` / `broll` / `duration`
  are only overwritten when a caller ASSERTS them; a re-caption knows nothing about the source
  family and used to re-label a PD Prelinger film as copyrighted YouTube.
- **Unknown duration is KEPT** by the optional length filter — but when a filter is active, an
  archive row's missing runtime is RESOLVED from the metadata API (bounded), or the filter silently
  does nothing (a 4-minute reel rode that rule into a caption run).
- **No silent caps.** Every bound reports what it dropped: the embed budget in the cold-index
  fallback, the archive deep-paging window (Prelinger: 10,000 of 10,376), the length gate, the
  duplicate collapse, the re-rank drops.
- **archive.org metadata is MULTI-VALUED** — `description`/`title` can be lists. Coerce with
  `archive_source._as_text` before anything treats them as strings.
- **The ranking is recomputed; the LLM's output is remembered.** Measured: 77% of a search's 33s is
  two LLM calls; the 60k-title vector scan is 0.024s. Caching a RANKING would go stale the moment a
  survey or ingest lands and silently hide new material — so `transcript_memory` persists the
  expansion and the per-(topic, video) judgements instead, scoped to the same subject AND model.

## The persisted sidecars (`projects/_library/transcripts/`)

`catalog.json` (display + provenance) · `sources.json` · `surveys.json` (the crawls) ·
`title_vectors.npz` (60k titles, fp16) · `topic_queries.json` · `topic_judgements.json` ·
`topic_vectors.npz` · `picks_accepted.json` (ground truth) · `topics_used.json`.

Rebuild the title index with `POST /api/transcripts/topic-index/build` or
`transcript_vectors.build()`; it is incremental (each row carries a signature of its embed text).

## Growing the library

- **By topic** (you know the subject): /transcripts → Topic tab → review → *Caption / ingest
  selected*. Acceptance is recorded — that ledger is the only ground truth for tuning the 0.42
  floor, the fit bar and the re-rank prompt.
- **By breadth** (you don't): the same tab's *🌱 Broaden the library* → `transcript_broaden` — an
  LLM proposes subjects the library lacks (shown a DIVERSE sample of what it holds plus every topic
  already searched), one pick per subject first, depth only when subjects run out.

Both LLM steps are PROPOSALS behind deterministic gates: a proposed topic that repeats a searched
one is dropped by cosine before it can spend a search; picks are reviewed before anything ingests.
