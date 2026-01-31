# NOLAN Implementation Status

**Version:** 0.1.0
**Status:** Complete
**Last Updated:** 2026-01-20

## Summary

NOLAN is a CLI tool that transforms structured essays into video production packages with scripts, scene plans, and organized assets ready for video editing.

## Implemented Features

### Core Pipeline
- **Essay Parser** - Extracts sections from markdown essays
- **Script Converter** - Converts essays to YouTube-style narration using Gemini API
- **Scene Designer** - Generates visual scene plans with asset suggestions

### Infrastructure
- **Configuration System** - YAML + environment variable configuration
- **Gemini LLM Client** - Async client for Gemini API
- **Video Indexer** - SQLite-backed video library indexing with visual analysis
- **Asset Matcher** - Matches scenes to indexed video library
- **Project Registry** - Organize videos by project with human-friendly slugs
  - Projects have unique IDs (internal) and slugs (CLI-facing)
  - Index videos scoped to specific projects
  - Search and filter by project

### Hybrid Indexing
- **Vision Provider** - Switchable vision models (Ollama/Gemini)
  - Default: qwen3-vl:8b via Ollama
  - Configurable host/port/model
- **Smart Sampling** - 5 strategies for frame extraction:
  - FFmpeg scene detection (default - 10-50x faster, hardware accelerated)
  - Hybrid (Python-based, combines time bounds with scene detection)
  - Fixed interval
  - Scene change detection (OpenCV)
  - Perceptual hashing (skip duplicates)
- **Transcript Alignment** - SRT/VTT/Whisper JSON support
- **Segment Analyzer** - LLM fusion of visual + audio with inferred context

### Whisper Integration
- **Auto-Transcription** - Generate transcripts for videos without them
  - Uses faster-whisper (4x faster than openai-whisper)
  - Multiple model sizes: tiny, base, small, medium, large-v2, large-v3
  - GPU acceleration (CUDA) with automatic CPU fallback
  - Voice activity detection (VAD) filtering
- **Audio Extraction** - Automatic via ffmpeg
- **Caching** - Saves generated transcripts as .whisper.json files

### Hybrid Inference
- **Combined Vision+Inference** - Single API call for frame analysis (50% fewer API calls)
  - Vision model sees both image AND transcript together
  - Better inference: can recognize faces, read on-screen text
  - Returns frame_description + combined_summary + inferred_context
  - Falls back to simple description for non-Gemini providers
- **Inferred Context** - Best guesses for:
  - People (named characters, speakers, face recognition)
  - Location (setting identification from visuals and audio)
  - Story context (narrative description)
  - Objects (notable items)
  - Confidence level (high/medium/low)

### Scene Clustering
- **Segment Grouping** - Cluster continuous segments into story moments
  - Groups by shared characters/people
  - Groups by shared location
  - Groups by similar story context
  - Configurable time gap threshold
- **LLM Story Boundary Detection** - Optional refinement using LLM
  - Detects narrative beat changes
  - Splits clusters at story boundaries
- **Cluster Summaries** - LLM-generated summaries for each cluster
  - Captures what's happening in the story moment
  - Identifies key characters/elements
  - Describes emotional/narrative significance

### Semantic Search
- **Vector Database** - ChromaDB for semantic similarity search
  - Stores embeddings for segments and clusters separately
  - Persistent storage alongside SQLite database

## Recent Indexing Improvements (2026-01-17)
- **Concurrency Default** - Indexing defaults to 25 concurrent calls (configurable via `indexing.concurrency`).
- **Bulk Segment Inserts** - Segments are inserted per video in batch for faster DB writes.
- **Frame Analysis Cache** - Cached results by `(fingerprint, timestamp, transcript_hash, inference_enabled)` to reuse on reindex.
- **Transcript Alignment Cache** - Cached aligned transcript slices per `(fingerprint, transcript_hash, timestamps_hash)`.
- **Rate-Limit Backoff** - Short exponential backoff on Gemini rate-limit errors (429/resource_exhausted).
- **FFmpeg Batch Extraction** - FFmpeg scene sampler extracts frames in batches per process for fewer spawns.
- **Path Refresh** - Video path/project is updated even when reindex is skipped.

## Recent Clip Matching Improvements (2026-01-17)
- **Parallel Matching** - Scene matching runs with bounded concurrency (`clip_matching.concurrency`).
- **Rate-Limit Backoff** - Retries LLM selection on 429/resource_exhausted errors.
- **Better Selection Context** - LLM prompt now includes the merged search query.
- **Deterministic Fallback** - LLM parse failures fall back to highest-similarity candidate.
- **No-Match Logging** - Clear messages when candidates are filtered out by similarity.
- **Two-Stage Search** - Cluster-first search narrows segment results when `search_level=both`.
- **Candidate Deduping** - Removes duplicate segment candidates across sources.
- **Dominant-Match Fast Path** - Skips LLM when top similarity is clearly ahead.
- **Deterministic Tie-Breaking** - Pre-LLM ranking uses similarity, transcript presence, and duration fit.
- **LLM Selection Cache** - Per-run cache for scene+candidates avoids repeated LLM calls.

## Codebase Refactoring (2026-01-31)

### File Organization
- **Scratch Directory** - All temporary/test outputs use `.scratch/` directory
  - Updated 5 CLI commands with problematic default paths
  - Added `.scratch/` to `.gitignore`
  - Prevents test files scattering in project root

### Models Package
- **Centralized Data Models** - Extracted dataclasses to `nolan/models/` package
  - `InferredContext` - Visual + audio analysis results
  - `VideoSegment` - Indexed video segment data
  - `SceneCluster` - Grouped segments representing story moments
- **Backwards Compatibility** - Re-exports in original modules maintain API stability
- **Type Hints** - Using `TYPE_CHECKING` imports to avoid circular dependencies

### CLI Package
- **Hybrid Approach** - Created `nolan/cli/` package with backwards-compatible entry point
  - `cli_legacy.py` - Original CLI preserved (4,478 lines)
  - `cli/__init__.py` - Entry point re-exports from legacy
  - `cli/utils.py` - Shared utilities for future command modules

### Downloaders Package
- **Shared Utilities** - Created `nolan/downloaders/` package with common code
  - `sanitize_filename()` - Safe filename generation
  - `extract_lottie_metadata()` - Parse Lottie JSON metadata
  - `save_lottie_json()` - Save with minification
  - `RateLimiter` - Request rate limiting for APIs
  - `CatalogBuilder` - Generate catalog JSON files
