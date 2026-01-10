# NOLAN Implementation Status

**Version:** 0.1.0
**Status:** Complete
**Last Updated:** 2026-01-07

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

### Hybrid Indexing (NEW)
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

### Integrations
- **ComfyUI Client** - Image generation via local ComfyUI API
- **Viewer Server** - FastAPI-based local viewer for reviewing outputs

### CLI Commands
| Command | Description |
|---------|-------------|
| `nolan process <essay.md>` | Full pipeline: essay → script → scenes |
| `nolan index <video_folder>` | Index video library for snippet matching |
| `nolan serve` | Launch local viewer to review outputs |
| `nolan generate` | Generate images via ComfyUI |

## Usage

```bash
# Install in development mode
pip install -e ".[dev]"

# Process an essay
nolan process path/to/essay.md -o ./output

# Index video library
nolan index path/to/videos --recursive

# Launch viewer
nolan serve -p ./output
```

## Test Coverage

81 tests covering all modules:
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
- Vision Provider: 9 tests (NEW)
- Sampler: 11 tests (NEW)
- Transcript: 15 tests (NEW)
- Analyzer: 10 tests (NEW)

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
│   ├── vision.py        # Vision providers (Ollama, Gemini) [NEW]
│   ├── sampler.py       # Smart frame sampling [NEW]
│   ├── transcript.py    # Transcript loading/alignment [NEW]
│   ├── analyzer.py      # Segment analysis + inference [NEW]
│   └── templates/
│       └── index.html   # Viewer UI
├── tests/               # Test suite (81 tests)
├── pyproject.toml       # Package configuration
└── .env                 # API keys (not committed)
```

## Requirements

- Python 3.10+
- Gemini API key (set `GEMINI_API_KEY` in .env)
- ComfyUI (optional, for image generation)

## Next Steps (Backlog)

- **HunyuanOCR integration** - Text extraction from video frames (subtitles, on-screen text, titles)
- **Whisper integration** - Auto-generate transcripts for videos without them
- Internet asset collection (Pexels, Pixabay integration)

## Recently Completed

- ✅ **Local VLM support** - Ollama integration with qwen3-vl:8b (switchable to other models)
- ✅ **Smart sampling** - 4 strategies (fixed, scene change, perceptual hash, hybrid)
- ✅ **Hybrid indexing** - Visual + transcript fusion with inferred context
- ✅ **Transcript support** - SRT, VTT, Whisper JSON loading and alignment
