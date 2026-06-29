# Scene grammar + comprehension eval (library-boost Wave 3, authoring layer)

Borrowed from the paper→video literature (Paper2Video, Data Player, PPTAgent) — the
*planning* discipline that sits above block selection, plus a quality metric.

## Section scene taxonomy (the planner backbone)
Empirically, paper explainers route into a small set of section types. The chapter agent
should plan beats against this spine (skip what a paper lacks):
`Hook → Problem/Motivation → Key idea → Method/Mechanism → Formula(s) → Results
(table/chart) → Figure walk-through → Ablation/Comparison → Takeaway/Punchline`.
Each maps to blocks: Hook→HeroStatement/KineticHeadline; Problem→ListReveal/ComparisonVS;
Method→StepFlow/ArchStack(bespoke); Formula→Formula; Results→DataTable/BarChart/LineChart/
Distribution/Heatmap; Figure→PaperFigure; Comparison→ComparisonVS; Takeaway→EndCard.
Long papers get **ChapterCard** dividers between acts.

## Audio is the master clock
Scene duration = narration length (we already derive `durationInFrames` from the wav). Never
pad a scene past its narration; never cut narration to fit a scene. One insight per beat.

## Entrance / Emphasis / Exit (the animation grammar)
Every reveal is one of three roles, gated: **Entrance** (the element arrives — enter easing,
decelerate), **Emphasis** (it's referenced again as spoken — pulse/accent; only *after* its
entrance), **Exit** (it leaves — accelerate). Enter-order = narration token order. This is
already how blocks behave; make it explicit when authoring bespoke beats.

## Transitions (scene-to-scene)
Film grammar: **cut within a topic, fade/dissolve between topics** (see BLOCK_CATALOG
"Transition layer"). Narrated Chapter = hard cuts (audio-safe). Silent montages = the
`Montage` composition with `fade|slide|wipe|clockWipe` + optional camera motion-blur.

## Comprehension eval (PaperQuiz-style harness) — the quality metric
The most transferable measure of explainer quality: **can a viewer answer questions about the
paper after watching?** A cheap agent-driven harness:
1. **Generate** — from the paper (content.md), an agent writes N (~8) multiple-choice
   comprehension questions with answers grounded in the text (cite the line).
2. **"Watch"** — a *fresh* agent sees ONLY what the video conveys: the narration script
   (segments.json) + the on-screen text (captions/labels) + the lifted figure captions.
   It answers the N questions.
3. **Score** — % correct = a comprehension proxy. Diff the misses against the questions to
   find what the video failed to convey → those become script/beat revisions.
Two gaps the literature says everyone leaves open (we can own): **equations** (we redraw them
via KaTeX) and **citations** (we attribute lifted figures + can add an EndCard source). Track
both as eval dimensions. (Implement as a small two-agent script when we want to A/B scripts;
the spec is the contract.)