- **Base Models** - Shared template dataclasses
  - `BaseLottieTemplate` - Common fields for all sources
  - `JitterTemplate`, `LottieflowTemplate`, `LottieFilesMetadata` - Source-specific
- **Updated Downloaders** - Jitter, LottieFiles, Lottieflow use shared utilities
- **New Tests** - 20 tests for shared downloader utilities

### HTTP Client Module
- **Shared HTTP Utilities** - Created `nolan/http_client.py` for consolidated HTTP access
  - `get_async_client()` - Pre-configured async httpx client
  - `get_sync_client()` - Pre-configured sync httpx client
  - `fetch_json_async()` / `fetch_json_sync()` - JSON fetch helpers
  - `download_file_async()` / `download_file_sync()` - File download helpers
  - `ServiceClient` - Base class for service-specific API clients
  - Default timeouts (30s read, 10s connect)
  - Default User-Agent header
  - Connection pooling support
- **New Tests** - 23 tests for HTTP client utilities

### New Test Coverage
- **test_aligner.py** - 23 tests for audio-scene alignment
  - Text normalization (unicode, punctuation, whitespace)
  - Word stream search (exact, fuzzy, case-insensitive)
  - Scene alignment algorithms
- **test_image_search.py** - 18 tests for image search
  - ImageSearchResult dataclass and scoring
  - ImageProvider base class
  - DDGSProvider implementation
- **test_clip_matcher.py** - 18 tests for clip matching
  - ClipCandidate and MatchResult dataclasses
  - Deduplication logic
  - Cache key generation
  - Project-level filtering support
- **BGE Embeddings** - BAAI/bge-base-en-v1.5 model (768 dimensions)
  - Query-document asymmetry support for better retrieval
  - Local inference (~440MB model download)
  - Combines visual descriptions, transcripts, and context
- **Search Levels** - Configurable granularity
  - `segments` - Individual video segments
  - `clusters` - Story moment clusters
  - `both` - Combined results (default)
- **Incremental Sync** - Only re-embeds changed videos
  - Uses `indexed_at` timestamps to detect re-indexing
  - Auto-triggered after `nolan index` completes
  - Use `--force` to re-embed everything
- **CLI Commands**
  - `nolan sync-vectors` - Sync SQLite index to ChromaDB
  - `nolan semantic-search <query>` - Natural language search

### Integrations
- **ComfyUI Client** - Image generation via local ComfyUI API
- **Viewer Server** - FastAPI-based local viewer for reviewing outputs
- **Library Viewer** - Web UI for browsing indexed video library (`nolan browse`)
  - Keyword and semantic search modes with toggle
  - Project filtering support
- **Scene Plan Viewer** - A/B column viewer for scene plan review (`/scenes` route)
  - Left column: Scene details (ID, timing, narration, type, query/prompt)
  - Right column: Asset preview (image/video with lightbox)
  - Section and status filters
  - Audio sync with range playback (play single scene, loop option)
  - Click timestamp to play that scene's audio range

### CLI Commands
| Command | Description |
|---------|-------------|
| `nolan script <essay.md>` | Step 1: Convert essay to narration script |
| `nolan design <script.json>` | Step 2: Design visual scenes from script |
| `nolan process <essay.md>` | Full pipeline: essay → script → scenes |
| `nolan index <video_folder>` | Index video library for snippet matching |
| `nolan export <video>` | Export indexed segments to JSON |
| `nolan cluster <video>` | Cluster segments into story moments |
| `nolan browse` | Browse indexed video library in web UI |
| `nolan serve` | Launch local viewer to review outputs |
| `nolan generate` | Generate images via ComfyUI |
| `nolan generate-test` | Quick single-image generation for testing |
| `nolan image-search` | Search for images from web/stock photo APIs |
| `nolan match-broll` | Batch search and download images for b-roll scenes |
| `nolan match-clips` | Match scenes to video library clips using semantic search |
| `nolan transcribe` | Transcribe audio/video to SRT/JSON/TXT |
| `nolan align` | Align scene plan to audio with word-level timestamps |
| `nolan render-clips` | Pre-render animated scenes to MP4 clips |
| `nolan assemble` | Assemble final video from scenes + audio |
| `nolan infographic` | Generate infographics via render-service |
| `nolan yt-download` | Download YouTube videos using yt-dlp |
| `nolan yt-search` | Search YouTube for videos |
| `nolan yt-info` | Get information about a YouTube video |
| `nolan projects create` | Create a new project with slug |
| `nolan projects list` | List all registered projects |
| `nolan projects info` | Show project details and videos |
| `nolan projects delete` | Remove a project from registry |
| `nolan sync-vectors` | Sync video index to ChromaDB for semantic search |
| `nolan semantic-search` | Semantic search across video library |
| `nolan showcase` | Launch Motion Effects Showcase UI |
| `nolan library` | Launch Video Library Viewer UI |
| `nolan hub` | Launch unified NOLAN Hub (Library + Showcase + Scenes) |

### ComfyUI Integration
- **Custom Workflows** - Load any ComfyUI workflow (API format)
- **Auto-detection** - Finds prompt nodes automatically
- **Explicit Node Selection** - `-n "node_id"` for reliable prompt injection
- **Parameter Overrides** - `-s "node_id:param=value"` for any workflow parameter
- **Config File** - `nolan.yaml` for port and other settings

### Image Search
- **Multi-Provider Support** - Extensible provider system
  - DuckDuckGo (no API key required)
  - Pexels (requires API key)
  - Pixabay (requires API key)
  - Wikimedia Commons (no API key, public domain/CC)
  - Smithsonian Open Access (requires API key, CC0)
  - Library of Congress (no API key, public domain)
- **JSON Output** - Results saved with URLs, thumbnails, dimensions, license
- **Search All** - Query multiple sources at once with `--source all`
- **Vision Model Scoring** - Score images by relevance using AI
  - Gemini vision model (cloud, fast)
  - Ollama vision model (local, requires running Ollama)
  - Scores from 0-10 with explanations
  - Results sorted by relevance

### Video Assembly Pipeline
- **Unique Scene IDs** - Section-prefixed IDs (`Hook_scene_001`, `Context_scene_002`)
  - Prevents asset file collisions across sections
  - Automatically applied during scene design
- **Timeline-Aware Assembly** - Matches video duration to audio
  - Sorts scenes by start time from audio alignment
  - Fills gaps between scenes with black frames
  - Total video duration matches voiceover exactly
