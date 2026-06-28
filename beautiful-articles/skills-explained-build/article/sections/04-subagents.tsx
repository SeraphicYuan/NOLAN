import { Section, Aside, Raw } from "reacticle";
import { CardGrid, FRow, Chip } from "../figures";

// Section 04 — What are subagents?  (one Section per file)
// Prose is the body; the delegation / context-isolation diagram is a reusable
// CardGrid figure (one card per subagent, with tool-permission chips).

export function SectionSubagents() {
  return (
    <Section index="04" title="What are subagents?">
      <p>
        Sometimes you don't want Claude to do everything in one long conversation. You want a
        focused helper that handles one job, with its own workspace and its own rules, then
        hands back a clean result. That's a subagent.
      </p>

      <p>
        <strong>Subagents</strong> are specialized AI assistants with their own context
        windows, custom system prompts, and specific tool permissions. Available in Claude
        Code and the Claude Agent SDK, they handle discrete tasks independently and return
        results to the main agent — the one you're actually talking to.
      </p>

      <p>
        <strong>How subagents work.</strong> Each subagent operates with its own
          configuration. You define what it does, how it approaches problems, and which tools
          it can access. From there, Claude automatically delegates tasks to the appropriate
          subagent based on its description — or you can explicitly request a specific one.
        </p>

        <Raw title="Delegation with isolation — each subagent gets its own context window and its own tool permissions">
          <CardGrid
            lead={
              <FRow justify="center">
                <Chip tone="strong">Main agent · delegates ↓</Chip>
              </FRow>
            }
            cards={[
              {
                title: "code-reviewer",
                subtitle: "Reviews changes for quality & security",
                footnote: "own context window",
                chips: [
                  { label: "Read" },
                  { label: "Grep" },
                  { label: "Glob" },
                  { label: "Write", on: false },
                  { label: "Edit", on: false },
                ],
              },
              {
                title: "test-writer",
                subtitle: "Generates tests for new code",
                footnote: "own context window",
                chips: [
                  { label: "Read" },
                  { label: "Glob" },
                  { label: "Write" },
                ],
              },
              {
                title: "security-auditor",
                subtitle: "Scans for vulnerabilities",
                footnote: "own context window",
                chips: [
                  { label: "Read" },
                  { label: "Grep" },
                  { label: "Bash", on: false },
                ],
              },
            ]}
          />
        </Raw>

        <p>
          The key idea in that picture is isolation. Each subagent works in a context window
          of its own, so the specialized work it does never clutters the main conversation —
          and the limited toolset it's given keeps it on a short, safe leash.
        </p>

      <p>
        <strong>When to use subagents.</strong> Reach for one when a job is well-defined
          enough to be handed off on its own:
        </p>
        <ul>
          <li>
            <strong>Task specialization</strong> — code review, test generation, security
            audits.
          </li>
          <li>
            <strong>Context management</strong> — keep the main conversation focused while
            offloading specialized work.
          </li>
          <li>
            <strong>Parallel processing</strong> — multiple subagents can work on different
            aspects simultaneously.
          </li>
          <li>
            <strong>Tool restriction</strong> — limit specific subagents to safe operations,
            such as read-only access.
          </li>
        </ul>

        <Aside tone="note" label="Example">
          Create a code-reviewer subagent with access to Read, Grep, and Glob tools — but not
          Write or Edit. When you modify code, Claude automatically delegates to this subagent
          for quality and security review, without risking unintended code changes.
        </Aside>

      <Aside tone="principle" label="When to use a Skill instead">
        If multiple agents or conversations need the same expertise — like security review
        procedures or data analysis methods — create a Skill rather than building that
        knowledge into individual subagents. Skills are portable and reusable, while subagents
        are purpose-built for specific workflows. Use Skills to teach expertise that any agent
        can apply; use subagents when you need independent task execution with specific tool
        permissions and context isolation.
      </Aside>
    </Section>
  );
}
