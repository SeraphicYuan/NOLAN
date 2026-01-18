# Motion Effects Library Design

> **Goal:** Create a library of reusable motion effects/presets that LLMs can use when generating video essays, with a Showcase UI for users to browse and generate effects.

---

## Architecture Overview

### Approach: Scene Presets

Effects are high-level, ready-to-use patterns (not low-level primitives). Each preset bundles specific animations with sensible defaults.

**Why presets over primitives:**
- LLMs excel at selecting from a curated catalog with clear descriptions
- Video essays have predictable patterns (title cards, quote callouts, stat reveals)
- Presets enforce good defaults (timing, easing, spacing)
- Easier to showcase - each preset = one preview video/GIF

### Organization: Content × Technique

Presets are organized as combinations of content type and motion technique:

| Category | Effects |
|----------|---------|
| `image` | ken-burns, zoom-focus, parallax-layers |
| `quote` | fade-center, typewriter, dramatic-reveal |
| `statistic` | counter-roll, bar-grow, highlight-pulse |
| `chart` | bar-race, line-draw, pie-expand |
| `comparison` | side-by-side, before-after-wipe, toggle-flip |
| `title` | title-card, chapter-heading, lower-third |
| `transition` | fade, wipe, zoom-through |

---

## Effects Registry

### File Structure

```
render-service/src/effects/
├── registry.ts          # Central catalog of all effects
├── types.ts             # TypeScript interfaces
└── presets/
    ├── image.ts         # ken-burns, zoom-focus, parallax
    ├── quote.ts         # fade-center, typewriter, dramatic
    ├── statistic.ts     # counter-roll, bar-grow
    ├── chart.ts         # bar-race, line-draw, pie-expand
    ├── comparison.ts    # side-by-side, before-after-wipe
    ├── title.ts         # title-card, chapter-heading
    └── transition.ts    # fade, wipe, zoom-through
```

### Type Definitions

```typescript
// render-service/src/effects/types.ts

type ParameterType =
  | "string"      // TextInput
  | "text"        // TextArea (multiline)
  | "number"      // NumberInput
  | "duration"    // DurationSlider (1-30s)
  | "color"       // ColorPicker
  | "image"       // ImageUpload
  | "select"      // SelectDropdown
  | "items";      // ItemsList (array of objects)

interface ParameterDef {
  name: string;
  type: ParameterType;
  label: string;
  description?: string;
  required: boolean;
  default?: any;
  options?: string[];        // For "select" type
  itemSchema?: ParameterDef[]; // For "items" type
  min?: number;              // For "number"/"duration"
  max?: number;
}

interface EffectPreset {
  id: string;                    // "image-ken-burns"
  name: string;                  // "Ken Burns"
  category: string;              // "image"
  description: string;           // Human/LLM readable
  engine: "remotion" | "motion-canvas" | "infographic";
  parameters: ParameterDef[];
  defaults: Record<string, any>;
  preview: string;               // Path to preview GIF/MP4

  // Maps user params to engine-specific data format
  toEngineData(params: Record<string, any>): Record<string, any>;
}
```

### Example Preset

```typescript
// render-service/src/effects/presets/image.ts

export const kenBurns: EffectPreset = {
  id: "image-ken-burns",
  name: "Ken Burns",
  category: "image",
  description: "Slow pan and zoom across a still image. Classic documentary technique for bringing photos to life.",
  engine: "remotion",
  parameters: [
    {
      name: "image",
      type: "image",
      label: "Image",
      description: "The image to animate",
      required: true
    },
    {
      name: "duration",
      type: "duration",
      label: "Duration",
      description: "Effect duration in seconds",
      required: false,
      default: 6,
      min: 2,
      max: 30
    },
    {
      name: "direction",
      type: "select",
      label: "Direction",
      description: "Pan direction",
      required: false,
      default: "left-to-right",
      options: ["left-to-right", "right-to-left", "top-to-bottom", "bottom-to-top"]
    },
    {
      name: "zoom",
      type: "select",
      label: "Zoom",
      description: "Zoom behavior",
      required: false,
      default: "zoom-in",
      options: ["zoom-in", "zoom-out", "none"]
    }
  ],
  defaults: {
    duration: 6,
    direction: "left-to-right",
    zoom: "zoom-in"
  },
  preview: "/previews/image-ken-burns.mp4",

  toEngineData(params) {
    return {
      duration: params.duration,
      image_focus: {
        image_path: params.image,
        zoom_from: params.zoom === "zoom-out" ? 1.3 : 1.0,
        zoom_to: params.zoom === "zoom-in" ? 1.3 : 1.0,
        pan_direction: params.direction
      }
    };
  }
};
```

---

## API Endpoints

### GET /effects

Returns the full effects catalog for UI and LLM consumption.

**Response:**
```json
{
  "effects": [
    {
      "id": "image-ken-burns",
      "name": "Ken Burns",
      "category": "image",
      "description": "Slow pan and zoom across a still image...",
      "engine": "remotion",
      "parameters": [...],
      "defaults": {...},
      "preview": "/previews/image-ken-burns.mp4"
    }
  ],
  "categories": ["image", "quote", "statistic", "chart", "comparison", "title", "transition"]
}
```

### POST /render (updated)

Now accepts effect ID instead of raw engine data:

**Request:**
```json
{
  "effect": "image-ken-burns",
  "params": {
    "image": "/path/to/uploaded/image.jpg",
    "duration": 8,
    "direction": "right-to-left",
    "zoom": "zoom-in"
  }
}
```

**Backwards compatible:** Still accepts `{ engine, data }` for direct engine access.

