import { Section, Raw } from "reacticle";
import { CardGrid, PullQuote } from "../figures";

// Section 02 — The four quadrants. Prose-first; CardGrid (2×2 quadrant) + one PullQuote.
const QUADRANTS = [
  {
    sticker: "Personal · Mental",
    title: "Mind",
    subtitle:
      "Your thoughts, emotions, beliefs, and internal world. How you interpret the world.",
  },
  {
    sticker: "Personal · Physical",
    title: "Body",
    subtitle:
      "Your behavior and appearance — how the world interprets you. Nutrition, training, habits, grooming, communication.",
  },
  {
    sticker: "Collective · Mental",
    title: "Spirit",
    subtitle:
      "Your relationship to environment, community, culture, family, reality. How you derive meaning and connection.",
  },
  {
    sticker: "Collective · Physical",
    title: "Vocation",
    subtitle:
      "Your relationship to systems and institutions — education, career, the economy. How you fit into and contribute to society.",
  },
];

export function SectionQuadrants() {
  return (
    <Section index="02" title="The four quadrants">
      <p>
        The foundation of HUMAN 3.0 is four quadrants, each representing one of the four domains
        of life. The structure is adapted from Ken Wilber's AQAL model — the four fundamental
        perspectives that together form a generalized map of all knowledge and experience.
      </p>

      <Raw title="The four quadrants — a map of every domain">
        <CardGrid min="16rem" cards={QUADRANTS} />
      </Raw>

      <p>
        Read across the grid and the logic appears: the top row is <strong>personal</strong>, the
        bottom row <strong>collective</strong>; the left column is <strong>mental</strong>, the
        right column <strong>physical</strong>. Mind and Body are how you relate to yourself;
        Spirit and Vocation are how you relate to everyone and everything else.
      </p>

      <Raw title="">
        <PullQuote cite="Human 3.0">
          This map of reality prevents partial thinking. An internal mental problem isn't best
          solved by vocational means; a spiritual problem isn't best solved by nutrition. Money
          often doesn't solve for meaning — but they're intimately connected.
        </PullQuote>
      </Raw>

      <p>
        Since life and evolution unfold toward more complexity, and ordered structures emerge to
        contain that chaos, we can call the process of life <strong>problem solving</strong>. A
        seed unfolds until it becomes a flower — many times more complex — and to get there it
        needs resources from its environment to self-develop.
      </p>
      <p>
        By developing yourself across all four quadrants at once, you begin to take control of
        your future.
      </p>
    </Section>
  );
}
