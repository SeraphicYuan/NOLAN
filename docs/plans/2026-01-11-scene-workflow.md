# Scene Workflow Module

**Purpose:** Orchestrate the complete video production pipeline from script to final render.

**Status:** Planning

---

## Overview

The scene workflow transforms a written script into a complete video by coordinating:
- LLM-based scene design
- Asset preparation (footage matching, image generation, infographics)
- Voiceover recording
- Precise timing alignment
- Final video assembly

---

## 5-Step Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         NOLAN Video Pipeline                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Step 1: Scene Design (two-pass approach)                               │
│  ────────────────────────────────────────                               │
│  Essay → Script → SceneDesigner (Pass 1 + Pass 2) → scene_plan.json     │
│                                                                         │
│  Pass 1: Narration → Beats (structural backbone)                        │
│          - Break narration into thought units                           │
│          - Assign visual category (b-roll, graphics, a-roll, etc.)      │
│          - Identify see-say vs counterpoint                             │
│          - Flag visual holes                                            │
│                                                                         │
│  Pass 2: Beats → Scenes (flexible mapping)                              │
│          - LLM sees ALL beats in section                                │
│          - Decides: 1 beat → 1 scene (common)                           │
│                     1 beat → N scenes (montage)                         │
│                     N beats → 1 scene (sustained visual)                │
│          - Adds category-specific details                               │
│                                                                         │
│  Output: scene_plan.json                                                │
│          ├── visual_type per scene                                      │
│          ├── asset suggestions                                          │
│          ├── infographic specs                                          │
│          └── sync points                                                │
│                                                                         │
│  Step 2: Asset Preparation (parallel, no audio needed)                  │
│  ─────────────────────────────────────────────────────                  │
│  scene_plan.json → AssetPreparer                                        │
│                         │                                               │
│                         ├── Library matching (indexed videos)           │
│                         ├── Image generation (ComfyUI)                  │
│                         ├── Infographic rendering (render-service)      │
│                         ├── Stock footage search                        │
│                         └── assets/ folder populated                    │
│                                                                         │
│  Step 3: Voiceover Recording (external)                                 │
│  ──────────────────────────────────────                                 │
│  Final script.md → Human/TTS → voiceover.mp3 + voiceover.srt            │
│                                                                         │
│  Step 4: Precise Timing (SRT + audio-driven)                            │
│  ───────────────────────────────────────────                            │
│  voiceover.srt + voiceover.mp3 → TimingAligner                          │
│                       │                                                 │
│                       ├── SRT parsing (word/phrase timestamps)          │
│                       ├── Silence detection (FFmpeg, for gaps)          │
│                       ├── Narration-to-scene matching                   │
│                       ├── Scene boundary markers                        │
│                       └── timed_scene_plan.json                         │
│                                                                         │
│  Step 5: Final Render                                                   │
│  ────────────────────                                                   │
│  timed_scene_plan.json + assets + voiceover.mp3                         │
│                       │                                                 │
│                       └── VideoAssembler → final_video.mp4              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Two-Pass Scene Design

Based on professional A/V script methodology from video essay research.

### Concepts

**Beat**: A distinct unit of thought in the narration. Not arbitrary time - a beat is where
the topic shifts, a new point is introduced, or a rhetorical moment occurs.

**Scene**: A visual specification with all details needed for asset preparation and rendering.
The basic unit for all subsequent pipeline steps.

**Visual Categories**:
| Category | Description | Example |
|----------|-------------|---------|
| `b-roll` | Stock/archival footage | Aerial landscape, historical clips |
| `graphics` | Infographics, charts, text overlays | Data visualization, kinetic typography |
| `a-roll` | Primary footage of subject | Interview clip, documentary footage |
| `generated` | AI-generated images | Conceptual illustration, abstract visual |
| `host` | Face-to-camera | Narrator speaking directly |

**Visual Modes**:
| Mode | Description |
|------|-------------|
| `see-say` | Visual directly illustrates narration |
| `counterpoint` | Visual adds meaning NOT in the narration |

### Pass 1: Beat Detection

**Input**: Section narration (text)
**Output**: List of beats (structural backbone)

