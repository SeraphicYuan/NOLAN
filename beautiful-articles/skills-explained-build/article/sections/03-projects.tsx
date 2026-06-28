import { Section, Aside, Raw } from "reacticle";
import { ProportionBar, FStack, Sticker, Chip, FRow } from "../figures";

// Section 03 — What are Projects?  (one Section per file)
// Prose is the body; the capacity visual is a reusable ProportionBar figure.

export function SectionProjects() {
  return (
    <Section index="03" title="What are Projects?">
      <p>
        Prompts and Skills both act in the flow of a conversation. Projects work one level
        up — they shape what Claude already knows before you say a word.{" "}
        <strong>Projects</strong> are self-contained workspaces — available on all paid
        Claude plans — each with its own chat history and knowledge base. Every project
        gives you a 200K context window where you can upload documents, supply background
        context, and set custom instructions that apply to every conversation inside that
        project. Think of it as a desk where all the right material is already laid out
        before you start talking.
      </p>

      <p>
        <strong>How Projects work.</strong> Everything you upload to a project's knowledge
        base becomes available across all chats within that project, and Claude
        automatically draws on it to give more informed, relevant responses. When your
        project knowledge starts approaching the context limit, Claude seamlessly switches
        on Retrieval Augmented Generation (RAG) mode, expanding capacity by up to 10× —
        so the workspace keeps growing without you having to prune it.
      </p>

      <Raw title="A 200K window that RAG can stretch up to 10× when knowledge gets big">
        <FStack gap={5}>
          <ProportionBar
            segments={[
              {
                label: "200K context window",
                sub: "Uploaded docs · context · custom instructions",
                weight: 2,
              },
              {
                label: "RAG-expanded headroom",
                weight: 3,
                dashed: true,
                hatch: true,
                tag: "RAG · up to 10×",
              },
            ]}
            caption="Knowledge grows → Claude switches on RAG automatically"
          />
          <FStack gap={2}>
            <Sticker>One knowledge base, shared by every chat</Sticker>
            <FRow gap={2}>
              <Chip tone="default">Chat · pricing</Chip>
              <Chip tone="default">Chat · launch plan</Chip>
              <Chip tone="default">Chat · FAQ draft</Chip>
            </FRow>
          </FStack>
        </FStack>
      </Raw>

      <p>
        <strong>When to use Projects.</strong> Reach for a Project whenever a body of work
        needs the same context to follow it everywhere:
      </p>
      <ul>
        <li>
          <strong>Persistent context</strong> — background knowledge that should inform
          every conversation.
        </li>
        <li>
          <strong>Workspace organization</strong> — separate contexts for different
          initiatives, kept tidily apart.
        </li>
        <li>
          <strong>Team collaboration</strong> — shared knowledge and conversation history
          (on Team and Enterprise plans).
        </li>
        <li>
          <strong>Custom instructions</strong> — a project-specific tone, perspective, or
          approach.
        </li>
      </ul>

      <Aside tone="note" label="Example">
        Create a "Q4 Product Launch" project containing your market research, competitor
        analysis, and product specifications. Every chat in this project has access to that
        knowledge — without you needing to re-upload or re-explain the context each time.
      </Aside>

      <Aside tone="principle" label="When to use a Skill instead">
        Projects give Claude persistent context for a specific body of work — your
        company's codebase, a research initiative, an ongoing client engagement. Skills
        teach Claude how to do something. A Project might hold all the background on your
        product launch, while a Skill could teach Claude your team's writing standards or
        code-review process. If you find yourself copying the same instructions across
        multiple Projects, that's a signal to create a Skill instead.
      </Aside>
    </Section>
  );
}
