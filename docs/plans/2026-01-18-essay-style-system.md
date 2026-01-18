# Essay Style System Implementation Plan

**Created:** 2026-01-18
**Status:** In Progress
**Goal:** Decouple motion logic from visual design with a scalable, swappable style system

---

## Overview

Implement a design system that separates motion presets (timing, layout, animation) from visual design (colors, typography, spacing, texture). Styles are swappable without duplicating motion code.

Reference: `D:\ClaudeProjects\style_guideline.md`

---

## Phase 1: Foundation

**Status:** Pending
**Files to create/modify:**
- `render-service/src/styles/types.ts` - EssayStyle interface
- `render-service/src/styles/styles.ts` - 3 flagship style definitions
- `render-service/src/styles/accent.ts` - resolveAccent helper with rule enforcement
- `render-service/src/styles/index.ts` - exports

**Deliverables:**
1. `EssayStyle` TypeScript interface matching the spec
2. Three flagship styles:
   - `noir-essay` - cinematic, analysis, default
   - `cold-data` - tech, finance, data
   - `modern-creator` - youtube, general
3. `resolveAccent()` function that:
   - Parses `**markup**` syntax
   - Supports explicit word arrays
   - Supports `auto` mode with rules
   - Enforces `maxWords` and `forbidden` patterns
4. Helper functions:
   - `getStyle(id: string): EssayStyle`
   - `getSafeArea(style, width, height)`
   - `resolveTextSizes(style, videoHeight)`

---

## Phase 2: High-Impact Preset Refactor

**Status:** Pending
**Files to modify:**
- `render-service/src/effects/presets/title.ts`
- `render-service/src/effects/presets/quote.ts`
- `render-service/src/effects/presets/text.ts`

**Deliverables:**
1. Refactor title presets (`title-card`, `chapter-heading`, `lower-third`) to:
   - Accept optional `style` parameter
   - Use `style.colors.*` instead of hardcoded colors
   - Use `style.typography.*` for fonts
   - Use `style.textScale1080p.*` for sizes
   - Call `resolveAccent()` for text with markup

2. Refactor quote presets (`quote-fade-center`, `quote-kinetic`, `quote-dramatic`) to:
   - Use style tokens for colors
   - Support accent markup in phrases

3. Refactor text presets (`text-highlight`, `text-typewriter`, `text-pop`, etc.) to:
   - Use style tokens
   - Respect `style.motion.*` for timing

4. Backward compatibility:
   - If no `style` provided, fall back to current behavior
   - Existing API calls continue to work

---

## Phase 3: Remaining Preset Refactor

**Status:** Pending
**Files to modify:**
- `render-service/src/effects/presets/chart.ts`
- `render-service/src/effects/presets/statistic.ts`
- `render-service/src/effects/presets/overlay.ts`
- `render-service/src/effects/presets/transition.ts`
- `render-service/src/effects/presets/progress.ts`
- `render-service/src/effects/presets/annotation.ts`
- `render-service/src/effects/presets/comparison.ts`
- `render-service/src/effects/presets/timeline.ts`
- `render-service/src/effects/presets/countdown.ts`
- `render-service/src/effects/presets/map.ts`
- `render-service/src/effects/presets/image.ts`

**Deliverables:**
1. Charts use `style.colors.accent` for bars, `style.colors.primaryText` for labels
2. Statistics use accent for numbers, primary for labels
3. Overlays respect background/text colors from style
4. Transitions use style timing (`style.motion.enterFrames`, etc.)
5. All presets support optional `style` parameter with fallback

---

## Phase 4: Style Gallery + Additional Styles

**Status:** Pending
**Files to create:**
- `render-service/src/styles/gallery.ts` - gallery generator
- `render-service/src/routes/gallery.ts` - API endpoint
- Remaining 8 style definitions in `styles.ts`

**Deliverables:**
1. Complete style library (11 total):
   - `noir-essay` (Phase 1)
   - `cold-data` (Phase 1)
   - `modern-creator` (Phase 1)
   - `editorial-desk` - culture, literature
   - `psycho-drama` - tension, conflict
   - `human-voice` - biography, reflective
   - `archive-analyst` - academic, research
   - `archival-historical` - history, grain required
   - `abstract-theory` - philosophy, conceptual
   - `satirical-meta` - humor, irony
   - `short-form-explainer` - shorts, vertical

2. Style gallery endpoint:
   - `GET /styles` - list all styles with metadata
   - `GET /styles/:id` - get single style
   - `POST /styles/:id/preview` - render title + quote + lower-third for QA

3. Gallery composition that renders verification set for each style

---

## Phase 5: LLM Content Authoring Guide

**Status:** Pending
**Files to create:**
- `docs/LLM_AUTHORING_GUIDE.md` - comprehensive guide for LLM content generation
- Update scene designer prompts in `src/nolan/scenes.py`

**Deliverables:**
1. Documentation covering:
   - Text markup syntax (`**accent**`)
   - Effect selection guide (when to use which effect)
   - Data structure formats (charts, kinetic quotes, etc.)
   - Style selection based on video tone
   - Typography hierarchy (h1/h2/body/caption)
   - Common mistakes to avoid

2. Prompt templates for:
   - Scene generation with proper markup
   - Style recommendation based on video topic
   - Data formatting for charts/stats

3. Validation helpers:
   - `validateSceneContent(scene, style)` - check markup, rules
   - Warnings for common mistakes

---

## Global Rules (from spec)

```json
{
  "frameRate": 30,
  "safeArea": {
    "marginX": 0.1,
    "marginY": 0.15,
    "maxTextWidth": 0.65
  },
  "rules": {
    "maxFontsPerVideo": 2,
    "maxAccentWordsPerTitle": 1,
    "maxBodyLines": 3,
    "noDropShadows": true,
    "noGlow": true
  }
}
```

---

## Success Criteria

- [ ] All 50+ presets accept optional `style` parameter
- [ ] Existing API calls work unchanged (backward compatible)
- [ ] Style gallery renders all 11 styles without errors
- [ ] LLM-generated content with markup renders correctly
- [ ] Accent rules are enforced (violations throw errors)
- [ ] No hardcoded colors remain in motion components