```
SECTION: "The Economic Crisis"
NARRATION: "Venezuela was once the richest country in South America.
            Oil revenues funded massive social programs. But when oil
            prices crashed in 2014, everything changed."

                    ↓ Pass 1 (LLM)

BEATS:
┌────────┬─────────────────────────────────────┬──────────┬──────────┐
│ ID     │ Narration                           │ Category │ Mode     │
├────────┼─────────────────────────────────────┼──────────┼──────────┤
│ beat_1 │ "Venezuela was once the richest..." │ b-roll   │ see-say  │
│ beat_2 │ "Oil revenues funded massive..."    │ graphics │ see-say  │
│ beat_3 │ "But when oil prices crashed..."    │ graphics │ see-say  │
└────────┴─────────────────────────────────────┴──────────┴──────────┘
```

**Pass 1 Prompt Focus**:
- Break at topic shifts
- Assign visual category
- Identify see-say vs counterpoint
- Flag "visual holes" (abstract concepts with no obvious visual)

### Pass 2: Beats to Scenes (Flexible Mapping)

**Input**: ALL beats from the section
**Output**: Scenes with flexible mapping

**Key Insight**: LLM sees all beats at once and decides the mapping:

```
┌─────────────────────────────────────────────────────────────────────┐
│ FLEXIBLE BEAT → SCENE MAPPING                                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Common: 1 beat → 1 scene                                           │
│  ┌─────────┐      ┌───────────┐                                     │
│  │ beat_1  │ ──── │ scene_001 │                                     │
│  └─────────┘      └───────────┘                                     │
│                                                                     │
│  Montage: 1 beat → N scenes (quick cuts)                            │
│  ┌─────────┐      ┌───────────┐                                     │
│  │ beat_2  │ ──┬─ │ scene_002 │  (wide shot)                        │
│  └─────────┘  │   └───────────┘                                     │
│               ├─  ┌───────────┐                                     │
│               │   │ scene_003 │  (detail shot)                      │
│               │   └───────────┘                                     │
│               └─  ┌───────────┐                                     │
│                   │ scene_004 │  (reaction shot)                    │
│                   └───────────┘                                     │
│                                                                     │
│  Sustained: N beats → 1 scene (single visual spans multiple beats)  │
│  ┌─────────┐                                                        │
│  │ beat_3  │ ──┐                                                    │
│  └─────────┘   │   ┌───────────┐                                    │
│  ┌─────────┐   ├── │ scene_005 │  (infographic with reveals)        │
│  │ beat_4  │ ──┘   └───────────┘                                    │
│  └─────────┘                                                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Pass 2 Output Structure**:
```json
{
  "scenes": [
    {
      "id": "scene_001",
      "covers_beats": ["beat_1"],
      "visual_type": "b-roll",
      "visual_description": "Aerial shot of Caracas skyline",
      "search_queries": ["caracas aerial", "venezuela cityscape"],
      ...
    },
    {
      "id": "scene_002",
      "covers_beats": ["beat_2", "beat_3"],
      "visual_type": "graphics",
      "visual_description": "Oil price chart with annotations",
      "infographic": {...},
      "sync_points": [
        {"trigger": "oil revenues", "action": "reveal_item", "target": 0},
        {"trigger": "crashed", "action": "highlight", "target": 1}
      ],
      ...
    }
  ]
}
```

### Processing Flow (Per Section)

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Per-Section Processing                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Script Section                                                     │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────┐                        │
│  │ Pass 1: Beat Detection                  │                        │
│  │ - Input: section.narration              │                        │
│  │ - Output: List[Beat] (10-20 beats)      │                        │
│  │ - Context: ~1,000 tokens (small)        │                        │
│  └─────────────────────────────────────────┘                        │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────┐                        │
│  │ Pass 2: Beats → Scenes                  │                        │
│  │ - Input: ALL beats from section         │                        │
│  │ - Output: List[Scene] (flexible count)  │                        │
│  │ - LLM decides mapping                   │                        │
│  └─────────────────────────────────────────┘                        │
│       │                                                             │
│       ▼                                                             │
│  Scenes for this section                                            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

                    ↓ Repeat for each section

┌─────────────────────────────────────────────────────────────────────┐
│  scene_plan.json                                                    │
│  {                                                                  │
│    "sections": {                                                    │
│      "Introduction": [scene_001, scene_002, ...],                   │
│      "The Problem": [scene_010, scene_011, ...],                    │
│      "Conclusion": [scene_020, scene_021, ...]                      │
│    }                                                                │
│  }                                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

### CLI Workflow

```bash
# Full two-pass design (default)
nolan design script.json -o ./output
# Output: scene_plan.json

