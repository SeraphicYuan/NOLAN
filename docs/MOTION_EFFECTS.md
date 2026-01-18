# Motion Effects Catalog

A library of motion effects for video essay generation. Each effect is a ready-to-use preset with sensible defaults.

---

## Image Effects

### image-ken-burns

**Engine:** Remotion

Slow pan and zoom across a still image. Classic documentary technique for bringing photos to life.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `image` | image | Yes | - | The image to animate |
| `duration` | duration | No | 6 | Effect duration (2-30s) |
| `direction` | select | No | left-to-right | Pan direction: left-to-right, right-to-left, top-to-bottom, bottom-to-top |
| `zoom` | select | No | zoom-in | Zoom behavior: zoom-in, zoom-out, none |

**Use when:** Showing historical photos, archival images, or any still that needs subtle movement.

---

### image-zoom-focus

**Engine:** Remotion

Start wide, zoom into a specific region of interest. For revealing details or directing attention.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `image` | image | Yes | - | The image to animate |
| `duration` | duration | No | 4 | Effect duration (2-15s) |
| `focus_x` | number | No | 0.5 | Horizontal focus point (0-1) |
| `focus_y` | number | No | 0.5 | Vertical focus point (0-1) |
| `zoom_level` | number | No | 2.0 | Final zoom multiplier (1.5-4) |

**Use when:** Highlighting a specific detail in an image, document, or map.

---

### image-parallax

**Engine:** Remotion

Multi-layer parallax movement creating depth illusion. Foreground moves faster than background.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `background` | image | Yes | - | Background layer image |
| `foreground` | image | No | - | Foreground layer image (transparent PNG) |
| `duration` | duration | No | 6 | Effect duration |
| `direction` | select | No | horizontal | Movement: horizontal, vertical |
| `intensity` | number | No | 1.0 | Parallax intensity (0.5-2.0) |

**Use when:** Creating depth from flat images, title sequences with layered elements.

---

## Quote Effects

### quote-fade-center

**Engine:** Motion Canvas

Text fades in centered on screen. Simple, elegant presentation.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `text` | text | Yes | - | The quote text |
| `author` | string | No | - | Attribution (optional) |
| `duration` | duration | No | 5 | Total duration |
| `color` | color | No | #ffffff | Text color |
| `background` | color | No | #0f172a | Background color |

**Use when:** Presenting quotes, key statements, or impactful text that should stand alone.

---

### quote-typewriter

**Engine:** Motion Canvas

Character-by-character reveal like typing. Creates anticipation and emphasis.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `text` | text | Yes | - | The quote text |
| `author` | string | No | - | Attribution (appears after text) |
| `duration` | duration | No | 6 | Total duration |
| `speed` | select | No | normal | Typing speed: slow, normal, fast |
| `cursor` | boolean | No | true | Show blinking cursor |
| `color` | color | No | #ffffff | Text color |

**Use when:** Revealing important statements, creating suspense, mimicking real-time typing.

---

### quote-dramatic

**Engine:** Motion Canvas

Text scales up from small with blur-to-sharp transition. High impact reveal.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `text` | text | Yes | - | The quote text |
| `author` | string | No | - | Attribution |
| `duration` | duration | No | 4 | Total duration |
| `color` | color | No | #ffffff | Text color |
| `accent` | color | No | #ef4444 | Accent color for emphasis |

**Use when:** Dramatic reveals, shocking statements, climactic moments.

---

### quote-kinetic

**Engine:** Motion Canvas

Multiple phrases animate in sequence with scale and fade. Kinetic typography style.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `phrases` | items | Yes | - | Array of {text, hold} objects |
| `color` | color | No | #0f172a | Text color |
| `size` | number | No | 96 | Base font size |

**Item schema for phrases:**
- `text` (string): The phrase text
- `hold` (number): Seconds to hold before next phrase

**Use when:** Breaking down a statement into impactful chunks, lyric-style reveals.

