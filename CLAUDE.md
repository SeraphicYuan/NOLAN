# Directory Restrictions
- NEVER read, write, edit, or create files outside the current project directory
- NEVER use absolute paths that reference locations outside this folder
- All paths must be relative to the project root or within its subdirectories
- If a task requires accessing external files, ask for permission first

You can also combine it with bash restrictions:

# Workspace Boundaries
Stay within D:\ClaudeProjects\NOLAN and its subdirectories only.
- Do not access parent directories (no `../` paths leading outside the project)
- Do not use absolute paths to system directories
- All bash commands must operate within the project folder

# Python Environment Rules
- This project uses a Conda environment named `nolan`.
- Always use the python binary located at: `D:\env\nolan\python.exe`
- Always use pip from: `D:\env\nolan\Scripts\pip.exe`
- Do not use system python or create a new .venv folder.

# Documentation Rules
After completing any new feature, update the corresponding documentation:
- Default update goes to "IMPLEMENTATION_STATUS.md"
- If there's no corresponding documentation (*.md), create it when necessary
- Keep updates concise: what changed, usage example, benefits

# Tool Permissions
- Before asking for user approval on any tool use, check `.claude/settings.local.json` first
- If the command pattern is listed in the `permissions.allow` array, proceed without asking
- Only ask for approval if the command is NOT covered by existing permissions

# Claude Domaine
- Strictly stay within this folder

# Notification Rule
- When requiring user approval for any action, play a notification sound first
- Use PowerShell to play a 3-tone ascending sound: `powershell -c "[console]::beep(1000,200); [console]::beep(1200,200); [console]::beep(1500,300)"`
- This helps alert the user that attention is needed

# Project Defaults
- Default Gemini model: `gemini-3-flash-preview`

# Quality Assurance Protocol
After completing any task, follow this self-review loop:

1. **Verify the result** - Actually test/run/check the output of your work
2. **Identify issues** - Look for bugs, edge cases, missing functionality, or room for improvement
3. **Fix and iterate** - If issues found, fix them immediately
4. **Repeat** - Continue the loop until satisfied that:
   - The code works correctly (tests pass, no errors)
   - The output meets the user's stated purpose
   - The implementation aligns with project goals (HERMES: reliable information aggregation)
   - No obvious improvements remain

**Do not** mark work as complete or report success until this loop is satisfied.
**Do not** wait for user to find bugs - proactively catch them yourself.

Examples of what to check:
- Run the code and verify output makes sense
- Check edge cases (empty input, missing data, errors)
- Review generated files for correctness
- Test the user-facing experience end-to-end
- Compare actual vs expected behavior

# Code Review Protocol (Karpathy-Inspired)

Before writing or modifying code, apply these four principles:

## 1. Think Before Coding
**No silent assumptions. Explicit reasoning only.**

- State uncertainties clearly - don't guess
- When ambiguity exists, present options and ask
- Question your approach if simpler alternatives exist
- If confused, ask for clarification before proceeding

**Bad:** Silently assume the user wants async when they said "fetch"
**Good:** "Should this be sync or async? The current codebase uses X pattern."

## 2. Simplicity First
**Minimal, focused solutions. YAGNI ruthlessly.**

- Implement ONLY what was requested
- Avoid abstractions unless used 3+ times
- Skip error handling for impossible scenarios
- Target 50 lines over 200 lines when both work
- No speculative features ("might need later")

**Bad:** Create AbstractFetcherFactory for one RSS fetcher
**Good:** Simple RSSFetcher class, refactor when needed

## 3. Surgical Changes
**Touch only what's necessary. Leave everything else alone.**

- Modify only code directly related to the request
- Don't refactor working code while fixing bugs
- Preserve existing style (quotes, indentation, naming)
- Don't "improve" unrelated code you happen to see
- Remove only imports/variables YOUR changes made obsolete

**Bad:** While fixing a bug, also reformat the file and rename variables
**Good:** Fix the bug. Period.

## 4. Goal-Driven Execution
**Define success criteria before coding.**

Transform vague requests into testable goals:
- "Add validation" → "Write test for invalid input, make it pass"
- "Improve performance" → "Reduce response time from X to Y ms"
- "Fix the bug" → "Reproduce with test, verify test fails, fix, verify passes"

**Every task should end with verification:**
```
1. What does "done" look like?
2. How will I verify it works?
3. Run verification before reporting success
```

## Code Review Checklist

When reviewing your own code (or receiving review), check:

