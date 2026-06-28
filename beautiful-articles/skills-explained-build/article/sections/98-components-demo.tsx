// Validation demo for the new article-native components (Tier-0, no heavy deps).
import { Section, Raw } from "reacticle";
import { Timeline, Stat, PullQuote, Term, Footnote } from "../figures";

export function SectionComponentsDemo() {
  return (
    <Section index="98" title="New article components">
      <p>
        Inline glossary and footnotes: a{" "}
        <Term def="A folder of instructions, scripts, and resources Claude loads on demand.">
          Skill
        </Term>{" "}
        is loaded via progressive disclosure
        <Footnote marker="1">Metadata (~100 tokens) first, full instructions only on match.</Footnote>{" "}
        — hover the dotted word or the marker.
      </p>

      <PullQuote cite="The bottom line">
        If you keep typing the same instructions, turn them into a Skill.
      </PullQuote>

      <Raw title="Stat — big-number callouts">
        <Stat
          items={[
            { value: "~100", label: "tokens", sub: "metadata, always scanned" },
            { value: "<5k", label: "tokens", sub: "full instructions, on match" },
            { value: "10×", label: "RAG capacity", delta: { dir: "up", text: "vs base" } },
          ]}
        />
      </Raw>

      <Raw title="Timeline — sequence of events">
        <Timeline
          events={[
            { date: "Step 1", title: "Set up a Project", body: "Upload research + instructions." },
            { date: "Step 2", title: "Connect MCP", body: "Drive, GitHub, web search." },
            { date: "Step 3", title: "Add Skills + subagents", body: "Framework + specialized workers." },
            { date: "Step 4", title: "Activate", body: "All five blocks fire together." },
          ]}
        />
      </Raw>
    </Section>
  );
}