---

## Statistic Effects

### stat-counter-roll

**Engine:** Motion Canvas

Number rolls up from 0 to target value. Classic counter animation.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `value` | number | Yes | - | Target number |
| `label` | string | No | - | Label text below number |
| `prefix` | string | No | - | Prefix (e.g., "$") |
| `suffix` | string | No | - | Suffix (e.g., "%", "M") |
| `duration` | duration | No | 3 | Roll duration |
| `color` | color | No | #0ea5e9 | Number color |

**Use when:** Revealing statistics, counts, monetary values, percentages.

---

### stat-bar-grow

**Engine:** Motion Canvas

Horizontal bar grows from left to represent value. Good for comparisons.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `value` | number | Yes | - | Value (determines bar length) |
| `max` | number | No | 100 | Maximum value for scale |
| `label` | string | No | - | Label text |
| `color` | color | No | #0ea5e9 | Bar color |
| `duration` | duration | No | 2 | Grow duration |
| `show_value` | boolean | No | true | Display value at end of bar |

**Use when:** Showing progress, percentages, single-value comparisons.

---

### stat-highlight-pulse

**Engine:** Motion Canvas

Number appears with pulsing highlight effect. Draws attention to key figures.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `value` | string | Yes | - | The value to display |
| `label` | string | No | - | Label text |
| `duration` | duration | No | 4 | Total duration |
| `pulse_color` | color | No | #fbbf24 | Highlight pulse color |

**Use when:** Emphasizing a single important number, drawing attention to key data.

---

## Chart Effects

### chart-bar-race

**Engine:** Motion Canvas

Animated bar chart with bars growing in sequence. Racing bar effect.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `items` | items | Yes | - | Array of {label, value, color?} |
| `title` | string | No | - | Chart title |
| `duration` | duration | No | 6 | Total animation duration |
| `color` | color | No | #0ea5e9 | Default bar color |
| `max` | number | No | auto | Maximum value for scale |

**Item schema:**
- `label` (string): Bar label
- `value` (number): Bar value
- `color` (color, optional): Override bar color

**Use when:** Comparing multiple values, showing rankings, data breakdowns.

---

### chart-bar-callout

**Engine:** Motion Canvas

Bar chart with animated callout annotations pointing to specific bars.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `items` | items | Yes | - | Array of {label, value} |
| `callouts` | items | No | - | Array of {target_index, label, color?} |
| `title` | string | No | - | Chart title |
| `duration` | duration | No | 8 | Total duration |
| `color` | color | No | #0ea5e9 | Default bar color |

**Callout schema:**
- `target_index` (number): Which bar to point to (0-indexed)
- `label` (string): Callout text
- `color` (color, optional): Callout color

**Use when:** Highlighting specific data points with explanatory notes.

---

### chart-line-draw

**Engine:** Remotion

Line chart that draws itself from left to right. Good for trends.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `points` | items | Yes | - | Array of {x, y, label?} |
| `title` | string | No | - | Chart title |
| `duration` | duration | No | 5 | Draw duration |
| `color` | color | No | #0ea5e9 | Line color |
| `fill` | boolean | No | false | Fill area under line |

**Use when:** Showing trends over time, progress, continuous data.

---

### chart-pie-expand

**Engine:** Remotion

Pie chart segments expand from center. Good for composition breakdowns.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `items` | items | Yes | - | Array of {label, value, color?} |
| `title` | string | No | - | Chart title |
| `duration` | duration | No | 4 | Expand duration |
| `show_labels` | boolean | No | true | Show segment labels |
| `show_percentages` | boolean | No | true | Show percentage values |

**Use when:** Showing composition, market share, budget breakdowns.

---

## Comparison Effects

### compare-side-by-side

**Engine:** Infographic

