# Two-Layer Orchestrator Architecture

**Date:** 2026-04-26
**Status:** Design draft — not yet implemented. Open for refinement.
**Scope:** How an agent should drive NOLAN's pipeline end-to-end for a long-form (5–20 min) video essay project, with human-in-the-loop iteration.

---

## 1. Context & Goal

NOLAN today is a parts catalog: ~25 CLI subcommands that produce a finished video when run in the right order. Running them by hand is the friction that keeps a project untouched for months. The goal of this design is to put an agent in front of the catalog so the user can:

- Hand the agent a **topic folder** (audio file + script + source library) and have it drive the pipeline to a watchable cut.
- **Review and comment** at natural checkpoints.
- Have the agent **refine on top of previous versions** rather than rebuilding from scratch on each round of feedback.

The architecture below splits "how" the agent drives the pipeline into two layers. This split is the central design decision; the rest follows from it.

---

## 2. The Two-Layer Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 2: Director                                              │
│  - Coordinates: diagnoses feedback → dispatches to specialists  │
│  - Stateless by default; --live mode for active sprints         │
│  - Holds the project as a whole, not the craft of any one stage │
└────────────────┬────────────────────────────────────────────────┘
                 │ invokes
       ┌─────────┴──────────┬──────────────────┐
       ▼                    ▼                  ▼
