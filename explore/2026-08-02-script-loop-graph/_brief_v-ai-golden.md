# NOLAN pairwise REVIEW: "the AI debate (golden A/B) [VALIDATE]"

Judge whether `draft-02` is **better than** the draft before it — and what still blocks it.

**You are not writing a list of everything wrong.** A draft that argues earns more criticism than
one that asserts, so a long list is not evidence of a bad draft and a short one is not evidence of
a good one. Reward the version that is stronger to read, even when it exposes more surface to
criticise.

## Read BOTH, in this order
- **previous:** `explore/2026-08-02-script-loop-graph/_runs/v-ai-golden/scriptgen/drafts/draft-01.md` (3215 narration words)
- **current:**  `explore/2026-08-02-script-loop-graph/_runs/v-ai-golden/scriptgen/drafts/draft-02.md` (3753 narration words)

Read the previous draft first, then the current one. You are judging the CHANGE, not auditing the current draft in isolation.

## Context (the same material the writer had)
- **Brief:** `explore/2026-08-02-script-loop-graph/_runs/v-ai-golden/scriptgen/brief.md`   · **Beatmap:** `explore/2026-08-02-script-loop-graph/_runs/v-ai-golden/scriptgen/beatmap.md`
- **Facts:** `explore/2026-08-02-script-loop-graph/_runs/v-ai-golden/scriptgen/facts.md`   · **Citations:** `explore/2026-08-02-script-loop-graph/_runs/v-ai-golden/scriptgen/citations.md`
- **Style guide (voice):** `script_styles/channel-lufei-wang-eng/style_guide.md`
- **Length target:** ~2900 narration words; the current draft is 3753.

## What to weigh — rubric `long-form-argument`
## Review rubric — archetype: **long-form-argument** (Long-form argument (business / economics / debate))

Work each dimension in order. For EACH finding, record: the beat it lives in, the exact phrase/line at issue, a severity (`high` / `med` / `low`), the problem, and a CONCRETE proposed fix. Diagnose only — do NOT edit the draft in this pass.

### 1. Evidential sufficiency  ·  `evidential-sufficiency`  ·  weight 5/5
_Reads: draft, facts, citations._

For THIS video's type and length, does each beat carry ENOUGH well-chosen examples and specific detail to feel substantive — neither thin/asserted nor padded/repetitive? Identify beats that are under-supported (claims without a concrete anchor, numbers without context, turns without evidence). For each, research and insert well-sourced specifics IN THE RIGHT PLACE, and update facts.md + citations.md so every addition is grounded, not invented.

### 2. Figurative fitness  ·  `figurative-fitness`  ·  weight 4/5
_Reads: draft, facts._

Audit every metaphor, analogy, and allegory in the draft. For each, decide: is it EARNED (it clarifies or intensifies a real point), ACCURATE (it does not distort the fact it dramatizes), and LOAD-BEARING (the beat is weaker without it)? Flag any that is merely decorative, mixed/incoherent, clichéd, or that bends a fact for effect. For each weak one, either cut it or replace it with a stronger image drawn from the actual source material — never invent flourish that isn't grounded.

### 3. Voice ownership vs. attribution  ·  `voice-ownership`  ·  weight 4/5
_Reads: draft, citations._

By default we paraphrase and assert in our OWN analytical voice. The target for non-load-bearing attributions is ZERO — do NOT merely trim or reduce them; strip them out entirely. Name a source ONLY when (a) the person or institution is prominent enough that the name itself adds authority the argument needs, or (b) it is a first-person human quote whose exact wording must stay verbatim and in context. Everything else — 'According to X…', 'As Y argues…', 'X points out…' — becomes our own claim, fact preserved, name removed. **A commentator's name appearing more than once or twice is itself a flag:** keep it on the ONE or two lines where the phrasing is genuinely theirs or the named authority IS the point, and strip it everywhere else. (Concretely: a pundit cited 4–5 times across the script should end at 0–2.) Conversely, flag any genuinely prominent authority or human quote we absorbed into our voice when it should be credited.

### 4. Example strength  ·  `example-strength`  ·  weight 4/5
_Reads: draft, facts._

