# NOLAN - Video Essay Pipeline Design

**Date:** 2026-01-07
**Status:** Draft

---

## Overview

NOLAN is a CLI tool that transforms a structured essay into a complete video production package - script, scene plan, and organized assets ready for a video editor.

### Core Workflow

```
essay.md → [NOLAN] → project_output/
                        ├── script.md         (YouTube-ready narration)
                        ├── scene_plan.json   (timestamped scenes with asset specs)
                        ├── assets/
                        │   ├── generated/    (ComfyUI images)
                        │   └── matched/      (clips from your library)
                        └── index.html        (viewer to review everything)
```

### Main Commands

| Command | Description |
|---------|-------------|
| `nolan process <essay.md>` | Full pipeline: essay → script → scenes → assets |
| `nolan index <video_folder>` | Index video library for snippet matching |
| `nolan serve` | Launch local viewer to review outputs |

### Key Principle

Each stage outputs files you can inspect and manually adjust before continuing. It's a pipeline, not a black box.

---

## Components

### 1. Essay-to-Script Conversion

**Input:** Structured Markdown essay with sections and headings.

**What the Gemini-powered conversion does:**

1. **Adapts tone for spoken word** - written prose → natural narration
   - Shortens complex sentences
   - Adds verbal transitions ("Now, let's look at...", "Here's the key insight...")
   - Removes things that work in text but not speech (parentheticals, dense citations)

2. **Preserves structure** - section headings become natural breakpoints
   - Each section maps to a segment of the video
   - Logical flow stays intact

3. **Estimates timing** - approximate word count → duration per section
   - ~150 words per minute baseline (adjustable)
   - Gives rough total runtime upfront

**Output:** `script.md` with:
```markdown
## Section: Introduction [0:00 - 0:45]
[Narration text here...]

## Section: The Problem [0:45 - 2:30]
[Narration text here...]
```

**User control:** Edit `script.md` before proceeding to scene design. Re-run scene design after edits.

---

### 2. Scene Design & Asset Suggestions

**Input:** The `script.md` from the previous stage.

For each script section, Gemini analyzes the narration and generates a **scene breakdown**:

```json
{
  "section": "The Problem",
  "timestamp": "0:45 - 2:30",
  "scenes": [
    {
      "id": "scene_003",
      "start": "0:45",
      "duration": "15s",
      "narration_excerpt": "Every day, millions of hours are spent...",
      "visual_type": "b-roll",
      "visual_description": "Time-lapse of people working at computers in an office",
      "asset_suggestions": {
        "search_query": "office timelapse workers computers",
        "comfyui_prompt": "time-lapse photography, modern office space, people working at desks with computers, natural lighting, 4k",
        "library_match": true
      }
    }
  ]
}
```

**Each scene includes:**
- Timestamp and duration
- Which narration it covers
- Visual type: `b-roll`, `graphic`, `text-overlay`, `generated-image`
- Description of what should appear on screen
- Asset suggestions: search terms, ComfyUI prompt, flag to search library

**Output:** `scene_plan.json` - the complete visual blueprint for the video.

---

### 3. Video Library Indexing

**Purpose:** Build a searchable index of personal footage and stock videos so NOLAN can suggest relevant clips for each scene.

**Command:**
```
nolan index /path/to/your/videos --recursive
```

**How it works:**

1. **Scans video files** - mp4, mov, webm, etc.
2. **Samples frames** - 1 frame every 5-10 seconds (configurable)
3. **Analyzes with Gemini** - each frame gets a visual description
4. **Stores locally** - SQLite database with video metadata and descriptions

#### Smart Sampling Approaches (Backlog)

Fixed interval sampling wastes API calls on static content. Here are smarter approaches to implement:

**Approach 1: Scene Change Detection (OpenCV)**
```python
import cv2

def detect_scene_changes(video_path, threshold=30.0):
    """Only sample when content actually changes."""
    cap = cv2.VideoCapture(video_path)
    prev_frame = None
    keyframes = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if prev_frame is not None:
            diff = cv2.absdiff(prev_frame, gray)
            change_score = diff.mean()

            if change_score > threshold:  # Scene changed!
                keyframes.append((cap.get(cv2.CAP_PROP_POS_MSEC), frame))
        else:
            keyframes.append((0, frame))  # First frame

        prev_frame = gray

    return keyframes
```

