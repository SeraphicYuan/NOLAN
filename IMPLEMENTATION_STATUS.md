# NOLAN Implementation Status

**Version:** 0.1.0
**Status:** Complete
**Last Updated:** 2026-01-11

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

### Hybrid Indexing
- **Vision Provider** - Switchable vision models (Ollama/Gemini)
  - Default: qwen3-vl:8b via Ollama
  - Configurable host/port/model
- **Smart Sampling** - 4 strategies for frame extraction:
  - Fixed interval
  - Scene change detection (OpenCV)
  - Perceptual hashing (skip duplicates)
  - Hybrid (recommended - combines time bounds with scene detection)
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
- **LLM Fusion** - Combines vision + transcript for richer understanding
- **Inferred Context** - Best guesses for:
  - People (named characters, speakers)
  - Location (setting identification)
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

### Integrations
- **ComfyUI Client** - Image generation via local ComfyUI API
- **Viewer Server** - FastAPI-based local viewer for reviewing outputs
- **Library Viewer** - Web UI for browsing indexed video library (`nolan browse`)

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
| `nolan infographic` | Generate infographics via render-service |

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

# Index with Gemini vision (cloud - faster)
nolan index path/to/videos --vision gemini

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
```

## Test Coverage

132 tests covering all modules:
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
- Clustering: 34 tests (NEW)

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
│   ├── library_viewer.py # Library browser server
│   ├── image_search.py  # Image search providers
│   └── templates/
│       ├── index.html   # Viewer UI
│       └── library.html # Library browser UI
├── tests/               # Test suite (132 tests)
├── render-service/      # Node.js microservice for infographics/animations
│   ├── src/
│   │   ├── server.ts    # Express API server
│   │   ├── routes/      # API endpoints (health, render)
│   │   ├── jobs/        # Job queue and types
│   │   └── engines/     # Render engines (infographic, etc.)
│   └── package.json
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

## Next Steps (Backlog)

- **LLM infographic placement** - Detect data points in scripts and suggest infographic placement
- **HunyuanOCR integration** - Text extraction from video frames (subtitles, on-screen text, titles)
- **Image search browser display** - View image search results in web UI
- **Vision model image selection** - Auto-select best matching images using vision model

## Recently Completed

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
- ✅ **Smart sampling** - 4 strategies (fixed, scene change, perceptual hash, hybrid)
- ✅ **Transcript support** - SRT, VTT, Whisper JSON loading and alignment