# Pass 1 only (for human review)
nolan design script.json --beats-only -o ./output
# Output: beats.json, av_script.txt

# Review av_script.txt, then run full design
nolan design script.json -o ./output
```

### A/V Script Format (Human Review)

Pass 1 outputs `av_script.txt` in industry-standard two-column format:

```
# A/V SCRIPT: Introduction
================================================================================
VISUAL                                   | AUDIO
-----------------------------------------+---------------------------------------
[B-ROLL] Aerial shot of Caracas          | Venezuela was once the richest
[GRAPHICS] Oil revenue chart             | Oil revenues funded massive social
⚠️ [GENERATED] Economic collapse concept  | But when oil prices crashed...
================================================================================
Summary: 12 beats
  - b-roll: 5
  - graphics: 4
  - generated: 2
  - a-roll: 1
  - ⚠️ Visual holes: 2
```

---

## Scene Data Model

The Scene class is a **holder** that gets progressively enriched across steps:

```python
@dataclass
class SyncPoint:
    """Word-to-action synchronization point."""
    trigger: str                    # Word/phrase to match in SRT
    action: str                     # reveal, highlight, zoom, show_lower_third, animate
    target: Optional[Any] = None    # Item index, element id, coordinates, etc.
    time: Optional[float] = None    # None in Step 1, populated in Step 4

@dataclass
class Layer:
    """A visual layer within a scene."""
    type: str                       # background, overlay, caption, lower_third
    asset: Optional[str] = None     # Path to asset
    style: Optional[Dict] = None    # Position, opacity, animation params
    sync_point: Optional[SyncPoint] = None  # When to show/animate this layer

@dataclass
class Beat:
    """A distinct unit of thought in the narration (Pass 1 output)."""
    id: str
    narration: str                          # The exact words for this beat
    category: str                           # b-roll, graphics, a-roll, generated, host
    mode: str                               # see-say, counterpoint
    visual_intent: str                      # Brief description of visual need
    has_visual_hole: bool = False           # True if abstract concept
    sync_word: Optional[str] = None         # Key word that triggers visual change


@dataclass
class Scene:
    """Visual scene - progressively enriched across workflow steps."""

    # === Identity ===
    id: str
    covers_beats: List[str] = field(default_factory=list)  # Beat IDs this scene covers

    # === Timing (estimated in Step 1, precise after Step 4) ===
    start: str                              # "0:15" - LLM estimate
    duration: str                           # "5s" - LLM estimate
    start_seconds: Optional[float] = None   # Precise, from SRT (Step 4)
    end_seconds: Optional[float] = None     # Precise, from SRT (Step 4)

    # === Content ===
    narration_excerpt: str                  # Key phrase for SRT matching (from covered beats)
    visual_type: str                        # b-roll, graphic, text-overlay, generated-image, infographic
    visual_description: str                 # What appears on screen

    # === Asset Sources (Step 1 hints) ===
    search_query: str                       # Stock footage keywords
    comfyui_prompt: str                     # AI image generation prompt
    library_match: bool                     # Try indexed library first

    # === Animation (Step 1 hints, refined in Step 4/5) ===
    animation_type: Optional[str] = None    # static, zoom, pan, reveal, kinetic
    animation_params: Optional[Dict] = None # {zoom_from, zoom_to, focus_x, focus_y, direction}
    transition: Optional[str] = None        # cut, fade, dissolve, wipe

    # === Sync Points (Step 1 hints trigger/action, Step 4 adds time) ===
    sync_points: List[SyncPoint] = field(default_factory=list)

    # === Layers for complex scenes ===
    layers: List[Layer] = field(default_factory=list)

    # === Infographic spec (if visual_type == "infographic") ===
    infographic: Optional[Dict] = None

    # === Text overlay style (if visual_type == "text-overlay") ===
    text_style: Optional[Dict] = None       # {position, font_size, color, animation}

    # === Asset Results (populated in Step 2) ===
    skip_generation: bool = False
    matched_asset: Optional[str] = None
    generated_asset: Optional[str] = None
    infographic_asset: Optional[str] = None

    # === SRT Cues (attached in Step 4) ===
    subtitle_cues: List[Any] = field(default_factory=list)  # SubtitleCue objects
