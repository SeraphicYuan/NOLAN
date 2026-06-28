import { Section, Raw, Aside } from "reacticle";
import { CardGrid } from "../figures";

// Section 06 — Channels and glitches. Prose-first; a CardGrid of Channels by
// quadrant and a warning Aside for the Glitches caveat.
const CHANNELS = [
  {
    title: "Mind",
    items: [
      "A deep meditative state (skill)",
      "A line of thought that keeps you up at night, ideas lighting up your brain (knowledge)",
    ],
  },
  {
    title: "Body",
    items: [
      "Bingeing every video on a new diet or method (knowledge)",
      "A 3-month obsession with running or lifting — more gains than ever (skill)",
    ],
  },
  {
    title: "Spirit",
    items: [
      "Mystical experiences, honeymoon phases, intimate moments",
      "A philosophy that finally clicks with your phase of life",
    ],
  },
  {
    title: "Vocation",
    items: [
      "A burst of clarity into a career change or product launch (skill)",
      "Finding the opportunity and not being able to stop learning the skills to start (knowledge)",
    ],
  },
];

export function SectionChannels() {
  return (
    <Section index="06" title="Channels and glitches">
      <p>
        When you reach the Dissonance phase of any level, you gain the ability to leverage a
        <strong> Channel</strong> — an exciting quest, a rabbit hole of knowledge or skill, the
        kind where you can't stop researching or building and time flies by. One end of a Channel
        is rooted in the knowledge trait, the other in the skill trait. A person becomes
        <strong> obsessed</strong> with learning or building, gaining experience fast and moving
        toward the next level.
      </p>

      <Raw title="Channels by quadrant">
        <CardGrid min="16rem" cards={CHANNELS} />
      </Raw>

      <p>
        To enter a Channel: reach Dissonance, use your distaste as fuel, set an aim within a
        quadrant, acquire knowledge and skill, make mistakes, refine your aim, and experiment
        until one of them sucks you in. You can tell someone is in a Channel by how excited they
        get talking about it.
      </p>

      <Aside tone="warning" label="Glitches — accelerants at real risk">
        There are tactics to force yourself into a Channel — <strong>glitches in the matrix</strong>.
        Psychedelics can force a mystical experience; PEDs accelerate fitness; an apartment you
        can't afford creates a real deadline. AI is the most recent, widely available Glitch,
        crossing every domain — it can self-develop or self-destruct you rapidly. They're high
        risk: for some they're smart, but for most — especially at Level 1 — they're death
        sentences. Max out your natural potential first so you don't get one-shotted. Knowledge
        and skill decrease the risk.
      </Aside>

      <p>
        If you feel lost, you're probably in a Dissonance phase. Stick it out, and you'll find
        your next Channel and fall back in love with life.
      </p>
    </Section>
  );
}