| Category | Question |
|----------|----------|
| **Assumptions** | Did I make any silent assumptions? Should I have asked? |
| **Scope** | Did I change only what was requested? Any scope creep? |
| **Simplicity** | Is there a simpler way? Can I delete code and still pass? |
| **Side Effects** | Did I touch unrelated code, comments, or formatting? |
| **Verification** | Did I actually run and test this? Evidence? |
| **Style** | Does it match surrounding code conventions? |

## When to Apply Rigor

**Full rigor (all 4 principles):**
- New features
- Bug fixes
- Refactoring
- Multi-file changes

**Light touch (common sense):**
- Typo fixes
- Single-line obvious changes
- Config value updates

# Video Analysis Workflow

**Trigger words:** "analyze video", "video analysis", "study this video", "what techniques"

When the user wants to analyze a video (for text overlays, visual effects, techniques, etc.):

## 1. Create Project Folder

```
video_analysis/
├── <project_slug>/           # Use descriptive name (e.g., "adlerian_selfhelp")
│   ├── source/               # Downloaded video + subtitles
│   ├── frames/               # Extracted frames (if needed)
│   ├── analyze.py            # Analysis script
│   ├── index.db              # SQLite segment database
│   ├── findings.md           # Key insights and results
│   └── techniques.json       # Raw extracted data
```

## 2. Analysis Pipeline

Use NOLAN's built-in video analysis tools:

```python
from src.nolan.youtube import YouTubeClient
from src.nolan.indexer import VideoIndex, HybridVideoIndexer
from src.nolan.vision import create_vision_provider, VisionConfig
from src.nolan.sampler import FFmpegSceneSampler
from src.nolan.whisper import WhisperTranscriber, WhisperConfig

# 1. Download video
client = YouTubeClient(output_dir=Path("source"))
result = client.download(url)

# 2. Create indexer with frame analysis
index = VideoIndex(Path("index.db"))
vision = create_vision_provider(VisionConfig(provider="gemini"))
sampler = FFmpegSceneSampler(min_interval=2.0, max_interval=10.0)
whisper = WhisperTranscriber(WhisperConfig(model_size="base"))

indexer = HybridVideoIndexer(
    vision_provider=vision,
    index=index,
    sampler=sampler,
    whisper_transcriber=whisper,
    enable_transcript=True,
    enable_inference=True
)

# 3. Run indexing
segment_count = await indexer.index_video(video_path)

# 4. Query segments
segments = index.get_segments(str(video_path))
```

## 3. Generate findings.md

Include in findings:
- **Video Info**: URL, title, duration, segments analyzed
- **Summary**: Key findings in numbered list
- **Techniques Detected**: Tables with timestamps and descriptions
  - Text overlays
  - Visual effects
  - Color schemes
  - Layout patterns
- **NOLAN Templates**: Which existing templates can be used
- **New Templates Needed**: Patterns that need new implementations

## 4. Look For

When analyzing videos for techniques:
- **Text Cards**: Quote presentations, key statements
- **Annotations**: Underlines, highlights, circles, arrows
- **Transitions**: Fades, slides, zooms
- **Data Visualization**: Stats, percentages, comparisons
- **Typography**: Font choices, animations, timing
- **Color Usage**: Mood, emphasis, branding
- **Layout Patterns**: Lower thirds, full-screen, split-screen

## 5. Promoting Techniques to NOLAN

When implementing a technique discovered from video analysis:

1. **Create the template/effect** in `src/nolan/renderer/scenes/` or `effects.py`
2. **Add tests** in `scripts/test_<template_name>.py`
3. **Update findings.md** with a "Promoted to NOLAN" section:

```markdown
## Promoted to NOLAN

| Technique | Template/Effect | File | Date |
|-----------|-----------------|------|------|
| Portrait slide + reveal | `portrait_reveal` | `scenes/portrait_reveal.py` | 2026-02-01 |
| Position animation | `MoveTo` effect | `effects.py` | 2026-02-01 |
```

4. **Update IMPLEMENTATION_STATUS.md** with the new template count

This creates a traceable link between video analysis insights and implemented features.

## Module Reference

| Module | What it does |
|--------|--------------|
| `youtube.py` | Download videos, get metadata |
| `sampler.py` | Frame extraction strategies (FFmpeg-based) |
| `whisper.py` | Speech-to-text transcription |
| `vision.py` | Frame analysis (Gemini/Ollama) |
| `indexer.py` | SQLite segment storage, project management |
| `vector_search.py` | Semantic search across segments |
| `clustering.py` | Scene grouping and story boundaries |