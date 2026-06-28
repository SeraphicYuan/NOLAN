import { Section, Aside, Detail, Raw } from "reacticle";
import { VersusPair } from "../figures";

// Section 07 — Common questions  (one Section per file)
// The Detail accordion is the structure; a VersusPair figure contrasts
// "what to know" (Projects) vs "how to do" (Skills).

export function SectionFAQ() {
  return (
    <Section index="07" title="Common questions">
      <p>
        A few common questions about how the pieces fit — and where the lines between
        them actually fall.
      </p>

      <Detail summary="How do Skills work?">
        <p>
          Skills use <strong>progressive disclosure</strong> to keep Claude efficient.
          When working on tasks, Claude first scans Skill metadata — descriptions and
          summaries — to identify relevant matches. If a Skill matches, Claude loads the
          full instructions. Finally, if the Skill includes executable code or reference
          files, those load only when needed.
        </p>
        <p>
          This architecture means you can have many Skills available without overwhelming
          Claude's context window — Claude accesses exactly what it needs, when it needs
          it.
        </p>
      </Detail>

      <Detail summary="Skills vs. subagents: when to use what?">
        <p>
          Use <strong>Skills</strong> when you want capabilities that any Claude instance
          can load and use — they're like training materials that make Claude better at
          specific tasks across all conversations.
        </p>
        <p>
          Use <strong>subagents</strong> when you need complete, self-contained agents
          designed for specific purposes that handle workflows independently — like
          specialized employees with their own context and tool permissions.
        </p>
        <p>
          Use them <strong>together</strong> when you want subagents with specialized
          expertise: a code-review subagent can use Skills for language-specific best
          practices.
        </p>
      </Detail>

      <Detail summary="Skills vs. prompts: when to use what?">
        <p>
          Use <strong>prompts</strong> when you're giving one-time instructions, providing
          immediate context, or having a conversational back-and-forth — reactive and
          ephemeral.
        </p>
        <p>
          Use <strong>Skills</strong> when you have procedures or expertise you'll need
          repeatedly — proactive (Claude knows when to apply them) and persistent across
          conversations.
        </p>
        <p>
          Use them <strong>together</strong>: Skills provide foundational expertise,
          prompts provide specific context and refinement for each task.
        </p>
      </Detail>

      <Detail summary="Skills vs. Projects: when to use what?">
        <p>
          Use <strong>Projects</strong> when you need background knowledge and context that
          should inform all conversations about a specific initiative — static reference
          material that's always loaded.
        </p>
        <p>
          Use <strong>Skills</strong> when you need procedural knowledge and executable code
          that activates only when relevant — dynamic expertise that loads on-demand,
          saving your context window.
        </p>
        <p>
          Use them <strong>together</strong> when you want both persistent context and
          specialized capabilities: a "Product Development" project with specs and user
          research, combined with Skills for creating technical documentation and analyzing
          feedback.
        </p>
      </Detail>

      <Detail summary="Can subagents use Skills?">
        <p>
          Yes. In Claude Code and the Agent SDK, subagents can access and use Skills just
          like the main agent. This creates powerful combinations where specialized
          subagents leverage portable expertise — a python-developer subagent using the
          pandas-analysis Skill, while a documentation-writer subagent uses the
          technical-writing Skill.
        </p>
      </Detail>

      <Raw title="Two questions, two answers — what to know vs. how to do">
        <VersusPair
          left={{
            sticker: "Projects",
            title: "“here's what you need to know”",
            body: "A knowledge base you work within.",
          }}
          right={{
            sticker: "Skills",
            title: "“here's how to do things”",
            body: "Capabilities that work everywhere.",
          }}
        />
      </Raw>

      <Aside tone="principle" label="Projects vs. Skills, in one line">
        Projects say "here's what you need to know." Skills say "here's how to do things."
        Projects provide a knowledge base you work within; Skills provide capabilities that
        work everywhere — any conversation, any project.
      </Aside>
    </Section>
  );
}