- **Format Handling** - Robust image format support
  - SVG to PNG conversion (via cairosvg)
  - AVIF/HEIC detection and conversion (via Pillow)
  - Handles mismatched file extensions
- **Asset Priority** - Smart asset resolution per scene
  1. `rendered_clip` - Pre-rendered MP4 (highest priority)
  2. `generated_asset` - AI-generated image
  3. `matched_asset` - Downloaded b-roll
  4. `infographic_asset` - Rendered SVG
  5. Black frame (fallback for missing assets)

### Motion Effects Library
- **Effects Registry** - Centralized catalog of motion effects for video essays
  - Organized by category: image, quote, statistic, chart, title, map, etc.
  - Each effect maps to underlying engine (Remotion, Motion Canvas, Infographic)
  - LLM-friendly descriptions for automated scene generation
- **Effect Presets** - Ready-to-use motion patterns with sensible defaults
  - `image-ken-burns` - Classic documentary pan/zoom
  - `image-zoom-focus` - Zoom to detail reveal
  - `image-parallax` - 2.5D depth parallax layers
  - `quote-fade-center` - Elegant centered text
  - `quote-kinetic` - Kinetic typography sequences
  - `chart-bar-race` - Animated bar charts
  - `stat-counter-roll` - Number counter animation
  - `title-card` - Full-screen title cards
  - `map-flyover` - Geographic pan/zoom
  - `light-leak` - Organic light leak and film burn overlay
  - `camera-shake` - Handheld camera shake for tension/urgency
  - `compare-before-after` - Before/after slider wipe transition
  - `text-pop` - Word-by-word text reveal animation
  - `source-citation` - Citation cards for sources
  - `screen-frame` - Browser/phone/laptop mockup frames
  - `audio-waveform` - Animated audio visualization
  - `zoom-blur` - Speed zoom with radial motion blur
  - `glitch-transition` - Digital glitch with RGB split
  - `data-ticker` - CNN-style scrolling news ticker
  - `social-media-post` - Twitter/social media post mockup
  - `video-frame-stack` - Grid/stack of video thumbnails
- **Showcase UI** - Web interface for browsing and generating effects
  - Gallery view with category filtering
  - Live parameter form for each effect
  - Image upload support
  - Preview generation with render service
  - Accessible at `nolan showcase` or via unified hub
- **Unified Hub** - Single entry point at `nolan hub` combining:
  - Video Library browser (`/library`)
  - Motion Effects Showcase (`/showcase`)
  - Scene Plan Viewer (`/scenes`) with dynamic project selection
  - Landing page shows all projects as clickable cards
  - Projects auto-discovered from `--projects` directory (default: `projects/`)
  - Project dropdown in scenes viewer for quick switching
- **API Endpoints**
  - `GET /effects` - List all effects with parameters
  - `GET /effects/:id` - Get specific effect details
  - `POST /render` - Render with `{effect, params}` format

### YouTube Integration
- **Video Download** - Download YouTube videos using yt-dlp
  - Single video, batch from file, or entire playlists
  - Configurable quality formats (default: 720p)
  - Automatic subtitle download (configurable languages)
  - Progress tracking with callbacks
- **YouTube Search** - Search for videos without downloading
  - Returns video metadata (title, duration, views, channel)
  - Export results to JSON
  - Optional: download first result directly
- **Video Info** - Get detailed metadata for a single video
  - Title, description, tags, categories
  - Duration, views, upload date
  - Channel information

## Usage

```bash
# Install in development mode
pip install -e ".[dev]"

# === Video Production Workflow ===

# Step 1: Convert essay to script
nolan script path/to/essay.md -o ./output
# Outputs: script.md (human-readable), script.json (for design)

# Step 2: Design scenes from script
nolan design ./output/script.json
# Outputs: scene_plan.json

# Or run full pipeline in one command
nolan process path/to/essay.md -o ./output

# Index video library (Ollama vision - local)
nolan index path/to/videos --recursive

# Index with Gemini vision (cloud - faster, async)
nolan index path/to/videos --vision gemini

# Control concurrency for rate limits
nolan index path/to/videos --vision gemini --concurrency 3   # free tier
nolan index path/to/videos --vision gemini --concurrency 10  # pay-as-you-go (default)
nolan index path/to/videos --vision gemini --concurrency 30  # higher tiers

# Choose frame sampling strategy (ffmpeg_scene is default, 10-50x faster)
nolan index path/to/videos --sampler ffmpeg_scene  # Fast FFmpeg-based (default)
nolan index path/to/videos --sampler hybrid        # Python-based, more sensitive to gradual changes
nolan index path/to/videos --sampler fixed         # Fixed 5-second intervals

# Index with Whisper auto-transcription (GPU accelerated)
nolan index path/to/videos --vision gemini --whisper --whisper-model base

# Export indexed segments to JSON
nolan export video.mp4 -o segments.json
nolan export --all -o library.json

# Cluster segments into story moments
nolan cluster video.mp4 -o clusters.json
nolan cluster video.mp4 --refine  # Use LLM for better boundaries
nolan cluster --all -o all_clusters.json

# Browse indexed library in web UI
nolan browse

# === Semantic Search ===

# Sync index to vector database (first time or after new indexing)
nolan sync-vectors
nolan sync-vectors --project venezuela  # Only sync specific project
nolan sync-vectors --clear              # Clear and rebuild

# Semantic search with natural language
nolan semantic-search "person looking worried"
nolan semantic-search "dramatic landscape" --level clusters
nolan semantic-search "Hugo Chavez speaking" --project venezuela --level segments
nolan semantic-search "emotional moment" -n 20 -o results.json

# Launch viewer for project outputs
nolan serve -p ./output

# Generate images with custom ComfyUI workflow
nolan generate-test "a dragon" -w workflow_api.json
nolan generate-test "a dragon" -w workflow.json -n "26:24"  # explicit prompt node
nolan generate-test "a dragon" -w workflow.json -s "13:width=1536" -s "3:steps=40"

# Search for images from web/stock photos
nolan image-search "sunset mountains"
nolan image-search "sunset mountains" -s pexels -n 20  # Pexels (needs API key)
nolan image-search "sunset mountains" -s all -o results.json  # all sources

# Search public domain sources
nolan image-search "Hugo Chavez" -s wikimedia  # Wikimedia Commons
nolan image-search "Abraham Lincoln" -s loc     # Library of Congress
nolan image-search "dinosaur" -s smithsonian    # Smithsonian (needs API key)

# Score images by relevance using vision model
nolan image-search "sunset mountains" --score --vision gemini
nolan image-search "sunset mountains" --score --vision ollama -c "for a travel documentary"

# Generate infographics (requires render-service running)
nolan infographic --title "My Process" -i "Step 1:First" -i "Step 2:Second"
nolan infographic --template list --theme dark --title "Features" -i "Fast:Blazing speed"
nolan infographic --template comparison --theme warm --title "A vs B" -i "Option A:Pro A" -i "Option B:Pro B"
nolan infographic spec.json -o my_infographic.svg  # From JSON spec file

# === YouTube Operations ===

# Search YouTube for videos
nolan yt-search "python tutorial" -n 5          # Search and show top 5 results
nolan yt-search "documentary" -o results.json   # Export results to JSON
nolan yt-search "cooking tips" --download       # Search and download first result

# Download YouTube videos
nolan yt-download "https://youtube.com/watch?v=xxxxx"                      # Single video
nolan yt-download urls.txt -o ./videos                                     # From file (one URL per line)
nolan yt-download "https://youtube.com/playlist?list=xxxxx" --playlist     # Entire playlist
nolan yt-download "https://youtube.com/playlist?list=xxxxx" --limit 10     # First 10 from playlist
nolan yt-download "https://youtube.com/watch?v=xxxxx" -f "bestvideo[height<=1080]+bestaudio"  # Custom quality

# Get video info without downloading
nolan yt-info "https://youtube.com/watch?v=xxxxx"                          # Show video metadata
nolan yt-info "https://youtube.com/watch?v=xxxxx" -o video_info.json       # Save to JSON

# === Project Management ===

# Create a new project
nolan projects create "Venezuela Documentary" -d "Documentary about Hugo Chavez"
nolan projects create "My Project" -s custom-slug -p projects/my-project   # Custom slug and path

# List all projects
nolan projects list                                                         # Shows slug, name, video count

# View project details
nolan projects info venezuela                                               # Show project info and videos

# Index videos scoped to a project
nolan index path/to/videos --project venezuela                              # Associate videos with project

# Delete a project
nolan projects delete venezuela                                             # Remove from registry only
nolan projects delete venezuela --delete-videos                             # Also delete indexed videos
```

