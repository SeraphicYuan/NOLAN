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
│  Step 1: Scene Design (text-based, no audio needed)                     │
│  ─────────────────────────────────────────────────                      │
│  Essay → Script → SceneDesigner → scene_plan.json                       │
│                                        │                                │
│                                        ├── visual_type per scene        │
│                                        ├── asset suggestions            │
│                                        ├── infographic specs            │
│                                        └── estimated timings            │
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
| `nolan design <script.md>` | Design scenes from script | 1 |
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

## SRT Transcript Benefits

Using SRT (SubRip) format provides:

| Benefit | Description |
|---------|-------------|
| **Precise timestamps** | Word/phrase-level timing from TTS or transcription |
| **Scene matching** | Fuzzy match `narration_excerpt` to SRT cues |
| **Natural boundaries** | Scene transitions at subtitle boundaries |
| **Fallback to Whisper** | Generate SRT if not provided |
| **Existing support** | NOLAN already has `transcript.py` for SRT parsing |

**SRT sources:**
- TTS services (ElevenLabs, Azure, etc.) often output SRT
- Transcription services (Whisper, AssemblyAI, etc.)
- Manual creation for precise control
- `nolan` can generate via Whisper if missing