Two items displayed side by side with VS styling. Classic comparison layout.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `left` | object | Yes | - | Left item {title, points[]} |
| `right` | object | Yes | - | Right item {title, points[]} |
| `title` | string | No | - | Overall comparison title |
| `theme` | select | No | default | Visual theme |

**Use when:** Comparing two options, before/after, pros/cons.

---

### compare-before-after

**Engine:** Remotion

Wipe transition revealing before and after states. Slider-style reveal.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `before` | image | Yes | - | Before state image |
| `after` | image | Yes | - | After state image |
| `duration` | duration | No | 5 | Total duration |
| `direction` | select | No | horizontal | Wipe direction |
| `pause_middle` | number | No | 1 | Seconds to pause at 50% |

**Use when:** Showing transformations, renovations, visual changes.

---

### compare-toggle-flip

**Engine:** Motion Canvas

3D flip between two states. Card-flip style comparison.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `front` | object | Yes | - | Front content {title, text} |
| `back` | object | Yes | - | Back content {title, text} |
| `duration` | duration | No | 4 | Total duration |
| `flip_count` | number | No | 2 | Number of flips |

**Use when:** Showing two perspectives, myth vs reality, expectation vs reality.

---

## Title Effects

### title-card

**Engine:** Remotion

Full-screen title card with fade in/out. Opening slide style.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `title` | string | Yes | - | Main title text |
| `subtitle` | string | No | - | Subtitle text |
| `duration` | duration | No | 4 | Total duration |
| `background` | color | No | #0f172a | Background color |
| `color` | color | No | #ffffff | Text color |

**Use when:** Video openings, section introductions, chapter starts.

---

### title-chapter

**Engine:** Remotion

Chapter heading with number and title. For structured content.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `number` | string | Yes | - | Chapter number (e.g., "01", "Part 1") |
| `title` | string | Yes | - | Chapter title |
| `duration` | duration | No | 3 | Total duration |
| `style` | select | No | minimal | Style: minimal, bold, elegant |

**Use when:** Breaking content into sections, numbered chapters.

---

### title-lower-third

**Engine:** Remotion

Lower third overlay with name and role. Speaker identification style.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | string | Yes | - | Person's name |
| `role` | string | No | - | Title/role/affiliation |
| `duration` | duration | No | 4 | Display duration |
| `position` | select | No | left | Position: left, center, right |
| `color` | color | No | #0ea5e9 | Accent color |

**Use when:** Identifying speakers, introducing experts, crediting sources.

---

## Transition Effects

### transition-fade

**Engine:** Remotion

Simple crossfade between scenes. Clean and professional.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `duration` | duration | No | 1 | Fade duration |
| `color` | color | No | transparent | Fade through color (or transparent) |

**Use when:** Default transitions, smooth scene changes.

---

### transition-wipe

**Engine:** Remotion

Directional wipe revealing next scene. More dynamic than fade.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `duration` | duration | No | 0.8 | Wipe duration |
| `direction` | select | No | left | Direction: left, right, up, down |
| `style` | select | No | sharp | Edge style: sharp, soft, diagonal |

**Use when:** Topic changes, location changes, more energetic transitions.

---

### transition-zoom

**Engine:** Remotion

Zoom through transition. Camera pushes forward into next scene.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `duration` | duration | No | 0.6 | Zoom duration |
| `direction` | select | No | in | Direction: in (forward), out (backward) |

**Use when:** Diving into details, dramatic emphasis, time jumps.

---

## Map Effects

### map-flyover

**Engine:** Remotion

Pan and zoom across a map image, visiting multiple points of interest.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `map` | image | Yes | - | Map image |
| `points` | items | Yes | - | Array of {x, y, zoom, label?} |
| `duration` | duration | No | 8 | Total duration |
| `show_labels` | boolean | No | true | Show point labels |

**Point schema:**
- `x` (number): Horizontal position (0-1)
- `y` (number): Vertical position (0-1)
- `zoom` (number): Zoom level at this point (1-3)
- `label` (string, optional): Label to show at this point

