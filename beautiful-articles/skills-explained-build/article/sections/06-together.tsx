import { Section, Subsection, Aside, Quote, CodeBlock, Raw } from "reacticle";
import { CompareCards, StepFlow } from "../figures";

// Section 06 — How they work together  (one Section per file)
// Prose-first; a CompareCards figure for the comparison (6.1) and a StepFlow
// "activation flow" of all five blocks firing together (6.2, Step 5).

export function SectionTogether() {
  return (
    <Section index="06" title="How they work together">
      <p>
        The real power emerges when you combine these building blocks. Each serves a
        distinct purpose, and together they create sophisticated agentic workflows. So
        far we've met them one at a time — now let's see what happens when they all show
        up to the same job.
      </p>

      <Subsection index="6.1" title="Comparison: choosing the right tool">
        <p>
          Before assembling them, it helps to keep the five blocks side by side. Notice
          how they differ on two axes that matter most: how long they stick around, and
          what kind of work they're built for.
        </p>

        <Raw title="Five blocks, side by side — how long each persists, and what it's built for">
          <CompareCards
            items={[
              {
                name: "Prompts",
                tag: "Ephemeral · one conversation",
                fields: [
                  { label: "What it is", value: "Natural-language instructions in conversation" },
                  { label: "Reach for it when", value: "One-off requests, immediate context, conversational refinement" },
                ],
              },
              {
                name: "Skills",
                tag: "Persistent · portable",
                fields: [
                  { label: "What it is", value: "Folders of instructions / scripts loaded on demand" },
                  { label: "Reach for it when", value: "Repeatable procedures and expertise — the “how to do something”" },
                ],
              },
              {
                name: "Projects",
                tag: "Persistent · within the project",
                fields: [
                  { label: "What it is", value: "Self-contained workspace with a knowledge base" },
                  { label: "Reach for it when", value: "Background knowledge that should inform every conversation — the “what to know”" },
                ],
              },
              {
                name: "Subagents",
                tag: "Purpose-built · reusable",
                fields: [
                  { label: "What it is", value: "Independent assistants with their own context + tools" },
                  { label: "Reach for it when", value: "Specialized independent tasks with tool restriction + context isolation" },
                ],
              },
              {
                name: "MCP",
                tag: "Persistent · live connection",
                fields: [
                  { label: "What it is", value: "Open protocol connecting Claude to external systems" },
                  { label: "Reach for it when", value: "Accessing external data and tools — connectivity" },
                ],
              },
            ]}
          />
        </Raw>
      </Subsection>

      <Subsection index="6.2" title="Example: a research agent">
        <p>
          Let's build a comprehensive research agent that combines multiple building
          blocks. This example shows how to assemble and activate an agent for
          competitive analysis.
        </p>

        <p>
          <strong>Step 1 · Set up your Project.</strong> Create a &ldquo;Competitive
          Intelligence&rdquo; project and upload the raw material your agent will reason
          over:
        </p>
        <ul>
          <li>Industry reports and market analyses</li>
          <li>Competitor product documentation</li>
          <li>Customer feedback from your CRM</li>
          <li>Previous research summaries</li>
        </ul>
        <p>Add project instructions:</p>
        <Quote source="Project instructions">
          Analyze competitors through the lens of our product strategy. Focus on
          differentiation opportunities and emerging market trends. Present findings with
          specific evidence and actionable recommendations.
        </Quote>

        <p>
          <strong>Step 2 · Connect data sources via MCP.</strong> Wire the project to the
          live systems where your real information lives:
        </p>
        <ul>
          <li>Google Drive (shared research documents)</li>
          <li>GitHub (competitor open-source repositories)</li>
          <li>Web search (real-time market information)</li>
        </ul>

        <p>
          <strong>Step 3 · Create specialized Skills.</strong> Create a
          &ldquo;competitive-analysis&rdquo; skill that teaches Claude exactly how to
          navigate your knowledge base:
        </p>
        <CodeBlock
          language="text"
          title="competitive-analysis Skill"
          code={`# My Company GDrive Navigation Skill

## Overview
Optimized search and retrieval strategy for Meridian Tech's Google Drive structure.
Use this skill to efficiently locate internal documents, research, and strategic materials.

## Drive Organization
**Top-level structure:**
- \`/Strategy & Planning/\` - OKRs, quarterly plans, board decks
- \`/Product/\` - PRDs, roadmaps, technical specs
- \`/Research/\` - Market research, competitive intel, user studies
- \`/Sales & Marketing/\` - Case studies, pitch decks, campaign materials
- \`/Customer Success/\` - Implementation guides, success metrics
- \`/Company Ops/\` - Policies, org charts, team directories

**Naming conventions:**
- Format: \`YYYY-MM-DD_DocumentName_vX\`
- Final versions marked with \`_FINAL\`
- Drafts include \`_DRAFT\` or \`_WIP\`

## Search Best Practices
1. **Start broad, then filter** - Use folder context + keywords
2. **Target document owners** - Sales materials from Sales/, not root
3. **Check recency** - Prioritize documents from last 6 months for current strategy
4. **Look for "source of truth"** - Files with \`_FINAL\`, \`_APPROVED\`, or in \`/Archives/Official/\`

## Research Agent Workflow
1. Identify topic category (product, market, customer)
2. Search relevant folder with targeted keywords
3. Retrieve 3-5 most recent/relevant documents
4. Cross-reference with \`/Strategy & Planning/\` for context
5. Cite sources with file names and dates`}
        />

        <p>
          <strong>Step 4 · Configure subagents (Claude Code/SDK only).</strong> Create
          specialized subagents so distinct kinds of analysis run in their own context
          with their own tools:
        </p>
        <CodeBlock
          language="text"
          title="market-researcher subagent"
          code={`name: market-researcher
description: Research market trends, industry reports, and competitive landscape data.
  Use proactively for competitive analysis.
tools: Read, Grep, Web-search
---
You are a market research analyst specializing in competitive intelligence.
When researching:
1. Identify authoritative sources (Gartner, Forrester, industry reports)
2. Gather quantitative data (market share, growth rates, funding)
3. Analyze qualitative insights (analyst opinions, customer reviews)
4. Synthesize trends and patterns
Present findings with citations and confidence levels.`}
        />
        <CodeBlock
          language="text"
          title="technical-analyst subagent"
          code={`name: technical-analyst
description: Analyze technical architecture, implementation approaches, and engineering
  decisions. Use for technical competitive analysis.
tools: Read, Bash, Grep
---
You are a technical architect analyzing competitor technology choices.
When analyzing:
1. Review public repositories and technical documentation
2. Assess architecture patterns and technology stack
3. Evaluate scalability and performance approaches
4. Identify technical strengths and limitations
Focus on actionable technical insights that inform our product decisions.`}
        />

        <p>
          <strong>Step 5 · Activate your research agent.</strong> Now when you ask
          Claude: &ldquo;Analyze how our top three competitors are positioning their new
          AI features and identify gaps we can exploit&rdquo; — here's what happens, with
          every building block firing in concert:
        </p>

        <Raw title="Activation flow — all five building blocks firing together">
          <StepFlow
            direction="vertical"
            steps={[
              {
                badge: 1,
                title: "Project context loads",
                body: "Claude accesses your uploaded research documents and follows project instructions",
              },
              {
                badge: 2,
                title: "MCP connections activate",
                body: "Claude searches your Google Drive for recent competitor briefs and pulls GitHub data",
              },
              {
                badge: 3,
                title: "Skills engage",
                body: "The competitive-analysis Skill provides the analytical framework",
              },
              {
                badge: 4,
                title: "Subagents execute (in Claude Code)",
                body: "The market-researcher gathers industry data while the technical-analyst reviews technical implementations",
              },
              {
                badge: 5,
                title: "Prompts refine",
                body: "You provide conversational guidance: “Focus especially on enterprise customers in healthcare”",
              },
            ]}
            terminal={{
              title: "One comprehensive competitive analysis",
              body: "All five blocks firing together — multiple data sources, one framework, specialized expertise, context held throughout.",
            }}
          />
        </Raw>

        <Aside tone="capability" label="The result">
          A comprehensive competitive analysis that draws from multiple data sources,
          follows your analytical framework, leverages specialized expertise, and
          maintains context throughout your research project.
        </Aside>
      </Subsection>
    </Section>
  );
}
