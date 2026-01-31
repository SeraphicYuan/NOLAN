# NOLAN File Organization

**Last Updated:** 2026-01-31
**Status:** Cleanup completed

## Overview

NOLAN follows a structured file organization to keep the codebase clean and maintainable.

---

## Historical Issues (Now Resolved)

The root directory had accumulated many files that didn't have a proper home:

### Scattered Test Files (root)
- `test_hub.py`, `test_hub2.py`, `test_hub3.py`, `test_hub4.py`, `test_hub5.py` - Ad-hoc test scripts
- `test_essay.md` - Test fixture
- `test_output.txt`, `test_output2.txt` - Test outputs

### Debug/Exploration JSON Files (root)
- `all_test.json`, `loc_test.json`, `wikimedia_test.json` - Search test outputs
- `chavez_scored_gemini.json`, `chavez_scored_ollama.json`, `chavez_search.json` - Scoring experiments
- `clusters.json`, `library_clusters.json`, `venezuela_dark_secret_clusters.json` - Cluster exports
- `full_export.json`, `indexed_*.json` - Index exports
- `image_search_results.json` - Search results
- `effects_list.json` - Effects export

### Stray Directories
- `asset/` - Contains a single video file (should be in a project or library)
- `output/` - Nearly empty, seems unused
- `test_output/` - Test outputs with videos and screenshots
- `comfy_api/` - A single workflow file

### Duplicate Concepts
- `assets/` vs `asset/` - Confusing naming
- `output/` vs `test_output/` - Unclear purpose

---

## Proposed Structure

```
NOLAN/
├── src/nolan/              # Python source code
│   └── *.py
│
├── tests/                  # Pytest test suite
│   ├── conftest.py         # Shared fixtures
│   ├── test_*.py           # Unit/integration tests
│   └── fixtures/           # Test data files
│       ├── essays/         # Sample essays for testing
│       └── workflows/      # Test workflow files
│
├── docs/                   # Documentation
│   ├── plans/              # Design/planning documents
│   └── *.md
│
├── projects/               # User video projects
│   └── <project-name>/     # Each project is self-contained
│       ├── project.yaml    # Project config
│       ├── source/         # Source videos for library
│       ├── assets/         # Generated assets
│       │   ├── generated/  # ComfyUI/AI generated
│       │   ├── matched/    # Library-matched clips
│       │   ├── lottie/     # Rendered Lottie animations
│       │   ├── infographics/
│       │   └── voiceover/
│       ├── output/         # Final rendered outputs
│       ├── scene_plan.json
│       ├── script.md
│       └── *.srt           # Subtitles
│
├── assets/                 # Shared assets (not project-specific)
│   ├── common/
│   │   ├── lottie/         # Lottie template library
│   │   ├── icons/          # Icon library
│   │   └── styles/         # Style presets
│   └── README.md
│
├── workflows/              # ComfyUI workflow files
│   ├── image/              # Image generation workflows
│   └── video/              # Video generation workflows
│
├── render-service/         # TypeScript render service
│
├── .scratch/               # Temporary/debug outputs (gitignored)
│   └── *.json, *.txt, etc.
│
├── nolan.yaml              # Main config
├── pyproject.toml          # Python project config
├── CLAUDE.md               # Claude instructions
├── IMPLEMENTATION_STATUS.md
└── README.md
```

---

## Migration Status

**Completed 2026-01-31:**

- ✅ Created `tests/fixtures/essays/` and `tests/fixtures/workflows/`
- ✅ Created `workflows/image/` and `workflows/video/`
- ✅ Created `.scratch/` for temporary/debug outputs
- ✅ Moved `test_hub*.py` to `tests/`
- ✅ Moved `test_essay.md` to `tests/fixtures/essays/`
- ✅ Moved all debug JSON files to `.scratch/`
- ✅ Moved `comfy_api/` contents to `workflows/image/`
- ✅ Removed empty `output/` and `asset/` directories
- ✅ Updated `.gitignore` to exclude `.scratch/`, large project files, and vector stores

---

## Code Fixes (Root Cause Prevention)

**Fixed CLI default paths in `src/nolan/cli.py`:**

| Command | Old Default | New Default |
|---------|-------------|-------------|
| `nolan export --all` | `library_export.json` | `.scratch/library_export.json` |
| `nolan cluster --all` | `library_clusters.json` | `.scratch/library_clusters.json` |
| `nolan generate-test` | `./test_output.png` | `.scratch/test_output.png` |
| `nolan image-search` | `./image_search_results.json` | `.scratch/image_search_results.json` |
| `nolan yt-download` | `./downloads` | `.scratch/downloads` |

These commands now default to the `.scratch/` directory instead of the project root, preventing future file clutter

---

## File Placement Rules

### Source Code → `src/nolan/`
All Python source code for the NOLAN package.

### Tests → `tests/`
- `test_*.py` - Pytest test files
- `conftest.py` - Shared fixtures
- `fixtures/` - Test data (essays, workflows, sample files)

### Documentation → `docs/`
- `*.md` - User documentation
- `plans/` - Design documents, architecture decisions

### User Projects → `projects/<name>/`
Each video project is self-contained with:
- `project.yaml` - Project configuration
- `source/` - Input videos for the library
- `assets/` - Generated/matched assets
- `output/` - Final video outputs
- `scene_plan.json`, `script.md` - Pipeline outputs

### Shared Assets → `assets/`
Non-project-specific resources:
- Lottie template library
- Icon library
- Style presets

### Workflows → `workflows/`
ComfyUI workflow files organized by type.

### Temporary/Debug → `.scratch/`
- Debugging outputs
- Exploration results
- Temporary files
- Should be gitignored

---

## Database & Vector Store Locations

| Store | Location | Purpose |
|-------|----------|---------|
| Video library DB | `nolan.db` (root) | Indexed videos, segments, clusters |
| Template vectors | `assets/common/lottie/.template_vectors/` | Template search embeddings |
| Video vectors | `chroma_db/` (root) | Video segment embeddings |

Consider consolidating to:
```
.data/
├── nolan.db
├── template_vectors/
└── video_vectors/
```
