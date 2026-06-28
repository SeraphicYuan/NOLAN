import { Section, Raw } from "reacticle";
import { StepFlow, PullQuote } from "../figures";

// Section 04 — The three macro levels within each quadrant. Prose-first; a StepFlow
// for the 1.0 → 3.0 progression and a closing PullQuote.
export function SectionLevels() {
  return (
    <Section index="04" title="Three levels: 1.0 → 3.0">
      <p>
        Within each quadrant there are three macro levels of development — low (1.0), mid
        (2.0), and high (3.0) consciousness. This is adapted from developmental psychology —
        Spiral Dynamics and the 9 Stages of Ego Development — which observe that our values,
        beliefs, and worldview evolve through <strong>predictable stages over time</strong>.
      </p>

      <Raw title="The three levels of development">
        <StepFlow
          direction="horizontal"
          steps={[
            {
              badge: "1.0",
              title: "The Conformist",
              body: "Values established authority and tradition. Narrow, black-and-white thinking — believes there is one right way, often from childhood conditioning.",
            },
            {
              badge: "2.0",
              title: "The Individualist",
              body: "Rejects the norm and pursues their own goals; wants status and to be seen as valuable. Less narrow — but now believes their way is the one right way.",
            },
            {
              badge: "3.0",
              title: "The Synthesist",
              body: "Adopts multiple perspectives, connects patterns, strategizes new paths. Sees that all perspectives hold truths that can be synthesized for more holistic results.",
            },
          ]}
        />
      </Raw>

      <p>
        These descriptions take a different shape in each quadrant. A 3.0 Synthesist in
        Vocation can leverage AI to pursue their life's work, while a 1.0 Conformist believes
        AI is purely evil — for lack of knowledge and experience.
      </p>

      <Raw title="">
        <PullQuote cite="Human 3.0">
          Like a video game: Level 1 is the NPC running on a script, Level 2 is the main
          character choosing their storyline, Level 3 is the programmer who creates new games.
          You do not leave any level — you transcend and include the one before it.
        </PullQuote>
      </Raw>
    </Section>
  );
}