For each example the draft uses, ask: is this the CLEAREST, most CONCRETE instance of the point it serves? Flag examples that are weak, generic, confusing, off-target, or that make the listener work to see the connection. Replace each with a sharper, more vivid instance drawn from facts.md — or, if none exists there, research a stronger one and ground it.

### 5. Retention & redundancy  ·  `retention-redundancy`  ·  weight 4/5
_Reads: draft._

Read for drag. Flag any mid-script sag, any point made more than once, any sentence or beat that could be cut with no loss, and any refrain used so often it deadens. A long script earns its length only if every beat pulls. Propose specific cuts and tightenings.

### 6. Genuine steelman  ·  `steelman-present`  ·  weight 4/5
_Reads: draft, facts._

The strongest counter-case must appear at FULL strength, in our own voice — not strawmanned, rushed, or skipped. Verify the draft genuinely steelmans the opposing view before it renders judgment, so the verdict reads as earned judgment rather than cheerleading. Flag every place the counter-argument is weakened or absent, and strengthen it.

### 7. Number integrity  ·  `number-integrity`  ·  weight 4/5
_Reads: draft, citations, factcheck._

Every number, date, and quantitative claim must be traceable to citations.md and appropriately HEDGED where it is an estimate or single-sourced. Flag any figure stated with false precision or unearned certainty, any that can't be traced, and any '[needs-check]' claim presented as settled fact. Soften or cut.

### 8. Through-line & payoff  ·  `throughline-payoff`  ·  weight 3/5
_Reads: draft, beatmap._

Check the spine. Does every beat earn its place by serving the through-line? If the script carries more than one thread, do the threads actually BRAID into the declared macro-structure (chronological / hierarchical / …), or do they merely sit side by side? Verify the hook makes a promise and the body pays it off, and that any refrain or label recurs with purpose and lands at the close. Flag beats that wander, threads that don't connect, and promises left unpaid.


## Output → `explore/2026-08-02-script-loop-graph/_runs/v-ai-golden/scriptgen/reviews/review-02.pairwise.json` (a single JSON object)
```json
{
  "verdict": "better|worse|mixed|same",
  "vs_draft": "draft-01",
  "confidence": "high|med|low",
  "why": "<2-4 sentences: the decisive reason, naming what changed>",
  "gains":      [{"beat": "<name>", "what": "<what improved, quote the change>"}],
  "regressions":[{"beat": "<name>", "what": "<what got worse>", "severity": "high|med|low"}],
  "blockers":   [{"beat": "<name>", "dim": "<rubric dim-id>", "severity": "high|med|low",
                   "quote": "<exact phrase>", "problem": "<one line>", "fix": "<concrete change>"}]
}
```

Rules that decide whether this is useful:
- **`blockers` is capped at 6** — the things that would genuinely stop you shipping,
  strongest first. Not everything you noticed. A pass that returns twenty items produces a
  revision that rewrites the script, and a rewrite is how the last one got worse.
- **`regressions` is the highest-value field.** Something the revision broke is worth more than
  anything it merely failed to improve, and it is the one thing an isolated read cannot see.
- **`verdict` is about the CHANGE.** "worse" means the previous draft was better to read — say so
  plainly; that verdict is allowed and acting on it is cheap.
- Quote the draft. A critique that cannot be located cannot be applied.
- Do **not** count anything. No scores, no totals, no "N issues found".

## Provenance — add your two fields to `explore/2026-08-02-script-loop-graph/_runs/v-ai-golden/scriptgen/reviews/review-02.provenance.json`
That file already exists and records the brief, rubric, archetype and commit. Fill in ONLY
`"model"` (the model you are running as) and `"session"` (your agent name). Leave everything else
exactly as you found it.

## FINAL STEP — signal completion
After `explore/2026-08-02-script-loop-graph/_runs/v-ai-golden/scriptgen/reviews/review-02.pairwise.json` is written, create `explore/2026-08-02-script-loop-graph/_runs/v-ai-golden/scriptgen/.runs/pairwise-02.done` containing one line
naming your verdict. The pipeline waits on this file.

STOP after that. Do not touch any draft.