**Use when:** Geographic storytelling, showing locations, travel narratives.

---

## Progress Effects

### progress-bar

**Engine:** Remotion

Horizontal progress bar at bottom of video. Shows video timeline progress.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `color` | color | No | #0ea5e9 | Bar color |
| `height` | number | No | 6 | Bar height in pixels |
| `margin` | number | No | 40 | Margin from edges |
| `position` | select | No | bottom | Position: top, bottom |

**Use when:** Always-on progress indicator, tutorial videos, long-form content.

---

## Data Overlay Effects

### data-csv-table

**Engine:** Remotion

Animated table display from CSV data. Rows appear in sequence.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `csv_path` | string | Yes | - | Path to CSV file |
| `duration` | duration | No | 6 | Total duration |
| `max_rows` | number | No | 6 | Maximum rows to display |
| `header_color` | color | No | #0ea5e9 | Header background color |

**Use when:** Showing tabular data, comparisons, structured information.

---

## Annotation Effects

### callout-line

**Engine:** Motion Canvas

Animated pointer line connecting to an element. Draws from origin to target with optional label.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `label` | string | Yes | - | Callout text label |
| `startX` | number | No | 0.2 | Line start X position (0-1) |
| `startY` | number | No | 0.8 | Line start Y position (0-1) |
| `endX` | number | No | 0.7 | Line end X position (0-1) |
| `endY` | number | No | 0.3 | Line end Y position (0-1) |
| `duration` | duration | No | 3 | Total duration |
| `color` | color | No | #0ea5e9 | Line and label color |
| `thickness` | number | No | 3 | Line thickness in pixels |

**Use when:** Pointing out specific elements, annotating images, explaining diagram parts.

---

### callout-box

**Engine:** Motion Canvas

Animated highlight box or circle that draws attention to a region.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `x` | number | No | 0.5 | Center X position (0-1) |
| `y` | number | No | 0.5 | Center Y position (0-1) |
| `width` | number | No | 0.3 | Box width (0-1) |
| `height` | number | No | 0.2 | Box height (0-1) |
| `shape` | select | No | rectangle | Shape: rectangle, circle, rounded |
| `style` | select | No | stroke | Style: stroke, fill, pulse |
| `duration` | duration | No | 3 | Total duration |
| `color` | color | No | #ef4444 | Highlight color |

**Use when:** Drawing attention to specific areas, highlighting important regions.

---

## Comparison Effects

### split-screen

**Engine:** Motion Canvas

Multi-panel split screen with animated reveals. Compare 2-4 items side by side.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `panels` | items | Yes | - | Array of {title, subtitle?, color?} |
| `layout` | select | No | horizontal | Layout: horizontal, vertical, grid |
| `duration` | duration | No | 5 | Total duration |
| `gap` | number | No | 4 | Gap between panels in pixels |
| `animation` | select | No | slide | Animation: slide, fade, expand |

**Panel schema:**
- `title` (string): Panel title
- `subtitle` (string, optional): Panel subtitle
- `color` (color, optional): Panel background color

**Use when:** Comparing options, showing multiple perspectives, before/after states.

---

## Overlay Effects

### picture-in-picture

**Engine:** Motion Canvas

Floating video/image window overlay. Slides in from corner with shadow.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `image` | image | No | - | Image to show in PiP window |
| `position` | select | No | bottom-right | Position: top-left, top-right, bottom-left, bottom-right |
| `size` | number | No | 0.25 | Size relative to screen (0.1-0.5) |
| `duration` | duration | No | 5 | Display duration |
| `border` | boolean | No | true | Show border/frame |
| `shadow` | boolean | No | true | Show drop shadow |

**Use when:** Showing reference material, speaker video, supplementary visuals.

---

### vhs-retro

**Engine:** Motion Canvas