## Test Coverage

174 tests covering all modules:
- Configuration: 3 tests
- LLM Client: 2 tests
- Parser: 3 tests
- Script Converter: 5 tests
- Scene Designer: 3 tests
- Video Indexer: 5 tests
- Asset Matcher: 3 tests
- ComfyUI Client: 3 tests
- Viewer Server: 3 tests
- CLI: 4 tests
- Integration: 2 tests
- Vision Provider: 9 tests
- Sampler: 11 tests
- Transcript: 15 tests
- Analyzer: 10 tests
- Whisper: 17 tests
- Clustering: 34 tests
- Lottie: 42 tests (NEW)

## Project Structure

```
NOLAN/
├── src/nolan/
│   ├── __init__.py      # Package version
│   ├── __main__.py      # Module entry point
│   ├── cli.py           # CLI commands
│   ├── config.py        # Configuration loading
│   ├── llm.py           # Gemini client
│   ├── parser.py        # Essay parsing
│   ├── script.py        # Script conversion
│   ├── scenes.py        # Scene design
│   ├── indexer.py       # Video indexing + HybridVideoIndexer
│   ├── matcher.py       # Asset matching
│   ├── comfyui.py       # ComfyUI integration
│   ├── viewer.py        # Viewer server
│   ├── vision.py        # Vision providers (Ollama, Gemini)
│   ├── sampler.py       # Smart frame sampling
│   ├── transcript.py    # Transcript loading/alignment
│   ├── analyzer.py      # Segment analysis + inference
│   ├── whisper.py       # Whisper auto-transcription
│   ├── clustering.py    # Scene clustering
│   ├── aligner.py       # Scene-to-audio alignment
│   ├── library_viewer.py # Library browser server
│   ├── image_search.py  # Image search providers
│   ├── assets.py        # Asset management for motion effects
│   └── templates/
│       ├── index.html   # Viewer UI
│       ├── scenes.html  # Scene plan A/B viewer
│       └── library.html # Library browser UI
├── tests/               # Test suite (174 tests)
├── render-service/      # Node.js microservice for infographics/animations
│   ├── src/
│   │   ├── server.ts    # Express API server
│   │   ├── routes/      # API endpoints (health, render)
│   │   ├── jobs/        # Job queue and types
│   │   └── engines/     # Render engines (infographic, etc.)
│   └── package.json
├── assets/              # Visual assets for motion effects
│   ├── common/icons/    # Shared SVG icons (check, star, etc.)
│   └── styles/          # Style-specific assets (per EssayStyle)
├── pyproject.toml       # Package configuration
└── .env                 # API keys (not committed)
```

## Requirements

- Python 3.10+
- Gemini API key (set `GEMINI_API_KEY` in .env)
- Ollama (optional, for local vision model)
- ffmpeg (optional, for Whisper auto-transcription)
- ComfyUI (optional, for image generation)
- Node.js 18+ (optional, for Infographic & Animation Render Service)

## Documentation

| Document | Description |
|----------|-------------|
| [Fair Use Transforms](docs/FAIR_USE_TRANSFORMS.md) | Strategies for transforming third-party clips to reduce copyright detection |
| [Motion Effects](docs/MOTION_EFFECTS.md) | Motion effects library for video essays |
| [TTS Integration](docs/TTS_INTEGRATION.md) | Voiceover generation with MiniMax and Chatterbox |
| [LLM Content Authoring](render-service/docs/LLM_CONTENT_AUTHORING.md) | Guide for LLMs writing content with style markup |

## Next Steps (Backlog)

### Autonomous Quality System (Priority)

See [docs/plans/2026-01-30-autonomous-quality-system.md](docs/plans/2026-01-30-autonomous-quality-system.md) for full design.

**Goal:** Enable NOLAN to produce high-quality video clips autonomously with minimal human intervention.

**Four-Layer Approach:**
1. **Scope to Strengths** - Route visual types to appropriate pipelines (templates vs. generation)
2. **Template Library** - Expand Lottie/Motion Canvas templates for automatable content
3. **Video Generation** - Integrate LTX-Video/Runway for b-roll and cinematic content
4. **Quality Evaluation** - Vision-based scoring with retry loops and human fallback