**Approach 2: FFmpeg Keyframe Extraction (Fastest)**
```bash
# Extract only I-frames (natural cut points)
ffmpeg -i video.mp4 -vf "select=eq(pict_type\,I)" -vsync vfr keyframe_%04d.jpg

# With timestamps
ffprobe -select_streams v -show_frames -show_entries frame=pict_type,pts_time -of csv video.mp4 | grep ",I,"
```

**Approach 3: Perceptual Hashing (Skip Duplicates)**
```python
import imagehash
from PIL import Image

def is_duplicate(frame1, frame2, threshold=5):
    """Skip frames that look nearly identical."""
    hash1 = imagehash.phash(Image.fromarray(frame1))
    hash2 = imagehash.phash(Image.fromarray(frame2))
    return abs(hash1 - hash2) < threshold

# Use with fixed sampling to skip similar frames
def sample_with_dedup(video_path, interval=2.0, hash_threshold=5):
    frames = extract_at_interval(video_path, interval)
    unique_frames = []
    last_hash = None

    for timestamp, frame in frames:
        current_hash = imagehash.phash(Image.fromarray(frame))
        if last_hash is None or abs(current_hash - last_hash) >= hash_threshold:
            unique_frames.append((timestamp, frame))
            last_hash = current_hash

    return unique_frames
```

**Approach 4: Hybrid (Recommended)**
```python
def smart_sample(video_path, min_interval=1.0, max_interval=30.0, change_threshold=25.0):
    """
    Combines time bounds with scene detection:
    - Never sample more than once per min_interval
    - Always sample at least once per max_interval
    - Sample immediately on scene changes (within bounds)
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    prev_gray = None
    last_sample_time = -max_interval
    keyframes = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        current_time = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        should_sample = False
        time_since_last = current_time - last_sample_time

        # Always sample if max_interval exceeded
        if time_since_last >= max_interval:
            should_sample = True
        # Check for scene change if min_interval passed
        elif time_since_last >= min_interval and prev_gray is not None:
            diff = cv2.absdiff(prev_gray, gray).mean()
            if diff > change_threshold:
                should_sample = True

        if should_sample:
            keyframes.append((current_time, frame))
            last_sample_time = current_time

        prev_gray = gray

    return keyframes
```

**Expected API call reduction:**

| Video Type | Fixed 5s | Smart Sampling | Reduction |
|------------|----------|----------------|-----------|
| Talking head | 120 calls | 15-20 calls | ~85% |
| Documentary | 120 calls | 30-40 calls | ~70% |
| Action/fast cuts | 120 calls | 80-100 calls | ~25% |
| Slideshow | 120 calls | 10-15 calls | ~90% |

**Index structure (per video):**
```json
{
  "path": "/videos/b-roll/city_night.mp4",
  "duration": "00:02:34",
  "indexed_at": "2026-01-07",
  "segments": [
    {"timestamp": "00:00:05", "description": "Aerial view of city skyline at dusk, warm orange lighting"},
    {"timestamp": "00:00:15", "description": "Close-up of car headlights on busy street"}
  ]
}
```

**Matching to scenes:**
- When processing a scene, NOLAN queries the index
- Matches `visual_description` against indexed segments
- Returns top candidates with timestamps for easy scrubbing

**Cost management:**
- Indexing is one-time per video (cached)
- Only re-indexes if file changes (checksum comparison)
- Estimated: ~$0.01-0.02 per minute of video indexed

#### Hybrid Indexing (Visual + Transcript) (Backlog)

When transcripts are available, combine visual descriptions with audio to create richer segment metadata.

**Enhanced Segment Model:**
```json
{
  "timestamp_start": "00:00:05",
  "timestamp_end": "00:00:15",
  "frame_description": "Man in dark suit walking through ornate hallway with marble floors",
  "transcript": "The President made his way through the West Wing, preparing for the most important speech of his career.",
  "combined_summary": "President walking through West Wing hallway before major speech",
  "inferred_context": {
    "people": ["President (unnamed, male)"],
    "location": "West Wing, White House",
    "story_context": "Preparation for significant political address",
    "confidence": "high"
  }
}
```