VHS/CRT style overlay with scanlines, noise, and color distortion.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `intensity` | number | No | 0.5 | Effect intensity (0-1) |
| `scanlines` | boolean | No | true | Show CRT scanlines |
| `noise` | boolean | No | true | Add static noise |
| `colorShift` | boolean | No | true | RGB color separation |
| `duration` | duration | No | 5 | Effect duration |

**Use when:** Flashback sequences, retro aesthetic, archival footage style.

---

### film-grain

**Engine:** Motion Canvas

Subtle film grain texture overlay for cinematic look.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `intensity` | number | No | 0.3 | Grain intensity (0-1) |
| `size` | number | No | 1 | Grain size multiplier |
| `duration` | duration | No | 5 | Effect duration |
| `animated` | boolean | No | true | Animate grain movement |

**Use when:** Adding cinematic texture, documentary feel, vintage look.

---

## Image Effects (Additional)

### photo-frame

**Engine:** Motion Canvas

Image displayed in an animated photo frame with optional tilt and shadow.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `image` | image | Yes | - | The image to frame |
| `style` | select | No | polaroid | Style: polaroid, simple, vintage, modern |
| `tilt` | number | No | 5 | Rotation angle in degrees |
| `caption` | string | No | - | Caption text below image |
| `duration` | duration | No | 4 | Display duration |
| `animation` | select | No | drop | Animation: drop, slide, fade |

**Use when:** Showing photos, memories, personal content, testimonials.

---

### document-reveal

**Engine:** Motion Canvas

Paper or document unfolds/slides into view. Great for showing text sources.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `title` | string | No | - | Document title/header |
| `content` | text | Yes | - | Document body text |
| `style` | select | No | paper | Style: paper, official, newspaper, letter |
| `animation` | select | No | unfold | Animation: unfold, slide, drop |
| `duration` | duration | No | 5 | Total duration |
| `highlight` | string | No | - | Text to highlight in document |

**Use when:** Showing sources, legal documents, quotes from text, newspaper headlines.

---

## Text Effects (Additional)

### text-scramble

**Engine:** Motion Canvas

Text decodes/unscrambles character by character. Matrix/hacker style reveal.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `text` | string | Yes | - | Final text to reveal |
| `duration` | duration | No | 3 | Decode duration |
| `charset` | select | No | alphanumeric | Characters: alphanumeric, binary, symbols, custom |
| `color` | color | No | #22c55e | Text color |
| `background` | color | No | #0f172a | Background color |

**Use when:** Tech/hacker themes, dramatic reveals, decoding secrets.

---

### gradient-text

**Engine:** Motion Canvas

Animated gradient flowing through text. Eye-catching title effect.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `text` | string | Yes | - | Text to display |
| `colors` | items | No | - | Array of gradient colors (defaults to blue-purple-pink) |
| `direction` | select | No | horizontal | Gradient direction: horizontal, vertical, diagonal |
| `speed` | number | No | 1 | Animation speed multiplier |
| `duration` | duration | No | 4 | Total duration |

**Use when:** Eye-catching titles, modern branding, emphasis text.

---

## Map Effects (Additional)

### location-pin

**Engine:** Motion Canvas

Animated pin drops onto a location with bounce effect and optional label.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `x` | number | Yes | - | Pin X position (0-1) |
| `y` | number | Yes | - | Pin Y position (0-1) |
| `label` | string | No | - | Location label text |
| `color` | color | No | #ef4444 | Pin color |
| `duration` | duration | No | 2 | Drop animation duration |
| `pulse` | boolean | No | true | Add pulse effect after drop |

**Use when:** Marking locations, showing destinations, geographic storytelling.

---

## Transition Effects (Additional)

### transition-dissolve

**Engine:** Motion Canvas

Smooth crossfade/dissolve between scenes. Classic film transition.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `duration` | duration | No | 1 | Dissolve duration |
| `easing` | select | No | smooth | Easing: linear, smooth, slow-start, slow-end |
| `color` | color | No | transparent | Optional fade through color |

