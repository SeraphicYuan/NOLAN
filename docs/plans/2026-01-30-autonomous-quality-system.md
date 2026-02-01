# Autonomous High-Quality Video Generation System

**Date:** 2026-01-30
**Status:** Planning
**Goal:** Enable NOLAN to produce high-quality video clips autonomously with minimal to no human intervention

---

## Problem Statement

### Current State Assessment

NOLAN's scene-to-video pipeline is **functional but produces draft-quality output**. The system works end-to-end (produces valid MP4s with audio sync), but the output quality is limited by:

1. **Generative Ceiling** - The system can't create novel motion graphics
2. **No Quality Feedback** - Accepts first result without evaluation
3. **No Style Consistency** - Each scene designed in isolation
4. **No Iterative Refinement** - One-shot generation only
5. **No Editorial Intelligence** - Mechanical timing, hard cuts

### What NOLAN Can Currently Produce

| Method | Output | Quality Ceiling |
|--------|--------|-----------------|
| B-roll search | Found clips from indexed library | Limited by what's indexed |
| ComfyUI | Static images + Ken Burns animation | Animated photographs, slideshow-like |
| Infographics | Template-based charts/lists | Functional, not cinematic |
| Lottie | Pre-made animations | High quality IF right template exists |
| Motion Canvas / Remotion | Programmatic video | Execution engines, not generative |

### The Core Gap

```
What we want:   Prompt → Professional Motion Graphics Video
What we have:   Prompt → Static Image → Ken Burns → Slideshow-ish Result
```

---

## Solution: Four-Layer Approach

After analysis, we identified 4 complementary strategies that work together:

### Layer 1: Scope to Strengths (Strategic Foundation)

**Concept:** Accept that different visual types have different automation potential. Design around this reality.

**Highly Automatable (target full quality):**
- Text overlays / kinetic typography
- Data visualizations / charts
- Infographics with templates
- Lottie micro-animations
- Simple transitions
- Lower thirds, titles, callouts

**Hard to Automate (needs different approach):**
- Cinematic b-roll footage
- Custom character animation
- Complex scene compositions
- Novel motion graphics

**Implementation:**
- Categorize visual types by automation potential
- Apply different quality standards and pipelines per category
- Route hard-to-automate types to appropriate fallback (video gen, human review)

---

### Layer 2: Template-Heavy Approach (Quality for Automatable Content)

**Concept:** Build/curate a massive library of professional templates. AI's job becomes selection + customization, not creation from scratch.

**How It Works:**
```
Scene needs "3-step process explanation"
  → AI searches template library by semantic match
  → Finds "steps-animated-03.json" (Lottie template)
  → Customizes: text content, colors, timing
  → Renders to video clip
```

**What's Needed:**
- 500+ categorized Lottie/Motion Canvas/Remotion templates
- Strong tagging/categorization system for template discovery
- Template customization engine (partially exists)
- Template schema system for valid customization options

**Quality Ceiling:** As good as the templates. Professional templates = professional output.

**Existing Foundation:**
- Lottie integration with downloaders (LottieFiles, Jitter, Lottieflow)
- Template schema generation (`analyze_lottie()`)
- Text/color customization utilities

---

### Layer 3: Video Generation Integration (Quality for B-Roll/Cinematic)

**Concept:** Use AI video generation models to create actual video clips from prompts, not just search for existing footage.

**Target Models:**
- Runway Gen-3/Gen-4
- Pika Labs
- LTX-Video (open source, can self-host)
- Kling
- Future: Sora (when API available)

**How It Works:**
```
Scene needs "aerial shot of Venezuelan oil fields at sunset"
  → Generate video generation prompt from scene spec
  → Send to Runway/LTX-Video API
  → Receive 4-8 second video clip
  → Quality score the result
  → Accept or regenerate with refined prompt
```

**What's Needed:**
- API integration with video generation service(s)
- Prompt engineering for video (different from image prompts)
- Cost/quota management (these APIs are expensive)
- Quality evaluation loop with vision model
- Caching to avoid regenerating identical prompts

**Quality Ceiling:** Improving rapidly. Good for b-roll, ambient footage. Struggles with specific faces, text, precise actions.

---

### Layer 4: Quality Evaluation & Human Fallback

**Concept:** Add quality gates throughout the pipeline. Use vision models to score outputs. Flag low-confidence results for human review.

