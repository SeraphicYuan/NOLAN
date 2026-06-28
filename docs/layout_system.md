# NOLAN Layout System

A cross-platform layout system for dividing screens into content regions (slots).

## Overview

The layout system provides a **renderer-agnostic** way to define screen regions. It works with:
- Python (PIL/MoviePy) - current NOLAN renderer
- Motion Canvas (TypeScript)
- Remotion (React)
- Any renderer that accepts x, y, width, height

## Core Concepts

### Slot

A `Slot` is a rectangular region of the screen:

```python
@dataclass
class Slot:
    x: int          # Left edge
    y: int          # Top edge
    width: int      # Total width
    height: int     # Total height
    padding: int    # Inner padding
    name: str       # Optional identifier
```

Slots provide helper methods:
- `center_x`, `center_y` - center coordinates
- `inner_width`, `inner_height` - content area (minus padding)
- `align_x(width, "left"|"center"|"right")` - position an element
- `place(width, height, align_x, align_y)` - get (x, y) for placement

### Layout

`Layout` divides a screen into slots:

```python
layout = Layout(width=1920, height=1080, margin=100)

# Create slots
left, right = layout.columns([1, 2])  # 1/3 + 2/3
top, bottom = layout.rows([1, 4])     # Header + body
grid = layout.grid(2, 2)              # 2x2 grid
```

## Quick Start

### Basic Usage

```python
from nolan.renderer.layout import Layout, Slot

# Create layout
layout = Layout(width=1920, height=1080)

# Divide into columns
portrait_slot, content_slot = layout.columns([1, 2])

# Use slot for positioning
portrait = Element(
    x=portrait_slot.center_x - portrait_width // 2,
    y=portrait_slot.center_y - portrait_height // 2,
    width=portrait_width,
    height=portrait_height,
)

# Or use alignment helpers
x, y = portrait_slot.place(portrait_width, portrait_height, "center", "center")
```

### Presets

```python
from nolan.renderer.layout import get_preset

# Common layouts
left, right = get_preset("split-1-2")      # 1/3 + 2/3
minor, major = get_preset("golden")         # Golden ratio
grid = get_preset("grid-2x2")               # 2x2 grid
a, b, c = get_preset("thirds")              # Equal thirds
```

### Schema-based

```python
from nolan.renderer.layout import Layout

layout = Layout()

# From schema dictionary
slots = layout.from_schema({
    "type": "columns",
    "ratios": [1, 2],
    "gap": 60
})
```

## Layout Types

### Columns

Divide horizontally by ratio:

```
┌──────────┬────────────────────┐
│          │                    │
│  1 part  │      2 parts       │
│          │                    │
└──────────┴────────────────────┘
```

```python
left, right = layout.columns([1, 2])
a, b, c = layout.columns([1, 1, 1])  # Equal thirds
```

### Rows

Divide vertically by ratio:

```
┌─────────────────────────────────┐
│            1 part               │
├─────────────────────────────────┤
│                                 │
│            4 parts              │
│                                 │
└─────────────────────────────────┘
```

```python
header, body = layout.rows([1, 4])
```

### Grid

Create a grid of cells:

```
┌───────────┬───────────┐
│  [0][0]   │  [0][1]   │
├───────────┼───────────┤
│  [1][0]   │  [1][1]   │
└───────────┴───────────┘
```

```python
grid = layout.grid(2, 2)
top_left = grid[0][0]
bottom_right = grid[1][1]

# Or flat list
cells = layout.grid_flat(2, 2)  # [cell0, cell1, cell2, cell3]
```

### Nested Layouts

Subdivide a slot:

```python
left, right = layout.columns([1, 2])

# Divide right slot into rows
header, body, footer = right.subdivide_rows([1, 6, 1])
```

## Presets Reference

| Preset | Description | Ratios |
|--------|-------------|--------|
| `full` | Single full-screen slot | - |
| `half` | Two equal columns | 1:1 |
| `thirds` | Three equal columns | 1:1:1 |
| `quarters` | Four equal columns | 1:1:1:1 |
| `split-1-2` | Narrow + wide | 1:2 |
| `split-2-1` | Wide + narrow | 2:1 |
| `split-1-3` | Narrow + very wide | 1:3 |
| `golden` | Golden ratio | 38:62 |
| `golden-reverse` | Reverse golden | 62:38 |
| `grid-2x2` | 2x2 grid | - |
| `grid-3x3` | 3x3 grid | - |
| `header-body` | Top strip + main | 1:4 |
| `body-footer` | Main + bottom strip | 4:1 |
| `portrait-reveal` | Portrait + content | 1:2 |
| `comparison` | Side by side | 1:1 |

## Cross-Platform Usage

### Export to JSON

```python
from nolan.renderer.layout import Layout, slots_to_json

layout = Layout()
slots = layout.columns([1, 2])

# Export for other renderers
json_str = slots_to_json(slots)
```

Output:
```json
[
  {"x": 100, "y": 100, "width": 553, "height": 880, "padding": 40, "name": "col0"},
  {"x": 613, "y": 100, "width": 1107, "height": 880, "padding": 40, "name": "col1"}
]
```

### Motion Canvas (TypeScript)