**Use when:** Default transitions, smooth scene changes, time passing.

---

### transition-zoom

**Engine:** Motion Canvas

Camera pushes forward/backward through to next scene.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `duration` | duration | No | 0.8 | Zoom duration |
| `direction` | select | No | in | Direction: in (push forward), out (pull back) |
| `focal_x` | number | No | 0.5 | Focal point X (0-1) |
| `focal_y` | number | No | 0.5 | Focal point Y (0-1) |
| `blur` | boolean | No | true | Add motion blur |

**Use when:** Diving into details, dramatic emphasis, entering new topic.

---

### transition-glitch

**Engine:** Motion Canvas

Digital glitch effect transitioning between scenes.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `duration` | duration | No | 0.5 | Glitch duration |
| `intensity` | number | No | 0.7 | Glitch intensity (0-1) |
| `slices` | number | No | 10 | Number of slice distortions |
| `colorShift` | boolean | No | true | Add RGB color separation |

**Use when:** Tech content, error/malfunction themes, edgy style.

---

### transition-shape

**Engine:** Motion Canvas

Shape-based wipe reveal (circle, diamond, star, etc.).

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `shape` | select | No | circle | Shape: circle, diamond, star, heart, hexagon |
| `duration` | duration | No | 1 | Transition duration |
| `direction` | select | No | expand | Direction: expand, contract |
| `color` | color | No | transparent | Shape fill color (or transparent) |

**Use when:** Creative transitions, thematic reveals, playful content.

---

## Quick Reference for LLM

When selecting effects, consider:

| Content Type | Recommended Effects |
|--------------|---------------------|
| Historical photo | `image-ken-burns`, `photo-frame` |
| Detail reveal | `image-zoom-focus` |
| Important quote | `quote-fade-center`, `quote-dramatic` |
| Statement breakdown | `quote-kinetic` |
| Single statistic | `stat-counter-roll`, `stat-highlight-pulse` |
| Multiple values | `chart-bar-race`, `chart-bar-callout` |
| Trend over time | `chart-line-draw` |
| Composition | `chart-pie-expand` |
| Two options | `compare-side-by-side`, `split-screen` |
| Transformation | `compare-before-after` |
| Video opening | `title-card`, `gradient-text` |
| Section start | `title-chapter` |
| Speaker ID | `title-lower-third` |
| Location story | `map-flyover`, `location-pin` |
| Annotation | `callout-line`, `callout-box` |
| Tech/hacker theme | `text-scramble`, `text-glitch` |
| Source document | `document-reveal` |
| Retro/flashback | `vhs-retro`, `film-grain` |
| Scene changes | `transition-dissolve`, `transition-zoom` |
| Supplementary visual | `picture-in-picture` |
| Depth/parallax | `image-parallax` |
| Before/after comparison | `compare-before-after` |
| Lyric-style text | `text-pop` |
| Academic credibility | `source-citation` |
| Website/app showcase | `screen-frame` |
| Podcast/audio clips | `audio-waveform` |
| Documentary texture | `light-leak`, `film-grain` |
| Tension/urgency | `camera-shake` |

---

## New Effects (2026-01-17)

### image-parallax

**Engine:** Motion Canvas

Multi-layer parallax movement creating 2.5D depth illusion. Foreground moves faster than background for a cinematic effect.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `image` | image | Yes | - | The image to animate with parallax |
| `layers` | number | No | 3 | Number of depth layers (2-5) |
| `direction` | select | No | horizontal | Movement: horizontal, vertical, diagonal |
| `intensity` | number | No | 1.0 | Parallax intensity (0.5-2.0) |
| `duration` | duration | No | 6 | Effect duration (2-20s) |

**Use when:** Bringing static images to life with depth, modern documentary style, title sequences.

---

### compare-before-after

**Engine:** Motion Canvas

