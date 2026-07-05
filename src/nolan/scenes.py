"""Scene design for NOLAN."""

import json
import re
import asyncio
from pathlib import Path
from dataclasses import dataclass, field, asdict
from dataclasses import fields as _dc_fields
from typing import List, Dict, Optional, Any

from nolan.script import ScriptSection


@dataclass
class Beat:
    """A beat is a distinct unit of thought in the narration.

    Pass 1 output: structural backbone of the A/V script.
    """
    id: str
    narration: str                          # The exact words for this beat
    category: str                           # b-roll, graphics, a-roll, generated, host
    mode: str                               # see-say, counterpoint
    visual_intent: str                      # Brief description of visual need
    has_visual_hole: bool = False           # True if abstract concept with no obvious visual
    sync_word: Optional[str] = None         # Key word that triggers visual change


@dataclass
class SyncPoint:
    """Word-to-action synchronization point.

    Connects a trigger word/phrase in the narration to a visual action.
    The `time` field is None in Step 1 (design), populated in Step 4 (timing alignment).
    """
    trigger: str                    # Word/phrase to match in SRT
    action: str                     # reveal, highlight, zoom, show_lower_third, animate
    target: Optional[Any] = None    # Item index, element id, coordinates, etc.
    time: Optional[float] = None    # None in Step 1, populated in Step 4


@dataclass
class Layer:
    """A visual layer within a scene.

    Used for complex scenes with multiple visual elements stacked together.
    """
    type: str                       # background, overlay, caption, lower_third
    asset: Optional[str] = None     # Path to asset
    style: Optional[Dict] = None    # Position, opacity, animation params
    sync_point: Optional[SyncPoint] = None  # When to show/animate this layer


# =============================================================================
# PASS 1: Beat Detection & Visual Assignment
# =============================================================================
# Break narration into "beats" (distinct thought units) and assign visual categories.
# This is the structural pass - no details yet, just the backbone.

PASS1_BEAT_PROMPT = """You are an A/V script writer for video essays.

SECTION: {title}
TIMESTAMP: {timestamp}
NARRATION:
{narration}

Break this narration into BEATS. A beat is a distinct unit of thought - it could be:
- A single sentence making one point
- A phrase introducing a new concept
- A rhetorical question
- A transition moment

For each beat, decide:
1. What VISUAL CATEGORY should accompany it? CHOOSE BY WHAT CAN ACTUALLY BE PRODUCED:
   - generated: THE DEFAULT for most beats. AI-generated imagery for anything that is NOT
     real, findable footage — historical reconstructions (ancient/period eras with no film),
     dramatizations, specific artifacts, metaphors, symbolic or conceptual shots. When unsure,
     choose generated: generation can render any single described image.
   - b-roll: ONLY for genuine REAL footage that plausibly exists in archives/stock — real
     historical events with known footage (e.g. WWII newsreels, a moon landing), real modern
     events, identifiable real people/places, or generic real-world stock (a stadium crowd, a
     city street, ocean waves). Do NOT use b-roll for reconstructions, pre-film eras, imagined
     scenes, or compound/montage visuals — those are 'generated'.
   - graphics: data, maps, timelines, comparisons, statistics, quotes, animated text.
   - a-roll: primary footage of the literal real subject (only if such footage exists).
   - host: face-to-camera presenter moment (rare).

2. Is this SEE-SAY or COUNTERPOINT?
   - see-say: Visual directly illustrates what's being said
   - counterpoint: Visual adds meaning NOT in the narration (more sophisticated)

3. Is there a VISUAL HOLE? (Abstract concept with no obvious visual)

Return a JSON array:
[
  {{
    "id": "beat_001",
    "narration": "the exact words for this beat",
    "category": "generated|b-roll|graphics|a-roll|host",
    "mode": "see-say|counterpoint",
    "visual_intent": "brief description of what this beat needs visually",
    "has_visual_hole": false,
    "sync_word": "optional key word that should trigger a visual change"
  }}
]

GUIDELINES:
- Every sentence or distinct thought = one beat
- Don't over-split: keep phrases that flow together as one beat
- PREFER 'generated' over 'b-roll' whenever in doubt — generation reliably produces any image;
  real footage is scarce and only fits real, documented events/people/places.
- Flag visual_hole=true for abstract concepts (e.g., "freedom", "economic anxiety")
- sync_word is optional - only include for impactful moments

IMPORTANT: Return ONLY the JSON array, no other text."""


# =============================================================================
# PASS 2: Category-Specific Details
# =============================================================================
# For each beat, generate details appropriate to its visual category.