```

### Field Population by Step

| Field | Step 1 (Design) | Step 2 (Assets) | Step 4 (Timing) | Step 5 (Render) |
|-------|-----------------|-----------------|-----------------|-----------------|
| `id`, `covers_beats` | ✅ LLM | - | - | - |
| `narration_excerpt` | ✅ LLM (from beats) | - | - | - |
| `start`, `duration` | ✅ LLM estimate | - | - | - |
| `visual_type`, `visual_description` | ✅ LLM | - | - | - |
| `search_query`, `comfyui_prompt` | ✅ LLM | - | - | - |
| `animation_type`, `animation_params` | ⚪ LLM hint | - | ⚪ Refine | ✅ Finalize |
| `sync_points[].trigger/action` | ✅ LLM | - | - | - |
| `sync_points[].time` | - | - | ✅ From SRT | - |
| `layers` | ⚪ LLM hint | ✅ Assets added | - | - |
| `infographic` | ✅ LLM | - | - | - |
| `matched_asset`, `generated_asset` | - | ✅ Populated | - | - |
| `start_seconds`, `end_seconds` | - | - | ✅ From SRT | - |
| `subtitle_cues` | - | - | ✅ Attached | - |

✅ = Populated, ⚪ = Optional/Hint, - = Not applicable

### Layers Example

Complex scene with b-roll background + infographic overlay + caption:

```json
{
  "id": "scene_007",
  "visual_type": "layered",
  "visual_description": "Statistics overlay on office footage",
  "layers": [
    {
      "type": "background",
      "asset": "assets/broll/office_workers.mp4",
      "style": {"opacity": 0.7, "filter": "blur(2px)"}
    },
    {
      "type": "overlay",
      "asset": "assets/infographics/revenue_chart.svg",
      "style": {"position": "center", "scale": 0.8},
      "sync_point": {"trigger": "revenue grew", "action": "fade_in", "time": null}
    },
    {
      "type": "caption",
      "style": {"position": "bottom", "font_size": 24}
    }
  ]
}
```

### Sync Points Example

```json
{
  "id": "scene_012",
  "visual_type": "infographic",
  "narration_excerpt": "three phases: research, development, and launch",
  "infographic": {
    "template": "steps",
    "data": {
      "title": "Growth Phases",
      "items": [
        {"label": "Research", "desc": "Market analysis"},
        {"label": "Development", "desc": "Product build"},
        {"label": "Launch", "desc": "Go to market"}
      ]
    }
  },
  "sync_points": [
    {"trigger": "research", "action": "reveal_item", "target": 0, "time": null},
    {"trigger": "development", "action": "reveal_item", "target": 1, "time": null},
    {"trigger": "launch", "action": "reveal_item", "target": 2, "time": null}
  ]
}
```

After Step 4 (timing alignment), `time` fields are populated:
```json
"sync_points": [
  {"trigger": "research", "action": "reveal_item", "target": 0, "time": 12.4},
  {"trigger": "development", "action": "reveal_item", "target": 1, "time": 14.1},
  {"trigger": "launch", "action": "reveal_item", "target": 2, "time": 15.8}
]
```

---

## Existing Components

| Component | File | Status |
|-----------|------|--------|
| SceneDesigner | `src/nolan/scenes.py` | ✅ Implemented |
| Scene/ScenePlan | `src/nolan/scenes.py` | ✅ Implemented |
| InfographicClient | `src/nolan/infographic_client.py` | ✅ Implemented |
| Render Service | `render-service/` | ✅ Implemented |
| Video Indexer | `src/nolan/indexer.py` | ✅ Implemented |
| Asset Matcher | `src/nolan/matcher.py` | ✅ Implemented |
| ComfyUI Client | `src/nolan/comfyui.py` | ✅ Implemented |
| Image Search | `src/nolan/image_search.py` | ✅ Implemented |
| Whisper Transcription | `src/nolan/whisper.py` | ✅ Implemented |
| Audio Markers | `render-service` (Remotion) | ✅ Implemented |

---

## Components to Build

### 1. AssetPreparer (`src/nolan/asset_preparer.py`)

Orchestrates asset preparation for all scenes in a plan.

```python
class AssetPreparer:
    """Prepares all assets for a scene plan."""

    def __init__(self,
                 indexer: HybridVideoIndexer,
                 matcher: AssetMatcher,
                 comfyui: ComfyUIClient,
                 infographic: InfographicClient,
                 image_search: ImageSearchClient):
        ...

    async def prepare_scene(self, scene: Scene) -> Scene:
        """Prepare assets for a single scene based on visual_type."""
        ...

    async def prepare_all(self, plan: ScenePlan,
                          output_dir: Path,
                          progress_callback: Callable = None) -> ScenePlan:
        """Prepare all assets for a scene plan."""
        ...