```typescript
// layout.ts - TypeScript implementation
interface Slot {
  x: number;
  y: number;
  width: number;
  height: number;
  padding: number;
  name?: string;
}

// Import from Python-generated JSON or re-implement
const slots: Slot[] = [
  {x: 100, y: 100, width: 553, height: 880, padding: 40},
  {x: 613, y: 100, width: 1107, height: 880, padding: 40}
];

// Use in scene
export default makeScene2D(function* (view) {
  const [portrait, content] = slots;

  view.add(
    <Rect
      x={portrait.x + portrait.width / 2}
      y={portrait.y + portrait.height / 2}
      width={portrait.width}
      height={portrait.height}
      fill="#333"
    />
  );
});
```

### Remotion (React)

```tsx
// Layout hook for Remotion
import {AbsoluteFill} from 'remotion';

interface Slot {
  x: number;
  y: number;
  width: number;
  height: number;
  padding: number;
}

const SlotContainer: React.FC<{slot: Slot; children: React.ReactNode}> = ({
  slot,
  children
}) => (
  <div
    style={{
      position: 'absolute',
      left: slot.x,
      top: slot.y,
      width: slot.width,
      height: slot.height,
      padding: slot.padding,
    }}
  >
    {children}
  </div>
);

// Usage
export const PortraitReveal: React.FC<{slots: Slot[]}> = ({slots}) => {
  const [portrait, content] = slots;

  return (
    <AbsoluteFill>
      <SlotContainer slot={portrait}>
        <Portrait />
      </SlotContainer>
      <SlotContainer slot={content}>
        <ContentBox />
      </SlotContainer>
    </AbsoluteFill>
  );
};
```

## Video Essay Layouts

Common patterns for video essays:

### Portrait Reveal
```
┌──────────┬────────────────────┐
│          │  Title             │
│ Portrait │  • Point 1         │
│          │  • Point 2         │
│          │  • Point 3         │
└──────────┴────────────────────┘
```

```python
portrait, content = get_preset("portrait-reveal")
# or: layout.columns([1, 2], names=["portrait", "content"])
```

### Comparison
```
┌───────────────┬───────────────┐
│    Before     │    After      │
│               │               │
│   Image A     │   Image B     │
│               │               │
└───────────────┴───────────────┘
```

```python
left, right = get_preset("comparison")
```

### Timeline
```
┌─────────────────────────────────┐
│           Main Content          │
├─────────────────────────────────┤
│  1900  │  1950  │  2000  │ Now  │
└─────────────────────────────────┘
```

```python
main, timeline = layout.rows([4, 1])
decades = timeline.subdivide_cols([1, 1, 1, 1])
```

### Picture-in-Picture
```
┌─────────────────────────────────┐
│                          ┌─────┤
│      Main Content        │ PiP │
│                          └─────┤
│                                 │
└─────────────────────────────────┘
```

```python
# Custom positioning for PiP
main = layout.full()
pip = Slot(
    x=layout.width - 400 - layout.margin,
    y=layout.margin,
    width=400,
    height=225,  # 16:9 aspect
    padding=0
)
```

## Schema Format

Layouts can be defined as JSON schemas:

```json
{
  "type": "columns",
  "ratios": [1, 2],
  "gap": 60,
  "names": ["portrait", "content"],
  "padding": 40
}
```

Schema types:
- `full` - single slot
- `columns` - horizontal split (requires `ratios`)
- `rows` - vertical split (requires `ratios`)
- `grid` - grid layout (requires `cols`, `rows`)
- `preset` - named preset (requires `name`)

## API Reference

### Slot

| Property | Type | Description |
|----------|------|-------------|
| `x` | int | Left edge coordinate |
| `y` | int | Top edge coordinate |
| `width` | int | Total width |
| `height` | int | Total height |
| `padding` | int | Inner padding |
| `name` | str | Optional identifier |
| `center_x` | int | Horizontal center |
| `center_y` | int | Vertical center |
| `inner_width` | int | Width minus padding |
| `inner_height` | int | Height minus padding |

| Method | Returns | Description |
|--------|---------|-------------|
| `align_x(w, align)` | int | X position for alignment |
| `align_y(h, align)` | int | Y position for alignment |
| `place(w, h, ax, ay)` | (int, int) | (x, y) for placement |
| `subdivide_cols(ratios)` | List[Slot] | Split into columns |
| `subdivide_rows(ratios)` | List[Slot] | Split into rows |

### Layout

| Parameter | Default | Description |
|-----------|---------|-------------|
| `width` | 1920 | Screen width |
| `height` | 1080 | Screen height |
| `margin` | 100 | Outer margin |
| `safe_zone` | 0 | Broadcast safe zone |
| `default_gap` | 60 | Gap between slots |
| `default_padding` | 40 | Padding inside slots |

| Method | Returns | Description |
|--------|---------|-------------|
| `full()` | Slot | Full-screen slot |
| `columns(ratios)` | List[Slot] | Horizontal split |
| `rows(ratios)` | List[Slot] | Vertical split |
| `grid(cols, rows)` | List[List[Slot]] | Grid of slots |
| `from_schema(dict)` | Slot(s) | Create from schema |