**Phase 1 (Template System): COMPLETE**
- [x] Unified template catalog (`TemplateCatalog` class)
- [x] Semantic tagging (240+ auto-generated tags)
- [x] CLI commands (`nolan templates list/search/info/semantic-search/match-scene`)
- [x] Semantic template discovery (ChromaDB + BGE embeddings)
- [x] Scene-to-template matching (`find_templates_for_scene()`)
- [x] Visual type router (`VisualRouter` class in `visual_router.py`)
- [x] CLI: `nolan route-scenes` - show routing decisions
- [x] CLI: `nolan render-templates` - render templates to video clips
- [ ] Template library expansion (200+ templates - currently 52)
- [ ] Template schema completion for all templates (13/52 have schemas)

**Phase 2 (Quality Evaluation):**
- [ ] Quality scoring prompts (semantic fit, visual quality, style consistency)
- [ ] Quality gate integration after asset generation
- [ ] Per-video style guide system

**Phase 3 (Video Generation):**
- [ ] LTX-Video integration (self-hostable)
- [ ] Runway API integration (commercial)
- [ ] Video generation router with cost management

**Phase 4 (Human Review):**
- [ ] Review queue with priority scoring
- [ ] Review web UI for flagged scenes
- [ ] Notification system for pending reviews

---

- **Database-Backed Asset Management** - SQLite storage for large asset libraries (100+ assets)
  - Search by name, tags, category
  - Asset versioning and thumbnails
  - CLI for asset management (`nolan assets list/add/tag`)
  - Trigger: Implement when asset count justifies complexity