PASS2_BROLL_PROMPT = """You are sourcing B-roll footage for a video essay beat.

BEAT: {beat_id}
NARRATION: "{narration}"
VISUAL INTENT: {visual_intent}
MODE: {mode}

Generate search queries and visual details for this beat.

Return JSON:
{{
  "search_queries": ["primary search terms", "alternative search", "abstract/metaphorical option"],
  "visual_description": "detailed description of ideal footage",
  "mood": "energetic|calm|tense|hopeful|somber|neutral",
  "motion": "static|slow|dynamic",
  "suggested_duration": "Xs"
}}

IMPORTANT: Return ONLY the JSON object, no other text."""


INFOGRAPHIC_TEMPLATE_REGISTRY = """
High-value AntV templates (use exact names):
- sequence-steps-simple: steps/process. data.items: [{label, desc?}]
- sequence-timeline-simple: timeline. data.items: [{label, desc?}]
- list-row-simple-horizontal-arrow: list of points. data.items: [{label, desc?}]
- list-grid-simple: grid list. data.items: [{label, desc?}]
- compare-binary-horizontal-simple-vs: A vs B. data.items: ["A label", "B label"] or
  [{label, children:[{label, desc?}]}] for multi-row comparisons.
- chart-column-simple: bar/column chart. data.items: [{label, value}]
- chart-line-plain-text: line chart. data.items: [{label, value}]
- chart-pie-plain-text: pie chart. data.items: [{label, value}]
- sequence-roadmap-vertical-simple: vertical roadmap. data.items: [{label, desc?}]
- list-pyramid-compact-card: pyramid hierarchy. data.items: [{label, desc?}]

Theme presets (reference only):
- theme_config_ref: docu-dark-minimal | docu-warm-soft
""".strip()

PASS2_GRAPHICS_PROMPT = """You are designing a graphic/infographic for a video essay beat.

BEAT: {beat_id}
NARRATION: "{narration}"
VISUAL INTENT: {visual_intent}

Determine what type of graphic best serves this beat.

TEMPLATE CATALOG:
{template_catalog}

Return JSON:
{{
  "graphic_type": "infographic|chart|text-overlay|diagram|timeline|comparison",
  "spec": {{
    "template": "pick from the catalog above",
    "theme": "default|dark|warm|cool",
    "theme_config_ref": "docu-dark-minimal|docu-warm-soft (optional)",
    "title": "optional title",
    "items": [
      {{"label": "Item 1", "desc": "Detail or value", "icon_keyword": "optional icon hint"}},
      {{"label": "Item 2", "desc": "Detail or value", "icon_keyword": "optional icon hint"}}
    ]
  }},
  "text_overlay": {{
    "text": "key phrase to display (if text-overlay type)",
    "position": "center|bottom|top",
    "animation": "fade|typewriter|none"
  }},
  "sync_points": [
    {{"trigger": "word", "action": "reveal_item", "target": 0}}
  ],
  "suggested_duration": "Xs"
}}

NOTE: Include only relevant fields based on graphic_type.
IMPORTANT: Return ONLY the JSON object, no other text."""


PASS2_GENERATED_PROMPT = """You are creating an AI image generation prompt for a video essay beat.

BEAT: {beat_id}
NARRATION: "{narration}"
VISUAL INTENT: {visual_intent}
MODE: {mode}

This beat needs a generated image because no stock footage exists for this concept.

Return JSON:
{{
  "comfyui_prompt": "detailed prompt for Stable Diffusion / FLUX image generation",
  "negative_prompt": "things to avoid in the image",
  "style": "photorealistic|illustration|abstract|cinematic|documentary",
  "aspect_ratio": "16:9|4:3|1:1",
  "visual_description": "what the final image should look like",
  "suggested_duration": "Xs"
}}

IMPORTANT: Return ONLY the JSON object, no other text."""


PASS2_AROLL_PROMPT = """You are matching primary footage (A-roll) for a video essay beat.

BEAT: {beat_id}
NARRATION: "{narration}"
VISUAL INTENT: {visual_intent}

This beat should show footage of the actual subject being discussed.

Return JSON:
{{
  "search_terms": ["terms to search in video library"],
  "visual_description": "what specific footage we need",
  "timestamp_hint": "if discussing a specific scene/moment, describe it",
  "framing": "wide|medium|close-up|detail",
  "suggested_duration": "Xs"
}}

IMPORTANT: Return ONLY the JSON object, no other text."""


# =============================================================================
# PASS 2: Flexible Beat → Scene Mapping
# =============================================================================
# LLM sees ALL beats and decides how to map them to scenes.

