# NOLAN Structure Map (v1)

> Architecture overview of NOLAN — what each module does and how they chain into the process.
> Generated 2026-06-14. High-level/architecture altitude; drop into individual module functions for finer detail.

## What NOLAN is

NOLAN turns a **written essay → a fully planned, asset-matched, rendered video production package**.
It's a CLI tool (`nolan ...`, entry `nolan.cli:main` → `cli_legacy.py`) with three big subsystems that feed each other:

1. **Authoring pipeline** — essay → script → scene plan → matched assets → rendered scenes → assembled video.
2. **Video library / indexing** — ingest source videos, analyze them with vision+transcript, store searchable segments.
3. **Orchestration + web UIs** — automate the above, and browse it.

~35k lines across `src/nolan/`.

---

## 1. The headline pipeline: `nolan process essay.md`

The spine. From `cli_legacy.py:_process_essay`, the stages are:

```
essay.md
  │  parser.py            parse_essay()         → sections (markdown → structured)
  ▼
  │  script.py            ScriptConverter        → narration script (Gemini/LLM rewrites prose into spoken VO)
  ▼
  │  scenes.py            scene design           → scene_plan.json (one scene per beat: type, text, visual intent)
  ▼
  │  visual_router.py     route each scene        → decide HOW to visualize (template? b-roll clip? stock image? generated image?)
  ▼
  ├─ clip_matcher.py      → match scenes to your indexed video library (semantic search over segments)
  ├─ image_search.py      → search/score stock images
  └─ comfyui.py           → generate images via ComfyUI if configured
  ▼
scene_plan.json (now with assets attached)  → ready for rendering/assembly
```

**Module roles in this pipeline:**

| Module | Role |
|---|---|
| `parser.py` | Splits the markdown essay into sections/beats. |
| `script.py` (`ScriptConverter`) | LLM converts essay prose → YouTube-style narration. Uses `llm.py`. |
| `scenes.py` | Designs a **scene plan** — for each script beat, what should be on screen (scene type, on-screen text, visual suggestion). Produces `scene_plan.json`. |
| `visual_router.py` | The "decider": for each scene picks a **visual strategy** — a motion-graphics template, a library clip, a stock image, or a generated image. |
| `clip_matcher.py` | Matches scenes to **your indexed footage** using semantic search over the library DB. |
| `image_search.py` | Searches stock providers (Pexels, Wikimedia, LoC, …) and **scores relevance** with a vision model (OpenRouter-default). |
| `comfyui.py` | Generates images via a local ComfyUI instance. |
| `assets.py` | Asset management — downloads/organizes matched media into the project folder. |

The `scene_plan.json` is the **central artifact** — produced by `scenes.py`, progressively enriched by routing/matching, then consumed by rendering.

---

## 2. The data models (what flows between modules)

In `src/nolan/models/`:
- **`video.py`** → `VideoSegment` (a time-bounded chunk: timestamps, `frame_description`, `transcript`, `combined_summary`, `inferred_context`) and `InferredContext` (people/location/objects/story_context/confidence).
- **`clustering.py`** → `SceneCluster` (a group of related segments = a "scene boundary").

These are the shared currency: the indexer produces `VideoSegment`s; clustering groups them into `SceneCluster`s; `clip_matcher`/`vector_search` query them; the authoring pipeline consumes them.

---

## 3. The video library / indexing subsystem (`nolan index`)

Flow from `indexer.py:HybridVideoIndexer.index_video`:

```
source video (or nolan yt-download)
  │  youtube.py            YouTubeClient        → download + metadata (yt-dlp)
  ▼
  │  sampler.py            FFmpegSceneSampler    → extract frames (scene-detection, in-memory np arrays)
  ▼
  │  whisper.py            WhisperTranscriber    → speech → text (faster-whisper)
  │  transcript.py/aligner.py                    → align transcript words to frame timestamps
  ▼
  │  vision.py             VisionProvider        → analyze each frame (+transcript) → FrameAnalysisResult
  │     (OpenRouter / Gemini / Ollama)
  ▼
  │  indexer.py            VideoIndex            → store VideoSegments in SQLite (library.db) + frame_cache
  ▼
  ├─ clustering.py         cluster_segments      → group segments into SceneClusters (story boundaries)
  └─ vector_search.py      sync-vectors / semantic-search → embeddings for semantic retrieval
```