┌──────────────┐  ┌──────────────────┐  ┌─────────────────┐
│ Layer 1a:    │  │ Layer 1b:        │  │ (Future modules)│
│ Deterministic│  │ Specialist agents│  │                 │
│ scripts      │  │ (one-shot LLM)   │  │                 │
│ - nolan CLI  │  │ - script_to_     │  │                 │
│ - ffmpeg     │  │   scenes         │  │                 │
│ - image-gen  │  │ - clip_selector  │  │                 │
│   wrapper    │  │ - slide_designer │  │                 │
│ - transition │  │                  │  │                 │
│   picker     │  │                  │  │                 │
└──────────────┘  └──────────────────┘  └─────────────────┘
```

**Layer 1 produces ingredients. Layer 2 assembles and iterates.**

Both layers also read from shared **template databases** (`assets/templates/styles/`, `assets/templates/scene_plans/`) — semantic-search-backed catalogs of reusable creative archetypes that mirror NOLAN's existing Lottie/effects catalog pattern. See §10.

### Layer 1a — Deterministic tools

Anything mechanical. Wrapped scripts, no LLM in the loop. Cheap, fast, predictable.

### Layer 1b — Specialist module agents

Tasks that require **judgment** in a focused craft (clip selection, scene splitting, slide design). Each one is a single-purpose agent with:

- A focused system prompt (its craft, not the whole project)
- Large context (1M) for its domain reference material (library index, style guide, etc.)
- One-shot subprocess invocation by default — runs, writes outputs, exits
- Optional persistence for "tweak this one thing interactively" sprint modes

### Layer 2 — Director

The coordinator. Stateless by default (re-reads project folder each invocation), with an opt-in `--live` mode for active back-and-forth sessions. Its job is **dispatch and integrate**, not craft. It diagnoses user feedback, routes to the right specialist, and merges results back into the project state.

---

## 3. Layer Definitions

### 3.1 Layer 1a: Deterministic Tools

These are existing or thin-wrapper utilities. The Director knows about them via its system prompt; the specialists may also call them.

| Tool | Type | Purpose |
|------|------|---------|
| `nolan index` | Existing | Index a video library |
| `nolan transcribe` | Existing | Whisper transcription |
| `nolan align` | Existing | Word-level timing alignment |
| `nolan render-clips` | Existing | Render animated scenes |
| `nolan assemble` | Existing | Final FFmpeg composition |
| `nolan match-clips` | Existing | Will be **superseded** by `clip_selector` module (1b) |
| `ffmpeg`, `ffprobe` | System | Direct video manipulation |
| `generate_image()` | New thin wrapper | ComfyUI call with style-guide-injected prompt |
| `pick_transition()` | New thin wrapper | Rule-based transition picker over scene-type pairs |
| `match_style_template()` | New thin wrapper | Semantic search over style template DB; returns top-K candidates + scores |
| `match_scene_plan_template()` | New thin wrapper | Semantic search over scene-plan structure DB; returns top-K candidates + scores |
| `generate_voiceover()` | Future | TTS API wrapper (MiniMax / ElevenLabs / Chatterbox) |
| `bake_captions()` | Future | Word-level captions from Whisper output |

**Rule:** if a task can be expressed as deterministic logic with at most parameter substitution, it lives here. No LLM.

### 3.2 Layer 1b: Specialist Module Agents

The judgment-requiring tasks. Each is a separately invoked agent process.

| Module | What it decides |
|--------|-----------------|
| `script_to_scenes` | How to break a script into beats and assign visual types |
| `clip_selector` | Which library clip best fits a scene, with editorial taste |
| `slide_designer` | Layout and content of info-rich scenes (quote, stat, comparison) |

**(Future, deferred):**
| Module | What it decides |
|--------|-----------------|
| `pacing_analyzer` | Whether scene cadence is monotonous; suggests breathing/varied durations |
| `quality_scorer` | Whether a rendered scene meets quality bar; flags for human or retry |
| `tweak_loop` | Persistent sprint-mode agent for interactive iteration on a single artifact |

### 3.3 Layer 2: Director

Single agent. Knows:

- The full NOLAN CLI catalog (Layer 1a)
- Each specialist's input/output contract (Layer 1b)
- The project folder convention
- The template databases (style + scene-plan structure) and the match-then-fallback logic (§10)
- The diagnosis logic: feedback type → which specialist to invoke

Modes:

- **Default (stateless):** `nolan orchestrate <project>` — reads `.orchestrator/` state, runs one step or the next checkpointed batch, writes results, exits. Resumable from any device, any time.
- **Live (`--live`):** persistent session for active editing sprints (~30 min review-comment-iterate cadence). Disk state remains authoritative; the live session is purely a latency/working-memory accelerator. Auto-saves every step.

---

## 4. Module List with Input/Output Contracts

Each module has a sharp contract: what it reads, what it writes, what triggers it. **Modules MUST NOT write outside their declared outputs.** Conflicts are routed through the Director.

### 4.1 `script_to_scenes`

- **Layer:** 1b (specialist agent)
- **Purpose:** Break a narration script into a sequence of scenes with visual types, narration excerpts, and search hints.
- **Inputs:**
  - `script.md` — the narration script
  - `style_guide.md` — prose creative brief (voice / pacing / editorial / visual_type vocabulary for this project)
  - **Scene-plan structure template** if Director matched one (from `assets/templates/scene_plans/`); otherwise none — module invents
  - (refine mode) `scene_plan.json` previous draft + `feedback/<latest>.md`
- **Outputs:**
  - `scene_plan.json` — initial draft (no clip matches, no rendered_clip paths)
- **Trigger from Director:**
  - Initial: when `script.md` exists and `scene_plan.json` does not
  - Refine: when user feedback affects scene structure, beats, or visual type assignments
- **Refine semantics:** Preserve scene IDs and adjacent untouched scenes; only modify scenes whose content the feedback names or implies.
- **Persistence:** One-shot subprocess.

### 4.2 `clip_selector`

- **Layer:** 1b (specialist agent)
- **Purpose:** For each scene that needs library footage, pick the best clip from the indexed library and propose `clip_start`/`clip_end` with editorial reasoning.
- **Inputs:**
  - `scene_plan.json` — current scenes
  - ChromaDB / library index (read-only handle)
  - `style_guide.md`
  - (refine mode) previous selections + `feedback/<latest>.md`
- **Outputs:**
  - `scene_plan.json` — updated with `matched_clip`, `clip_start`, `clip_end`, `clip_reasoning` per applicable scene
  - `.orchestrator/modules/clip_selector/history/step_N/` snapshot
- **Trigger from Director:**
  - Initial: after `script_to_scenes` produces a draft and the library is indexed
  - Refine: when feedback names specific scenes ("scene 14 is wrong") or clip qualities ("less talking heads")
- **Refine semantics:** Re-select **only** scenes named in feedback or scenes whose preceding/following clip changed and now creates an adjacency problem (e.g., two same-shot-type clips back-to-back). Preserve unrelated selections.
- **Persistence:** One-shot subprocess.

### 4.3 `slide_designer`

- **Layer:** 1b (specialist agent)
- **Purpose:** For info-rich scenes (quote, stat, comparison, definition, etc.), produce a layout specification the renderer can consume.
- **Inputs:**
  - The single scene object from `scene_plan.json`
  - `style_guide.md`
  - Available scene templates from `src/nolan/renderer/scenes/`
  - (refine mode) previous layout spec + feedback
- **Outputs:**
  - `layout_spec` field appended/updated on the scene in `scene_plan.json`
- **Trigger from Director:**
  - Initial: when a scene's `visual_type` is in the info-scene set and no `layout_spec` exists
  - Refine: when feedback targets layout, content, or template choice
- **Refine semantics:** Modify only the named scene's layout_spec.
- **Persistence:** One-shot per scene. May be batch-invoked over multiple scenes in a single process for token efficiency.

### 4.4 `director` (Layer 2)

- **Purpose:** Coordinate end-to-end pipeline; route feedback to specialists; manage iteration history.
- **Inputs:**
  - Project folder (`projects/<topic>/`)
  - `.orchestrator/director_state.json`
  - `.orchestrator/feedback/<latest>.md` (if refining)
  - User-supplied flags (`--feedback`, `--refine`, `--live`)
- **Outputs:**
  - Dispatches to Layer 1a/1b
  - Updates `.orchestrator/director_state.json`
  - Writes `.orchestrator/history/<step>/` snapshots after each major action
  - Writes `.orchestrator/CHECKPOINT.md` when human review is required, then exits
- **First-pass template matching** (before any specialist runs on a new project):
  1. Call `match_style_template()` over project topic + script + intent. If best-match score ≥ threshold → load that template, **adapt** its prose to this topic (do not copy verbatim), record provenance. If miss → invent a `style_guide.md` from scratch and flag this as a fallback.
  2. Call `match_scene_plan_template()`. Same logic — adapt or invent.
  3. Surface both at checkpoint 1 for user approval. User can swap templates, edit prose, or accept.
- **Diagnosis logic** (lives in the system prompt): given user feedback, decide:
  - Is this a **structure** problem? → call `script_to_scenes` in refine mode
  - A **clip choice** problem? → call `clip_selector` in refine mode
  - A **layout** problem? → call `slide_designer` in refine mode
  - A **style/voice** problem (affects multiple specialists)? → edit `style_guide.md` first, then re-invoke affected specialists
  - A **mechanical** problem (timing, render artifact)? → call Layer 1a tool
  - **Ambiguous**? → ask user via CHECKPOINT.md before acting
- **Permissions:** cwd scoped to `projects/<topic>/`. Bash allowlist: `nolan *`, `ffmpeg`, `ffprobe`, `cat`, `ls`, plus path matchers under the project folder. Read-only access to `assets/templates/` for template DB lookups. No `--dangerously-skip-permissions`.

---

## 5. Shared State Conventions

```
projects/<topic>/
├── project.yaml                       # existing — metadata
├── script.md                          # narration
├── style_guide.md                     # NEW — creative brief (prose); all modules read this
├── scene_plan.json                    # current truth; modules edit in their declared lanes
├── source/                            # existing — indexed footage
├── assets/                            # existing — rendered/matched/generated
├── output/                            # existing — final video
└── .orchestrator/                     # NEW — agent state, hidden from user-facing tree
    ├── director_state.json            # iteration_count, last_step, status
    ├── instructions/
    │   ├── ORCHESTRATOR.md            # Director's system prompt + CLI catalog
    │   ├── design.md                  # initial-pass instruction template
    │   └── refine.md                  # refinement instruction template
    ├── feedback/
    │   ├── review_1.md                # user's plain-text feedback after step 1
    │   └── review_2.md
    ├── history/                       # director-level snapshots
    │   ├── step_1_initial/
    │   │   ├── scene_plan.json
    │   │   ├── reasoning.md
    │   │   └── manifest.json
    │   └── step_2_refine_1/
    └── modules/                       # per-specialist iteration history
        ├── script_to_scenes/history/step_N/
        ├── clip_selector/history/step_N/
        └── slide_designer/history/step_N/