**Quality Evaluation Loop:**
```
Generate/match asset
  → Vision model evaluates:
     - Does it match narration intent? (semantic fit)
     - Is it visually high quality? (no artifacts, good composition)
     - Does it match video's style guide? (consistency)
  → Score 0-100
  → If score >= 80: Accept
  → If score 50-79: Retry with refined prompt (max 3x)
  → If score < 50 after retries: Flag for human review
```

**Human Review Interface:**
- Web UI showing flagged scenes with context
- Asset swap capability (upload or search alternatives)
- Approve/reject workflow
- Optional: human can review full video before final export

**Smart Flagging:**
- Not just quality, but importance weighting
- Intro/outro scenes matter more than mid-video b-roll
- Hero moments (key narrative beats) get stricter thresholds

---

## Combined Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: Scope to Strengths (Strategic Router)                │
│  "What type of visual is this? Route to appropriate pipeline"  │
├─────────────────────────────────────────────────────────────────┤
│                              │                                  │
│  Automatable Visual Types    │    Hard-to-Automate Types       │
│  ─────────────────────────   │    ──────────────────────       │
│  • text-overlay              │    • b-roll                     │
│  • infographic               │    • cinematic                  │
│  • chart                     │    • custom-animation           │
│  • lottie                    │                                 │
│  • lower-third               │                                 │
│           │                  │              │                  │
│           ▼                  │              ▼                  │
│  Layer 2: Templates          │    Layer 3: Video Generation   │
│  ───────────────────         │    ─────────────────────────   │
│  • Search template library   │    • Send to Runway/LTX-Video  │
│  • Semantic matching         │    • Generate video clip       │
│  • Customize & render        │    • Prompt refinement         │
│           │                  │              │                  │
│           ▼                  │              ▼                  │
├─────────────────────────────────────────────────────────────────┤
│  Layer 4: Quality Evaluation                                    │
│  ───────────────────────────                                    │
│  • Vision model scores output                                   │
│  • Check: semantic fit, visual quality, style consistency       │
│  • Accept (≥80) / Retry (50-79) / Flag for human (<50)         │
├─────────────────────────────────────────────────────────────────┤
│  Human Review (Optional)                                        │
│  ───────────────────────                                        │
│  • Web UI for flagged scenes                                    │
│  • Asset swap / approve / reject                                │
│  • Final video review before export                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Strategy

**Principle:** Build generation capability FIRST, then add quality control on top.

### Phase A: Generation Capabilities (Priority)

Build the ability to produce high-quality clips before adding quality gates.

| Order | Layer | Status | Description |
|-------|-------|--------|-------------|
| 1 | **Templates** | ✅ COMPLETED | Expand Lottie library + semantic matching |
| 2 | **Video Gen** | ✅ COMPLETED | LTX-Video / Runway integration |
| 3 | **Router** | ✅ COMPLETED | Visual type → pipeline routing |

### Phase B: Quality Control (After Phase A)

Only after generation works well:

| Component | Status | Description |
|-----------|--------|-------------|
| Quality Scoring | Not Started | Vision-based evaluation |
| Retry Loops | Not Started | Auto-retry with prompt refinement |
| Human Review | Not Started | Flagging + review UI |

---

## Backlog / TODO

### Phase A-1: Template System (COMPLETED)

**Completed 2026-01-31:**

- ✅ **Unified Catalog System** (`src/nolan/template_catalog.py`)
  - `TemplateCatalog` class merges all sources (LottieFiles, Jitter, Lottieflow)
  - `TemplateInfo` dataclass with consistent fields
  - Auto-scans for uncataloged template files
  - Saves unified catalog to `unified-catalog.json`

- ✅ **Semantic Tagging**
  - `auto_tag_all()` generates 240+ tags from category/name patterns
  - `search_by_tag()` and `search_by_tags()` for tag-based search
  - `save_tags()` / `load_tags()` for persistence

- ✅ **CLI Commands** (`nolan templates`)
  - `list` - List templates (filter by category, source, schema)
  - `info <id>` - Show detailed template info
  - `search <tags>` - Search by tags
  - `categories` - List all categories
  - `summary` - Show catalog stats
  - `auto-tag` - Generate tags
  - `index` - Index for semantic search
  - `semantic-search <query>` - Natural language search
  - `match-scene <type> <desc>` - Find templates for scene

- ✅ **Semantic Template Search** (`TemplateSearch` class)
  - ChromaDB vector storage with BGE embeddings
  - Natural language queries
  - Category and schema filtering
  - 53 templates indexed