```

**Asset preparation by visual_type:**

| visual_type | Asset Source | Output |
|-------------|--------------|--------|
| `b-roll` | Library match → Stock search → Image gen | `assets/broll/` |
| `graphic` | Image generation (ComfyUI) | `assets/graphics/` |
| `text-overlay` | Generate text graphic | `assets/text/` |
| `generated-image` | ComfyUI generation | `assets/generated/` |
| `infographic` | Render-service | `assets/infographics/` |

---

### 2. TimingAligner (`src/nolan/timing.py`)

Aligns scene boundaries to voiceover using SRT transcript and audio analysis.

```python
class TimingAligner:
    """Aligns scenes to voiceover timing using SRT + audio."""

    def __init__(self, infographic_client: InfographicClient):
        ...

    def load_srt(self, srt_path: Path) -> List[SubtitleCue]:
        """Load SRT file with timestamps."""
        ...

    async def detect_silences(self, audio_path: Path,
                              threshold_db: float = -35,
                              min_silence_ms: int = 400) -> AudioMarkers:
        """Detect silence gaps in audio (for scene boundaries)."""
        ...

    def match_narration_to_scenes(self, plan: ScenePlan,
                                   cues: List[SubtitleCue]) -> List[SceneMatch]:
        """Match scene narration_excerpt to SRT cues using fuzzy matching."""
        ...

    def align_scenes(self, plan: ScenePlan,
                     cues: List[SubtitleCue],
                     silences: AudioMarkers) -> TimedScenePlan:
        """Align scene boundaries using SRT timestamps + silence gaps."""
        ...
```

**Timing data structures:**

```python
@dataclass
class SubtitleCue:
    """Single SRT cue with timestamp."""
    index: int
    start: float      # seconds
    end: float        # seconds
    text: str

@dataclass
class AudioMarkers:
    duration_seconds: float
    silences: List[SilenceRegion]
    markers_seconds: List[float]  # Silence-based boundary candidates

@dataclass
class SceneMatch:
    """Match between scene narration and SRT cue."""
    scene_id: str
    narration_excerpt: str
    matched_cue: SubtitleCue
    confidence: float  # 0-1 fuzzy match score

@dataclass
class TimedScene(Scene):
    start_seconds: float
    end_seconds: float
    subtitle_cues: List[SubtitleCue]  # SRT cues during this scene
