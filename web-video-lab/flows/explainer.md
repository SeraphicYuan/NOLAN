# Flow: Paper / Article Explainer (`explainer`)

The solidified, battle-tested flow (validated on the Transformer paper + the J.P. Morgan
tail-trading report). This doc *packages* the existing pipeline as the first registry entry —
the template the other flows fork from. Nothing here is new; it names the parts.

## When to use
An **idea-dense, text-first** source (paper, report, article). The visuals are *generated* to
represent abstract ideas; any figures are *exhibits*, not the subject.

## Ingest
- **generate-from-source** — `load_source` → script (the **script skill**) → OmniVoice TTS →
  Whisper word-align → `gen_spec`.
- **byo-script** — user supplies the script → TTS → align → `gen_spec`.
- Sources: arXiv HTML, MinerU parsed folders (`extract_figure.py` for figures).

## Grammar (`SCENE_GRAMMAR.md` + `SCRIPT_SKILL.md`)
- Scene taxonomy: Hook → Problem → Key idea → Method → Formula → Results → Figure → Comparison
  → Takeaway.
- **Rules:** *redraw synthetic, lift empirical* · *front-load the visual keyword* (the anchor
  word lands in the beat's first sentence) · *one insight per beat* · audio = master clock.

## Palette
The full library (see `BLOCK_CATALOG.md`): HeroStatement, KineticHeadline, PullQuote,
ListReveal, StepFlow, StatCount, ValueLadder, BarChart, LineChart, Distribution, Heatmap,
DataTable, Formula, PaperFigure, ComparisonVS, Timeline, ArchetypeCards, WebVsBoxes,
UnlockGrid, ChapterCard, EndCard, LottieIcon.

## Pacing profile (linter `--profile explainer`)
WPM 130–165 · first reveal ≤6s (fail) / ≤3s (warn) · dead gap ≤9s (fail) / ≤5s (warn) ·
density ≤1.2 reveals/s. Enforced by `pacing_lint.py` as a pre-render gate.

## Defaults
Theme by topic (e.g. blueprint for ML, midnight-press for finance) · hard-cut transitions
(audio-safe) · PostFX optional (subtle grade/bloom/vignette).

## Pipeline (the canonical run)
`script → TTS → words → spec → gen_spec → pacing_lint (gate) → render.mjs → mp4`
