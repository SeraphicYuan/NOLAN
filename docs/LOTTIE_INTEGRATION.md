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

### 4. Scene Plan Integration (Planned)

```json
{
  "type": "lottie",
  "file": "lower-thirds/simple.json",
  "duration": 3,
  "customizations": {
    "text": {
      "Name": "John Smith",
      "Title": "CEO, Acme Corp"
    },
    "colors": {
      "primary_color": "#0077B6",
      "accent_color": "#FFD700"
    }
  }
}
```

---

## Limitations

| Limitation | Workaround |
|------------|------------|
| Expressions not supported | Bake to keyframes in After Effects |
| 3D layers not supported | Use 2D with parallax effects |
| Effects (blur, glow) not supported | Pre-render effects or use CSS filters |
| Complex masks may fail | Simplify masks or pre-render |
| Large file sizes | Optimize paths, reduce keyframes |
| Font embedding | Use web-safe fonts or embed as paths |

---

## Resources

- [dotLottie Documentation](https://dotlottie.io/)
- [dotLottie Web API](https://developers.lottiefiles.com/docs/dotlottie-player/dotlottie-web/)
- [Lottie JSON Spec](https://lottiefiles.github.io/lottie-docs/)
- [LottieFiles (Free Animations)](https://lottiefiles.com/)
- [dotLottie Theming Guide](https://developers.lottiefiles.com/docs/tools/dotlottie-js/theming/)
- [Bodymovin (AE Export)](https://aescripts.com/bodymovin/)

---

## Changelog

- **2025-01-19**: Initial documentation created after spike test success