| Module | Role |
|---|---|
| `youtube.py` | Download videos + metadata. |
| `sampler.py` | 5 frame-sampling strategies; `FFmpegSceneSampler` is default (`extract_frames`, `list_timestamps`). |
| `whisper.py` | Local transcription. |
| `transcript.py` / `aligner.py` | Parse SRT/VTT/Whisper JSON and align words to timestamps so each segment gets the right transcript slice. |
| `vision.py` | **Provider abstraction** (`VisionProvider` ABC + `OllamaVision`/`GeminiVision`/`OpenRouterVision`, factory `create_vision_provider`). `analyze_frame()` returns a `FrameAnalysisResult`. |
| `analyzer.py` | Higher-level fusion of visual + audio into `combined_summary` + inferred context. |
| `indexer.py` | `VideoIndex` = SQLite storage layer (videos/segments/clusters/frame_cache tables, projects, migrations). `HybridVideoIndexer` = orchestration tying sampler+whisper+vision together. |
| `clustering.py` | Groups segments into scenes. |
| `vector_search.py` | Embeddings + semantic search (`nolan sync-vectors`, `nolan semantic-search`). |
| `clip_matcher.py` | Bridges library → authoring: finds the best library clip for a scene. |

`library.db` (at `D:\ClaudeProjects\.nolan\library.db`) is the persistent store; projects are namespaced via the `projects` table.

---

## 4. The rendering subsystem (`renderer/` + `render-service/`)

Turns scene plans into actual motion graphics. Two halves:

**Python side (`src/nolan/renderer/`):**
- `base.py`, `engine.py` — the render engine core.
- `layout.py`, `text_layout.py`, `presets.py`, `easing.py`, `effects.py` — layout system, animation/easing, visual effects.
- `scenes/` — **~27 scene templates** (one file each): `quote.py`, `lower_third.py`, `stat_comparison.py`, `timeline.py`, `news_headline.py`, `portrait_reveal.py`, `tweet_card.py`, `ranking.py`, `verdict.py`, `flashback.py`, `ken_burns.py`, etc. Each renders one type of on-screen graphic.
- `lottie.py`, `template_catalog.py`, `lottie_downloader.py`, `jitter_downloader.py`, `lottieflow_downloader.py` — Lottie animation catalog + downloaders.
- `infographic_client.py` — talks to the infographic renderer.

**Node side (`render-service/`, port 3010):** the actual pixel renderer (Remotion / Motion-Canvas / Puppeteer). The Python `renderer`/`infographic_client` POST jobs to it. This is the service `start_webui.bat` launches.

CLI: `render-infographics`, `render-templates`, `render-clips`, `generate`, `infographic`.

---

## 5. Assembly (`nolan align → render-clips → assemble`)

