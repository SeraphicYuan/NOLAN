# NOLAN script REVIEW task (diagnose-only): "Homer [CALIBRATION]"

You are a **fresh-eyes producer/editor**. You did NOT write this draft. Review it hard against
the rubric below and record a **located** critique. **Do NOT edit the draft in this pass** —
diagnosis only; a separate revise pass applies the fixes the producer approves.

## Context — read the SAME material the writer had, plus the draft
- **Draft under review:** `explore/2026-08-02-script-loop-graph/_runs/homer-cal/scriptgen/drafts/draft-02.md`  (draft #2)
- **Style guide (voice constitution):** `script_styles/channel-great-books-explained/style_guide.md`
- **Brief:** `explore/2026-08-02-script-loop-graph/_runs/homer-cal/scriptgen/brief.md`
- **Grounded facts:** `explore/2026-08-02-script-loop-graph/_runs/homer-cal/scriptgen/facts.md`
- **Beat-map (spine + pacing):** `explore/2026-08-02-script-loop-graph/_runs/homer-cal/scriptgen/beatmap.md`
- **Citations:** `explore/2026-08-02-script-loop-graph/_runs/homer-cal/scriptgen/citations.md`   ·   **Fact-check:** `explore/2026-08-02-script-loop-graph/_runs/homer-cal/scriptgen/factcheck.md`
Judge the draft on the SAME context that produced it — never on less.

## Review rubric — archetype: **explainer** (Explainer)

Work each dimension in order. For EACH finding, record: the beat it lives in, the exact phrase/line at issue, a severity (`high` / `med` / `low`), the problem, and a CONCRETE proposed fix. Diagnose only — do NOT edit the draft in this pass.

### 1. Example strength  ·  `example-strength`  ·  weight 5/5
_Reads: draft, facts._

For each example the draft uses, ask: is this the CLEAREST, most CONCRETE instance of the point it serves? Flag examples that are weak, generic, confusing, off-target, or that make the listener work to see the connection. Replace each with a sharper, more vivid instance drawn from facts.md — or, if none exists there, research a stronger one and ground it.

### 2. Figurative fitness  ·  `figurative-fitness`  ·  weight 4/5
_Reads: draft, facts._

Audit every metaphor, analogy, and allegory in the draft. For each, decide: is it EARNED (it clarifies or intensifies a real point), ACCURATE (it does not distort the fact it dramatizes), and LOAD-BEARING (the beat is weaker without it)? Flag any that is merely decorative, mixed/incoherent, clichéd, or that bends a fact for effect. For each weak one, either cut it or replace it with a stronger image drawn from the actual source material — never invent flourish that isn't grounded.

### 3. Voice ownership vs. attribution  ·  `voice-ownership`  ·  weight 4/5
_Reads: draft, citations._

By default we paraphrase and assert in our OWN analytical voice. The target for non-load-bearing attributions is ZERO — do NOT merely trim or reduce them; strip them out entirely. Name a source ONLY when (a) the person or institution is prominent enough that the name itself adds authority the argument needs, or (b) it is a first-person human quote whose exact wording must stay verbatim and in context. Everything else — 'According to X…', 'As Y argues…', 'X points out…' — becomes our own claim, fact preserved, name removed. **A commentator's name appearing more than once or twice is itself a flag:** keep it on the ONE or two lines where the phrasing is genuinely theirs or the named authority IS the point, and strip it everywhere else. (Concretely: a pundit cited 4–5 times across the script should end at 0–2.) Conversely, flag any genuinely prominent authority or human quote we absorbed into our voice when it should be credited.

### 4. Evidential sufficiency  ·  `evidential-sufficiency`  ·  weight 4/5
_Reads: draft, facts, citations._

For THIS video's type and length, does each beat carry ENOUGH well-chosen examples and specific detail to feel substantive — neither thin/asserted nor padded/repetitive? Identify beats that are under-supported (claims without a concrete anchor, numbers without context, turns without evidence). For each, research and insert well-sourced specifics IN THE RIGHT PLACE, and update facts.md + citations.md so every addition is grounded, not invented.

### 5. Through-line & payoff  ·  `throughline-payoff`  ·  weight 3/5
_Reads: draft, beatmap._

Check the spine. Does every beat earn its place by serving the through-line? If the script carries more than one thread, do the threads actually BRAID into the declared macro-structure (chronological / hierarchical / …), or do they merely sit side by side? Verify the hook makes a promise and the body pays it off, and that any refrain or label recurs with purpose and lands at the close. Flag beats that wander, threads that don't connect, and promises left unpaid.

### 6. Retention & redundancy  ·  `retention-redundancy`  ·  weight 3/5
_Reads: draft._

Read for drag. Flag any mid-script sag, any point made more than once, any sentence or beat that could be cut with no loss, and any refrain used so often it deadens. A long script earns its length only if every beat pulls. Propose specific cuts and tightenings.


## Output → `explore/2026-08-02-script-loop-graph/_runs/homer-cal/scriptgen/reviews/review-02.findings.json` (machine-readable findings — this is the deliverable)
Emit `explore/2026-08-02-script-loop-graph/_runs/homer-cal/scriptgen/reviews/review-02.findings.json` — a JSON array, one object per finding:
`{"id":"f1","dim":"<dim-id>","severity":"high|med|low","beat":"<name>","quote":"<phrase>","problem":"<...>","fix":"<...>"}`
Be specific and quote the draft; a vague critique can't be applied. (Unattended run — the prose write-up is skipped.)

STOP after writing the findings. Do not touch the draft.
