import { Section, Raw } from "reacticle";
import { CardGrid, PullQuote, Stat } from "../figures";

// Section 07 — Archetypes and metatypes. Prose-first; CardGrid (per-quadrant
// progression) + PullQuote (pre-trans fallacy) + Stat (worked example).
const PROGRESSIONS = [
  {
    title: "Mind",
    subtitle: "NPC → Player → Creator",
    items: [
      "Stop living the script you were assigned, start playing your own game, then create new games others play.",
    ],
  },
  {
    title: "Body",
    subtitle: "Incel → Chad → Sigma",
    items: ["Common archetypes you can read in someone's behavior and appearance."],
  },
  {
    title: "Vocation",
    subtitle: "Job → Career → Calling",
    items: ["From low-consciousness conformity toward your true work."],
  },
  {
    title: "Spirit",
    subtitle: "Religion → Atheism → Mysticism",
    items: [
      "Strict upbringing, rebellion, then a new perspective on God that loops back to the truths of Level 1.",
    ],
  },
];

const WORKED_EXAMPLE = [
  {
    value: "2.0",
    label: "Metatype score",
    sub: "(total ÷ 12 developmental slices)",
  },
  {
    value: "The Outlier",
    label: "the synthesis",
    sub: "drifted from the mainstream without rebellion",
  },
];

export function SectionArchetypes() {
  return (
    <Section index="07" title="Archetypes and metatypes">
      <p>
        With the map in hand, we can run it in two directions: outward, to understand the people
        around us, and inward, to overcome the problems in our own life. Two terms make this
        precise. <strong>Archetypes</strong> are patterns of people that show up in specific
        quadrants and levels. <strong>Metatypes</strong> are the synthesis of one person's four
        archetypes across the quadrants — think of it as a personality test, but for
        self-development.
      </p>
      <p>
        Within each quadrant there is a general progression from low to high consciousness. The
        same arc repeats, even as the names change.
      </p>

      <Raw title="A progression in each quadrant">
        <CardGrid min="15rem" cards={PROGRESSIONS} />
      </Raw>

      <p>
        Notice the loop in Spirit: the third stage doesn't abandon the first, it returns to its
        truths from a wider vantage. This is exactly where most people misread one another.
      </p>

      <Raw title="">
        <PullQuote cite="The pre-trans fallacy (Ken Wilber)">
          We confuse pre-rational (Conformist) states with trans-rational (Synthesist) states,
          because both look &lsquo;non-rational&rsquo; from a conventional rational view. A
          bible-thumper finds it hard to take a mystic seriously — when the mystic often holds the
          same truths, from a more comprehensive perspective.
        </PullQuote>
      </Raw>

      <p>
        Plot someone's points of development across quadrant, level, phase, and trait, and you get
        a comprehensive picture of where they lie. To turn that picture into a number, score each
        point: everything in Level 1 counts as 1, Level 2 as 2, Level 3 as 3. Add it all up and
        divide by 12. A worked example lands at 2.0 — and we can name the resulting Metatype
        <strong> The Outlier</strong>.
      </p>

      <Raw title="A worked example">
        <Stat items={WORKED_EXAMPLE} />
      </Raw>

      <p>Reading the four quadrants of this example back out:</p>
      <ul>
        <li>
          <strong>Mind</strong> — no longer lives by a script, near construct-level awareness.
        </li>
        <li>
          <strong>Body</strong> — ungroomed with poor habits, but occasionally exudes confidence.
        </li>
        <li>
          <strong>Spirit</strong> — believes in a literal God, but tolerant of atheist friends.
        </li>
        <li>
          <strong>Vocation</strong> — valuable education and skills, but focused on a safe,
          fulfilling career.
        </li>
      </ul>

      <p>
        This is only the foundation of the model. There's a lot more nuance to unpack — but already
        you can place a person, or yourself, somewhere honest on the map.
      </p>
    </Section>
  );
}