The back half that produces the final cut:
- `aligner.py` — aligns narration audio to scenes via word-level timestamps (so each scene's on-screen timing matches the VO).
- `video_gen.py` — video generation backends.
- `assemble` command — stitches rendered scenes + clips + audio into the final video.

---

## 6. The two-layer orchestrator (`nolan orchestrate`)

`src/nolan/orchestrator/` is the **automation layer** that runs the pipeline with an AI "director":
- `director.py` (Layer 2) — first-pass **template matching → adapt or invent → write `style_guide.md` → checkpoint**. Decides how the video should look.
- `claude_runner.py` — invokes the Claude CLI as a sub-agent (uses the Windows-side `claude.CMD`, with WSL-wrapping for version skew).
- `template_match.py` — matches a scene plan to existing templates.
- `render.py`, `state.py`, `dashboard.py` (web dashboard), `prompts/` — execution, run state, monitoring.

The "agentic" path: instead of running each CLI step manually, the director plans and drives them.

---

## 7. Quality, config, and the web layer

- **`quality/`** — `protocol.py` + `checks/visual_text.py`: automated QA (e.g., verifying rendered text is legible) — codified version of the QA loop in CLAUDE.md.
- **`config.py`** — `NolanConfig` (loads `nolan.yaml` + `.env`); holds `gemini`, `vision`, `whisper`, `indexing`, `comfyui`, `image_sources`, `clip_matching` sub-configs. Where the OpenRouter/qwen default is set.
- **`llm.py`** — `GeminiClient` (text + vision generation).
- **`http_client.py`** — shared async HTTP wrapper.
- **Web UIs:** `hub.py` (unified hub, :8011 — Library + Showcase + Scenes), `library_viewer.py`, `showcase.py`, `viewer.py`. These read `library.db` and `projects/`.
- **`cli/`** — thin package that re-exports `main` from `cli_legacy.py` (the real command definitions).

---

## How it all links — the mental model

```
                          ┌─────────────────────────────────────┐
   nolan yt-download ──►   │   VIDEO LIBRARY (indexing)          │
                          │  youtube→sampler→whisper→vision→     │
                          │  indexer(SQLite)→clustering→vectors  │
                          └───────────────┬─────────────────────┘
                                          │ (semantic search / clip match)
                                          ▼
   essay.md ──► parser ──► script ──► scenes ──► visual_router ──┤
                                                  │              │
                                  ┌───────────────┼──────────────┤
                                  ▼               ▼              ▼
                            clip_matcher    image_search     comfyui
                            (library)       (stock+score)   (generate)
                                  └───────────────┬──────────────┘
                                                  ▼
                                          scene_plan.json
                                                  │
                                                  ▼
                                   renderer/ ──► render-service (:3010)
                                                  │
                                          align + assemble
                                                  ▼
                                            final video
   (orchestrate = AI director that drives this whole chain automatically)
   (hub :8011 = browse library, showcase effects, review scene plans)
```

**Two connection points worth remembering:**
1. `scene_plan.json` links authoring → assets → rendering. Everything reads/writes it.
2. `library.db` links indexing → retrieval. `clip_matcher`/`vector_search` query it to fill scenes with your own footage.

---

## CLI command surface (the process, in commands)

| Group | Commands |
|---|---|
| Authoring | `process` (full pipeline), `script`, `design`, `generate`, `generate-test` |
| Indexing/library | `index`, `cluster`, `browse`, `export`, `sync-vectors`, `semantic-search` |
| Assets | `image-search`, `match-broll`, `match-clips` |
| Rendering | `infographic`, `render-infographics`, `render-templates`, `render-clips` |
| Assembly | `transcribe`, `align`, `assemble` |
| YouTube | `yt-download`, `yt-search`, `yt-info` |
| Projects (group) | `projects init/create/list/info/delete` |
| Templates (group) | template catalog management |
| Video-gen (group) | video generation backends |
| Web UIs | `hub` (:8011), `library`, `showcase` |
| Orchestration | `orchestrate`, `route-scenes` |

---

## Largest modules (orientation by size)

| Lines | File | What |
|---|---|---|
| 4704 | `cli_legacy.py` | All CLI command definitions (the real entry point) |
| 1989 | `indexer.py` | `VideoIndex` (SQLite) + `HybridVideoIndexer` |
| 1499 | `orchestrator/director.py` | Layer-2 AI director |
| 1096 | `image_search.py` | Stock image search + vision scoring |
| 1005 | `renderer/effects.py` | Visual effects |
| 950 | `sampler.py` | Frame sampling strategies |
| 903 | `renderer/base.py` | Render engine core |
| 896 | `lottie.py` | Lottie animation handling |
| 828 | `renderer/layout.py` | Layout system |
| 753 | `template_catalog.py` | Template catalog |
| 748 | `scenes.py` | Scene plan design |
| 701 | `video_gen.py` | Video generation backends |
| 694 | `hub.py` | Unified web UI |
| 643 | `vector_search.py` | Semantic search |
| 603 | `clip_matcher.py` | Scene → library clip matching |
| 547 | `vision.py` | Vision provider abstraction |
| 529 | `clustering.py` | Segment → scene clustering |
