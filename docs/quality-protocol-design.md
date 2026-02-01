# Quality Protocol Design for NOLAN Template Automation

## Problem Statement

When auto-generating video content from templates, several quality issues can occur:
1. **Text rendering failures** - Font glyphs missing, characters cut off, wrong encoding
2. **Layout issues** - Content cut off, wrong positioning, overlapping elements
3. **Duration mismatches** - Video shorter/longer than expected
4. **Visual artifacts** - Corruption, blank frames, color issues

Currently, there's no automated validation after rendering. Issues are only caught by manual review.

## Proposed Solution: Quality Protocol Module

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     RENDER PIPELINE                              │
├─────────────────────────────────────────────────────────────────┤
│  Input Spec  →  Engine Render  →  Quality Protocol  →  Output   │
│                                        │                         │
│                                        ▼                         │
│                              ┌─────────────────┐                │
│                              │   Validation    │                │
│                              │   - Properties  │                │
│                              │   - Visual QA   │                │
│                              │   - Text OCR    │                │
│                              └────────┬────────┘                │
│                                       │                         │
│                              ┌────────▼────────┐                │
│                              │  Issue Found?   │                │
│                              └────────┬────────┘                │
│                                       │                         │
│                         ┌─────────────┼─────────────┐           │
│                         ▼             ▼             ▼           │
│                      [Pass]     [Auto-Fix]    [Report]          │
│                         │             │             │           │
│                         └─────────────┴─────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

### Module Location

```
render-service/
├── src/
│   ├── quality/                    # NEW: Quality Protocol Module
│   │   ├── index.ts               # Main exports
│   │   ├── types.ts               # QA types and interfaces
│   │   ├── validator.ts           # Core validation logic
│   │   ├── checks/
│   │   │   ├── properties.ts      # Duration, resolution, file size
│   │   │   ├── visual.ts          # Frame extraction, visual checks
│   │   │   └── text.ts            # OCR text verification
│   │   └── fixes/
│   │       ├── font.ts            # Font fallback strategies
│   │       └── rerender.ts        # Re-render with adjustments
│   └── jobs/
│       └── processor.ts           # Modified to include QA step
```

### Integration Points

#### 1. Render Service (Primary)

In `processor.ts`, add QA step after engine render:

```typescript
// After engine.render()
const qaResult = await qualityValidator.validate(result.outputPath, {
  expectedText: spec.text,
  expectedDuration: spec.duration,
  expectedResolution: { width: spec.width, height: spec.height }
});

if (!qaResult.passed) {
  if (qaResult.autoFixable) {
    result = await qualityValidator.fix(result, qaResult.issues);
  } else {
    jobQueue.updateJob(job.id, {
      status: 'qa_failed',
      qaReport: qaResult.issues
    });
    return;
  }
}
```

#### 2. Python Scripts (Secondary)

For standalone scripts like `render_quote_simple.py`:

```python
from nolan.quality import QualityProtocol

# After creating video
qa = QualityProtocol()
result = qa.validate(
    video_path=output_path,
    expected_text="WE ARE TIRED",
    expected_duration=7.0
)

if not result.passed:
    if result.auto_fixable:
        output_path = qa.fix(output_path, result.issues)
    else:
        raise QualityError(result.issues)
```

### Validation Checks

#### 1. Property Checks (Fast)
- File exists and size > 0
- Duration within tolerance (±0.5s)
- Resolution matches expected
- Frame count reasonable for duration/fps

#### 2. Visual Checks (Medium)
- Extract frames at 10%, 50%, 90% of duration
- Check for blank/black frames
- Verify content is within safe zones
- Detect obvious artifacts

#### 3. Text Verification (Slow, Optional)
- OCR on extracted frames
- Compare against expected text
- Fuzzy matching for minor differences
- Character-level validation for critical text

### Issue Categories and Fixes

| Issue | Detection | Auto-Fix Strategy |
|-------|-----------|-------------------|
| Font glyph missing | OCR mismatch, visual check | Try fallback fonts (Arial → DejaVu → FreeSans) |
| Text cut off | OCR incomplete, visual bounds | Reduce font size, adjust positioning |
| Wrong duration | Property check | Re-render with correct duration |
| Blank frames | Visual check (histogram) | Check source, re-render |
| Low quality | File size ratio | Increase quality preset |

### Configuration

```typescript
interface QualityConfig {
  // Enable/disable check categories
  checks: {
    properties: boolean;  // Always on
    visual: boolean;      // Default on
    textOcr: boolean;     // Default off (slow)
  };

  // Tolerance settings
  durationTolerance: number;  // seconds, default 0.5
  textMatchThreshold: number; // 0-1, default 0.95

  // Fix settings
  autoFix: boolean;           // Default true
  maxFixAttempts: number;     // Default 3
  fallbackFonts: string[];    // Font fallback chain
}
```

### Implementation Priority

1. **Phase 1: Core Validation** (Essential)
   - Property checks (duration, resolution, file size)
   - Basic visual checks (blank frame detection)
   - Integration into processor.ts

2. **Phase 2: Text Verification** (Important)
   - OCR integration (Tesseract or cloud API)
   - Text matching logic
   - Font fallback system

3. **Phase 3: Auto-Fix** (Enhancement)
   - Re-render pipeline
   - Font substitution
   - Layout adjustments

### Dependencies

- **ffprobe**: Video property extraction (already available)
- **sharp** or **jimp**: Frame extraction and image analysis
- **tesseract.js** (optional): OCR for text verification

### Example Workflow

```
1. User submits render job with text "WE ARE TIRED"
2. Engine renders video using template
3. Quality Protocol runs:
   a. Property check: ✓ Duration 7s, Resolution 1920x1080
   b. Visual check: ✓ No blank frames, content centered
   c. Text check: ✗ OCR reads "WE ARE TIREN" (D cut off)
4. Auto-fix triggered:
   a. Issue: Font rendering problem with character "D"
   b. Strategy: Re-render with fallback font "DejaVu Sans"
5. Re-render completes
6. Quality Protocol re-validates: ✓ All checks pass
7. Job marked as done
```

### Metrics & Logging

Track quality metrics over time:
- Pass rate by template
- Common failure modes
- Fix success rate
- Average validation time

This data helps identify problematic templates and improve the system.
