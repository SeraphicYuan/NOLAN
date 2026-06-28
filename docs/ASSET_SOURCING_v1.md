# Asset Sourcing — v1 (Tracks 1 + 3)

Date: 2026-06-16. Addresses bottleneck #1 (asset sourcing) — see
[NOLAN_BOTTLENECKS_v1.md](NOLAN_BOTTLENECKS_v1.md). Scope chosen: **video/archival sourcing**
+ **ComfyUI generation**; AI video gen deferred.

## What changed

### Track 1 — video + more sources
- **`ImageSearchResult` now carries `media_type` ("image"|"video"), `duration`, `preview_image_url`** — the whole search layer is image/video aware (was image-only).
- **Internet Archive provider (keyless)** — `archive` searches archive.org movies and resolves a
  downloadable mp4 + duration per item. Best fit for historical/archival documentary footage.
  Verified: "world war 1 trenches" → real WWI/WWII archival video.
- **Pexels + Pixabay VIDEO providers** (`pexels_video`, `pixabay_video`) — hit their video endpoints.
  Ready once `PEXELS_API_KEY`/`PIXABAY_API_KEY` are set (currently unset → unavailable).
- **`ImageSearchClient.search_assets(query, media_type, sources)`** — multi-source, media-aware search;
  `video_providers()` lists available video sources.
- **`match_broll_v2`** (webUI `kind="broll-video"`): per b-roll scene → **query-variant fallback**
  (original → drop years/proper-nouns → generic phrase), **video-first across all variants then image
  fallback**, vision-score candidates (poster for video), reject score<4. Images are downloaded;
  **videos are attached by reference** (URL+source+license+duration in `matched_clip`) — full archival
  programs are not downloaded; fetch+trim to scene duration is a render-time follow-up.

### Track 3 — ComfyUI generation
- **`generate_assets`** (webUI `/api/generate`): runs the existing ComfyUI generation for every
  `generated` scene; clear "ComfyUI not reachable" error if it's not running.
- Studio "Review & match assets" stage now has: **Match b-roll (video+archival)**, **Match library
  clips**, **Generate (ComfyUI)**, and an images-only fallback.

## Honest results (measured)
- **Coverage where wikimedia gave 0/122:** the fallback chain now finds assets. On a modern/abstract
  6-scene subset → 3/6 (image fallback); the video path attaches archival clips on historical queries.
- **Quality is capped by sources + scoring:** Internet Archive is historical-film-skewed (great for
  WWI/WWII/news, weak for "favela kids soccer"); poster-based scoring sometimes rejects good hits
  (IA thumbnail fetch fails → score 0) or scores an ambiguous poster too high (a "Tsunami" clip matched
  "bombing city"). Clean modern b-roll needs Pexels/Pixabay **video** keys (not yet set).

## Provider roster (expanded)

**Keyless, available now (11):** `ddgs`, `wikimedia`, `loc`, `nasa` (PD images), `nasa_video`
(PD video), `openverse` (CC aggregator: Flickr+museums), `met` (CC0), `artic` (CC0), `cleveland`
(CC0), `wellcome` (CC/PD history & medicine, IIIF), `archive` (archival video). Verified
returning real results.

**Key-needed (built, gated on key — set in .env to enable):**
| Provider | env var | media | where to get a (free) key |
|---|---|---|---|
| Europeana | `EUROPEANA_API_KEY` | image+video | pro.europeana.eu/pages/get-api |
| DPLA | `DPLA_API_KEY` | image | pro.dp.la/developers |
| Flickr | `FLICKR_API_KEY` | image (CC) | flickr.com/services/apps/create |
| Unsplash | `UNSPLASH_ACCESS_KEY` | image | unsplash.com/developers |
| Rijksmuseum | `RIJKSMUSEUM_API_KEY` | image | data.rijksmuseum.nl |
| Harvard Art | `HARVARD_ART_API_KEY` | image | harvardartmuseums.org/collections/api |
| Coverr | `COVERR_API_KEY` | video | coverr.co |
| Pexels | `PEXELS_API_KEY` | image+video | pexels.com/api |
| Pixabay | `PIXABAY_API_KEY` | image+video | pixabay.com/api/docs |

Deferred (uncertain/complex API): NARA (now key-gated), Vimeo (OAuth), Videvo (partner API). Each
is a small follow-up if wanted.

## Render-time fetch + trim (done)
- **`materialize_clips`** (webUI `/api/materialize-clips`, Studio "Fetch & trim matched clips"):
  for every scene whose `matched_clip` is a video (external archival URL **or** local library clip)
  and lacks a `rendered_clip`, ffmpeg extracts a scene-duration segment (scaled to 1280×720, audio
  dropped) and sets `rendered_clip` — the highest-priority asset in `assemble`. External archival
  programs are **HTTP-range-seeked** (`-ss` before `-i`), so the full file is never downloaded.
  Verified: a 6.0s clip pulled from a 3556s archival program (≈0.5 MB). This also makes **library
  `matched_clip`s usable** (assemble previously ignored `matched_clip` entirely).

## B-roll matching performance (optimized)
`match_broll_v2` was profiled and sped up ~20×:
- **Scenes processed concurrently** (ThreadPoolExecutor, cap 6).
- **Candidate pre-filter**: cheap quality-rank → vision-score only the top 4 (was up to ~30).
- **Fast scorer**: `qwen/qwen3-vl-8b-instruct` for relevance (small/fast; quality-neutral for 0–10 scoring).
- **Lazy video resolution**: Internet Archive / NASA-video search returns posters (enough to score)
  and defers the per-item mp4-manifest fetch to a `resolve()` call on the **winner only** — was the
  real bottleneck (8–24 serial HTTP calls/scene).
- **Parallel provider search**: `search_assets` queries all providers concurrently (~6s → ~1s).

Measured: 24-scene b-roll match **521s → 45s (1.9s/scene)**; full 122-scene project ≈ **3.8 min**
(was ~16 min). Coverage unchanged. A concurrency probe confirmed scoring already parallelizes
(6 concurrent ≈ 1 call), so the win came from the search layer, not the model.

## Limits / follow-ups
- **Add `PEXELS_API_KEY` / `PIXABAY_API_KEY`** → unlocks clean modern stock video (the providers are built).
- Segment selection from long archival programs is a heuristic (skip ~10% intro, ≤60s) — no
  shot-level relevance yet.
- **Scoring on video**: currently scores the poster; scoring a sampled frame would be more accurate.
- Deferred (per plan): fallback-to-graphics routing, fetch-and-index (library growth), licensing/credits
  export, curation gallery, AI video generation.

## Status vs bottleneck #1
Sourcing is no longer image-only and no longer 0-coverage: NOLAN can now pull **archival video**
(keyless) + stock video (with keys) + images, with query-variant fallback and vision scoring, and can
generate imagery via ComfyUI. The remaining gap to a *finished* video is render-time handling of
external video clips + (optionally) better/keyed sources.
