---
id: lab.kb
name: Knowledge base (video-craft KB)
description: >
  NOLAN's video-craft knowledge base, backed by an Obsidian vault. Markdown-first: the vault .md
  files (E:\Nolan_KB) are CANONICAL; SQLite + Chroma are DERIVED indices rebuilt from the files, so
  a human (in Obsidian) and the agent (via the retrieval API) read the same notes. Pipeline:
  ingest (url/youtube/file/text → raw/*.md) → distill (LLM → parsed insight notes) → index (BGE +
  keyword) → link (related notes + MOCs). Read before touching KB ingest/distill/index/retrieval,
  or wiring craft knowledge into authoring.
kind: methodology
purpose: >
  Orient any KB task — the markdown-is-canonical / indices-are-derived rule, the
  ingest→distill→index→link pipeline, and hybrid retrieval (BGE + keyword).
status: active
version: 1
tier: lab
handoffs: []
uses: []
documents:
  module: src/nolan/kb/__init__.py
loaded_by: []
evals: []
---

# Knowledge base — video-craft KB (`src/nolan/kb/`)

A craft KB backed by an Obsidian vault at `E:\Nolan_KB\Nolan_KB`. Both a human (in Obsidian) and
the agent (retrieval API) read the same notes.

## The canonical rule (don't invert it)

**Markdown is canonical; SQLite + Chroma are DERIVED.** The vault `.md` files are the source of
truth; the indices are rebuilt FROM them. Never treat the index as authoritative or write facts
only into the index — edit the note, re-index. This is what keeps the human's Obsidian view and the
agent's retrieval in agreement.

## The pipeline

`ingest` (url / youtube / file / text → `raw/*.md`) → `distill` (LLM → parsed insight notes) →
`index` (BGE embeddings + keyword) → `link` (related notes + MOCs). Modules: `ingest.py`,
`distill.py`, `insights_store.py`, `index.py`, `vectors.py`, `catalog.py`.

## Status + retrieval

Ingest + distill are done; hybrid search (FTS5 + BGE / RRF) is the retrieval layer; the pipeline
bridge (feeding KB craft into authoring) is deferred. HERMES-derived. See `[[project_nolan_kb]]`.
This is a LAB/reference subsystem — it informs authoring craft, it is not a spine step.