PASS2_SCENES_PROMPT = """You are converting beats into visual scenes for a video essay.

SECTION: {section_title}
BEATS:
{beats_json}

Convert these beats into SCENES. Mapping:
- 1 beat → 1 scene (most common)
- 1 beat → multiple scenes when the beat implies a montage / quick cuts — emit ONE SCENE PER
  SHOT, each with its OWN single-visual description and asset (never pack a montage into one scene)
- Multiple beats → 1 scene (when one sustained visual spans multiple thoughts, e.g., an infographic
  with reveals)

CRITICAL — each scene depicts ONE clear, single, concrete visual:
- The visual_description must be a SINGLE image/shot ("a Mayan stone relief of ballplayers"), never a
  list of shots ("Shot 1… Shot 2… Shot 3…"). If you wrote a montage, split it into multiple scenes.
- Make subjects concrete and self-contained so they can be sourced or generated.

ROUTE BY FULFILLABILITY (generation-first):
- Default to "generated" with a concrete, cinematic `comfyui_prompt` for reconstructions, period
  scenes, artifacts, metaphors, and any imagined/symbolic shot.
- Use "b-roll" ONLY for genuine real footage that plausibly exists (real documented events/people/
  places, generic real-world stock). If a b-roll subject isn't real findable footage, switch it to
  "generated" and write a comfyui_prompt instead.
- "graphics" for data/maps/timelines/quotes.

For each scene, provide full visual specifications based on its category.

TEMPLATE CATALOG:
{template_catalog}

Return JSON array:
[
  {{
    "id": "scene_001",
    "covers_beats": ["beat_001"],
    "visual_type": "b-roll|graphics|a-roll|generated|host",
    "visual_description": "detailed description of what appears on screen",
    "narration_excerpt": "the key phrase from covered beats for timing alignment",
    "duration": "Xs",
    "search_queries": ["for b-roll/a-roll: search terms"],
    "comfyui_prompt": "for generated: AI image prompt",
    "infographic": {{
      "template": "pick from catalog",
      "theme": "default|dark|warm|cool",
      "theme_config_ref": "docu-dark-minimal|docu-warm-soft (optional)",
      "data": {{"title": "...", "items": [{{"label": "...", "icon_keyword": "optional"}}]}}
    }},
    "sync_points": [
      {{"trigger": "word", "action": "reveal|highlight|cut", "target": 0}}
    ],
    "mood": "energetic|calm|tense|hopeful|somber|neutral",
    "transition": "cut|fade|dissolve"
  }}
]

GUIDELINES:
- Include only relevant fields per visual_type
- ALWAYS include a concrete `comfyui_prompt` for "generated" scenes (single subject, cinematic,
  period/style-accurate)
- For graphics with multiple data points, use sync_points to reveal items on trigger words
- For montage (1 beat → N scenes), create quick sequential scenes, EACH a single visual
- For sustained visual (N beats → 1 scene), combine narration_excerpt from all beats
- narration_excerpt should be the KEY PHRASE for SRT timestamp matching

IMPORTANT: Return ONLY the JSON array, no other text."""


# Legacy prompt for backward compatibility
SCENE_DESIGN_PROMPT = PASS1_BEAT_PROMPT


