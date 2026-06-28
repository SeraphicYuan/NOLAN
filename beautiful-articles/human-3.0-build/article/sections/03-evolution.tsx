import { Section, Raw } from "reacticle";
import { StepFlow } from "../figures";

// Section 03 — The evolution loop. Prose-first; one StepFlow figure for the cycle.
export function SectionEvolution() {
  return (
    <Section index="03" title="The engine: an evolution loop">
      <p>
        Development is not a straight line but a repeating loop. In your own personal
        evolution you move through a cycle, and you climb a level each time you complete it —
        <strong> unless you get stuck</strong>.
      </p>

      <Raw title="The personal evolution loop">
        <StepFlow
          direction="horizontal"
          steps={[
            {
              badge: "1",
              title: "Desire",
              body: "You feel the pull to reach your potential.",
            },
            {
              badge: "2",
              title: "Step into the unknown",
              body: "You take a step and are introduced to complexity.",
            },
            {
              badge: "3",
              title: "Acquire knowledge & skill",
              body: "You solve the problems that block forward movement — or stagnate and let chaos consume you.",
            },
            {
              badge: "4",
              title: "Identity expands",
              body: "You ascend to a new level of development.",
            },
          ]}
          terminal={{
            title: "…then it repeats",
            body: "A new level, a new cycle — unless you get stuck.",
          }}
        />
      </Raw>

      <p>
        This pattern repeats across all domains and scales. Complexity always introduces new
        problems; to constrain the entropy that comes with it, an ordered structure must emerge
        through creation. That is the work of a life — and HUMAN 3.0 is a map for doing it
        <strong> on purpose</strong>.
      </p>
    </Section>
  );
}