- **TTS Voiceover Generation** - `nolan voiceover` command with MiniMax API and Chatterbox local fallback
- **End-to-End Orchestrator** - `nolan make-video` single command for full pipeline automation
- **Fair Use Transform Presets** - Implement `--fair-use-transform` flag for automated clip transformation
- **AI Clip Regeneration** - `nolan regenerate-clips` using LTX-2 / Wan I2V to create new AI videos from key frames
- **yt-fts transcript search integration** - Use YouTube transcript search for full-text search
- **LLM infographic placement** - Detect data points in scripts and suggest infographic placement
- **HunyuanOCR integration** - Text extraction from video frames (subtitles, on-screen text, titles)
- **Image search browser display** - View image search results in web UI
- **Vision model image selection** - Auto-select best matching images using vision model
- **dotLottie Integration** ✅ COMPLETED
  - ✅ Spike completed: frame-accurate rendering with `setFrame()` works
  - ✅ No flickering observed (unlike @remotion/lottie)
  - ✅ `LottieAnimation` component added to Remotion engine
  - ✅ Python utility module: `src/nolan/lottie.py` (customize_lottie, validate, transform colors)
  - ✅ Scene plan support: `visual_type: "lottie"` with `lottie_template` and `lottie_config`
  - ✅ Asset library structure: `assets/common/lottie/` (lower-thirds, transitions, icons, etc.)
  - ✅ ThorVG engine supports: expressions, drop shadows, blur, masks, gradients, text
  - Test files: `render-service/test/dotlottie-spike/`
  - Docs: [docs/LOTTIE_INTEGRATION.md](docs/LOTTIE_INTEGRATION.md)
  - See: [ThorVG Lottie Support](https://github.com/thorvg/thorvg/wiki/Lottie-Support)
- **Lottie Template Catalog** ✅ COMPLETED (was: Motion Pattern Library)
  - ✅ LottieFiles Downloader: `src/nolan/lottie_downloader.py`
    - Rate-limited downloads (15-20 req/min), metadata extraction, duplicate detection
    - Color palette extraction, search functionality
  - ✅ Jitter.video Downloader: `src/nolan/jitter_downloader.py`
    - Playwright browser automation for Jitter's SPA
    - Category discovery, multi-artboard handling, blob content extraction
    - CLI: `python -m nolan.jitter_downloader --essential`
  - ✅ Lottieflow Downloader: `src/nolan/lottieflow_downloader.py`
    - Bulk download via network interception (no login required)
    - 21 categories of UI micro-interactions
    - CLI: `python -m nolan.lottieflow_downloader --essential`
  - ✅ 50+ production-ready animations across multiple sources:
    - LottieFiles: lower-thirds (2), title-cards (1), transitions (2), data-callouts (2), progress-bars (2), loaders (1), icons (2)
    - Jitter: text effects (glide, morph, sliding reveal), icons (rotate-scale)
    - Lottieflow: menu-nav (5), arrows (5), checkboxes (3), loaders (5), play (3), scroll-down (3), success (3), attention (3)
  - ✅ Catalogs: `catalog.json`, `jitter-catalog.json`, `lottieflow-catalog.json`
  - ✅ Template Schema System: `src/nolan/lottie.py`
    - `analyze_lottie()` - Discover customizable fields (text, colors, timing)
    - `generate_schema()` / `save_schema()` - Create `.schema.json` files
    - `render_template()` - Magicbox API with semantic field names
    - `list_templates()` - List templates with schema status
  - ✅ Curated schemas for 3 templates: magic-box, modern lower-third, simple lower-third
  - ✅ 42 tests: `tests/test_lottie.py`
  - ✅ Docs: [docs/LOTTIE_INTEGRATION.md](docs/LOTTIE_INTEGRATION.md#lottie-template-catalog)
- **Template Analysis Tool** - CLI to help document animation timing from reference
  - `nolan analyze-template <video>` to measure keyframes and timing
  - Export structured motion specs from reference videos
- **SVG Animation Import** - Parse animated SVGs (SMIL) to Motion Canvas code
  - Convert SMIL animations to Motion Canvas generator functions
  - Preserve timing, easing, and transform sequences
- **Canva Static Export** - Download Canva designs as static assets via API
  - OAuth flow for [Canva Connect API](https://www.canva.dev/docs/connect/)
  - Export PNG/SVG elements from Canva templates
  - Animate exported assets in NOLAN with custom timing
  - Note: No animation keyframe access, static export only

## Recently Completed

- ✅ **Video Generation Integration** - Dual-backend video generation for autonomous content creation
  - `VideoGenerator` abstract base class with unified interface
  - `ComfyUIVideoGenerator` for local video models (LTX-Video, Wan, HunyuanVideo, CogVideoX, AnimateDiff)
  - `RunwayGenerator` for commercial API (Gen-3 Alpha Turbo, Gen-3 Alpha)
  - Auto-detection of prompt nodes in ComfyUI workflows
  - Scene-to-video generation with optimized prompts: `generate_video_for_scene()`
  - CLI: `nolan video-gen check/generate/scene/batch`
  - Cost tracking for commercial API usage
  - Part of Autonomous Quality System Phase A-2
- ✅ **Visual Router** - Intelligent scene-to-pipeline routing for asset generation
  - `VisualRouter` class routes scenes to appropriate pipelines
  - Route types: template, library, generation, infographic, passthrough
  - Template types: lower-third, text-overlay, title, counter, icon, loading, lottie, ui
  - Library types: b-roll, a-roll, footage, cinematic
  - Generation types: generated, generated-image
  - Template matching with score threshold (default 0.5)
  - CLI: `nolan route-scenes`, `nolan render-templates`
  - Part of Autonomous Quality System Phase A-3
- ✅ **Template Catalog System** - Unified Lottie template management for autonomous video generation
  - `TemplateCatalog` class merges LottieFiles, Jitter, Lottieflow sources
  - 53 templates across 17 categories with auto-tagging (240+ tags)
  - `TemplateSearch` with ChromaDB vector embeddings for semantic search
  - Scene-to-template matching: `find_templates_for_scene()`, `match_scene_to_template()`
  - CLI: `nolan templates list/info/search/semantic-search/match-scene/index/auto-tag`
  - Visual type routing maps scene types to template categories
  - Part of Autonomous Quality System Phase A-1
- ✅ **Video Library Clip Matching** - `nolan match-clips` command for matching scenes to library clips
  - Semantic search using ChromaDB vector database finds relevant clips
  - LLM selection picks best candidate considering visual relevance, narrative fit, and duration
  - Smart clip tailoring algorithm: skips first 7% (avoid transitions), ratio-based centering
  - Combines `narration_excerpt + visual_description + search_query` for rich search queries
  - Configurable via `clip_matching` section in nolan.yaml:
    - `candidates_per_scene`: Top N candidates (default: 3)
    - `min_similarity`: Threshold 0-1 (default: 0.5)
    - `search_level`: segments, clusters, or both
  - Updates `matched_clip` field in scene_plan.json with video_path, clip_start, clip_end, reasoning
  - Supports --dry-run, --project filter, --skip-existing options
- ✅ **Semantic Search UI** - Toggle between keyword and semantic search in library viewer
  - Search mode toggle button (Keyword/Semantic) in web UI
  - Semantic scores displayed as percentage badges (e.g., "69.3%")
  - Fields dropdown hidden in semantic mode (not applicable)
  - `/api/search/semantic` API endpoint for programmatic access
- ✅ **Adaptive Scene Detection** - Automatic threshold tuning per video
  - Uses statistical analysis (mean + 5σ) to find significant scene changes
  - Adapts to different editing styles: fast cuts get higher threshold, slow pacing gets lower
  - Example: Fast-cut video (10.8 segments/min) vs slow video (5.1 segments/min)
  - Runs FFmpeg once to collect all scores, then filters - no repeated processing
  - Configurable sigma multiplier (default 5.0) in SamplerConfig
  - Falls back to fixed threshold if specified (for backwards compatibility)
  - **Score caching**: Saves frame scores to `video.scores.json` for instant reindexing
    - Skips FFmpeg on reindex if video unchanged (checks mtime + size)
    - ~100s savings on 40-min video reindex
  - **FFmpeg frame extraction**: Uses FFmpeg with input seeking instead of CV2
    - 3.7x faster frame extraction (190ms vs 700ms per frame)
    - Uses libdav1d for AV1 videos (faster decoder)
- ✅ **FFmpeg Scene Detection** - 10-50x faster frame sampling (new default)
  - Uses FFmpeg's hardware-accelerated scene detection filter
  - Only decodes frames at detected scene changes (vs every frame)
  - Respects min/max interval constraints for coverage
  - 30-min video: ~5 seconds (vs 3-8 minutes with Python-based hybrid)
  - Codec-aware decoder selection (libdav1d for AV1, native for others)
  - Use `--sampler hybrid` to fall back to Python-based detection
- ✅ **Combined Vision+Inference** - Single API call per frame (50% fewer calls)
  - Frame + transcript analyzed together in one vision call
  - Better inference: vision model can recognize faces, read text
  - Cost: ~$0.03-0.05 for 30-min video (vs ~$0.06-0.10 before)
- ✅ **Auto-Whisper Transcription** - Enabled by default when no subtitle exists
  - Generates transcripts automatically using faster-whisper
  - ~45 sec for 30-min video on GPU (base model)
  - Use `--no-whisper` to opt-out
- ✅ **Language-coded Subtitles** - Support for yt-dlp style .en.srt files
- ✅ **Async Batch Indexing** - ~10x faster video indexing with concurrent API calls
  - Process multiple frames in parallel using asyncio with semaphore
  - `--concurrency` CLI option to control parallelism (default 10)
  - Rate limit friendly: use 2-3 for free tier, 10-15 for pay-as-you-go
- ✅ **Project Registry** - Organize videos by project with human-friendly slugs
  - `nolan projects create/list/info/delete` commands for project management
  - Projects have internal UUIDs and CLI-facing slugs (e.g., `venezuela`)
  - `nolan index --project <slug>` scopes videos to a project
  - Auto-generated slugs from project names (URL-safe)
  - Database schema v4 with projects table
- ✅ **YouTube Video Download** - Download and organize YouTube videos with yt-dlp
  - Single video, batch, or playlist download
  - Automatic subtitle download (configurable languages)
  - Project-based folder organization
- ✅ **Video Assembly Pipeline** - Two-phase render pipeline for final video output
  - `nolan render-clips`: Pre-render animated scenes (infographics, sync_points) to MP4
  - `nolan assemble`: FFmpeg-based assembly of all assets + voiceover
  - Asset priority: rendered_clip > generated_asset > matched_asset > infographic_asset
  - Automatic scaling/padding to target resolution
  - Support for cut, fade, crossfade transitions
  - Full architecture documented in `docs/plans/2026-01-12-render-pipeline.md`
- ✅ **Scene-Audio Alignment** - `nolan align` command for word-level audio alignment
  - Transcribes audio with word-level timestamps via Whisper
  - Matches scene `narration_excerpt` to word stream using text matching
  - Updates scene_plan.json with `start_seconds` and `end_seconds`
  - Confidence scoring for alignment quality
  - Optional word timestamp export for debugging
- ✅ **Transcription Command** - `nolan transcribe` for audio/video to subtitles
  - Outputs SRT, JSON, or plain text formats
  - GPU (CUDA) with automatic CPU fallback
  - Multiple Whisper model sizes (tiny to large-v3)
- ✅ **B-Roll Image Matching** - `nolan match-broll` command for batch image search and download
  - Searches images for all b-roll scenes using search_query from scene_plan.json
  - Multiple providers: DuckDuckGo (default), Pexels, Pixabay, Wikimedia, Library of Congress
  - Optional vision model scoring (Gemini/Ollama) for relevance ranking
  - Downloads best match for each scene to assets/broll/
  - Updates scene_plan.json with matched_asset paths
  - Supports dry-run mode and skip-existing option
- ✅ **Two-Pass Scene Design** - Professional A/V script workflow based on video essay research
  - Pass 1 (`--beats-only`): Break narration into beats, assign visual categories
  - Pass 2 (default): Enrich beats with category-specific details
  - Visual categories: b-roll, graphics, a-roll, generated, host
  - Identifies "visual holes" (abstract concepts needing creative solutions)
  - Outputs A/V script format (av_script.txt) for human review
  - Based on "The Architecture of the Digital Argument" research
- ✅ **Standalone Script & Design Commands** - Split workflow into separate steps
  - `nolan script` converts essay to script.md + script.json
  - `nolan design` generates scene_plan.json from script.json
  - Script class now supports JSON export/import for workflow persistence
  - Enables review/editing between steps before committing to scene design
- ✅ **Scene Workflow Data Model** - Enhanced Scene dataclass for 5-step video pipeline
  - `SyncPoint` dataclass for word-to-action synchronization (trigger → action at precise time)
  - `Layer` dataclass for complex multi-element scenes (background, overlay, caption)
  - Scene fields for timing alignment: `start_seconds`, `end_seconds`, `subtitle_cues`
  - Animation fields: `animation_type`, `animation_params`, `transition`
  - Progressive enrichment pattern: Scene is a "holder" filled across workflow steps
  - Updated LLM prompt to request sync_points, layers, animation specs
  - Full plan documented in `docs/plans/2026-01-11-scene-workflow.md`
- ✅ **Motion Canvas Engine** - Render-service can export MP4s via Motion Canvas + FFmpeg
  - Generates a temporary Motion Canvas project (project, scene, render entry, spec)
  - Uses Vite + @motion-canvas/vite-plugin + @motion-canvas/ffmpeg for rendering
  - Launches headless Chromium to execute the render pipeline and writes MP4s to output
  - Supports basic spec fields (title, subtitle, items, width, height, duration, theme)
- ✅ **Remotion Engine** - Render-service can export MP4s via Remotion renderer
  - Bundles a temporary Remotion project for each job and renders via @remotion/renderer
  - Infographic composition supports title, subtitle, items, and theme colors
- ✅ **AntV Infographic Engine Enablement** - render-service now supports @antv/infographic via headless Chromium
  - Uses bundled `infographic.min.js` with Puppeteer for SVG extraction
  - Added template aliasing so `steps/list/comparison` map to real AntV templates
  - Added `INFOGRAPHIC_ENGINE` and `engine_mode` to force AntV vs SVG fallback
  - Added `PUPPETEER_EXECUTABLE_PATH`/`CHROME_PATH` support for local Chrome/Edge
  - Debug logging is gated behind `INFOGRAPHIC_DEBUG=1`
- ✅ **Render Service Engine Coverage** - Motion Canvas and Remotion engines now render MP4s
  - Processor wiring routes motion-canvas and remotion jobs to live engines
- ✅ **Render Service Code Quality Refactor** - Cleaned up engine and preset code
  - Extracted common utilities (`ensureDir`, `toNumber`, `toString`) to `engines/utils.ts`
  - Centralized theme definitions in `themes.ts` (used by all 3 engines)
  - Fixed inconsistent null handling: changed 70+ `||` to `??` for numeric params
  - Prevents bugs where falsy values like `0` incorrectly trigger fallbacks
- ✅ **Infographic Scene Integration** - Scene designer supports infographic suggestions
  - Prompt updated to allow infographic visual_type and spec payloads
  - Scene model stores infographic specs and rendered assets
- ✅ **Infographic Batch Rendering** - `nolan render-infographics` renders infographic scenes
  - Writes SVGs to assets/infographics and updates scene_plan.json
- ✅ **Viewer Infographic Review** - project viewer displays infographic specs and previews
  - Summary now includes infographic counts and render status

- ✅ **Infographic CLI Integration** - `nolan infographic` command for generating infographics
  - Connects Python CLI to Node.js render-service via HTTP
  - Three input modes: command-line options, JSON file, stdin pipe
  - Support for templates (steps, list, comparison) and themes (default, dark, warm, cool)
  - Configurable output size and location
- ✅ **Job Processor** - Connect infographic engine to job queue for render-service
  - Job processor polls for pending jobs and processes them through appropriate engines
  - Real-time status and progress updates during rendering
  - Error handling with detailed error messages stored in job
  - Singleton processor started with server
- ✅ **Infographic Engine** - SVG template-based rendering engine for render-service
  - RenderEngine interface abstraction for pluggable engines
  - InfographicEngine with native SVG template generation
  - Multiple templates: steps/sequence, list, comparison
  - Theme support: default, dark, warm, cool color schemes
  - SVG output with gradients, shadows, and proper styling
  - Note: Replaced @antv/infographic due to browser-only limitations
- ✅ **Public Domain Image Sources** - New providers for public domain images
  - Wikimedia Commons (100M+ images, no API key, CC licenses)
  - Library of Congress (historical photos, no API key, public domain)
  - Smithsonian Open Access (2.8M+ images, API key from api.data.gov, CC0)
- ✅ **Image Search Scoring** - Vision model scoring for image relevance
  - Score images from 0-10 with explanations
  - Support for Gemini (cloud) and Ollama (local) vision models
  - Quality scoring (0-10) based on resolution and aspect ratio
  - Combined sorting: relevance first, quality as tiebreaker
  - Fallback download: thumbnail → main URL if thumbnail fails
  - Optional context for better scoring (e.g., "for a documentary")
- ✅ **Image Search** - `nolan image-search` command for finding images from web/stock photos
  - DuckDuckGo search (no API key required)
  - Pexels and Pixabay stock photo APIs (optional, with API keys)
  - JSON output with URLs, thumbnails, dimensions
  - Extensible provider system for adding more sources
- ✅ **ComfyUI Custom Workflows** - Full workflow customization support
  - Load any ComfyUI workflow exported in API format
  - Explicit prompt node selection (`--prompt-node`)
  - Generic parameter overrides (`--set "node:param=value"`)
  - Auto-detection fallback for common workflow patterns
- ✅ **Video Index Viewer** - `nolan browse` command for browsing indexed video library
  - Browse videos and their segments in web UI
  - View frame descriptions, transcripts, inferred context
  - View clusters with summaries
  - Video preview playback at timestamps
  - Full-text search across segments
- ✅ **Scene Clustering** - `nolan cluster` command for grouping segments into story moments
  - Groups by shared characters, location, and story context
  - Optional LLM-based story boundary detection (`--refine`)
  - Cluster-level summaries for deeper narrative understanding
- ✅ **Export command** - `nolan export` for full JSON output with all fields
- ✅ **Gemini vision CLI** - `--vision gemini` option for cloud-based frame analysis (3-4x faster)
- ✅ **GPU Whisper** - CUDA acceleration with automatic CPU fallback
- ✅ **Hybrid inference** - LLM fusion of vision + transcript with inferred context (people, location, story)
- ✅ **Whisper integration** - Auto-generate transcripts using faster-whisper
- ✅ **Local VLM support** - Ollama integration with qwen3-vl:8b (switchable to other models)
- ✅ **Smart sampling** - 5 strategies (ffmpeg_scene, hybrid, fixed, scene_change, perceptual_hash)
- ✅ **Transcript support** - SRT, VTT, Whisper JSON loading and alignment
- ✅ **Essay Style System** - Consistent visual branding across video essay motion effects
  - **EssayStyle type** - Complete style definition with colors, typography, layout, motion, texture
  - **11 flagship styles** - noir-essay, cold-data, modern-creator, academic-paper, documentary, podcast-visual, retro-synthwave, breaking-news, minimalist-white, true-crime, nature-documentary
  - **Accent markup** - `**word**` syntax for emphasizing key terms in quotes and titles
  - **Auto-accent detection** - Numbers, dates, percentages, money auto-detected per style rules
  - **Style-driven presets** - All effect presets now support style parameter:
    - Title, quote, text (highlight, typewriter, glitch, bounce, scramble, gradient, pop, citation)
    - Chart (bar, line, pie, donut), statistic (counter, comparison, percentage)
    - Image (ken-burns, zoom-focus, parallax, photo-frame, document-reveal)
    - Overlay (picture-in-picture, vhs-retro, film-grain, light-leak, camera-shake, screen-frame, audio-waveform, data-ticker, social-media-post, video-frame-stack)
    - Transition (slide, wipe, dissolve, zoom, blur, glitch)
    - Progress, annotation, comparison, timeline, countdown, map
  - **Backward compatible** - Style parameter is optional; legacy color params still work
  - **Styles API** - Full REST API for styles:
    - `GET /styles` - List all available styles
    - `GET /styles/:id` - Get full style definition
    - `POST /styles/:id/resolve-accent` - Test accent resolution
    - `POST /styles/:id/preview` - Generate style preview with sample content
  - **Validation helper** - `validateSceneContent()` checks content against style accent rules
  - **LLM Authoring Guide** - Documentation for LLMs on how to write styled content (`render-service/docs/LLM_CONTENT_AUTHORING.md`)
  - **Texture rendering** - Grain, vignette, and gradient overlays rendered in Motion-Canvas engine
  - **Remotion style integration** - All 11 EssayStyles mapped to Remotion themes with texture support
  - **Font loading** - Inter, Georgia, Playfair Display loaded in Motion-Canvas for style fonts
  - **Style parameter convention** - Use `style` param when possible; use `essayStyle` when another `style` param exists (e.g., animation style, frame style)
  - **Known limitations**:
    - Motion timing (enterFrames, exitFrames, easing) not yet derived from style; uses per-effect defaults
    - Helper functions (getTextureSettings, getFontProps, getSafeArea) available but not fully utilized
- ✅ **Layout System** - Region-based positioning for effect placement
  - **Region type** - Position defined by `{ x, y, w, h, align, valign, padding }` (all percentage-based 0-1)
  - **11 layout templates** - Predefined region configurations for video essays:
    - `center` - Single centered region (default)
    - `full` - Full bleed with safe margins
    - `lower-third` - Bottom bar for names, citations
    - `upper-third` - Top bar for chapter titles
    - `split` - Left/right 50-50 comparison
    - `split-60-40` / `split-40-60` - Asymmetric left/right emphasis
    - `thirds` - Three equal columns
    - `split-with-lower` - Two columns + bottom bar
    - `presenter` - Main content + lower third
    - `grid-2x2` - Four equal quadrants
  - **Render API integration** - `POST /render` accepts `layout` parameter:
    - Template name: `{ layout: "lower-third" }`
    - Custom regions: `{ layout: { regions: { main: { x: 0.1, y: 0.8, w: 0.5, h: 0.15 } } } }`
  - **Engine integration** - Layouts resolved before bundling, passed as CSS styles to components
  - **Layouts endpoint** - `GET /render/layouts` returns all templates with region definitions
  - **Remotion CSS conversion** - `regionToRemotionStyle()` converts regions to CSS flexbox properties
  - **Motion Canvas support** - `regionToMotionCanvas()` converts to center-based coordinates
  - **Style layout merge** - `applyStyleToRegion()` merges EssayStyle.layout with region defaults
  - **Extensible architecture** - Phase 1 (templates) complete; designed for Phase 2 (composition) and Phase 3 (full CSS)
- ✅ **Asset Management System** - File-based visual assets for motion effects
  - **Folder structure** - Organized by style with common fallback:
    - `assets/styles/{style-id}/` - Style-specific assets
    - `assets/common/` - Shared assets (fallback for all styles)
  - **AssetManager API** - Python module for asset access:
    - `get_asset(style, name)` - Get path with style→common fallback
    - `get_asset_content(style, name)` - Read file content directly
    - `get_icon(style, name)` - Convenience for `.svg` icons
    - `list_assets(style, category)` - List available assets
  - **Common icons** - 9 SVG icons (24x24 viewBox, `currentColor` stroke):
    - check, star, arrow-up, trending-up, code, database, users, zap, award
  - **Design decision** - Chose file-based over database for simplicity
    - Database-backed system in backlog for future scaling (100+ assets)
  - **Documentation** - `assets/README.md` with guidelines and usage
