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
- **Unknown duration is KEPT** by the optional length filter — so the filter needs a duration to
  bite (a 4-minute reel rode that rule into a caption run). WHERE it gets one is per source family
  (`_len_on`): youtube/youtube_cc rows carry a duration 100% of the time, archive rows **14.0%**
  (measured: 1,403 of 10,000 Prelinger items — advancedsearch asks for `runtime`, archive.org just
  hasn't got one). Resolving the rest is an HTTP round-trip each against a server that throttles per
  client, so a caller passing `length_kinds=("youtube","youtube_cc")` gets a fully OFFLINE tier-2
  scan and the rule is enforced at CAPTION time instead (`operations.LengthSkip`), on the exact
  runtime the download already produced — fed back via `remember_duration` so it is never asked for
  twice. `length_kinds=None` keeps the filter-everything behaviour for an interactive search.
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

## A SOURCE is only what someone added; a CHANNEL is a property of the videos

Two different things that used to share the Sources card, to everyone's confusion:

- **Sources** = `sources.json` rows. What you chose to draw from; the card's actions are built for
  them (Sync all iterates `load_sources()`; Curate surveys the whole collection).
- **Channels** = every distinct `catalog.json` `channel` value. Most were never added, and the
  Sources card's actions never applied to them. They belong to the VIDEOS, so they are surfaced as
  the Indexed-videos filter (`channel_facets`), not as fake source tiles.

`sources_view()` still returns BOTH, tagged with `origin` (`managed` / `search` / `unregistered`);
the route splits it — `sources` are the managed rows, and the rest collapses to an `unregistered`
`{channels, videos, search}` summary line so the tab can't understate what is indexed.

`origin: "search"` is the bulk of them and the one that provokes "I never added this":
`archive_source.fetch_transcript` has no collection to attribute a global-tier hit to, so it takes
`metadata.collection[0]`, and archive.org's first collection is frequently an aggregator or inbox —
`television_inbox`, `altcensored`, `mirrortube`, `fringe`, `vhsvault_inbox`. `origin:
"unregistered"` is a youtube channel with videos but no source row (a crawl whose source was
removed; or single-video ingests, where the value is yt-dlp's uploader NAME).

A channel's `kind` comes from its videos' catalog `kind`, never guessed from the string — else
`FedFlix` and `PeriscopeFilm`, both archive collections, would read as YouTube channels.

**Links.** `source_url()` → `(url, exact)`: the collection page or the channel page. `exact=False`
means a bare uploader name with no resolvable channel URL, so the link degrades to a YouTube search
rather than a guessed `/c/` 404. `exact` also gates `channel_facets`' `promotable`: registering an
uploader name would create a source `list_channel` could never crawl, so `POST
/api/transcripts/register-source` rejects it rather than making a dead source.

**Removing.** `remove_source` only UNREGISTERS — the videos stay, so the channel just demotes to
`unregistered` and lives on in the video list. `purge_source(index, channel)` deletes the channel's
videos everywhere (DB + vectors + frames + catalog) then the source row; that is the only thing
that removes a channel from the library. `DELETE /api/transcripts/sources?purge=true`. It reports
`deleted` vs `errors` per video and leaves a failed row in the catalog rather than swallowing it.

Known gap: ~60 stock-channel videos carry `channel: null` and so appear under no channel facet —
the filter's counts sum to less than the library total until the ingest backfills a channel.

## Growing the library

- **By topic** (you know the subject): /transcripts → Topic tab → review → *Caption / ingest
  selected*. Acceptance is recorded — that ledger is the only ground truth for tuning the 0.42
  floor, the fit bar and the re-rank prompt.
- **By breadth** (you don't): the same tab's *🌱 Broaden the library* → `transcript_broaden` — X
  picks across as many subjects as possible: one per topic first, depth only when subjects run out.
  Where the topics come from is the `topic_source` switch:
  - `corpus` (DEFAULT) — `corpus_topics` clusters the SURVEYED corpus off the persisted
    `title_vectors.npz` (`topic_cluster(..., vecs=)`, so no embedding), subtracts the clusters the
    captioned catalog already represents, and searches what's left. Every topic is servable by
    construction, and no expansion is needed (a cluster's medoid title already embeds against the
    title index). Clustered PER SOURCE FAMILY and interleaved under a per-family cap — one Bloomberg
    feed is 81% of the corpus, so a single global clustering returns nothing but finance clips.
    Clusters that are catalogue-number runs rather than subjects are dropped by `_topic_worthy` and
    the count is reported.
  - `llm` — `propose_topics`, the open-ended proposer. Honest tension to know about: it asks for
    subjects the library LACKS, then searches what the library HAS, so with tier 3 off a proposed
    topic can legitimately return nothing.
  Depth picks are diversified by MMR (`_mmr_order`) against this run's picks AND the captioned
  library — `_MMR_LAMBDA = 0.5` because that is where a perfectly redundant candidate can never
  outrank a novel one at ANY pool size; higher and the answer depends on pool depth.
  `expand_topics_batch` expands a whole plan in ONE call, prewarming the same `topic_queries.json`
  cache the per-topic path reads (no second code path).

Both LLM steps are PROPOSALS behind deterministic gates: a proposed topic that repeats a searched
one is dropped by cosine before it can spend a search; picks are reviewed before anything ingests.