- ✅ **Scene-to-Template Matching**
  - `find_templates_for_scene()` - Find matching templates
  - `match_scene_to_template()` - Get best match
  - `VISUAL_TYPE_TO_CATEGORIES` mapping for routing

**Stats:**
- 53 templates across 17 categories
- 13 templates with schemas
- 3 sources: LottieFiles, Jitter, Lottieflow

**Still TODO:**
- [ ] Expand template library to 200+
- [ ] Generate schemas for more templates
- [ ] Auto-fill template fields from scene data
- [ ] Integrate into render pipeline

### Phase A-2: Video Generation Integration (COMPLETED)

**Completed 2026-01-31:**

- [x] **Unified Video Generator Interface** (`src/nolan/video_gen.py`)
  - `VideoGenerator` abstract base class
  - `VideoGenerationResult` with success/error tracking
  - `VideoGenerationConfig` for duration, resolution, style, seed
  - `VideoGeneratorFactory.create()` for backend instantiation
  - `generate_video_for_scene()` utility for scene-optimized prompts

- [x] **ComfyUIVideoGenerator** (local, self-hostable)
  - Supports any video workflow (LTX-Video, Wan, HunyuanVideo, CogVideoX, AnimateDiff)
  - Auto-detects prompt nodes in workflow files
  - Converts UI format to API format
  - Node overrides: `node_id:param=value` syntax
  - Async polling for completion, video download

- [x] **RunwayGenerator** (commercial, high quality)
  - Gen-3 Alpha Turbo and Gen-3 Alpha models
  - Cost tracking per generation ($0.05-0.10/second)
  - Async task polling with timeout handling
  - Reads API key from `RUNWAY_API_KEY` env var

- [x] **CLI Commands** (`nolan video-gen`)
  - `check` - Check backend availability (ComfyUI/Runway)
  - `generate` - Generate single video from prompt
  - `scene` - Generate video for specific scene in plan
  - `batch` - Batch generate videos for matching visual types

- [x] **Tests** (`tests/test_video_gen.py`) - 28 tests

**Stats:**
- 2 backends: ComfyUI (local), Runway (commercial)
- Unified interface for seamless backend switching
- Scene-optimized prompt generation with style hints

### Phase A-3: Visual Type Router (COMPLETED)

**Completed 2026-01-31:**

- [x] **Visual Router Module** (`src/nolan/visual_router.py`)
  - `VisualRouter` class routes scenes to pipelines
  - `RouteDecision` dataclass with route, reason, template match
  - Visual type mappings: TEMPLATE_VISUAL_TYPES, LIBRARY_VISUAL_TYPES, etc.
  - Template matching with score threshold

- [x] **Routing Logic**
  - Routes to `template` for: lower-third, text-overlay, title, counter, icon, loading, lottie
  - Routes to `library` for: b-roll, a-roll, footage
  - Routes to `generation` for: generated, generated-image (with comfyui_prompt)
  - Routes to `infographic` for: infographic, chart, graphics (with spec)
  - `passthrough` for scenes with existing rendered_clip

- [x] **CLI Commands**
  - `nolan route-scenes <plan>` - Show routing decisions for all scenes
  - `nolan render-templates <plan>` - Render Lottie templates to video clips
  - Options: --threshold, --force, --dry-run

- [x] **Template Rendering Pipeline**
  - Find matching template via TemplateSearch
  - Customize with scene data (narration → text fields)
  - Copy/customize Lottie JSON to assets/lottie/
  - Render to MP4 via render-service
  - Update scene_plan.json with lottie_asset and rendered_clip

- [x] **Tests** (`tests/test_visual_router.py`)
  - 15 tests covering all routing scenarios

**Stats:**
- 4 route types: template, library, generation, infographic
- 7 template-eligible visual types
- Tested with 102-scene scene plan

### Phase B-1: Quality Evaluation System

