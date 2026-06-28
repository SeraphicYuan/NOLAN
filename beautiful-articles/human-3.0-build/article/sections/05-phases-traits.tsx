import { Section, Raw } from "reacticle";
import { StepFlow, VersusPair, PullQuote } from "../figures";

// Section 05 — Phases (vertical development) and traits (horizontal development).
// Prose-first; one StepFlow, one PullQuote, one VersusPair.
export function SectionPhasesTraits() {
  return (
    <Section index="05" title="Phases and traits">
      <p>
        Within each level are three phases you must pass through to reach the next. Phases are
        <strong> vertical development</strong> — the movement of climbing up a level, or
        regressing back down one.
      </p>

      <Raw title="The three phases (vertical development)">
        <StepFlow
          direction="horizontal"
          steps={[
            {
              badge: "1",
              title: "Dissonance",
              body: "You've tasted your current stage and grow tired of it — but you're unsure what comes next.",
            },
            {
              badge: "2",
              title: "Uncertainty",
              body: "Aware of your distaste, you take an uncertain step into the unknown and open up to new knowledge and skill.",
            },
            {
              badge: "3",
              title: "Discovery",
              body: "Like navigating a map, you find the education, tools, and insights that let you reach the next level.",
            },
          ]}
        />
      </Raw>

      <p>
        You can map any area of life by appending the phase to the level. <strong>Vocation 2.1</strong>,
        for instance, means Level 2 (the Individualist), Phase 1: you've nearly exhausted that stage
        and are about to step toward Level 3 — perhaps realizing you climbed the wrong career ladder.
      </p>

      <Raw title="">
        <PullQuote cite="False Transformation">
          You can feel you've advanced to a new level when you're merely imitating it without the
          required trait development. This self-deception traps people — often when you develop in
          one domain and assume you've advanced in another.
        </PullQuote>
      </Raw>

      <p>
        While phases are vertical, <strong>traits are horizontal development</strong> — the
        knowledge and skill you accumulate while navigating the unknown, until you reach the next
        phase. The two are not the same. One can be deeply knowledgeable in fitness yet, without
        practice, become the <strong>fat personal trainer</strong>: their knowledge is admirable,
        but few take them seriously. The trap of both phases and traits is the same pair —
        boredom and anxiety.
      </p>

      <Raw title="The two traps">
        <VersusPair
          left={{
            sticker: "Move too fast",
            title: "Anxiety",
            body: "Jump to a new level without the skill to do so and you become anxious and fail.",
          }}
          right={{
            sticker: "Don't move",
            title: "Boredom",
            body: "Never attempt to move up and you grow bored, resorting to comfort and distraction.",
          }}
        />
      </Raw>

      <p>
        Both lead to disorder in the mind and remove you from the unfolding flow of evolution. Your
        life may seem okay, but everything feels dull and meaningless.
      </p>
    </Section>
  );
}