```

**`style_guide.md`** is the load-bearing shared file. All specialists read it as natural-language context. It is **prose, not JSON**, because creative briefs are inherently genre-variable — what a documentary's style guide wants to express is shaped differently from a tech-explainer's, and a fixed JSON schema either over-constrains some genres or leaves fields meaningless for others. Module agents have 1M context windows; prose is no harder for them to read than parsed config.

The Director matches and adapts a template (see §11) on first pass, or invents one from scratch on a fallback. Either way, the user reviews and approves at checkpoint 1.

Suggested section structure (loose; adapt per project):

```markdown
# Style Guide: <Project Name>

## Voice
<Tone, vocabulary, rhetorical posture, narrator persona>

## Look
<Visual language: framing, color grade, typography, references to other works>

## Pacing
<Rhythm: average scene length, where to vary, breathing moments, section breaks>

## Editorial
<Conventions: when to use slides vs b-roll vs aerials; what to avoid>

## Visual Type Vocabulary
<Open list of valid `visual_type` values for this project — e.g., `b-roll`, `archival`,
`info-scene`, `talking-head`, `screen-recording`, `diagram`. Different topics declare
different vocabularies; no global enum.>

## Provenance
<Which template(s) this descended from, if any. e.g., "style: vox-essayist v3 / scene_plan: 5-act-doc v2">
```

Sections are mix-and-matchable: a project could descend its **Voice** section from one template and its **Look** section from another (deferred composition, see §7).

---

## 6. Key Design Decisions & Reasoning

These are the calls that shaped the architecture. Captured here so future-you (or future-me) can revisit with the original tradeoffs in view, not just the conclusion.

### 6.1 Two layers, not one big agent

**Decision:** Specialist modules + Director, not a single mega-orchestrator.

**Why:**
- Real video production has a director plus specialists. Trying to make one agent equally good at clip selection, slide layout, transition picking, and pacing is a prompt-engineering nightmare — each lane wants different reference examples and different success criteria.
- Module-level prompts can be focused and elite. Director's prompt becomes simpler (dispatch, not craft).
- 1M context earns its keep at the **module** level (clip_selector needs full library + style guide), not the director level.
- Modules are independently improvable; tests can target one module at a time.

### 6.2 Specialists are subprocesses, not persistent sessions

**Decision:** Layer 1b agents run as one-shot SDK invocations by default, not as long-lived tmux sessions.

**Why:**
- Module work is batch-shaped (run once over inputs, produce outputs, exit). Persistence buys nothing for one-shot work.
- Persistent sessions add tmux/IPC complexity, occupy memory, and are fragile across machine sleep / restart.
- Disk artifacts carry forward state between invocations cleanly.
- Exception: `tweak_loop` for interactive single-artifact iteration earns persistence — but defer building it until the others ship.

### 6.3 Director is stateless by default, `--live` is opt-in

**Decision:** The folder is the unit of truth, not a session.

**Why:**
- Long-form video iteration spans days. tmux sessions held alive for days are fragile.
- Anthropic's prompt cache TTL is 5 minutes — persistent session's cache advantage evaporates the moment the user walks away.
- Stateless re-invocation is trivially resumable from any device, any time, after any interruption.
- `--live` is correct for active 30-minute review-comment-iterate sprints, where working memory across turns matters and disk reload would feel laggy. But it must remain opt-in or the architecture calcifies around it.

### 6.4 Not every "creative" task gets an LLM

**Decision:** Be selective. Image generation, transition picking, and voiceover are deterministic wrappers, not agents.

**Why:**
- Image generation is prompt engineering + ComfyUI call. The judgment ("what should this image *be*") belongs upstream in `script_to_scenes` or the Director, not in a separate image-gen agent.
- Transition picking is rules over scene-type pairs in the 90% case. An agent here is overkill.
- Calling everything "creative" and giving each lane an LLM is the trap. Some lanes are structured execution wearing a creative-sounding name.

### 6.5 Sandboxing is enforced, not conventional

**Decision:** Director runs with `cwd=projects/<topic>/` plus a Bash allowlist. **No `--dangerously-skip-permissions`.**

**Why:**
- SPARTA's pattern (`--dangerously-skip-permissions` + instruction file says "write here") is convention-only. Works because the agent is well-behaved, but provides no real boundary.
- NOLAN orchestrator is write-heavy (renders, asset edits, scene_plan rewrites). The blast radius of a mis-targeted write is real.
- Modern Claude Agent SDK supports proper allowlists. Use them.

### 6.6 Refinement uses a separate prompt template

**Decision:** `design.md` for initial pass, `refine.md` for everything after. Not the same prompt with a "is this a refinement?" flag.

**Why (from SPARTA's iterate pattern):**
- Initial generation and refinement want different framings. Refine assumes context exists and asks "what changes, what stays."
- The decision logic ("re-run downstream stages **only if** the change affects them") lives in the prompt, because only the agent has the context to judge that.
- Default action in refine mode is **edit**, not **rebuild**. This is the difference between a tool and a creative collaborator.

### 6.7 History snapshots per module per step

**Decision:** Snapshot every module's outputs into `.orchestrator/modules/<name>/history/step_N/` after each invocation. Snapshot Director-level state separately into `.orchestrator/history/`.

**Why:**
- Free version control for rollback ("go back to clip_selector step 2").
- The refine prompt can load previous reasoning to seed continuity.
- Disk is cheap; debugging a regression six iterations in is not.

### 6.8 Style guide is prose markdown, not JSON

**Decision:** `style_guide.md` instead of `style_guide.json`.

**Why:**
- Creative briefs are inherently genre-variable. A documentary's brief and a tech-explainer's brief want different vocabularies — JSON forces premature universality.
- Module agents have 1M context windows. Prose is no harder for them to read than parsed config.
- Lets templates compose partially (e.g. "Voice section from template A + Look section from template B") without schema gymnastics.
- Trade-off: harder to validate programmatically. Acceptable because the consumers are LLMs, not code.

### 6.9 Template-first, fallback to LLM invention

**Decision:** Maintain template databases for styles and scene-plan structures (see §11). On a new project, the Director matches first; falls back to LLM invention only when no template clears the threshold.

**Why:**
- Mirrors NOLAN's existing pattern (Lottie catalog, scene templates, effects library) one level up the stack — same idiom, applied to creative archetypes.
- Curated, iteratively-refined templates outperform one-shot LLM invention. Quality compounds across projects.
- Library grows organically via a promotion loop — successful one-off inventions can be promoted to templates after a project ships.
- The existing `video_analysis/` workflow (analyze reference video → extract techniques → promote to NOLAN) is already the upstream pipeline; this just routes its output to a new destination.
- Fallback is never silent: misses are surfaced explicitly, with the option to promote the result later.

---

## 7. Open Questions / To Refine

These are real gaps in the design that need decisions before or during build:

1. **Style guide source.** Resolved direction: Director matches a style template first; if no match clears threshold, invents one. Either way, user reviews at checkpoint 1. Open: can the user pre-pick a template by ID before running (e.g., `nolan orchestrate venezuela --style-template vox-essayist`)? — *Lean: yes, opt-in flag.*
2. **Cross-module conflict resolution.** If `clip_selector` wants 8s for a scene and pacing implies 10s, who wins? — *Lean: Director arbitrates; specialists propose, never finalize.*
3. **Snapshot/rollback UX.** What's the user-facing command? `nolan orchestrate <topic> --rollback clip_selector:2`? — *Defer.*
4. **Concurrency.** Can `clip_selector` and `slide_designer` run in parallel during initial pass? They touch different scenes / different fields. — *Yes, design contracts so they can.*
5. **Token budget.** Each module call burns tokens. Per-iteration cap? Daily cap? — *Add `max_tokens_per_step` to director_state.json. Warn at 80%, halt at 100%.*
6. **Feedback parsing.** Director needs to map free-text feedback ("punchier intro") to (module, scope) pairs. How structured does this need to be? — *Start with LLM diagnosis. If unreliable, add a structured `--feedback-target` flag.*
7. **Failure recovery.** A module crashes mid-run. Director resumes with partial outputs? Discards? — *Discard partial outputs from the failing module's last step folder; Director retries once, then surfaces to user.*
8. **`tweak_loop` design.** When is persistence justified within a module? Probably for image regeneration ("tweak this image until it looks right") and clip trimming ("nudge the in-point earlier"). Defer until first three modules ship.
9. **Where does `pacing_analyzer` go?** It's a quality check, not an ingredient producer. Maybe it's a Director sub-call before checkpoints rather than a Layer 1b module. — *Defer.*
10. **Existing `nolan match-clips` lifecycle.** It overlaps with `clip_selector`. Plan to deprecate after `clip_selector` ships, or keep as the deterministic fallback when no LLM is desired? — *Lean: keep as fallback, surface via `--no-agent` flag.*
11. **Template match threshold.** What similarity score counts as "good enough" to adapt vs. fall back to invention? — *Defer; start at 0.6 and tune from real usage. Surface the score to the user at checkpoint 1 either way so they can override.*
12. **Promotion UX.** When/how does the user get prompted to promote a successful one-off style or scene_plan into the database? — *Lean: at project sign-off, Director surfaces "this style was invented — save to library?" with a name suggestion.*
13. **Initial library seeding.** Bulk-author a starter library, or grow purely from real projects? — *Lean: grow organically. Seed with 1–2 templates extracted from existing projects (Venezuela first); avoid speculative archetypes.*
14. **Template composition.** Can a project mix sections from multiple templates (e.g., Voice from template A + Look from template B)? — *Defer to v2. Single-template selection in v1.*
15. **Template versioning.** When a template is refined based on derivative-project feedback, are old projects re-derived against the new version? — *No: provenance records the version used; templates are immutable once published. Refining = publishing a new version (`vox-essayist v4`).*

---

## 8. What's Explicitly NOT Being Built (Yet)

Avoid scope creep. These are **out of scope** for the first orchestrator build:

- TTS / voiceover generation (in NOLAN backlog separately)
- Burnt-in captions (separate feature)
- Music bed / SFX layer (separate feature)
- Pacing analyzer module (defer to second pass)
- Quality scorer module (defer; depends on `quality/` package maturing)
- `tweak_loop` interactive sprint-mode module (defer)
- Multi-project parallelism
- Web UI for the Director (CLI-only first)

The point of the first orchestrator is to get a single Venezuela-style project end-to-end: hand the agent a topic folder with audio + script + library, get a watchable cut, iterate on feedback, ship. Everything not on that critical path waits.

---

## 9. Build Order (Suggested)

1. **`style_guide.md` format + one example** — prose template, derived from the existing Venezuela project.
2. **Project folder convention + `.orchestrator/` skeleton** — directory layout, state file shapes.
3. **Template DB plumbing** — `assets/templates/styles/` and `assets/templates/scene_plans/` directories, ChromaDB index following the `template_catalog.py` pattern, `match_style_template()` and `match_scene_plan_template()` Layer 1a wrappers. Seed with **one** style template and **one** scene-plan template extracted from Venezuela. No bulk authoring.
4. **Director skeleton (no specialists yet)** — runs Layer 1a tools end-to-end including template match → adapt → checkpoint flow. No LLM judgment in the modules yet, just a smarter `nolan process` that handles template lookup, sandboxing, and the iteration loop.
5. **`clip_selector` module** — the highest-leverage specialist. The thing that hurts most to do by hand.
6. **`script_to_scenes` module** — replaces the existing `nolan design` for agent-driven flows.
7. **`slide_designer` module.**
8. **`refine.md` flow** — wire up the iteration loop end-to-end.
9. **Promotion loop** — at project sign-off, surface invented style/scene_plan for promotion to the template DB.
10. **`--live` mode.**

Steps 1–4 prove the architecture before any specialist is built. If the orchestration loop (with template match + checkpoint + resume) doesn't work without LLM judgment, adding LLM judgment won't save it.

---

## 10. Template Databases

Two parallel libraries of reusable creative archetypes, mirroring NOLAN's existing template-catalog pattern (`template_catalog.py` for Lottie) one level up the stack. Both are semantic-search-backed (ChromaDB), grow organically via a promotion loop, and fall back cleanly to LLM invention on miss.

### 10.1 What lives in each database

**Style templates** — `assets/templates/styles/`
Each entry is a directory with prose plus metadata:

```
assets/templates/styles/
├── vox-essayist-v3/
│   ├── template.md         # prose (Voice / Look / Pacing / Editorial / Visual Type Vocab sections)
│   ├── meta.json           # match metadata
│   └── examples/           # optional: links to projects descended from this template
└── kurzgesagt-look-v2/
```

**Scene-plan structure templates** — `assets/templates/scene_plans/`
Each entry describes a narrative shape — beat counts, section purposes, pacing arc — not specific content:

```
assets/templates/scene_plans/
├── 5-act-doc-v2/
│   ├── template.md         # prose description of beat structure
│   ├── skeleton.json       # structured beat outline (open visual_types, open content)
│   └── meta.json
└── problem-solution-cta-v1/
```

`meta.json` is the only uniform contract — it powers the match step:

```json
{
  "id": "vox-essayist-v3",
  "kind": "style",                  // "style" or "scene_plan"
  "version": 3,
  "name": "Vox-style essayist",
  "genres": ["explainer", "current-events"],
  "duration_range": [300, 1200],    // seconds, soft hint for filtering
  "tags": ["narrative-voiceover", "archival-heavy", "graphic-overlay"],
  "summary": "Conversational-but-rigorous narration over heavy graphic overlay...",
  "provenance": {
    "derived_from_project": "venezuela-v1",
    "promoted_at": "2026-05-12"
  }
}
```

### 10.2 Match mechanism

Two-stage, mirroring `clip_selector`:

1. **Semantic search.** Embed the project's topic + script summary + intent. Query the relevant template index. Return top-K candidates with similarity scores.
2. **Hard filters.** Drop candidates outside the project's duration range or declared genre.
3. **LLM final pick.** Director reads the top survivors' `template.md` prose and reasons about fit. Returns choice + adaptation plan + confidence.

Threshold for "above match": configurable, default 0.6 on combined semantic+LLM score. Below threshold → fallback.

### 10.3 Adaptation, not copying

A matched template is a **starting point**, never copied verbatim. The Director's adaptation step:

1. Reads the template's `template.md`.
2. Reads the project's script + topic.
3. Generates a fresh `style_guide.md` that respects the template's spirit but specializes vocabulary, examples, and constraints to this topic.
4. Records provenance in the new file's "Provenance" section.

This is the difference between "use Vox style" producing five identical-looking videos vs. five videos that share Vox's DNA but each fit their specific topic.

### 10.4 Fallback flow

When no template clears threshold:

- Director invents a fresh `style_guide.md` from scratch (LLM generation against project topic + script).
- The fact that fallback fired is logged in `director_state.json` and surfaced at checkpoint 1:
  > *"No matching style template above 0.6 similarity — generated from scratch. Review and approve, or pick a template manually."*
- User can override and pick a template anyway, accept the invention, or edit either.

Fallback is **never silent**. Every invented style or scene_plan is a candidate for promotion later.

### 10.5 Promotion loop

At project sign-off (final assembly approved by user), Director scans for inventions:

- Was `style_guide.md` a fallback or template-derived?
- Was the scene_plan structure a fallback or template-derived?

For each invented artifact, Director prompts the user:

> *"This project's style was generated from scratch. Save it to the template library as `<suggested-name>-v1` for reuse?"*

If yes:
- Copy artifact into the appropriate template DB folder.
- Generate `meta.json` (Director suggests fields; user edits).
- Re-index the template DB.

This is how the library grows — only from artifacts that survived end-to-end production. No speculative archetypes.

### 10.6 Provenance tracking

Every project's `style_guide.md` ends with a Provenance section recording:

- Which style template (and version) it descended from, or `invented` if fallback
- Which scene_plan structure template (and version) it descended from
- The Director's adaptation summary (one short paragraph: what stayed, what changed, why)

When a template is later refined, provenance lets us see which projects used the prior version and could benefit from re-derivation (manually — no automatic re-derivation; templates are immutable per version, refining means publishing a new version).

### 10.7 Composition (deferred)

Long-term: templates compose section-wise — Voice from template A, Look from template B, Pacing from template C. The prose `style_guide.md` already supports this structurally (sections are independent). Deferred from v1 to keep match logic simple — single-template selection only at first.

---

## 11. Glossary

- **Director** — the Layer 2 agent that coordinates the pipeline.
- **Specialist** / **module agent** — a Layer 1b agent with a single craft.
- **Ingredient** — any artifact a module produces that the Director assembles into the final video.
- **Style guide** — `style_guide.md`, the per-project prose creative brief that all modules read.
- **Style template** — a reusable, parameterized creative-brief archetype stored in the style template database (e.g., "vox-essayist v3"). Adapted to a specific topic when matched.
- **Scene-plan structure template** — a reusable narrative-structure archetype stored in the scene-plan template database (e.g., "5-act-doc v2"). Specifies beat counts, section purposes, pacing shape — not specific content.
- **Template database** — semantic-search-backed catalog (ChromaDB) of style and scene-plan structure templates. Mirrors NOLAN's existing Lottie/effects catalog pattern.
- **Match-then-fallback** — the Director's first-pass logic: try template match; on miss, invent fresh via LLM and surface as a fallback.
- **Promotion** — taking a successful invented style or scene_plan from a finished project and adding it to the template database for future reuse.
- **Provenance** — record in a project's `style_guide.md` of which template(s) and version(s) it descended from.
- **Checkpoint** — a deliberate pause point where the Director writes `CHECKPOINT.md` and exits, awaiting human review.
- **Refine mode** — invocation that loads a previous version + feedback and edits in place rather than regenerating.
- **Sprint mode** (`--live`) — opt-in persistent Director session for active back-and-forth editing.