@dataclass
class Scene:
    """A single visual scene - progressively enriched across workflow steps.

    Step 1 (Design): id, covers_beats, narration_excerpt, visual_type,
                     visual_description, search_query, comfyui_prompt, animation hints,
                     sync_points (trigger/action only), layers hints, infographic spec
    Step 2 (Assets): matched_asset, generated_asset, infographic_asset, layer assets
    Step 4 (Timing): start_seconds, end_seconds, sync_points (time populated), subtitle_cues
    Step 5 (Render): final composition using all populated fields
    """
    # === Identity ===
    id: str
    covers_beats: List[str] = field(default_factory=list)  # Beat IDs this scene covers

    # === Timing (estimated in Step 1, precise after Step 4) ===
    start: str = "0:00"                     # Placeholder, refined in Step 4
    duration: str = "5s"                    # LLM estimate
    start_seconds: Optional[float] = None   # Precise, from SRT (Step 4)
    end_seconds: Optional[float] = None     # Precise, from SRT (Step 4)

    # === Content ===
    narration_excerpt: str = ""             # Key phrase for SRT matching
    visual_type: str = "b-roll"             # b-roll, graphic, text-overlay, generated-image, infographic, layered, lottie
    visual_description: str = ""            # What appears on screen

    # === Asset Sources (Step 1 hints) ===
    search_query: str = ""                  # Stock footage keywords
    comfyui_prompt: str = ""                # AI image generation prompt
    library_match: bool = True              # Try indexed library first

    # === Animation (Step 1 hints, refined in Step 4/5) ===
    animation_type: Optional[str] = None    # static, zoom, pan, reveal, kinetic
    animation_params: Optional[Dict] = None # {zoom_from, zoom_to, focus_x, focus_y, direction}
    transition: Optional[str] = None        # cut, fade, dissolve, wipe

    # === Rhythm/tempo (set by the Editorial Arc pass — nolan.tempo_plan) ===
    energy: Optional[float] = None          # 0..1 target intensity for this beat (whole-script arc)
    motion_speed: Optional[str] = None      # slow | medium | fast — biases motion selection

    # === Sync Points (Step 1 hints trigger/action, Step 4 adds time) ===
    sync_points: List[SyncPoint] = field(default_factory=list)

    # === Layers for complex scenes ===
    layers: List[Layer] = field(default_factory=list)

    # === Infographic spec (if visual_type == "infographic") ===
    infographic: Optional[Dict[str, Any]] = None

    # === Lottie animation (if visual_type == "lottie") ===
    lottie_template: Optional[str] = None   # Path to Lottie JSON template
    lottie_config: Optional[Dict] = None    # {text: {old: new}, colors: {#hex: #hex}, duration, fps}
    lottie_asset: Optional[str] = None      # Generated customized Lottie file

    # === Text overlay style (if visual_type == "text-overlay") ===
    text_style: Optional[Dict] = None       # {position, font_size, color, animation}

    # === Asset Results (populated in Step 2/3) ===
    skip_generation: bool = False
    matched_asset: Optional[str] = None
    layout_spec: Optional[str] = None    # slide_designer JSON (info scenes)      # Downloaded b-roll image
    generated_asset: Optional[str] = None    # AI-generated image
    infographic_asset: Optional[str] = None  # Static SVG infographic
    infographic_asset_png: Optional[str] = None  # PNG preview for infographics
    rendered_clip: Optional[str] = None      # Pre-rendered MP4 clip (highest priority)
    matched_clip: Optional[Dict[str, Any]] = None  # Video library clip match
    motion_spec: Optional[Dict[str, Any]] = None  # nolan.motion spec (NL-authored effect)
    resolved_source: Optional[str] = None    # segment builder: which source rendered this

    # === SRT Cues (attached in Step 4) ===
    subtitle_cues: List[Any] = field(default_factory=list)  # SubtitleCue objects
    # Lossless round-trip: unknown keys survive here (schema contract v2)
    extra: Dict[str, Any] = field(default_factory=dict)


_SCENE_FIELD_NAMES = {f.name for f in _dc_fields(Scene)}