```

**Alignment strategy:**

1. Parse SRT → `List[SubtitleCue]` with precise timestamps
2. Detect silences → `AudioMarkers` for natural break points
3. Fuzzy match `scene.narration_excerpt` → SRT cues
4. Set scene boundaries:
   - `start_seconds` = matched cue start time
   - `end_seconds` = next scene start OR silence gap OR cue end
5. Attach relevant `subtitle_cues` to each `TimedScene`

---

### 3. VideoAssembler (`src/nolan/assembler.py`)

Assembles final video from timed scenes, assets, and voiceover.

```python
class VideoAssembler:
    """Assembles final video from components."""

    def __init__(self, infographic_client: InfographicClient):
        ...

    async def assemble(self,
                       timed_plan: TimedScenePlan,
                       voiceover: Path,
                       output_path: Path,
                       progress_callback: Callable = None) -> Path:
        """Assemble final video using Remotion."""
        ...

    def generate_remotion_spec(self, timed_plan: TimedScenePlan) -> dict:
        """Generate Remotion composition spec from timed plan."""
        ...
```

---

### 4. SceneWorkflow (`src/nolan/workflow.py`)

High-level orchestrator for the complete pipeline.

```python
class SceneWorkflow:
    """Orchestrates the complete video production pipeline."""

    def __init__(self, config: Config):
        self.scene_designer = SceneDesigner(...)
        self.asset_preparer = AssetPreparer(...)
        self.timing_aligner = TimingAligner(...)
        self.video_assembler = VideoAssembler(...)

    async def step1_design_scenes(self, script: Script) -> ScenePlan:
        """Design scenes from script text."""
        ...

    async def step2_prepare_assets(self, plan: ScenePlan) -> ScenePlan:
        """Prepare all assets for scenes."""
        ...

    async def step4_align_timing(self, plan: ScenePlan,
                                  voiceover: Path) -> TimedScenePlan:
        """Align scenes to voiceover timing."""
        ...

    async def step5_render(self, timed_plan: TimedScenePlan,
                           voiceover: Path,
                           output: Path) -> Path:
        """Render final video."""
        ...
```

---

## CLI Commands

| Command | Description | Step |
|---------|-------------|------|
| `nolan script <essay.md>` | Convert essay to narration script | Pre-1 |
| `nolan design <script.json>` | Design scenes (full two-pass) | 1 |
| `nolan design <script.json> --beats-only` | Pass 1 only (for review) | 1a |
| `nolan prepare-assets <scene_plan.json>` | Prepare all assets | 2 |
| `nolan align <scene_plan.json> <voiceover.srt>` | Align timing using SRT | 4 |
| `nolan render <timed_plan.json> <voiceover.mp3>` | Final render | 5 |
| `nolan produce <script.md> <voiceover.mp3> --srt <voiceover.srt>` | Full pipeline | All |

---

## Output Structure

```
project_output/
├── script.md                    # Final narration script
├── scene_plan.json              # Scene design (Step 1 output)
├── timed_scene_plan.json        # With audio timing (Step 4 output)
├── voiceover.mp3                # Recorded narration
├── voiceover.srt                # Transcript with timestamps (from TTS/transcription)
├── audio_markers.json           # Silence detection results
├── assets/
│   ├── broll/
│   │   ├── scene_001_match.mp4
│   │   └── scene_003_stock.mp4
│   ├── graphics/
│   │   └── scene_002_graphic.png
│   ├── generated/
│   │   └── scene_005_comfyui.png
│   ├── infographics/
│   │   ├── scene_004_infographic.svg
│   │   └── scene_004_infographic.mp4
│   └── text/
│       └── scene_006_overlay.png
└── final_video.mp4              # Assembled video (Step 5 output)
```

---

## Implementation Order

1. **AssetPreparer** - Connect existing asset sources
2. **TimingAligner** - Leverage existing Whisper + audio markers
3. **VideoAssembler** - Use Remotion engine for final render
4. **SceneWorkflow** - Orchestrate the pipeline
5. **CLI Commands** - Expose workflow steps

---

## Dependencies

**Python:**
- Existing NOLAN modules (scenes, matcher, indexer, comfyui, whisper)
- httpx (for render-service calls)

**Render Service:**
- Remotion engine (already implemented)
- Audio markers endpoint (already implemented)

**External:**
- FFmpeg (audio processing)
- Whisper (word-level timing)

---

## Usage Example

```bash
# Step 1: Design scenes from script
nolan design essay_script.md -o project/

# Step 2: Prepare assets (can run while recording voiceover)
nolan prepare-assets project/scene_plan.json

