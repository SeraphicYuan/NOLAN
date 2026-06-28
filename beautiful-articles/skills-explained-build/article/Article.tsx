import { Article, Hero, Lead, Summary, Conclusion, Raw } from "reacticle";
import { SectionSkills } from "./sections/01-skills";
import { SectionPrompts } from "./sections/02-prompts";
import { SectionProjects } from "./sections/03-projects";
import { SectionSubagents } from "./sections/04-subagents";
import { SectionMCP } from "./sections/05-mcp";
import { SectionTogether } from "./sections/06-together";
import { SectionFAQ } from "./sections/07-faq";
import { SectionGettingStarted } from "./sections/08-getting-started";

// Article.tsx is the ASSEMBLER, owned by the main agent. It imports and orders
// Section components — it must NOT contain Section bodies inline.
// One Section = one file (article/sections/NN-*.tsx). See references/section-build.md.
//
// width="regular" + toc confirmed at Checkpoint 1 (decoupled from theme).
export function ArticleDoc() {
  return (
    <Article toc width="regular">
      <Hero
        eyebrow="Agents · Guide"
        title="Skills explained"
        subtitle="How Skills compare to prompts, Projects, MCP, and subagents — and where each fits in the Claude stack."
        meta={[
          { label: "Category", value: "Agents" },
          { label: "Product", value: "Claude apps · Claude Platform" },
          { label: "Date", value: "March 5, 2026" },
          { label: "Reading time", value: "5 min" },
          { label: "Source", value: "claude.com" },
        ]}
      />
      <Lead>
        Since introducing Skills, there's been a lot of interest in how the pieces of
        Claude's agentic ecosystem fit together. Whether you're building in Claude Code,
        on the API, or on Claude.ai, knowing which tool to reach for — and when — can
        transform how you work. This guide breaks down each building block, explains when
        to use what, and shows how to combine them.
      </Lead>

      <Summary
        title="At a glance"
        points={[
          "Prompts — ephemeral, in-the-moment instructions for one-off requests and refinement.",
          "Skills — folders of instructions Claude loads on demand; portable, reusable how-to expertise.",
          "Projects — persistent workspaces with a knowledge base; the background “what to know.”",
          "Subagents — independent assistants with their own context window and tool permissions.",
          "MCP — an open protocol that connects Claude to external data and tools.",
          "Rule of thumb: if you keep typing the same instructions, turn them into a Skill.",
        ]}
      />

      <SectionSkills />
      <SectionPrompts />
      <SectionProjects />
      <SectionSubagents />
      <SectionMCP />
      <SectionTogether />
      <SectionFAQ />
      <SectionGettingStarted />

      <Conclusion
        title="The bottom line"
        takeaways={[
          "Each block has one job: prompts for the moment, Skills for the how, Projects for the what, subagents for independent work, MCP for connectivity.",
          "If you keep typing the same instructions, turn them into a Skill.",
          "The real power is composing them — as the research-agent example shows.",
        ]}
      >
        These building blocks aren't competing choices so much as complementary parts of one
        stack. Reach for the simplest thing that fits the moment — often a prompt — and graduate
        recurring know-how into Skills, durable context into Projects, independent work into
        subagents, and live data into MCP connections. Combined, they turn Claude from a capable
        assistant into a workflow that remembers, connects, and specializes.
      </Conclusion>

      {/*
        ─── Colophon ─── (required, do not remove; keep low-contrast, centered, --ra-* only)
      */}
      <Raw title="">
        <footer
          style={{
            marginTop: "var(--ra-space-7, 3rem)",
            paddingTop: "var(--ra-space-4, 1rem)",
            borderTop: "1px solid var(--ra-color-border, currentColor)",
            color: "var(--ra-color-muted, inherit)",
            fontSize: "var(--ra-text-xs, 0.78rem)",
            textAlign: "center",
            letterSpacing: "0.02em",
            opacity: 0.85,
          }}
        >
          Made with <strong style={{ fontWeight: 600 }}>NOLAN</strong> · freddie theme
        </footer>
      </Raw>
    </Article>
  );
}