@dataclass
class ScenePlan:
    """Complete scene plan for a video."""
    sections: Dict[str, List[Scene]] = field(default_factory=dict)
    # Non-"sections" top-level keys (e.g. _meta) — preserved on round-trip.
    meta: Dict[str, Any] = field(default_factory=dict)

    SCHEMA_VERSION = 2

    @staticmethod
    def _scene_to_dict(scene: "Scene") -> Dict:
        """Scene → dict, folding preserved unknown keys back to the top level."""
        d = asdict(scene)
        extra = d.pop("extra", None) or {}
        for k, v in extra.items():
            d.setdefault(k, v)
        return d

    def to_json(self, indent: int = 2) -> str:
        """Export to JSON string (lossless: schema_version + preserved meta/extra)."""
        data = {"schema_version": self.SCHEMA_VERSION}
        for k, v in (self.meta or {}).items():
            if k not in ("sections", "schema_version"):
                data[k] = v
        data["sections"] = {
            title: [self._scene_to_dict(scene) for scene in scenes]
            for title, scenes in self.sections.items()
        }
        return json.dumps(data, indent=indent)

    def save(self, path: str) -> None:
        """Save to JSON file."""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> "ScenePlan":
        """Load from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        plan = cls()
        plan.meta = {k: v for k, v in data.items()
                     if k not in ("sections", "schema_version")}
        for title, scenes_data in data["sections"].items():
            plan.sections[title] = [
                cls._scene_from_dict(scene) for scene in scenes_data
            ]
        return plan

    @staticmethod
    def _scene_from_dict(data: Dict) -> "Scene":
        """Convert a dict to a Scene, handling nested dataclasses."""
        # Parse sync points
        sync_points = []
        for sp_data in data.get("sync_points", []):
            if isinstance(sp_data, dict):
                sync_points.append(SyncPoint(
                    trigger=sp_data.get("trigger", ""),
                    action=sp_data.get("action", "reveal"),
                    target=sp_data.get("target"),
                    time=sp_data.get("time"),
                ))
            elif isinstance(sp_data, SyncPoint):
                sync_points.append(sp_data)

        # Parse layers
        layers = []
        for layer_data in data.get("layers", []):
            if isinstance(layer_data, dict):
                layer_sync = None
                if layer_data.get("sync_point"):
                    sp = layer_data["sync_point"]
                    layer_sync = SyncPoint(
                        trigger=sp.get("trigger", ""),
                        action=sp.get("action", "fade_in"),
                        target=sp.get("target"),
                        time=sp.get("time"),
                    )
                layers.append(Layer(
                    type=layer_data.get("type", "overlay"),
                    asset=layer_data.get("asset"),
                    style=layer_data.get("style"),
                    sync_point=layer_sync,
                ))
            elif isinstance(layer_data, Layer):
                layers.append(layer_data)

        # Build scene with parsed nested objects
        return Scene(
            id=data["id"],
            covers_beats=data.get("covers_beats", []),
            start=data.get("start", "0:00"),
            duration=data.get("duration", "5s"),
            start_seconds=data.get("start_seconds"),
            end_seconds=data.get("end_seconds"),
            narration_excerpt=data.get("narration_excerpt", ""),
            visual_type=data.get("visual_type", "b-roll"),
            visual_description=data.get("visual_description", ""),
            search_query=data.get("search_query", ""),
            comfyui_prompt=data.get("comfyui_prompt", ""),
            library_match=data.get("library_match", True),
            animation_type=data.get("animation_type"),
            animation_params=data.get("animation_params"),
            transition=data.get("transition"),
            energy=data.get("energy"),
            motion_speed=data.get("motion_speed"),
            sync_points=sync_points,
            layers=layers,
            infographic=data.get("infographic"),
            text_style=data.get("text_style"),
            skip_generation=data.get("skip_generation", False),
            matched_asset=data.get("matched_asset"),
            layout_spec=data.get("layout_spec"),
            generated_asset=data.get("generated_asset"),
            infographic_asset=data.get("infographic_asset"),
            infographic_asset_png=data.get("infographic_asset_png"),
            rendered_clip=data.get("rendered_clip"),
            matched_clip=data.get("matched_clip"),
            motion_spec=data.get("motion_spec"),
            resolved_source=data.get("resolved_source"),
            subtitle_cues=data.get("subtitle_cues", []),
            # lossless: any key this schema doesn't know survives in `extra`
            extra={k: v for k, v in data.items()
                   if k not in _SCENE_FIELD_NAMES and k != "extra"},
        )

    @property
    def all_scenes(self) -> List[Scene]:
        """Get all scenes flattened."""
        scenes = []
        for section_scenes in self.sections.values():
            scenes.extend(section_scenes)
        return scenes


@dataclass
class BeatPlan:
    """Pass 1 output: structural backbone of the A/V script."""
    section_title: str
    beats: List[Beat] = field(default_factory=list)

    def to_av_script(self) -> str:
        """Export as human-readable two-column A/V script."""
        lines = [f"# A/V SCRIPT: {self.section_title}\n"]
        lines.append("=" * 80)
        lines.append(f"{'VISUAL':<40} | {'AUDIO':<38}")
        lines.append("-" * 40 + "-+-" + "-" * 38)

        for beat in self.beats:
            # Truncate narration for display
            narration = beat.narration[:35] + "..." if len(beat.narration) > 38 else beat.narration
            visual = f"[{beat.category.upper()}] {beat.visual_intent[:25]}"
            if beat.has_visual_hole:
                visual = f"⚠️ {visual}"

            lines.append(f"{visual:<40} | {narration:<38}")

        lines.append("=" * 80)

        # Summary
        categories = {}
        visual_holes = 0
        for beat in self.beats:
            categories[beat.category] = categories.get(beat.category, 0) + 1
            if beat.has_visual_hole:
                visual_holes += 1

        lines.append(f"\nSummary: {len(self.beats)} beats")
        for cat, count in sorted(categories.items()):
            lines.append(f"  - {cat}: {count}")
        if visual_holes:
            lines.append(f"  - ⚠️ Visual holes: {visual_holes}")

        return "\n".join(lines)

    def to_dict(self) -> Dict:
        """Export as dictionary."""
        return {
            "section_title": self.section_title,
            "beats": [asdict(b) for b in self.beats]
        }


class SceneDesigner:
    """Designs visual scenes for script sections using a two-pass approach.

    Pass 1: Beat detection - break narration into thought units, assign visual categories
    Pass 2: Detail enrichment - add category-specific details (search queries, specs, etc.)
    """

    def __init__(self, llm_client, cache_dir=None, model_id: str = "default"):
        """Initialize the designer.

        Args:
            llm_client: The LLM client for scene generation.
            cache_dir: Optional directory to cache LLM responses on disk, so
                re-running design on the same script + model is instant.
            model_id: Identifier mixed into the cache key (so different models
                don't collide).
        """
        self.llm = llm_client
        self.model_id = model_id
        self._cache_dir = Path(cache_dir) if cache_dir else None
        if self._cache_dir:
            self._cache_dir.mkdir(parents=True, exist_ok=True)

    async def _cached_generate(self, prompt: str) -> str:
        """LLM generate with optional on-disk response cache (keyed by model+prompt)."""
        if not self._cache_dir:
            return await self.llm.generate(prompt)
        import hashlib
        key = hashlib.sha256(f"{self.model_id}\x00{prompt}".encode("utf-8")).hexdigest()[:32]
        cache_file = self._cache_dir / f"{key}.txt"
        if cache_file.exists():
            return cache_file.read_text(encoding="utf-8")
        result = await self.llm.generate(prompt)
        try:
            cache_file.write_text(result, encoding="utf-8")
        except Exception:
            pass  # cache best-effort
        return result

    # =========================================================================
    # PASS 1: Beat Detection
    # =========================================================================

    async def detect_beats(self, section: ScriptSection) -> BeatPlan:
        """Pass 1: Break narration into beats and assign visual categories.

        Args:
            section: The script section to analyze.

        Returns:
            BeatPlan with structural backbone.
        """
        prompt = PASS1_BEAT_PROMPT.format(
            title=section.title,
            timestamp=section.timestamp,
            narration=section.narration
        )

        response = await self._cached_generate(prompt)
        beats_data = self._parse_json_array(response)

        beats = []
        for beat_data in beats_data:
            beats.append(Beat(
                id=beat_data.get("id", f"beat_{len(beats)+1:03d}"),
                narration=beat_data.get("narration", ""),
                category=beat_data.get("category", "b-roll"),
                mode=beat_data.get("mode", "see-say"),
                visual_intent=beat_data.get("visual_intent", ""),
                has_visual_hole=beat_data.get("has_visual_hole", False),
                sync_word=beat_data.get("sync_word"),
            ))

        return BeatPlan(section_title=section.title, beats=beats)

    # =========================================================================
    # PASS 2: Flexible Beat → Scene Mapping
    # =========================================================================

    async def beats_to_scenes(self, beat_plan: BeatPlan) -> List[Scene]:
        """Pass 2: Convert beats to scenes with flexible mapping.

        The LLM sees ALL beats and decides:
        - 1 beat → 1 scene (common)
        - 1 beat → N scenes (montage)
        - N beats → 1 scene (sustained visual)

        Args:
            beat_plan: BeatPlan from Pass 1.

        Returns:
            List of Scene objects with flexible mapping.
        """
        # Format beats as JSON for the prompt
        beats_json = json.dumps([asdict(b) for b in beat_plan.beats], indent=2)

        prompt = PASS2_SCENES_PROMPT.format(
            section_title=beat_plan.section_title,
            beats_json=beats_json,
            template_catalog=INFOGRAPHIC_TEMPLATE_REGISTRY,
        )

        response = await self._cached_generate(prompt)
        scenes_data = self._parse_json_array(response)

        return [self._parse_scene_data(s) for s in scenes_data]

    def _parse_scene_data(self, data: Dict) -> Scene:
        """Parse scene data from Pass 2 LLM response."""
        # Extract search queries
        search_queries = data.get("search_queries", [])
        search_query = search_queries[0] if search_queries else ""

        # Extract sync points
        sync_points = []
        for sp in data.get("sync_points", []):
            sync_points.append(SyncPoint(
                trigger=sp.get("trigger", ""),
                action=sp.get("action", "reveal"),
                target=sp.get("target"),
            ))

        return Scene(
            id=data.get("id", "scene_001"),
            covers_beats=data.get("covers_beats", []),
            duration=data.get("duration", "5s"),
            narration_excerpt=data.get("narration_excerpt", ""),
            visual_type=data.get("visual_type", "b-roll"),
            visual_description=data.get("visual_description", ""),
            search_query=search_query,
            comfyui_prompt=data.get("comfyui_prompt", ""),
            library_match=(data.get("visual_type") in ["b-roll", "a-roll"]),
            transition=data.get("transition"),
            sync_points=sync_points,
            infographic=data.get("infographic"),
        )

    def _beat_to_basic_scene(self, beat: Beat) -> Scene:
        """Convert a beat to a basic scene (for --beats-only mode)."""
        return Scene(
            id=beat.id.replace("beat_", "scene_"),
            covers_beats=[beat.id],
            duration="5s",
            narration_excerpt=beat.narration,
            visual_type=beat.category,
            visual_description=beat.visual_intent,
            search_query="",
            comfyui_prompt="",
            library_match=(beat.category in ["b-roll", "a-roll"]),
        )

    # =========================================================================
    # Main API
    # =========================================================================

    async def design_section(self, section: ScriptSection, enrich: bool = True) -> List[Scene]:
        """Design scenes for a single script section using two-pass approach.

        Args:
            section: The script section to design for.
            enrich: If True, run Pass 2 with flexible mapping. If False, basic 1:1 scenes.

        Returns:
            List of Scene objects.
        """
        # Pass 1: Detect beats
        beat_plan = await self.detect_beats(section)

        if not enrich:
            # Return basic scenes without enrichment (1:1 mapping)
            return [self._beat_to_basic_scene(beat) for beat in beat_plan.beats]

        # Pass 2: Flexible beat → scene mapping
        # LLM sees all beats and decides the mapping
        scenes = await self.beats_to_scenes(beat_plan)

        return scenes

    async def design_section_beats_only(self, section: ScriptSection) -> BeatPlan:
        """Run only Pass 1 to get beat structure for review.

        Args:
            section: The script section to analyze.

        Returns:
            BeatPlan for human review before enrichment.
        """
        return await self.detect_beats(section)

    # Scenes whose visual is footage/generation — not authored as a motion effect.
    _NON_MOTION_TYPES = {"b-roll", "a-roll", "footage", "cinematic", "generated",
                         "generated-image", "host", "passthrough"}

    async def author_motion(self, scenes: List[Scene], concurrency: int = 4) -> List[Scene]:
        """Attach a `motion_spec` to graphic/text/data scenes by compiling their visual
        intent through the nolan.motion spec system (covers Python + Remotion effects)."""
        from nolan.motion import compile_spec
        sem = asyncio.Semaphore(max(1, concurrency))

        async def _one(scene: Scene):
            vt = (scene.visual_type or "").lower().strip()
            if vt in self._NON_MOTION_TYPES:
                return
            brief = (scene.visual_description or scene.narration_excerpt or "").strip()
            if not brief:
                return
            async with sem:
                try:
                    spec, _errors = await compile_spec(brief, self.llm)
                except Exception:
                    return
            if spec.get("backend"):   # a valid effect resolved
                scene.motion_spec = spec

        await asyncio.gather(*[_one(s) for s in scenes])
        return scenes

    async def design_full_plan(self, sections: List[ScriptSection], enrich: bool = True,
                               progress_callback=None, concurrency: int = 8,
                               author_motion: bool = False) -> ScenePlan:
        """Design scenes for all script sections.

        Args:
            sections: List of script sections.
            enrich: If True, run full two-pass. If False, beats only.
            progress_callback: Optional callable(current, total, scenes_so_far, message)
                invoked after each section, for live progress reporting.

        Returns:
            Complete ScenePlan.
        """
        plan = ScenePlan()
        total = len(sections)

        # Sections are independent, so design them concurrently (bounded) instead
        # of serially — the dominant speedup for long scripts. Order and progress
        # are preserved.
        sem = asyncio.Semaphore(max(1, concurrency))
        done = 0
        scenes_so_far = 0
        lock = asyncio.Lock()

        async def _one(i, section):
            nonlocal done, scenes_so_far
            async with sem:
                scenes = await self.design_section(section, enrich=enrich)
            section_prefix = self._sanitize_section_name(section.title)
            for scene in scenes:
                scene.id = f"{section_prefix}_{scene.id}"
            async with lock:
                done += 1
                scenes_so_far += len(scenes)
                if progress_callback:
                    progress_callback(done, total, scenes_so_far,
                                      f"{done}/{total} sections · {scenes_so_far} scenes so far")
            return section.title, scenes

        results = await asyncio.gather(*[_one(i, s) for i, s in enumerate(sections)])
        # Preserve original section order in the plan.
        by_title = dict(results)
        for section in sections:
            plan.sections[section.title] = by_title.get(section.title, [])

        # Optional: author motion specs (Python + Remotion effects) for graphic scenes.
        if author_motion:
            await self.author_motion(plan.all_scenes, concurrency=concurrency)

        return plan

    def _sanitize_section_name(self, name: str) -> str:
        """Sanitize section name for use in IDs (remove spaces, special chars)."""
        import re
        # Remove special chars, replace spaces with underscores
        sanitized = re.sub(r'[^\w\s-]', '', name)
        sanitized = re.sub(r'[\s-]+', '_', sanitized)
        return sanitized.strip('_')

    async def design_full_beats(self, sections: List[ScriptSection]) -> List[BeatPlan]:
        """Run Pass 1 on all sections, returning beat plans for review.

        Args:
            sections: List of script sections.

        Returns:
            List of BeatPlans (one per section).
        """
        beat_plans = []
        for section in sections:
            beat_plan = await self.detect_beats(section)
            beat_plans.append(beat_plan)
        return beat_plans

    # =========================================================================
    # JSON Parsing Helpers
    # =========================================================================

    @staticmethod
    def _strip_fences(response: str) -> str:
        """Strip markdown code fences (```json … ```) that some models add."""
        s = response.strip()
        if s.startswith("```"):
            s = re.sub(r'^```[a-zA-Z0-9_-]*\s*', '', s)
            s = re.sub(r'\s*```$', '', s.strip())
        return s.strip()

    def _parse_json_array(self, response: str) -> List[Dict]:
        """Parse a JSON array from an LLM response (tolerant of code fences)."""
        s = self._strip_fences(response)
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            match = re.search(r'\[.*\]', s, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError(f"Could not parse JSON array from response: {response[:200]}")

    def _parse_json_object(self, response: str) -> Dict:
        """Parse a JSON object from an LLM response (tolerant of code fences)."""
        s = self._strip_fences(response)
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', s, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError(f"Could not parse JSON object from response: {response[:200]}")


def tile_scene_windows(plan: "ScenePlan", audio_duration: float) -> int:
    """Make aligned scene windows TILE the audio (no gaps, no overlaps).

    `nolan align` gives each scene the span of its own matched words; the
    pauses/breaths between scenes belong to no scene, so summed durations run
    shorter than the audio and picture-sound sync drifts. Tiling extends each
    scene to the next scene's start (the last one to the audio end): a scene
    simply holds through the pause that follows it. Returns scenes adjusted.
    """
    scenes = [s for section in plan.sections.values() for s in section]
    starts = [s.start_seconds for s in scenes]
    n = 0
    for i, scene in enumerate(scenes):
        if starts[i] is None:
            continue
        nxt = next((starts[j] for j in range(i + 1, len(scenes))
                    if starts[j] is not None), audio_duration)
        new_end = max(float(nxt), float(starts[i]) + 1.0)
        if scene.end_seconds != new_end:
            scene.end_seconds = new_end
            n += 1
    return n


def anchor_scenes_to_sections(plan: "ScenePlan",
                              section_durations: "list[float]") -> int:
    """Beat-anchored sync: confine each section's scenes to its KNOWN audio span.

    When the voiceover is synthesized per-section and concatenated, the section
    boundaries in the audio are exact (cumulative file durations) — no speech
    matching involved. Within a section, whisper-aligned starts are kept when
    they fall inside the span in order; otherwise scene windows are distributed
    proportionally by narration word count. Scenes then tile the section, so
    sync error can never propagate across a beat boundary. Returns scenes set.
    """
    sections = list(plan.sections.values())
    if len(sections) != len(section_durations):
        raise ValueError(f"{len(sections)} plan sections vs "
                         f"{len(section_durations)} audio sections")
    n = 0
    cursor = 0.0
    for scenes, dur in zip(sections, section_durations):
        s0, s1 = cursor, cursor + float(dur)
        cursor = s1
        if not scenes:
            continue
        # keep whisper starts that are usable: inside the span, strictly increasing
        starts = []
        last = s0
        usable = True
        for sc in scenes:
            st = sc.start_seconds
            if st is None or st < last or st >= s1:
                usable = False
                break
            starts.append(float(st))
            last = float(st)
        if not usable:
            # proportional by narration length (words), min 1s per scene
            words = [max(1, len((sc.narration_excerpt or "").split()))
                     for sc in scenes]
            total = float(sum(words))
            starts, acc = [], s0
            for w in words:
                starts.append(acc)
                acc += (s1 - s0) * (w / total)
        # tile within the section (first scene owns the leading pause)
        starts[0] = s0
        for i, sc in enumerate(scenes):
            sc.start_seconds = round(starts[i], 3)
            sc.end_seconds = round(starts[i + 1] if i + 1 < len(scenes) else s1, 3)
            n += 1
    return n

