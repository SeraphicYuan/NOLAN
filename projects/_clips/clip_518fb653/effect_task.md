# NOLAN effect-analysis task

A user saved a clip from a source video and wants to know **what visual / motion
effect it uses** and **whether NOLAN can already reproduce it**.

## The clip
- Source video: `projects\_library\source\The Mystery Of The Samurai In Venice.mp4`
- In/out: 389.133s → 399.5s (10.367000000000019s)
- Label: (none)
- Extracted clip file (watch motion via ffmpeg/your tools): `projects/_clips/clip_518fb653/clip.mp4`
- Sample frames:
  - projects/_clips/clip_518fb653/frames/frame_0001.jpg
  - projects/_clips/clip_518fb653/frames/frame_0002.jpg
  - projects/_clips/clip_518fb653/frames/frame_0003.jpg
  - projects/_clips/clip_518fb653/frames/frame_0004.jpg
  - projects/_clips/clip_518fb653/frames/frame_0005.jpg
  - projects/_clips/clip_518fb653/frames/frame_0006.jpg
  - projects/_clips/clip_518fb653/frames/frame_0007.jpg
  - projects/_clips/clip_518fb653/frames/frame_0008.jpg
  - projects/_clips/clip_518fb653/frames/frame_0009.jpg
  - projects/_clips/clip_518fb653/frames/frame_0010.jpg

## What to do (in order)
1. **Inspect** the frames (and the clip file if you need finer motion detail —
   e.g. `ffmpeg -i projects/_clips/clip_518fb653/clip.mp4 -vf fps=10 ...`). Describe the effect precisely:
   camera move, transition, text/graphic animation, color/filter, etc.
2. **Dedup against the existing motion library FIRST.** NOLAN can recreate effects on
   **two backends** — pick whichever fits the effect. Check these registered effects
   (the `nolan.motion` registry, `src/nolan/motion/registry.py`) before proposing anything new:
   - **Remotion compositions (`render-service/remotion-lib/`, ids in `registry.json`)**:
     - `kinetic-text` (Kinetic) — Reveal a short headline word-by-word, accenting key words.
     - `bar-compare` (BarCompare) — Animated bar comparison with count-up labels.
     - `k-shape` (KShape) — Two diverging lines (rising vs falling) from a shared origin — the K split.
     - `annotate-video` (AnnotateOverVideo) — Draw-on circle + arrow + label pointing at a spot on b-roll.
     - `annotate-stat` (AnnotateStat) — Emphasize one number/stat with a drawn circle + caption.
     - `route-map` (RouteMap) — Animated pins + routes over a basemap (money/flow/geo).
     - `premium-card` (PremiumCard) — Glass/gradient hero or chapter title card.
   - **Python renderers (`src/nolan/renderer/scenes/`)**:
     - `counter` (CounterRenderer) — Animated count-up number with a caption (a stat reveal).
     - `title` (TitleRenderer) — Animated title card (title + subtitle + accent line).
     - `lower-third` (LowerThirdRenderer) — Lower-third name/title caption.
     - `comparison` (ComparisonRenderer) — Two-sided VS comparison.
     - `line-chart` (LineChartRenderer) — Animated single-series line chart (rise/crash/rally).
     - `loop-diagram` (LoopDiagramRenderer) — Animated feedback-loop: labelled nodes in a cycle with arrows.
   - Effect primitives (Python): `src/nolan/renderer/effects.py` (FadeIn/Out, Slide*,
     MoveTo, ScaleIn/Out, Pulse, Shake, Glitch, BlurIn/FocusPull, Glow*, Shadow*,
     Letterbox, Scanlines, ColorTint, VHSEffect, Reveal, RotateIn/Spin, …)
   - Remotion is best for kinetic typography, animated charts/SVG, transitions, glossy
     CSS; Python is best for fast simple cards. State clearly: **already covered**
     (name the registry `effect` id + backend) or **new**.
3. If **new**, assess **replicability** and pick a backend:
   - **Remotion** → add a composition in `render-service/remotion-lib/src/` + a
     `MotionEffect(..., backend="remotion", target="<CompId>")` row in `registry.py`.
   - **Python** → a scene renderer in `src/nolan/renderer/scenes/` + a
     `MotionEffect(..., backend="python", target="<ClassName>")` row in `registry.py`.
   The executor (`nolan.motion.executor.render`) already handles both backends, so a new
   registry row makes it renderable from a spec immediately. Give a concrete plan.

## Output
Write your findings to `projects/_clips/clip_518fb653/effect_analysis.md` as markdown with sections:
**Effect**, **Dedup result** (registry id + backend if covered), **Replicable?**
(chosen backend), **Plan**. Keep it concise and actionable. (Follow the repo's
"Promoting Techniques to NOLAN" convention if you implement it.)