**Key Insight: Inferred Context**

The LLM can make educated guesses about objects, people, or story elements when evidence from both sources supports it - but only when available, not forced:

```python
async def analyze_segment(
    frame_desc: str,
    transcript: str,
    llm: LLMClient
) -> dict:
    prompt = f"""Analyze this video segment based on visual and audio information.

VISUAL: {frame_desc}
AUDIO: {transcript}

Provide:
1. combined_summary: A 1-2 sentence description capturing both visual and audio
2. inferred_context: ONLY if evidence supports it (don't guess without basis):
   - people: Named or identifiable individuals (with evidence source)
   - location: Specific place if identifiable
   - story_context: What's happening narratively
   - objects: Notable items relevant to the content
   - confidence: "high" (explicit mention), "medium" (strong implication), "low" (educated guess)

If there's insufficient evidence for any field, omit it entirely.
Return as JSON."""

    response = await llm.generate(prompt)
    return json.loads(response)
```

**Inference Examples:**

| Visual | Transcript | Inferred |
|--------|------------|----------|
| "Man at podium with American flags" | "...and that's why I'm announcing today..." | people: ["speaker (political figure)"], location: "press briefing room" |
| "Close-up of hands typing on laptop" | "Sarah had been coding for 12 hours straight" | people: ["Sarah"], story_context: "extended coding session" |
| "Aerial shot of factory buildings" | "Tesla's Gigafactory produces..." | location: "Tesla Gigafactory", objects: ["factory buildings"] |
| "Person walking on beach" | "[ambient waves, no speech]" | (minimal inference - only visual description) |

**Transcript Alignment:**

```python
def align_transcript_to_frames(
    frames: list[dict],
    transcript: list[dict]
) -> list[dict]:
    """
    Align timestamped transcript chunks to frame sample windows.

    frames: [{"timestamp": 5.0, "description": "..."}]
    transcript: [{"start": 3.2, "end": 4.8, "text": "..."}, ...]
    """
    segments = []

    for i, frame in enumerate(frames):
        start = frame["timestamp"]
        end = frames[i + 1]["timestamp"] if i + 1 < len(frames) else start + 10

        # Collect transcript chunks within this time window
        text_chunks = [
            t["text"] for t in transcript
            if t["start"] >= start and t["start"] < end
        ]

        segments.append({
            "timestamp_start": start,
            "timestamp_end": end,
            "frame_description": frame["description"],
            "transcript": " ".join(text_chunks) if text_chunks else None
        })

    return segments
```

**Workflow:**

```
Video File
    │
    ├──► Frame Sampling ──► Vision LLM ──► frame_description
    │
    └──► Audio Extract ──► Whisper ──► transcript (with timestamps)
                                            │
                                            ▼
                              Align transcript to frame windows
                                            │
                                            ▼
                    ┌───────────────────────┴───────────────────────┐
                    │                                               │
                    ▼                                               ▼
          LLM Fusion + Inference                          Embedding Model
                    │                                               │
                    ▼                                               ▼
          combined_summary                                   vector embedding
          inferred_context                                  (for semantic search)
```

**Search Benefits:**

With hybrid indexing, searches can match on:
- Visual content: "aerial city shot"
- Spoken content: "President's speech"
- Inferred context: "White House", "Tesla factory"
- Combined: "interview about climate change" (person talking + topic mentioned)

---

### 4. ComfyUI Integration

**Purpose:** Generate custom images for scenes where stock footage or library doesn't fit - diagrams, stylized visuals, conceptual imagery.

**How it connects:**

ComfyUI exposes a local API (typically `http://127.0.0.1:8188`). NOLAN sends generation requests and polls for results.

**Workflow:**

1. Scene plan includes `comfyui_prompt` for scenes marked as `generated-image`
2. NOLAN sends prompt to ComfyUI API
3. Waits for generation (with timeout)
4. Downloads result to `assets/generated/scene_XXX.png`

**Configuration:**
```yaml
comfyui:
  host: "127.0.0.1"
  port: 8188
  workflow: "default"  # or path to custom workflow JSON
  defaults:
    width: 1920
    height: 1080
    steps: 20
```