---

## Showcase UI

### Location

Separate page at `/showcase` - independent from library viewer.

### Layout: Gallery-First

```
┌─────────────────────────────────────────────────────────────┐
│  SHOWCASE                                    [Search] [Filter]│
├─────────────────────────────────────────────────────────────┤
│  Categories: [All] [Image] [Quote] [Statistic] [Chart] ...  │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ [GIF]    │  │ [GIF]    │  │ [GIF]    │  │ [GIF]    │    │
│  │ Ken Burns│  │ Zoom     │  │ Parallax │  │ Fade     │    │
│  │          │  │ Focus    │  │ Layers   │  │ Center   │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ [GIF]    │  │ [GIF]    │  │ [GIF]    │  │ [GIF]    │    │
│  │Typewriter│  │ Counter  │  │ Bar Race │  │ Side by  │    │
│  │          │  │ Roll     │  │          │  │ Side     │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Detail Panel (on click)

```
┌─────────────────────────────────────────────────────────────┐
│  ← Back                                                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌─────────────────────────┐    Ken Burns                  │
│   │                         │    ─────────────────────────  │
│   │      [Preview Video]    │    Slow pan and zoom across   │
│   │                         │    a still image. Classic     │
│   │                         │    documentary technique.     │
│   └─────────────────────────┘                               │
│                                                              │
│   Parameters                                                 │
│   ─────────────────────────────────────────────────────────│
│   Image:     [Upload Image]  [Browse...]                    │
│   Duration:  [====●=====] 6s                                │
│   Direction: [Left to Right ▼]                              │
│   Zoom:      [Zoom In ▼]                                    │
│                                                              │
│   [Generate Preview]                                         │
│                                                              │
│   ┌─────────────────────────┐                               │
│   │   [Generated Result]    │    [Download] [Use in Project]│
│   └─────────────────────────┘                               │
└─────────────────────────────────────────────────────────────┘
```

### Typed Input Components

| Component | HTML/Implementation |
|-----------|---------------------|
| `ImageUpload` | Drag-drop zone + file input, preview thumbnail |
| `ColorPicker` | Native color input + preset swatches |
| `DurationSlider` | Range input with value display (1-30s) |
| `TextInput` | Standard text input |
| `TextArea` | Multiline textarea |
| `NumberInput` | Number input with min/max/step |
| `SelectDropdown` | Native select element |
| `ItemsList` | Dynamic list with add/remove, per-item fields |

---

## File Handling

### Upload Flow

1. User uploads image in Showcase UI
2. Frontend sends to `/upload` endpoint
3. Server saves to `render-service/uploads/{uuid}.{ext}`
4. Path returned to frontend
5. Path included in render request
6. After render, cleanup old uploads (>1 hour)

### Preview Generation

Script to generate preview GIFs/MP4s for all effects:

```bash
cd render-service
npm run generate-previews
```

- Uses sample data for each effect
- Outputs to `render-service/public/previews/`
- Run after adding new effects

---

## LLM Integration

### How LLM Uses Effects

1. Scene planning prompt includes effect catalog (from `GET /effects`)
2. LLM selects effect ID based on content and intent
3. Scene plan includes:
   ```json
   {
     "scene_type": "effect",
     "effect": "image-ken-burns",
     "params": {
       "image": "{asset_path}",
       "duration": 6
     }
   }
   ```
4. Render pipeline calls `/render` with effect + params

### Prompt Context

Include in scene planning prompt:
```
Available motion effects:

IMAGE EFFECTS:
- image-ken-burns: Slow pan and zoom across still image. Documentary style.
- image-zoom-focus: Static start, zoom to detail. For revealing specifics.
- image-parallax: Multi-layer parallax movement. For depth.

QUOTE EFFECTS:
- quote-fade-center: Text fades in centered. Simple, elegant.
- quote-typewriter: Character-by-character reveal. For emphasis.
- quote-dramatic: Scale up with blur-to-sharp. For impact.

[... etc]
```

---

## Implementation Plan

### Phase 1: Effects Registry
1. Create `render-service/src/effects/types.ts`
2. Create `render-service/src/effects/registry.ts`
3. Implement preset files for each category
4. Add `GET /effects` endpoint
5. Update `POST /render` to accept effect ID

### Phase 2: Preview Generation
1. Create sample assets for each effect
2. Build preview generation script
3. Generate and store previews

### Phase 3: Showcase UI
1. Create `/showcase` route in Flask app
2. Build `showcase.html` template
3. Implement gallery grid with category filters
4. Build detail panel with parameter form
5. Implement typed input components
6. Connect to render API

### Phase 4: Polish
1. Add search functionality
2. Add "Use in Project" integration
3. Update LLM prompts with effect catalog
4. Documentation sync

---

## Files to Create/Modify

### New Files
- `render-service/src/effects/types.ts`
- `render-service/src/effects/registry.ts`
- `render-service/src/effects/presets/*.ts`
- `render-service/scripts/generate-previews.ts`
- `src/nolan/templates/showcase.html`
- `docs/MOTION_EFFECTS.md`

### Modified Files
- `render-service/src/routes/render.ts` - Add effect ID support
- `render-service/src/server.ts` - Add /effects route
- `src/nolan/cli.py` - Add showcase route
- `src/nolan/infographic_client.py` - Add effects methods

---

## Success Criteria

1. All existing engine capabilities exposed as named effects
2. `GET /effects` returns complete catalog
3. Showcase UI renders gallery of all effects
4. Users can generate any effect with custom params
5. LLM can select effects by ID in scene plans
6. Preview GIFs exist for all effects
