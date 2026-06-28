import { Section, Raw } from "reacticle";
import { CardGrid } from "../figures";

// Section 08 — Getting started  (one Section per file)
// Prose intro + a reusable CardGrid of audience tracks (responsive, collapses
// to one column on narrow screens).

export function SectionGettingStarted() {
  return (
    <Section index="08" title="Getting started">
      <p>
        Ready to build with Skills? Here's how to start — pick the track that matches where
        you already work, and follow the short checklist. Each one gets you to a working
        setup in just a few steps.
      </p>

      <Raw title="Three tracks — find yours and follow the checklist">
        <CardGrid
          min="15rem"
          cards={[
            {
              sticker: "Claude.ai",
              title: "Claude.ai users",
              items: [
                "Enable Skills in Settings → Features",
                "Create your first project at claude.ai/projects",
                "Combine project knowledge with Skills for your next analysis task",
              ],
            },
            {
              sticker: "API",
              title: "API developers",
              items: [
                "Explore the Skills endpoint in the documentation",
                "Check out the skills cookbook",
              ],
            },
            {
              sticker: "Claude Code",
              title: "Claude Code users",
              items: [
                "Install Skills via plugin marketplaces",
                "Check out the skills cookbook",
              ],
            },
          ]}
        />
      </Raw>
    </Section>
  );
}