**Flexibility:**
- Use your own ComfyUI workflows (SDXL, custom models, ControlNet, etc.)
- NOLAN handles API communication and file management
- Regenerate individual scenes: `nolan generate --scene scene_003`

**Manual override:**
- Edit `scene_plan.json` to change prompts and re-run
- Set `"skip_generation": true` to skip a scene

---

### 5. The Viewer

**Purpose:** A simple local web interface to review pipeline outputs visually.

**Launch:**
```
nolan serve --project ./my_essay_output
```

Opens browser at `http://localhost:8000`.

**What you see:**

1. **Script view** - Full narration with section timestamps
2. **Scene timeline** - Visual grid of all scenes
   - Thumbnail preview (generated image or matched video frame)
   - Duration, timestamp, visual description
   - Click to expand details
3. **Asset panel** - For each scene:
   - Matched library clips with preview + timestamps
   - Generated images (if any)
   - One-click to open file location
4. **Export summary** - Final checklist before editing
   - Total duration estimate
   - Assets collected vs. still needed
   - Folder structure ready for editor

**Tech approach:**
- Simple Python HTTP server (FastAPI or built-in)
- Static HTML/CSS/JS - no heavy frontend framework
- Reads directly from project output folder
- Live server enables video previews (browser security requires localhost for local video playback)

---

## Configuration

### Global Configuration (`~/.nolan/config.yaml`)

```yaml
gemini:
  api_key: "${GEMINI_API_KEY}"  # loaded from .env
  model: "gemini-3-flash-preview"

comfyui:
  host: "127.0.0.1"
  port: 8188
  workflow: "default"

indexing:
  frame_interval: 5  # seconds between sampled frames
  database: "~/.nolan/library.db"

defaults:
  words_per_minute: 150
  output_dir: "./output"
```

### Environment Variables (`.env`)

```
GEMINI_API_KEY=your_api_key_here
```

Use `python-dotenv` to load environment variables.

### Video Library Locations (`~/.nolan/libraries.yaml`)

```yaml
libraries:
  - name: "personal"
    path: "/Videos/B-roll"
  - name: "stock"
    path: "/Videos/Stock-footage"
```

### Per-Project Structure

```
my_essay_project/
├── input/
│   └── essay.md              # Source essay
├── output/
│   ├── script.md             # Generated narration
│   ├── scene_plan.json       # Full scene breakdown
│   ├── assets/
│   │   ├── generated/        # ComfyUI outputs
│   │   └── matched/          # Clips from library
│   └── index.html            # Viewer entry point
└── nolan.yaml                # Project-specific overrides (optional)
```

### Project Overrides (`nolan.yaml`)

```yaml
# Override globals for this project
words_per_minute: 130  # slower narration style
comfyui:
  workflow: "./custom_workflow.json"
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.x (Conda env: `nolan`) |
| LLM | Gemini API (`gemini-3-flash-preview`) |
| Image Generation | ComfyUI (local API) |
| Video Index | SQLite |
| Viewer Server | FastAPI or built-in http.server |
| Config | YAML + python-dotenv |

**Python environment:**
- Conda environment: `nolan`
- Python binary: `D:\env\nolan\python.exe`
- Pip: `D:\env\nolan\Scripts\pip.exe`

---

## v1 Scope

| Component | Included |
|-----------|----------|
| Essay → Script conversion | Yes |
| Scene design with timestamps | Yes |
| Visual asset suggestions | Yes |
| Video library indexing (visual analysis) | Yes |
| ComfyUI integration | Yes |
| Local viewer | Yes |
| CLI commands | Yes |

---

## Backlog (Future Features)

| Feature | Notes |
|---------|-------|
| Internet asset collection | Pexels, Pixabay, search engine integration |
| Transcript indexing | Add audio/speech search to video index (hybrid approach) |

---

## Not in Scope

- Multi-user / authentication
- Cloud deployment
- Automatic video assembly
- Audio/music suggestions

---

## Test Fixture

Sample article for testing: `D:\ClaudeProjects\NOLAN\draft-20260104-110039.md`

- 7 sections: Hook, Context, Thesis, Evidence 1-3, Conclusion
- ~1500 words
- Documentary-style essay about Venezuela
- Good mix of narrative, historical context, and argumentation
