# Design Discussion: Asset-Based vs Code-Generated Graphics

**Date:** 2026-01-19
**Status:** Open for discussion
**Context:** After implementing `chart-progress-staircase` effect

---

## Background

Implemented a progress staircase chart effect (similar to growth journey / milestone visualization). The effect works but the arrow graphic looks "underwhelming" compared to polished reference designs that have 3D gradients, bevels, and shadows.

**Reference style:** Corporate infographic with 3D ribbon arrow effect
**Current output:** Flat green lines with basic shadow layer

---

## Design Question

> Should we create pre-made graphic assets (SVGs) for complex visual elements, or continue generating everything in code?

---

## Options Considered

### Option 1: Pre-made Assets
Store designed SVG/PNG assets in a folder, load them at render time.

```
assets/
  staircase/
    arrow-horizontal.svg
    arrow-vertical.svg
    arrow-corner.svg
    arrow-head.svg
```

**Pros:**
- Polished visuals (gradients, bevels, shadows) easy to create in design tools
- Designer can iterate independently
- Complex effects look professional

**Cons:**
- Less dynamic - need new assets for different variations
- Hard to change colors at runtime
- Asset management overhead
- Doesn't scale well across 50+ effects

### Option 2: Code-Generated (Current)
Draw all graphics programmatically using Motion Canvas/Remotion primitives.

**Pros:**
- Fully dynamic (any number of steps, any color)
- Easy theming (EssayStyle integration)
- No external dependencies
- Works for all effects consistently

**Cons:**
- Complex visual effects (3D, gradients) are tedious/limited
- Current result looks flat compared to designed graphics

### Option 3: Hybrid
Use assets for complex visual pieces, code for composition/animation.

**Pros:**
- Best of both worlds
- Polished look from designed assets
- Still dynamic positioning/animation

**Cons:**
- Adds framework complexity (asset loading, tinting, management)
- May be over-engineering for the use case

---

## Analysis: What Does NOLAN Actually Need?

### Target Use Case
- **Video essays** (documentary/explainer style)
- Channels like Vox, Wendover, Johnny Harris

### What Video Essays Typically Use
- Clean, flat design (not hyper-polished corporate infographics)
- Good animation/timing (this matters more than visual complexity)
- Text overlays, simple charts, lower thirds
- Footage + Ken Burns effects on images

### Observation
The reference image showing 3D ribbon arrows is more "corporate presentation" style than typical video essay style. Most successful video essay channels use relatively simple graphics with good motion design.

---

## Recommendation

**Keep code-generated approach** with targeted improvements:

| Area | Action |
|------|--------|
| Graphics | Improve shadows, gradients, proportions in code |
| Animation | Better easing, timing, sequencing |
| Icons | Add small SVG icon library (genuinely reusable) |
| Complex visuals | Users import as image/video, apply Ken Burns |

### Why Not Build Asset Framework
1. Adds complexity for marginal benefit
2. Video essay genre doesn't require hyper-polished infographics
3. Animation quality matters more than graphic complexity
4. Maintenance burden across 50+ effects

### One Exception: Icon Library
A small set of reusable SVG icons WOULD be valuable:
- Common icons (check, star, arrow, brand, growth, code, data, etc.)
- Used across multiple effects (staircase, timelines, lists)
- Easy to tint/color at runtime
- Low maintenance overhead

---

## Open Questions for Tomorrow

1. **Target audience clarification:** Is the target more video-essay or corporate-infographic?
2. **Icon library scope:** What icons would be most useful across effects?
3. **Polish priorities:** Which existing effects need visual refinement?
4. **Staircase specifically:** Accept flat design or invest in code-based 3D effect?

---

## Files Changed Today

- `render-service/src/effects/presets/chart.ts` - Added `chart-progress-staircase` preset
- `render-service/src/engines/motion-canvas.ts` - Added staircase rendering + animation
- Fixed Motion Canvas center-based coordinate system issue

## Current Staircase Output

Working features:
- Staircase arrow draws progressively
- Cards reveal at each step with label, description, value
- Value counter animation
- Alternating card positions (above/below steps)
- EssayStyle theming support

Visual limitations:
- Flat arrow (no 3D gradient effect)
- Basic shadow layer
- No arrow head at end
