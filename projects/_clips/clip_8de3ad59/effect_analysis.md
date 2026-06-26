# Effect Analysis — clip_8de3ad59

Source: `US Economy / If The Economy Is F＊cked, Why Hasn't It Crashed Yet？.mp4`
In/out: 581.16s → 583.35s (2.19s)

## Effect

An **animated highlighter-marker sweep** over a line of body text.

- The layout is a static "report" card (kicker date, bold headline *Executive Excess 2025*,
  byline, and two paragraphs of bold/grey body copy over a dark mountain photo). Nothing in
  the layout moves.
- The single moving element is a **semi-transparent light-grey/white highlight bar** that
  **wipes left→right** across the first key sentence ("From 2019 through 2024, the Low-Wage 100
  spent $644 billion…"). Across the 6 frames the bar grows from just the leading "F"
  (frame 3) → "From 20" (frame 4) → "From 2019 thro" (frame 5) → "From 2019 through 20" (frame 6).
- It reads as a marker drawing over the text (translucent, text stays readable through it),
  **not** an underline, not a glow, not a color change. Reveal width is proportional to elapsed
  time (linear-ish progress over ~the clip duration). Color is neutral grey, not classic
  highlighter-yellow.

## Dedup result

**Partially covered by API, but effectively NEW (the renderer path is a stub).**

- `effects.py:657 Underline(style="highlight")` is *exactly* this concept: a progress-driven
  (`underline_progress`) semi-transparent bar revealed L→R. **But it does not render.** In
  `base.py:618-622` the `'highlight'` branch builds the bar image and stops at a comment —
  `# Note: Would need to composite onto main image` — so nothing is drawn. Only the `'line'`
  branch (`base.py:623-627`) works, and it draws a thin line *below the baseline*
  (`line_y = y + text_height + offset`), not a fill *over* the text.
- Other nearby primitives are not a match:
  - `Highlight` (`effects.py:632`) = a glow flash that fades, not a directional sweep.
  - `WipeIn` / `Reveal` = mask-reveal the *element itself*, not an overlay bar behind text.
  - `DrawBox` = animated box *outline*, not a translucent fill.
  - `ColorShift` / `Pulse` / `Flash` = no directional reveal.
- Scene templates: `document_highlight.py` builds a paper-document card and *names* a
  `highlight_text` / `highlight_bg_color`, but `_setup_elements()` never creates a highlight
  element or attaches any highlight/underline effect — so it doesn't produce this motion either.
- render-service (`effects/presets/image.ts:424`) exposes a `highlight` param on the document
  preset but is a separate TS pipeline (static styling, not this animated sweep).

**Verdict: NEW.** The motion is not produced anywhere today.

## Replicable?

**Yes — low effort.** It's a straight finish of an already-designed primitive, no new math.

The only real work is compositing a translucent rectangle whose width tracks
`underline_progress`. The L→R progress, easing, timing, color and thickness fields already
exist on `Underline`.

## Plan

Smallest correct change (recommended):

1. **`src/nolan/renderer/base.py` (~lines 615-622)** — implement the `'highlight'` branch:
   - Position the bar to overlap the text box instead of below it
     (e.g. `bar_y = y`, `bar_height = text_height` rather than `y + text_height + offset`).
   - Composite the RGBA bar onto the frame with `Image.alpha_composite` / `paste` using the
     bar as its own mask, at `(x, bar_y)` with `width = int(text_width * underline_progress)`.
     Draw it **before** the glyphs (or keep alpha low ~0.3 so text reads through) so it looks
     like a marker, matching the clip.
2. **`src/nolan/renderer/effects.py:657 Underline`** — add a `mode`/`over_text: bool` field (or
   reuse `offset_y<=0`) so callers can pick "marker over text" vs "underline below". Default
   keeps current behavior; surgical, backwards-compatible.
3. **Wire into a scene** — make `document_highlight.py` actually attach
   `Underline(style="highlight", color=highlight_bg_color, ...)` to the text element for the
   `highlight_text` span (today it ignores both params). That turns the existing template into a
   real match for this clip.
4. **Test** — `scripts/test_highlight_sweep.py`: render a one-line and a wrapped two-line text
   with the highlight sweep, assert frames differ over time and the bar grows monotonically.

Difficulty: **Low** (core fix ~10-15 lines in base.py; the rest is plumbing). Multi-line
sweep (bar continuing onto the wrapped second line) is the only nuance — defer unless needed,
since the clip only highlights within the first line during the captured window.

For the clip's neutral-grey look, pass `color=(235, 235, 240)` (not the default highlighter
yellow).

## Promoted to NOLAN

Implemented 2026-06-24. The `Underline(style="highlight")` stub now renders, and phrase-based
selection was added (line-index targeting was deliberately skipped — wrap-dependent/brittle;
phrase matching is robust and matches authoring intent).

| Technique | Effect / API | File | Date |
|-----------|--------------|------|------|
| Highlight-marker sweep (renders a translucent swept bar over text) | `Underline(style="highlight")` | `src/nolan/renderer/effects.py`, `src/nolan/renderer/base.py` | 2026-06-24 |
| Phrase-based span selection (word-level, wrap-aware across lines) | `Underline(highlight_text="…")` | `src/nolan/renderer/base.py` (`_highlight_segments`, `_render_highlight_marker`) | 2026-06-24 |
| Wired into the document card (its `highlight_text` param now drives the sweep) | `DocumentHighlightRenderer(highlight_text="…")` | `src/nolan/renderer/scenes/document_highlight.py` | 2026-06-24 |
| Reusable motion-library preset | `EffectPresets.highlight_sweep(...)` | `src/nolan/renderer/effects.py` | 2026-06-24 |

Usage:

```python
Element(text="From 2019 through 2024, the Low-Wage 100 spent $644 billion on stock buybacks.",
        max_width=560, text_align="left", ...).add_effect(
    Underline(style="highlight", highlight_text="From 2019 through 2024",
              color=(235, 235, 240), opacity=0.5, start=1.0, duration=3.0))
```

- `highlight_text=None` sweeps the whole element; an unmatched phrase falls back to that too.
- Verified by `scripts/test_highlight_sweep.py` (renders, grows monotonically, phrase span is a
  strict subset of the full sweep). Visual check confirmed the bar stops exactly at the phrase end.