- [ ] **Quality Scoring Prompts**
  - Design vision model prompts for quality evaluation
  - Semantic fit scoring (does visual match narration?)
  - Visual quality scoring (artifacts, composition, clarity)
  - Style consistency scoring (matches video's look)

- [ ] **Quality Gate Integration**
  - Insert quality check after asset generation/matching
  - Configurable thresholds (accept/retry/flag)
  - Retry logic with prompt refinement

- [ ] **Style Guide System**
  - Define per-video style guide (color palette, typography, motion style)
  - Pass style guide to quality evaluation
  - Reject assets that break style

### Phase B-2: Human Review System

- [ ] **Review Queue**
  - Track flagged scenes in database
  - Priority scoring (importance × quality gap)
  - Status: pending, in-review, resolved

- [ ] **Review Web UI**
  - Display scene with narration context
  - Show current asset and why it was flagged
  - Asset swap interface (upload, search, regenerate)
  - Approve/reject buttons

- [ ] **Notification System**
  - Alert human when review needed
  - Configurable: email, webhook, CLI notification
  - Batch notifications for multiple scenes

### Phase B-3: Polish & Optimization

- [ ] **Transition Intelligence**
  - Analyze adjacent scenes for visual continuity
  - Select appropriate transition type
  - Pre-rendered transition library

- [ ] **Pacing Refinement**
  - Adjust timing beyond mechanical SRT
  - Add breathing room at section breaks
  - Emphasis detection from narration

- [ ] **Cost Optimization**
  - Track generation costs per video
  - Budget constraints on video generation
  - Prefer cheaper options when quality sufficient

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Human interventions per 10-min video | ~20-30 | <5 |
| Scenes requiring manual asset swap | ~50% | <10% |
| Visual quality score (1-10 human rating) | ~5 | ≥8 |
| Style consistency across scenes | Low | High |
| Time from script to final video | Manual | <1 hour automated |

---

## Dependencies & Prerequisites

1. **Template Library** - Need significant curation effort
2. **Video Generation API** - Either self-host LTX-Video or get Runway API access
3. **Vision Model Access** - Gemini or equivalent for quality scoring
4. **Review UI** - Web interface for human review workflow

---

---

## Architecture Integration

### Current Module Structure

```
src/nolan/
├── cli.py              # Command routing
├── scenes.py           # SceneDesigner, Scene, Beat dataclasses
├── script.py           # ScriptConverter
├── clip_matcher.py     # Video library matching
├── image_search.py     # Stock image providers
├── comfyui.py          # Image generation
├── lottie.py           # Lottie template system
├── vision.py           # Vision providers (Gemini, Ollama)
└── aligner.py          # Audio-scene alignment

render-service/
├── src/engines/        # Remotion, Motion Canvas, Infographic
├── src/effects/        # Effect registry and presets
└── src/routes/         # API endpoints
```

### New Modules to Add

```
src/nolan/
├── quality.py          # NEW: Quality evaluation system
├── video_gen.py        # NEW: Video generation clients (LTX, Runway)
├── template_search.py  # NEW: Semantic template discovery
├── style_guide.py      # NEW: Per-video style consistency
└── review_queue.py     # NEW: Human review queue management

render-service/
└── src/routes/
    └── review.ts       # NEW: Review UI endpoints
```

### Integration Points

#### 1. Visual Type Router (Layer 1)

**Location:** `src/nolan/scenes.py` - Extend `SceneDesigner`

```python
# New method in SceneDesigner
def route_visual_type(self, scene: Scene) -> str:
    """Determine which pipeline to use for this scene.

    Returns: 'template' | 'video_gen' | 'library_search' | 'comfyui'
    """
    TEMPLATE_TYPES = {'text-overlay', 'infographic', 'lottie', 'lower-third', 'chart'}
    VIDEO_GEN_TYPES = {'b-roll', 'cinematic', 'ambient'}

    if scene.visual_type in TEMPLATE_TYPES:
        return 'template'
    elif scene.visual_type in VIDEO_GEN_TYPES:
        # Check if library has good matches first
        if self._library_has_coverage(scene):
            return 'library_search'
        else:
            return 'video_gen'
    elif scene.visual_type == 'generated':
        return 'comfyui'
    else:
        return 'library_search'  # fallback
```

**CLI Integration:** Add `--routing-strategy` flag to `nolan process`

---

#### 2. Template Discovery (Layer 2)

**Location:** New `src/nolan/template_search.py`

```python
@dataclass
class TemplateMatch:
    template_path: str
    similarity_score: float
    customization_schema: Dict
    preview_url: Optional[str]

class TemplateSearcher:
    """Semantic search over Lottie/Motion Canvas template library."""

    def __init__(self, template_dir: Path, vector_db: VectorSearch):
        self.template_dir = template_dir
        self.vector_db = vector_db

    async def find_templates(
        self,
        visual_description: str,
        visual_type: str,
        style_guide: Optional[StyleGuide] = None,
        top_k: int = 5
    ) -> List[TemplateMatch]:
        """Find best matching templates for a scene."""
        # Embed description
        # Search vector DB
        # Filter by visual_type compatibility
        # Rank by style consistency
        pass

    async def index_templates(self):
        """Index all templates with embeddings and metadata."""
        pass
```

**Scene Integration:** Add `template_candidates` field to Scene

```python
@dataclass
class Scene:
    # ... existing fields ...

    # Template matching (Layer 2)
    template_candidates: Optional[List[Dict]] = None  # Top matches with scores
    selected_template: Optional[str] = None           # Chosen template path
```

---

#### 3. Video Generation (Layer 3)

**Location:** New `src/nolan/video_gen.py`

```python
from abc import ABC, abstractmethod

class VideoGenerator(ABC):
    """Abstract base for video generation backends."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        duration: float = 4.0,
        aspect_ratio: str = "16:9",
        style: Optional[str] = None
    ) -> Path:
        """Generate a video clip from prompt."""
        pass

class LTXVideoGenerator(VideoGenerator):
    """Local LTX-Video generation."""

    def __init__(self, host: str = "localhost", port: int = 8188):
        self.base_url = f"http://{host}:{port}"

    async def generate(self, prompt: str, **kwargs) -> Path:
        # Send to LTX-Video API
        # Poll for completion
        # Download result
        pass

class RunwayGenerator(VideoGenerator):
    """Runway Gen-3/Gen-4 API."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def generate(self, prompt: str, **kwargs) -> Path:
        # Runway API call
        pass
```

**Scene Integration:** Add video generation fields

```python
@dataclass
class Scene:
    # ... existing fields ...

    # Video generation (Layer 3)
    video_gen_prompt: Optional[str] = None      # Optimized prompt for video gen
    video_gen_backend: Optional[str] = None     # 'ltx' | 'runway' | None
    generated_video: Optional[str] = None       # Path to generated clip
```

---

#### 4. Quality Evaluation (Layer 4)

**Location:** New `src/nolan/quality.py`

```python
@dataclass
class QualityScore:
    overall: float              # 0-100
    semantic_fit: float         # Does it match narration?
    visual_quality: float       # Artifacts, composition, clarity
    style_consistency: float    # Matches video style guide?
    explanation: str            # Why this score

@dataclass
class QualityConfig:
    accept_threshold: float = 80.0
    retry_threshold: float = 50.0
    max_retries: int = 3
    importance_weight: float = 1.0  # Hero scenes get stricter thresholds

class QualityEvaluator:
    """Vision-based quality scoring for generated assets."""

    def __init__(self, vision_provider: VisionProvider, style_guide: Optional[StyleGuide] = None):
        self.vision = vision_provider
        self.style_guide = style_guide

    async def evaluate(
        self,
        asset_path: Path,
        scene: Scene,
        context: Optional[str] = None
    ) -> QualityScore:
        """Score an asset against scene requirements."""
        prompt = self._build_evaluation_prompt(scene, context)

        # Vision model evaluates the asset
        response = await self.vision.analyze(
            image_path=asset_path,
            prompt=prompt
        )

        return self._parse_score(response)

    def _build_evaluation_prompt(self, scene: Scene, context: str) -> str:
        return f"""Evaluate this image/video for use in a video essay.

NARRATION: "{scene.narration_excerpt}"
VISUAL INTENT: {scene.visual_description}
STYLE GUIDE: {self.style_guide.summary() if self.style_guide else 'None specified'}

Score from 0-100 on:
1. SEMANTIC FIT: Does the visual match what's being said?
2. VISUAL QUALITY: Is it high quality (no artifacts, good composition)?
3. STYLE CONSISTENCY: Does it match the video's visual style?

Return JSON:
{{
  "semantic_fit": 0-100,
  "visual_quality": 0-100,
  "style_consistency": 0-100,
  "overall": 0-100,
  "explanation": "brief reason for scores"
}}"""
```

**Scene Integration:** Add quality tracking fields

```python
@dataclass
class Scene:
    # ... existing fields ...

    # Quality tracking (Layer 4)
    quality_score: Optional[float] = None
    quality_details: Optional[Dict] = None
    generation_attempts: int = 0
    flagged_for_review: bool = False
    review_reason: Optional[str] = None
```

---

#### 5. Human Review System (Layer 4)

**Location:** New `src/nolan/review_queue.py`

```python
@dataclass
class ReviewItem:
    scene_id: str
    project_path: Path
    current_asset: Optional[Path]
    quality_score: float
    reason: str
    priority: float  # importance × quality_gap
    status: str      # 'pending' | 'in_review' | 'resolved'
    resolution: Optional[str] = None  # 'approved' | 'replaced' | 'regenerated'

class ReviewQueue:
    """Manages scenes flagged for human review."""

    def __init__(self, db_path: Path):
        self.db = sqlite3.connect(db_path)
        self._init_schema()

    def add(self, scene: Scene, reason: str, importance: float = 1.0):
        """Add a scene to the review queue."""
        priority = importance * (100 - (scene.quality_score or 0))
        # Insert into DB
        pass

    def get_pending(self, limit: int = 10) -> List[ReviewItem]:
        """Get top priority items needing review."""
        pass

    def resolve(self, scene_id: str, resolution: str, new_asset: Optional[Path] = None):
        """Mark an item as reviewed."""
        pass
```

**CLI Integration:**

```bash
# New commands
nolan review list                    # Show pending reviews
nolan review serve                   # Launch review web UI
nolan review resolve <scene_id> --approve
nolan review resolve <scene_id> --replace <asset_path>
```

---

### Modified Pipeline Flow

```
CURRENT PIPELINE:
Essay → Script → Beats → Scenes → Assets → Align → Assemble

NEW PIPELINE:
Essay → Script → Beats → Scenes
                           ↓
                    ┌──────┴──────┐
                    │ Visual Type │
                    │   Router    │
                    └──────┬──────┘
          ┌────────────────┼────────────────┐
          ↓                ↓                ↓
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │ Template │    │ Video    │    │ Library  │
    │ Search   │    │ Generate │    │ Search   │
    └────┬─────┘    └────┬─────┘    └────┬─────┘
          └────────────────┼────────────────┘
                           ↓
                    ┌──────────────┐
                    │   Quality    │
                    │  Evaluation  │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ↓            ↓            ↓
         Accept       Retry (≤3x)    Flag
         (≥80)        (50-79)       (<50)
              │            │            │
              │            │            ↓
              │            │     ┌──────────┐
              │            │     │  Human   │
              │            │     │  Review  │
              │            │     └────┬─────┘
              └────────────┴──────────┘
                           ↓
                    Align → Assemble
```

---

### Config Changes

**nolan.yaml additions:**

```yaml
# Autonomous quality system
quality:
  enabled: true
  accept_threshold: 80
  retry_threshold: 50
  max_retries: 3
  vision_provider: gemini  # or ollama

# Visual type routing
routing:
  template_types: [text-overlay, infographic, lottie, lower-third, chart]
  video_gen_types: [b-roll, cinematic, ambient]
  prefer_library: true  # Try library before video generation

# Video generation
video_generation:
  backend: ltx  # ltx | runway
  ltx:
    host: localhost
    port: 8188
  runway:
    api_key: ${RUNWAY_API_KEY}
  cost_limit_per_video: 10.00  # USD

# Template library
templates:
  library_path: assets/templates/
  vector_db_path: .template_vectors/

# Human review
review:
  enabled: true
  notification: cli  # cli | webhook | email
  webhook_url: null
```

---

### Database Schema Additions

```sql
-- Review queue table
CREATE TABLE review_queue (
    id TEXT PRIMARY KEY,
    scene_id TEXT NOT NULL,
    project_path TEXT NOT NULL,
    current_asset TEXT,
    quality_score REAL,
    reason TEXT,
    priority REAL,
    status TEXT DEFAULT 'pending',
    resolution TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);

-- Quality history table
CREATE TABLE quality_history (
    id INTEGER PRIMARY KEY,
    scene_id TEXT NOT NULL,
    attempt INTEGER,
    asset_path TEXT,
    score REAL,
    details TEXT,  -- JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Template index table
CREATE TABLE templates (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    visual_type TEXT,
    tags TEXT,  -- JSON array
    schema TEXT,  -- JSON customization schema
    embedding BLOB,  -- Vector embedding
    indexed_at TIMESTAMP
);
```

---

## Related Documents

- [Scene Workflow](./2026-01-11-scene-workflow.md) - Current scene design system
- [Render Pipeline](./2026-01-12-render-pipeline.md) - Current render architecture
- [Lottie Integration](../LOTTIE_INTEGRATION.md) - Template system foundation
- [Motion Effects](../MOTION_EFFECTS.md) - Animation capabilities
