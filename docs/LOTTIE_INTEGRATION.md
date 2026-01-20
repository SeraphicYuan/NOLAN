# Lottie Integration Guide for NOLAN

This document covers how to use Lottie animations in NOLAN, including customization options, theming, and best practices.

## Overview

NOLAN uses [dotLottie](https://dotlottie.io/) (powered by ThorVG/WebAssembly) to render Lottie animations in the Remotion engine. This provides frame-accurate video rendering without the flickering issues of traditional lottie-web.

**Spike Test Results:**
- Location: `render-service/test/dotlottie-spike/`
- Status: Successfully renders Lottie to video with `setFrame()` for frame-accurate seeking

---

## Customizable Properties

### Quick Reference

| Property | Customizable | Method | Requires Slot ID |
|----------|--------------|--------|------------------|
| Text content | ✅ Yes | JSON edit or `setSlots()` | Yes (for theming) |
| Text font | ✅ Yes | JSON edit or theme | Yes |
| Text size | ✅ Yes | JSON edit or theme | Yes |
| Text color | ✅ Yes | JSON edit or theme | Yes |
| Fill colors | ✅ Yes | JSON edit or theme | Yes |
| Stroke colors | ✅ Yes | JSON edit or theme | Yes |
| Opacity | ✅ Yes | JSON edit or theme | Yes |
| Duration | ✅ Yes | JSON edit (`op` field) | No |
| Frame rate | ✅ Yes | JSON edit (`fr` field) | No |
| Dimensions | ✅ Yes | JSON edit (`w`, `h` fields) | No |
| Speed | ✅ Yes | `setSpeed()` API | No |
| Expressions | ⚠️ Limited | Must bake in AE | N/A |

---

## Method 1: Direct JSON Modification

For simple customizations, directly edit the Lottie JSON before rendering.

### Global Properties

```json
{
  "v": "5.3.4",       // Lottie version
  "fr": 30,           // Frame rate (fps)
  "ip": 0,            // In point (start frame)
  "op": 38,           // Out point (end frame = duration)
  "w": 1920,          // Width
  "h": 1080,          // Height
  "nm": "Animation"   // Name
}
```

### Text Content

Text layers have type `"ty": 5` and contain text data in the `t.d.k[0].s` path:

```json
{
  "ty": 5,
  "nm": "Text Layer",
  "t": {
    "d": {
      "k": [{
        "s": {
          "t": "Hello World",           // Text content
          "f": "Teko-Bold",             // Font name
          "s": 41,                       // Font size
          "fc": [0.113, 0.597, 0.871],  // Fill color (RGB 0-1)
          "sc": [0, 0, 0],              // Stroke color (RGB 0-1)
          "sw": 0,                       // Stroke width
          "j": 2,                        // Justify (0=left, 1=right, 2=center)
          "lh": 49.2,                    // Line height
          "ls": 0,                       // Letter spacing
          "tr": 0                        // Tracking
        },
        "t": 0
      }]
    }
  }
}
```

### Colors in Shape Layers

Colors in shape layers are stored as RGBA arrays (0-1 range):

```json
{
  "ty": "fl",           // Fill
  "c": {
    "k": [0.012, 0.663, 0.957, 1]  // RGBA
  }
}
```

```json
{
  "ty": "st",           // Stroke
  "c": {
    "k": [1, 1, 1, 1]   // RGBA
  }
}
```

### Python Example: Modify Lottie JSON

```python
import json

def customize_lottie(
    lottie_path: str,
    output_path: str,
    text_replacements: dict = None,
    color_replacements: dict = None,
    duration_frames: int = None,
    fps: int = None
):
    """
    Customize a Lottie animation file.

    Args:
        lottie_path: Path to input Lottie JSON
        output_path: Path to save modified JSON
        text_replacements: Dict of {old_text: new_text}
        color_replacements: Dict of {hex_color: new_hex_color}
        duration_frames: New duration in frames
        fps: New frame rate
    """
    with open(lottie_path, 'r') as f:
        data = json.load(f)

    # Modify global properties
    if duration_frames:
        data['op'] = duration_frames
    if fps:
        data['fr'] = fps

    # Convert to string for text/color replacement
    json_str = json.dumps(data)

    # Replace text
    if text_replacements:
        for old, new in text_replacements.items():
            json_str = json_str.replace(f'"t":"{old}"', f'"t":"{new}"')

    # Replace colors (hex to RGB 0-1)
    if color_replacements:
        for old_hex, new_hex in color_replacements.items():
            old_rgb = hex_to_lottie_rgb(old_hex)
            new_rgb = hex_to_lottie_rgb(new_hex)
            # This is simplified - real implementation needs more robust matching
            json_str = json_str.replace(str(old_rgb), str(new_rgb))

    data = json.loads(json_str)

    with open(output_path, 'w') as f:
        json.dump(data, f)

def hex_to_lottie_rgb(hex_color: str) -> list:
    """Convert hex color to Lottie RGB (0-1 range)."""
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16) / 255
    g = int(hex_color[2:4], 16) / 255
    b = int(hex_color[4:6], 16) / 255
    return [round(r, 3), round(g, 3), round(b, 3)]
```

---

## Method 2: Theming with Slots (Advanced)

For reusable templates, use the dotLottie theming system with **Slots**.

### Step 1: Add Slot IDs in After Effects

When creating the animation, add slot IDs (`sid`) to properties you want to theme:

```json
{
  "ty": "fl",
  "c": {
    "sid": "primary_color",    // Slot ID for theming
    "k": [0.012, 0.663, 0.957, 1]
  }
}
```

### Step 2: Define Themes

Themes map slot IDs to values:

```json
{
  "themes": [
    {
      "id": "dark_mode",
      "rules": {
        "primary_color": { "p": [0.1, 0.1, 0.1, 1] },
        "text_color": { "p": [0.9, 0.9, 0.9, 1] }
      }
    },
    {
      "id": "brand_blue",
      "rules": {
        "primary_color": { "p": [0.0, 0.47, 0.75, 1] },
        "text_color": { "p": [1, 1, 1, 1] }
      }
    }
  ]
}
```

### Step 3: Apply Theme at Runtime

```typescript
import { DotLottie } from '@lottiefiles/dotlottie-web';

const dotLottie = new DotLottie({
  canvas: document.querySelector('#canvas'),
  src: '/animation.lottie',
});

// Apply theme
dotLottie.loadTheme('dark_mode');

// Or set slots directly
dotLottie.setSlots(JSON.stringify({
  "primary_color": { "p": [1, 0, 0, 1] }  // Override to red
}));
```

---

## Method 3: Runtime API

dotLottie provides runtime methods for dynamic control:

### Playback Control

```typescript
const dotLottie = new DotLottie({ ... });

// Speed
dotLottie.setSpeed(2);        // 2x speed
dotLottie.setSpeed(0.5);      // Half speed

// Segment (play only frames 10-30)
dotLottie.setSegment(10, 30);

// Mode
dotLottie.setMode('reverse');  // Play backwards
dotLottie.setMode('bounce');   // Ping-pong

// Frame control (for video rendering)
dotLottie.setFrame(15);        // Jump to frame 15
```

### Visual Control

```typescript
// Background
dotLottie.setBackgroundColor('#000000');

// Layout
dotLottie.setLayout({
  fit: 'contain',     // contain, cover, fill, none
  align: [0.5, 0.5]   // Center alignment
});

// Transform
dotLottie.setTransform({
  scale: 1.5,
  rotation: 45
});
```

### Theming

```typescript
// Apply named theme
dotLottie.setTheme('dark_mode');

// Apply raw theme data
dotLottie.setThemeData(JSON.stringify({
  rules: { "color_slot": { "p": [1, 0, 0, 1] } }
}));

// Reset to default
dotLottie.resetTheme();
```

---

## Lottie JSON Structure Reference

### Layer Types

| Type | Value | Description |
|------|-------|-------------|
| Precomp | 0 | Pre-composed layers |
| Solid | 1 | Solid color layer |
| Image | 2 | Image asset |
| Null | 3 | Null/empty layer |
| Shape | 4 | Vector shapes |
| Text | 5 | Text layer |

### Shape Types

| Type | Value | Description |
|------|-------|-------------|
| Fill | `fl` | Solid fill |
| Stroke | `st` | Stroke/outline |
| Gradient Fill | `gf` | Gradient fill |
| Gradient Stroke | `gs` | Gradient stroke |
| Group | `gr` | Shape group |
| Rectangle | `rc` | Rectangle |
| Ellipse | `el` | Ellipse/circle |
| Path | `sh` | Bezier path |
| Transform | `tr` | Transform properties |

### Color Format

All colors in Lottie use **0-1 range** (not 0-255):

```
Hex #FF5500 = RGB(255, 85, 0) = Lottie [1.0, 0.333, 0.0]
```

---

## Best Practices for NOLAN

### 1. Template Design Guidelines

When creating Lottie templates for NOLAN:

- **Keep text as text layers** - Don't convert to outlines if text needs to be editable
- **Use consistent naming** - Name layers descriptively (e.g., "Title", "Subtitle", "Icon")
- **Add slot IDs** - For themeable properties, add `sid` fields
- **Bake expressions** - Convert expressions to keyframes before export (AE: Animation > Keyframe Assistant > Convert Expression to Keyframes)
- **Test at target resolution** - Design at 1920x1080 for video output

### 2. Recommended Template Categories

| Category | Use Case | Customizable |
|----------|----------|--------------|
| Lower Thirds | Speaker names, titles | Name, Title, Colors |
| Title Cards | Section headers | Title, Subtitle, Colors |
| Transitions | Scene transitions | Colors, Duration |
| Icons | Animated icons | Colors |
| Data Callouts | Stats, numbers | Number, Label, Colors |
| Progress Bars | Timelines, loading | Progress %, Colors |

### 3. File Organization

```
assets/
├── common/
│   └── lottie/
│       ├── lower-thirds/
│       │   ├── simple.json
│       │   └── modern.json
│       ├── transitions/
│       │   ├── fade.json
│       │   └── slide.json
│       └── icons/
│           ├── checkmark.json
│           └── arrow.json
└── styles/
    └── noir-essay/
        └── lottie/
            └── lower-third-noir.json
```

### 4. Scene Plan Integration

```json
{
  "visual_type": "lottie",
  "lottie_template": "assets/common/lottie/lower-thirds/simple.json",
  "lottie_config": {
    "text": {
      "Name": "John Smith",
      "Title": "CEO, Acme Corp"
    },
    "colors": {
      "#0077B6": "#FFD700"
    },
    "duration_seconds": 3
  }
}
```

---

## ThorVG Feature Support

dotLottie uses [ThorVG](https://github.com/thorvg/thorvg), a high-performance vector graphics engine. It has **comprehensive Lottie support**:

### Fully Supported

| Category | Features |
|----------|----------|
| **Shapes** | Ellipse, Group, Path, Polystar, Rectangle |
| **Fills** | Solid colors, opacity, linear/radial gradients, fill rules (NonZero/EvenOdd) |
| **Strokes** | Dashes, caps (butt/round/square), joins (miter/bevel/round), width, miter limits |
| **Transforms** | Anchor point, auto-orient, opacity, parenting, position, scale, skew |
| **Masks** | Add, subtract, intersect, lighten, darken, difference + alpha/luma mattes |
| **Effects** | Drop shadows, Gaussian blur, fill, stroke, tint, tritone |
| **Text** | Alignment, capitalization, embedded fonts/glyphs, outlines, range selectors, paths, tracking |
| **Images** | Base64 embedded, local/URL sources (JPG, PNG, WebP) |
| **Interpolation** | Linear, cubic bezier, step/hold, spatial bezier, rove-across-time |
| **Modifiers** | Offset paths, repeaters, corner rounding, trim paths |
| **Expressions** | JavaScript-based expressions supported |
| **Advanced** | Markers, precompositions, time remapping, time stretch, property slots |

### Limitations

| Limitation | Workaround |
|------------|------------|
| 3D layers not supported | Use 2D with parallax effects |
| Some complex layer effects | Pre-render in After Effects |
| Large file sizes | Optimize paths, reduce keyframes |
| Custom fonts | Embed as glyphs or use web-safe fonts |

> **Note**: Unlike older Lottie players, ThorVG supports expressions, drop shadows, Gaussian blur, and advanced masking. Most After Effects animations export cleanly.

---

## Lottie Template Catalog

NOLAN includes a curated library of production-ready Lottie animations.

### Included Templates

| Category | Count | Use Case |
|----------|-------|----------|
| `lower-thirds/` | 2 | Speaker names, titles |
| `title-cards/` | 1 | Section headers, reveals |
| `transitions/` | 2 | Scene transitions, wipes |
| `data-callouts/` | 2 | Number counters, statistics |
| `progress-bars/` | 2 | Loading, timelines |
| `loaders/` | 1 | Processing indicators |
| `icons/` | 2 | Checkmarks, arrows |

### Location

```
assets/common/lottie/
├── catalog.json                    # Full metadata for all templates
├── lower-thirds/
│   ├── simple.json                 # 3-color animated lower third
│   ├── simple.schema.json          # Schema: primary_color, secondary_color, accent_color
│   ├── modern.json                 # Clean minimal style with text
│   └── modern.schema.json          # Schema: headline
├── title-cards/
│   ├── text-reveal.json            # Animated text reveal
│   └── text-reveal.schema.json
├── transitions/
│   ├── wipe-simple.json            # Fast screen wipe (0.67s)
│   └── shape-morph.json            # Organic shape transition
├── data-callouts/
│   ├── number-counter.json         # Animated number display
│   └── counting.json               # Multi-digit counter
├── progress-bars/
│   ├── minimal.json                # Clean progress indicator
│   └── loading-bar.json            # Full-width loading bar
├── loaders/
│   └── paperplane.json             # Paper plane loading animation
└── icons/
    ├── magic-box.json              # Gift box reveal animation
    ├── magic-box.schema.json       # Schema: message, box_color, ribbon_color
    ├── checkmark-success.json
    └── arrow-down.json
```

### Catalog JSON

Each animation has rich metadata in `catalog.json`:

```python
from nolan.lottie_downloader import LottieFilesDownloader

# Load catalog
downloader = LottieFilesDownloader()
catalog = downloader.create_catalog()

# Find animations by category
lower_thirds = catalog['categories']['lower-thirds']
for anim in lower_thirds:
    print(f"{anim['local_path']}: {anim['duration_seconds']}s @ {anim['fps']}fps")
    print(f"  Colors: {anim['color_palette']}")
```

### Metadata Fields

| Field | Description |
|-------|-------------|
| `id` | LottieFiles animation ID |
| `author` | Original creator |
| `source_url` | Link to LottieFiles page |
| `duration_seconds` | Animation length |
| `fps` | Frame rate |
| `width`, `height` | Dimensions |
| `color_palette` | Extracted hex colors |
| `has_expressions` | Uses JS expressions |
| `has_images` | Contains embedded images |
| `layer_count` | Number of layers |
| `license` | Lottie Simple License (free for commercial use) |

---

## Jitter.video Downloader

Download Lottie animations from Jitter.video's template library using browser automation.

### Features

- **Browser automation** - Uses Playwright to navigate Jitter's SPA
- **Category discovery** - Finds templates from category pages (video-titles, text, icons, etc.)
- **Multi-artboard handling** - Auto-selects first artboard for templates with multiple artboards
- **Metadata extraction** - Captures dimensions, FPS, duration from Lottie JSON
- **Catalog generation** - Creates `jitter-catalog.json` with all template metadata

### Installation

```bash
# Install Playwright (required)
pip install playwright
playwright install chromium
```

### Python Usage

```python
from nolan.jitter_downloader import JitterDownloader, JITTER_CATEGORIES
import asyncio

async def download_jitter_templates():
    async with JitterDownloader(
        output_dir="assets/common/lottie",
        headless=True,            # Set False to see browser
        delay_between_downloads=2.0
    ) as downloader:
        # Discover templates from a category
        templates = await downloader.discover_templates("text", limit=5)

        # Download each template
        for template in templates:
            result = await downloader.download_template(template)
            if result:
                print(f"Saved: {result.local_path}")

        # Create catalog of all downloaded templates
        downloader.create_catalog(templates)

asyncio.run(download_jitter_templates())
```

### CLI Usage

```bash
# List available categories
python -m nolan.jitter_downloader --list-categories

# Download from a specific category
python -m nolan.jitter_downloader --category text --limit 5

# Download essential templates (curated set)
python -m nolan.jitter_downloader --essential

# Show browser window for debugging
python -m nolan.jitter_downloader --category icons --visible
```

### Available Categories

| Category | Description |
|----------|-------------|
| `video-titles` | Title cards and intro animations |
| `text` | Text reveal and typography effects |
| `icons` | Animated icon sets |
| `logos` | Logo animations and reveals |
| `social-media` | Social platform templates |
| `ui-elements` | UI component animations |
| `buttons` | Button hover and click states |
| `backgrounds` | Animated backgrounds |
| `charts` | Data visualization |
| `devices` | Device mockups |
| `ads` | Advertisement templates |
| `showreels` | Showreel transitions |

### Output Structure

```
assets/common/lottie/
├── jitter-catalog.json          # Catalog of all Jitter templates
├── jitter-text/
│   ├── glide.json               # 1080x1080, 2.9s @ 60fps
│   ├── morph-inflating-text.json
│   └── sliding-text-reveal.json
├── jitter-icons/
│   └── wow-rotate-scale.json    # 800x600, 5.0s @ 60fps
└── jitter-video-titles/
    └── ...
```

### Notes

- **Rate limiting** - Built-in 2-3 second delay between downloads to avoid overwhelming Jitter
- **~70% success rate** - Some templates are private/deleted or have unsupported multi-artboard configurations
- **Blob downloads** - Uses JavaScript evaluation to fetch blob content directly

---

## LottieFiles Downloader

Download additional animations from LottieFiles.com:

```python
from nolan.lottie_downloader import LottieFilesDownloader

downloader = LottieFilesDownloader(
    output_dir="assets/common/lottie",
    requests_per_minute=15  # Rate limiting
)

# Download single animation
meta = downloader.download(
    "https://lottiefiles.com/free-animation/loading-40-paperplane-pXSmJB5J2C",
    category="loaders",
    local_name="paperplane"
)
print(f"Saved: {meta.local_path} ({meta.file_size_kb} KB)")

# Search for animations
results = downloader.search_lottiefiles("lower third", limit=5)
for r in results:
    print(f"{r['title']}: {r['url']}")

# Download batch
urls = [
    ("https://lottiefiles.com/...", "transitions", "fade"),
    ("https://lottiefiles.com/...", "icons", "star"),
]
downloader.download_batch(urls)
```

### CLI Usage

```bash
# Download curated essential library (all 12 animations)
python -m nolan.lottie_downloader --download-essential

# Search LottieFiles
python -m nolan.lottie_downloader --search "title card"

# Download single animation
python -m nolan.lottie_downloader --download "https://lottiefiles.com/..." transitions

# Regenerate catalog
python -m nolan.lottie_downloader --catalog
```

### Features

- **Rate limiting** - 15-20 requests/minute to avoid blocks
- **Metadata extraction** - Author, dimensions, FPS, colors, expressions
- **Duplicate detection** - Content hashing prevents re-downloads
- **Color palette extraction** - Hex colors from the animation
- **Organized storage** - Saves by category with descriptive names

---

## Template Schema System

Each Lottie template can have a `.schema.json` file that defines its customizable fields with semantic names. This enables a "magicbox" API where you pass field names without knowing the internal Lottie structure.

### Schema File Structure

```json
{
  "$schema": "lottie-template-schema-v1",
  "name": "Magic Box",
  "description": "Gift box that opens to reveal a message.",
  "usage": "Success states, celebrations. Keep message short.",
  "fields": {
    "message": {
      "type": "text",
      "label": "Message",
      "path": "layers[0].t.d.k[0].s.t",
      "default": "Yey!",
      "properties": {
        "font": "Teko-Bold",
        "size": 41,
        "color": "#1c98de"
      }
    },
    "box_color": {
      "type": "color",
      "label": "Box Color",
      "path": "layers[3].shapes[0].it[1].c.k",
      "default": "#0295d7",
      "color_type": "fill"
    }
  },
  "timing": {"fps": 30, "duration_seconds": 1.27},
  "dimensions": {"width": 315, "height": 600},
  "examples": [
    {"message": "WIN!", "box_color": "#4CAF50"}
  ]
}
```

### Using Templates (Magicbox API)

```python
from nolan.lottie import render_template

# Just pass semantic field names - no Lottie knowledge required
render_template(
    "assets/common/lottie/icons/magic-box.json",
    "output/celebration.json",
    message="100%",
    box_color="#9C27B0",
    ribbon_color="#E91E63"
)

# Lower third with custom headline
render_template(
    "assets/common/lottie/lower-thirds/modern.json",
    "output/breaking.json",
    headline="EXCLUSIVE"
)

# Color-only template
render_template(
    "assets/common/lottie/lower-thirds/simple.json",
    "output/branded.json",
    primary_color="#1a1a2e",
    secondary_color="#16213e",
    accent_color="#e94560"
)
```

### Analyzing Templates

Discover customizable fields in any Lottie file:

```python
from nolan.lottie import analyze_lottie, generate_schema, save_schema

# Analyze to see what's customizable
analysis = analyze_lottie("path/to/animation.json")
print(f"Text fields: {len(analysis['text_fields'])}")
print(f"Color fields: {len(analysis['color_fields'])}")
print(f"Duration: {analysis['timing']['duration_seconds']}s")

# Generate starter schema (then manually curate field names)
schema = generate_schema("path/to/animation.json", template_name="My Template")
save_schema(schema, "path/to/animation.json")
# Creates: path/to/animation.schema.json
```

### Listing Available Templates

```python
from nolan.lottie import list_templates

for t in list_templates():
    status = "✓" if t['has_schema'] else "○"
    fields = ", ".join(t['fields'][:3])
    print(f"[{status}] {t['category']}/{t['name']}: {fields}")
```

Output:
```
[✓] icons/Magic Box: message, box_color, ribbon_color
[✓] lower-thirds/Modern Lower Third: headline
[✓] lower-thirds/Simple Lower Third: primary_color, secondary_color, accent_color
[✓] transitions/shape-morph: color_1, color_2, color_3
...
```

### Curated Templates

These templates have human-curated semantic field names:

| Template | Fields | Use Case |
|----------|--------|----------|
| `icons/magic-box` | `message`, `box_color`, `ribbon_color`, `accent_color` | Celebrations, achievements |
| `lower-thirds/modern` | `headline` | Breaking news, alerts |
| `lower-thirds/simple` | `primary_color`, `secondary_color`, `accent_color` | Branded overlays |

Other templates have auto-generated field names (`color_1`, `color_2`, etc.) that work but are less semantic.

---

## Resources

- [dotLottie Documentation](https://dotlottie.io/)
- [ThorVG Lottie Support Wiki](https://github.com/thorvg/thorvg/wiki/Lottie-Support) - Full feature matrix
- [LottieFiles Supported Features](https://lottiefiles.com/supported-features) - Platform comparison
- [dotLottie Web API](https://developers.lottiefiles.com/docs/dotlottie-player/dotlottie-web/)
- [Lottie JSON Spec](https://lottiefiles.github.io/lottie-docs/)
- [LottieFiles (Free Animations)](https://lottiefiles.com/)
- [dotLottie Theming Guide](https://developers.lottiefiles.com/docs/tools/dotlottie-js/theming/)
- [Bodymovin (AE Export)](https://aescripts.com/bodymovin/)

---

## Changelog

- **2026-01-20**: Added Jitter.video downloader (`src/nolan/jitter_downloader.py`) - Playwright-based browser automation for downloading Lottie templates from Jitter
- **2026-01-19**: Updated feature support docs - ThorVG supports expressions, effects, masks (better than expected)
- **2026-01-19**: Added Python utility module (`src/nolan/lottie.py`), integrated Lottie into Remotion engine, added scene plan support
- **2026-01-19**: Initial documentation created after spike test success
