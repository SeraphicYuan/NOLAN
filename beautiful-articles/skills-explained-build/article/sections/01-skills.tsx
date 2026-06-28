import { Section, Aside, Raw } from "reacticle";
import { StepFlow } from "../figures";

// Section 01 — What are Skills?  Prose is the body; the progressive-disclosure
// visual is the reusable StepFlow figure (data only — no hand-written layout).

export function SectionSkills() {
  return (
    <Section index="01" title="What are Skills?">
      <p>
        Start with the building blocks themselves. Claude's agentic ecosystem is made of
        five pieces — Skills, prompts, Projects, subagents, and MCP — and the fastest way
        to use them well is to understand what each one is for. We'll take them one at a
        time, beginning with the one everyone's asking about.
      </p>

      <p>
        <strong>Skills</strong> are folders containing instructions, scripts, and resources
        that Claude discovers and loads dynamically when they're relevant to a task. Think
        of them as specialized training manuals that give Claude expertise in specific
        domains — from working with Excel spreadsheets to following your organization's
        brand guidelines.
      </p>

      <p>
        <strong>How Skills work.</strong> When Claude encounters a task, it scans the
        available Skills for relevant matches. The trick that keeps this efficient is
        <strong>progressive disclosure</strong>: just the metadata loads first (around 100
        tokens), then the full instructions (under 5k tokens) only when a Skill actually
        matches, and any bundled scripts or files later still — pulled in step by step, on
        demand.
      </p>

      <Raw title="Progressive disclosure — Claude loads only what it needs, when it needs it">
        <StepFlow
          steps={[
            { badge: "1", title: "Metadata", tag: "~100 tokens", body: "Always scanned, for every task" },
            { badge: "2", title: "Full instructions", tag: "< 5k tokens", body: "Loads when the Skill is relevant" },
            { badge: "3", title: "Scripts & files", tag: "as needed", body: "Load only when actually required" },
          ]}
        />
      </Raw>

      <p>
        This architecture means you can have many Skills available without overwhelming
        Claude's context window — it accesses exactly what it needs, exactly when it needs
        it.
      </p>

      <p>
        <strong>When to use Skills.</strong> Reach for a Skill when you need Claude to
        perform specialized tasks consistently and efficiently. They're ideal for:
      </p>
      <ul>
        <li>
          <strong>Organizational workflows</strong> — brand guidelines, compliance
          procedures, document templates.
        </li>
        <li>
          <strong>Domain expertise</strong> — Excel formulas, PDF manipulation, data
          analysis.
        </li>
        <li>
          <strong>Personal preferences</strong> — note-taking systems, coding patterns,
          research methods.
        </li>
      </ul>

      <Aside tone="note" label="Example">
        Create a brand-guidelines Skill that includes your company's color palette,
        typography rules, and layout specifications. When Claude creates presentations or
        documents, it applies these standards automatically — you never have to re-explain
        them.
      </Aside>
    </Section>
  );
}