Slider-style wipe transition revealing before and after states. Classic comparison effect for transformations.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `before_label` | string | No | Before | Label for before state |
| `after_label` | string | No | After | Label for after state |
| `before_color` | color | No | #64748b | Background for before |
| `after_color` | color | No | #22c55e | Background for after |
| `direction` | select | No | horizontal | Wipe direction |
| `pause_middle` | number | No | 1 | Seconds to pause at 50% |
| `show_slider` | boolean | No | true | Show animated slider handle |

**Use when:** Showing transformations, renovations, before/after comparisons.

---

### text-pop

**Engine:** Motion Canvas

Word-by-word reveal with scale and color emphasis. Lyric video style for impactful statements.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `text` | text | Yes | - | Text to animate (words pop one by one) |
| `emphasis_words` | string | No | - | Comma-separated words to emphasize |
| `style` | select | No | scale-up | Animation: scale-up, drop-in, slide-up, fade-scale |
| `color` | color | No | #ffffff | Default text color |
| `emphasis_color` | color | No | #fbbf24 | Color for emphasized words |
| `font_size` | number | No | 72 | Text size (32-200) |

**Use when:** Key statements, lyric-style reveals, impactful quotes.

---

### source-citation

**Engine:** Motion Canvas

Animated source/reference citation. Academic style attribution for credibility in documentaries.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `source` | string | Yes | - | Source name (e.g., "New York Times") |
| `title` | string | No | - | Article/report title |
| `date` | string | No | - | Publication date |
| `url` | string | No | - | Source URL (truncated) |
| `style` | select | No | minimal | Style: minimal, full, academic, news |
| `position` | select | No | bottom-left | Position on screen |

**Use when:** Citing sources, academic credibility, documentary attribution.

---

### screen-frame

**Engine:** Motion Canvas

Browser, phone, or laptop mockup frame. Perfect for showing websites, apps, tweets.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `device` | select | No | browser | Device: browser, phone, laptop, tablet, monitor |
| `url` | string | No | - | URL for browser address bar |
| `title` | string | No | - | Window/app title |
| `content_text` | text | No | - | Text content inside frame |
| `theme` | select | No | dark | Light or dark theme |
| `animation` | select | No | scale | Entry: fade, slide-up, scale, none |

**Use when:** Showing websites, tweets, apps, social media posts, screen recordings.

---

### audio-waveform

**Engine:** Motion Canvas

Animated audio waveform visualization. Great for podcast clips and music discussions.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `style` | select | No | bars | Visualization: bars, line, circular, mirrored |
| `color` | color | No | #0ea5e9 | Waveform color |
| `secondary_color` | color | No | #a855f7 | Gradient end color |
| `intensity` | number | No | 1.0 | Animation intensity (0.5-2) |
| `label` | string | No | - | Optional label (speaker name) |

**Use when:** Podcast clips, music discussions, audio-focused content, interview clips.

---

### light-leak

**Engine:** Motion Canvas

Organic light leak and film burn overlay. Adds warmth, nostalgia, and texture.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `style` | select | No | warm | Style: warm, cool, rainbow, burn, flare |
| `intensity` | number | No | 0.5 | Effect intensity (0-1) |
| `position` | select | No | corner | Origin: left, right, top, bottom, corner, center |
| `animated` | boolean | No | true | Animate the light leak movement |
| `color` | color | No | #ff6b35 | Override tint color |

**Use when:** Adding cinematic texture, nostalgia, Johnny Harris style warmth.

---

### camera-shake

**Engine:** Motion Canvas

Handheld camera shake effect. Adds tension, urgency, or documentary realism.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `intensity` | select | No | subtle | Level: subtle, moderate, intense, earthquake |
| `style` | select | No | handheld | Type: handheld, impact, nervous, smooth |
| `text` | string | No | - | Optional text to display |

**Use when:** Tension, urgency, documentary feel, impact moments.