# Step 3: Record voiceover externally
#   → Save audio as project/voiceover.mp3
#   → Save transcript as project/voiceover.srt (from TTS or transcription service)

# Step 4: Align timing using SRT transcript
nolan align project/scene_plan.json project/voiceover.srt

# Step 5: Render final video
nolan render project/timed_scene_plan.json project/voiceover.mp3 -o project/final.mp4

# Or do it all at once (after voiceover + SRT are ready)
nolan produce essay_script.md project/voiceover.mp3 --srt project/voiceover.srt -o project/
```

## SRT as the Sync Backbone

The SRT transcript is the **central timing source** that drives everything:

```
                              voiceover.srt
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
        ▼                           ▼                           ▼
   Scene Timing              Visual Sync                 Animations
        │                           │                           │
        ├── Scene boundaries        ├── Show asset when         ├── Kinetic typography
        ├── Asset transitions       │   words are spoken        │   (word-by-word reveal)
        └── Duration calc           ├── B-roll cuts on          ├── Text overlays timed
                                    │   key phrases             │   to speech
                                    └── Infographic             ├── Lower thirds sync
                                        element reveals         └── Progress indicators
```

### SRT-Driven Features

| Feature | How SRT Drives It |
|---------|-------------------|
| **Subtitles/Captions** | Display SRT cues as on-screen text |
| **Scene transitions** | Cut to new visual when cue mentions scene topic |
| **Kinetic typography** | Animate words as they're spoken |
| **Text overlays** | Show key phrases at exact moment spoken |
| **Infographic reveals** | Reveal data points as narrator explains them |
| **B-roll timing** | Switch footage on key words/phrases |
| **Lower thirds** | Show speaker name when introduced in narration |
| **Chapter markers** | Insert chapter cards at section transitions |

### Animation Sync Examples

**Kinetic Typography (Motion Canvas):**
```json
{
  "engine": "motion-canvas",
  "data": {
    "kinetic": {
      "phrases": [
        {"text": "The real story", "start": 2.5, "hold": 0.7},
        {"text": "is in the data", "start": 3.4, "hold": 0.7}
      ]
    }
  }
}
```
↑ `start` times come directly from SRT cue timestamps

**Infographic Reveal (Remotion):**
```json
{
  "engine": "remotion",
  "data": {
    "items": [
      {"label": "Step 1", "reveal_at": 5.2},
      {"label": "Step 2", "reveal_at": 8.1},
      {"label": "Step 3", "reveal_at": 11.4}
    ]
  }
}
```
↑ `reveal_at` synced to when narrator says "first", "second", "third"

**Caption Overlay:**
```json
{
  "engine": "remotion",
  "data": {
    "captions": {
      "enabled": true,
      "style": "bottom-center",
      "cues": [/* from SRT */]
    }
  }
}
```

### Alignment Data Flow

```
scene_plan.json                    voiceover.srt
       │                                 │
       │  narration_excerpt:             │  00:00:05,200 --> 00:00:08,100
       │  "GDP grew by 15%"              │  GDP grew by fifteen percent
       │                                 │
       └─────────────┬───────────────────┘
                     │
                     ▼
              TimingAligner
                     │
                     ├── Fuzzy match: "GDP grew by 15%" ≈ "GDP grew by fifteen percent"
                     ├── Scene starts at 5.2s
                     ├── Scene ends at 8.1s (next cue or silence)
                     │
                     ▼
           timed_scene_plan.json
                     │
                     ├── scene.start_seconds = 5.2
                     ├── scene.end_seconds = 8.1
                     ├── scene.subtitle_cues = [cue]
                     └── scene.animation_sync = {
                           "infographic_reveal": 5.2,
                           "highlight_15_percent": 6.8
                         }
```

### SRT Sources

| Source | Quality | Notes |
|--------|---------|-------|
| TTS services (ElevenLabs, Azure) | High | Often output SRT with audio |
| Whisper transcription | High | Word-level timestamps |
| AssemblyAI, Deepgram | High | Speaker diarization available |
| Manual creation | Perfect | Full control, labor intensive |
| Auto-generate via `nolan` | Good | Whisper fallback if no SRT |
