# Layout System Design

**Date:** 2026-01-18
**Status:** Implementation

## Overview

Add a region-based layout system that allows positioning effects within the video frame. Built on top of Remotion's native CSS capabilities.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  User API                                               │
│  ├── Templates (simple): 'center', 'split', 'thirds'   │
│  └── Regions (flexible): { x, y, w, h, align, valign } │
├─────────────────────────────────────────────────────────┤
│  Preset Layer                                           │
│  └── toEngineData() passes layout to engine            │
├─────────────────────────────────────────────────────────┤
│  Engine Layer (Remotion/Motion-Canvas)                  │
│  └── Converts regions to CSS positioning               │
└─────────────────────────────────────────────────────────┘
```

## Types

```typescript
// Region definition (percentage-based)
interface Region {
  x: number;      // 0-1, left edge
  y: number;      // 0-1, top edge
  w: number;      // 0-1, width
  h: number;      // 0-1, height
  align?: 'left' | 'center' | 'right';
  valign?: 'top' | 'center' | 'bottom';
  padding?: number; // 0-1, internal padding
}

// Layout can be template name or custom regions
type Layout = LayoutTemplate | CustomLayout;

type LayoutTemplate =
  | 'center'           // Single centered region
  | 'full'             // Full bleed with safe margins
  | 'lower-third'      // Bottom bar
  | 'upper-third'      // Top bar
  | 'split'            // Left/right 50-50
  | 'split-60-40'      // Left 60%, right 40%
  | 'thirds'           // Three columns
  | 'split-with-lower' // Left/right + bottom bar
  | 'presenter'        // Main content + lower third
  | 'grid-2x2';        // 2x2 grid

interface CustomLayout {
  regions: Record<string, Region>;
}
```

## Predefined Templates

### center (default)
```
┌─────────────────────────────────┐
│                                 │
│           ┌───────┐             │
│           │content│             │
│           └───────┘             │
│                                 │
└─────────────────────────────────┘
```
```typescript
{ main: { x: 0.1, y: 0.1, w: 0.8, h: 0.8, align: 'center', valign: 'center' } }
```

### split
```
┌───────────────┬─────────────────┐
│               │                 │
│     left      │      right      │
│               │                 │
└───────────────┴─────────────────┘
```
```typescript
{
  left: { x: 0.05, y: 0.1, w: 0.43, h: 0.8, align: 'center', valign: 'center' },
  right: { x: 0.52, y: 0.1, w: 0.43, h: 0.8, align: 'center', valign: 'center' },
}
```

### split-with-lower
```
┌───────────────┬─────────────────┐
│               │                 │
│     left      │      right      │
│               │                 │
├───────────────┴─────────────────┤
│            bottom               │
└─────────────────────────────────┘
```
```typescript
{
  left: { x: 0.05, y: 0.05, w: 0.43, h: 0.75, align: 'center', valign: 'center' },
  right: { x: 0.52, y: 0.05, w: 0.43, h: 0.75, align: 'center', valign: 'center' },
  bottom: { x: 0.05, y: 0.82, w: 0.9, h: 0.13, align: 'left', valign: 'center' },
}
```

### lower-third
```
┌─────────────────────────────────┐
│                                 │
│                                 │
│                                 │
├─────────────────────────────────┤
│  name / citation                │
└─────────────────────────────────┘
```
```typescript
{ main: { x: 0.05, y: 0.82, w: 0.9, h: 0.13, align: 'left', valign: 'center' } }
```

### presenter
```
┌─────────────────────────────────┐
│                                 │
│           main                  │
│                                 │
├─────────────────────────────────┤
│  lower-third                    │
└─────────────────────────────────┘
```
```typescript
{
  main: { x: 0.1, y: 0.1, w: 0.8, h: 0.7, align: 'center', valign: 'center' },
  lower: { x: 0.05, y: 0.82, w: 0.5, h: 0.13, align: 'left', valign: 'center' },
}
```

### grid-2x2
```
┌───────────────┬─────────────────┐
│   top-left    │   top-right     │
├───────────────┼─────────────────┤
│  bottom-left  │  bottom-right   │
└───────────────┴─────────────────┘
```

## Usage

### Single Effect (current behavior, unchanged)
```typescript
POST /render
{
  effect: 'title-card',
  params: { title: 'Hello', style: 'podcast-visual' }
}
// Uses style.layout for positioning (center by default)
```

### Single Effect with Layout Override
```typescript
POST /render
{
  effect: 'title-card',
  params: { title: 'Hello', style: 'podcast-visual' },
  layout: 'lower-third'  // Override position
}
```

### Composition (multiple effects) - Future
```typescript
POST /render/compose
{
  layout: 'split-with-lower',
  style: 'podcast-visual',
  effects: [
    { effect: 'title-card', region: 'left', params: {...} },
    { effect: 'chart-bar', region: 'right', params: {...} },
    { effect: 'title-lower-third', region: 'bottom', params: {...} },
  ]
}
```

## Implementation Plan

### Phase 1: Single Effect Layout (This PR)

1. **Add layout types** - `render-service/src/layout/types.ts`
2. **Add layout templates** - `render-service/src/layout/templates.ts`
3. **Add layout resolver** - `render-service/src/layout/index.ts`
4. **Update Remotion engine** - Apply region as CSS
5. **Update render route** - Accept optional `layout` param
6. **Update presets** - Pass style.layout to engine data

### Phase 2: Composition (Future)

1. Add `/render/compose` endpoint
2. Engine renders multiple effects in their regions
3. Z-ordering based on array order

## Engine Implementation

### Remotion

```typescript
// Convert region to CSS
function regionToStyle(region: Region, width: number, height: number): CSSProperties {
  return {
    position: 'absolute',
    left: `${region.x * 100}%`,
    top: `${region.y * 100}%`,
    width: `${region.w * 100}%`,
    height: `${region.h * 100}%`,
    display: 'flex',
    alignItems: region.valign === 'top' ? 'flex-start'
              : region.valign === 'bottom' ? 'flex-end'
              : 'center',
    justifyContent: region.align === 'left' ? 'flex-start'
                  : region.align === 'right' ? 'flex-end'
                  : 'center',
    padding: region.padding ? `${region.padding * 100}%` : undefined,
  };
}
```

### Motion-Canvas

```typescript
// Convert region to Motion-Canvas positioning
function regionToPosition(region: Region, width: number, height: number) {
  return {
    x: (region.x + region.w / 2) * width - width / 2,  // Center-based coords
    y: (region.y + region.h / 2) * height - height / 2,
    width: region.w * width,
    height: region.h * height,
  };
}
```

## Style Integration

When a style is set, use `style.layout` values:
- `style.layout.marginX` → region padding
- `style.layout.marginY` → region padding
- `style.layout.align` → region align
- `style.layout.maxTextWidth` → constrain content width

## Backward Compatibility

- All existing presets continue to work unchanged
- Default layout is 'center' (current behavior)
- Layout param is optional
- Templates expand to regions internally

## Files to Create/Modify

**Create:**
- `render-service/src/layout/types.ts`
- `render-service/src/layout/templates.ts`
- `render-service/src/layout/index.ts`

**Modify:**
- `render-service/src/engines/remotion.ts` - Add region rendering
- `render-service/src/engines/motion-canvas.ts` - Add region rendering
- `render-service/src/routes/render.ts` - Accept layout param
- `render-service/src/effects/presets/*.ts` - Pass layout in toEngineData
