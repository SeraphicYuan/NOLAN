# Plan

## Brief

- 目标读者：Claude developers / power users deciding **which agentic building block to reach for** — people who've heard of Skills, Projects, MCP, subagents but aren't sure how they relate.
- 目标语言：English (follows source; no translation).
- 文章类型：`explainer` (recommended) — the article self-describes as "this guide breaks down each building block, explains when to use what."
- 信息保留比例：**~95–100%** (explainer standard is 80%, but bumped because the source is already lean and reference-grade — every building block, all code examples, the worked research-agent workflow, and the FAQ carry distinct value; only pure nav/promo links are cut). **Non-standard combo** → main agent keeps full content, does NOT apply explainer's default 80% trimming.
- 必须保留的信息：
  - All 5 building-block definitions (Skills / prompts / Projects / subagents / MCP) with their "how it works" + "when to use" + "when to use a Skill instead" + example.
  - All code blocks verbatim: security-review prompt, GDrive-navigation Skill, market-researcher + technical-analyst subagent configs.
  - The 5-step "research agent" worked example + "here's what happens" activation list.
  - The comparison table (reconstructed — see extraction-notes.md).
  - The "Common questions" FAQ (5 Q&As) and "Getting started" CTAs.
- 可删减的信息：inline promotional "Learn more / check out our library" navigation links (redundant, non-substantive); footer newsletter + related-posts (not article body).
- 语气：clear, friendly-professional product explainer (Anthropic dev-blog voice).
- 主要观点 (1–3 takeaways):
  1. Each building block has ONE distinct job (ephemeral instruction / portable how-to / persistent what / independent worker / connectivity).
  2. The recurring decision rule: "if you type the same thing repeatedly → make it a Skill."
  3. Real power = composing them (the research-agent example).
- 阅读目标：reader can pick the right tool for a given need and knows how to combine them.
- 版式宽度：`regular` (prose-first explainer; the one comparison table + code blocks fit comfortably).
- TOC：开 (on) — multi-section guide benefits from nav.
- 配图策略：`none` — conceptual article; all visuals carried by themed Raw blocks (no external/AI images).
- 封面：开 (on). Concept: template **D (geometric collage)** — the 5 building blocks as 5 labeled tokens orbiting/feeding a central "Claude" node, theme-colored, with the title. Conveys "distinct parts, one system" at a glance. Finalized in Phase 4.

## Outline

- Hero：article title + subtitle ("where do they fit in the Claude stack?") + meta (Agents · Mar 5 2026 · 5 min · claude.com).
- Lead：1–2 sentence framing — knowing which tool to reach for transforms how you work with Claude.
- Summary：a compact "at-a-glance" Raw block — one-line identity for each of the 5 blocks (the TL;DR).

### Sections

1. `01` Understanding your agentic building blocks — Skills
   - 保留信息：full "What are Skills?" + how it works (progressive disclosure) + when to use + example.
   - 组件：Section prose + CodeBlock(no) + Raw: **progressive-disclosure diagram** (metadata ~100 tok → instructions <5k → scripts on demand).
   - Raw：yes — serves the "progressive disclosure" mechanism.
2. `02` Prompts
   - 保留信息：definition (ephemeral/reactive) + when to use bullets + security-review code example + "when to use a Skill instead".
   - 组件：Section prose + CodeBlock (security-review prompt) + Callout ("pro-tip").
   - Raw：light — a small "ephemeral vs persistent" marker.
3. `03` Projects
   - 保留信息：definition + how it works (200K + RAG 10x) + when to use + example + "Skill instead".
   - 组件：Section prose + Callout (RAG fact) + Raw optional.
4. `04` Subagents
   - 保留信息：definition + how it works + when to use + code example + "Skill instead".
   - 组件：Section prose + CodeBlock (code-reviewer example) + Raw light.
5. `05` MCP
   - 保留信息：definition + how it works (client/server) + when to use + example + "Skill instead".
   - 组件：Section prose + Raw: **MCP client/server connection diagram**.
6. `06` How they work together — comparison + research-agent workflow
   - 保留信息：intro + **comparison table** (5 blocks) + full 5-step research-agent example + activation list + result.
   - 组件：Section prose + **Raw comparison table/cards** + CodeBlock×3 (skill + 2 subagent configs) + Raw: **5-step workflow / activation flow diagram**.
   - Raw：yes — the comparison matrix and the workflow flow are the visual centerpieces.
7. `07` Common questions (FAQ)
   - 保留信息：all 5 Q&As (how Skills work; Skills vs subagents/prompts/Projects; can subagents use Skills).
   - 组件：Section + Raw: **accordion or Q/A card list**; include the "Projects say what / Skills say how" key-difference callout.
8. `08` Getting started
   - 保留信息：3 audience tracks (Claude.ai / API / Claude Code) with their steps.
   - 组件：Section + Raw: **3-column getting-started cards**.
- 结尾方式：short closing + colophon (scaffold-provided, kept).

## Theme

- 选定主题：`freddie` (recommended) — warm, friendly, professional-but-not-stiff; `bestFor` explicitly includes explainer / product-intro / faq, which matches this article's approachable product-guide voice. Alternatives: `vignelli` (cleaner, systematic Swiss docs — great for the comparison/decision content) or `tufte` (evidence/data-ink restraint).
- 理由：the source is a friendly Anthropic product explainer with comparison + code; freddie's warm-yet-precise personality fits better than a cold spec theme while still handling tables/code well.
- 与源材料的冲突：none significant. (Risk note: must confirm `freddie` ships a runtime theme in the installed `reacticle` at scaffold time; if not, fall back to nearest supported — `press` for warmth or `tufte`/`vignelli` for structure — and report.)
- 当前信息密度下的表现建议：~95–100% retention → prose-first, with Raw used to light up the 4–5 key mechanisms (progressive disclosure, MCP client/server, comparison matrix, workflow flow). Don't over-decorate; every Raw block serves a specific paragraph.

## Assets

- 策略：`none`.
- 一句话说明：conceptual content with no essential photography; all visual explanation is carried by themed Raw blocks (diagrams, comparison matrix, cards) using `--ra-*` tokens. No external or AI-generated images.
