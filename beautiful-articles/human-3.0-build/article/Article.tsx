import { Article, Hero, Lead, Summary, Conclusion, Raw } from "reacticle";
import { SectionWhyOneMap } from "./sections/01-why-one-map";
import { SectionQuadrants } from "./sections/02-quadrants";
import { SectionEvolution } from "./sections/03-evolution";
import { SectionLevels } from "./sections/04-levels";
import { SectionPhasesTraits } from "./sections/05-phases-traits";
import { SectionChannels } from "./sections/06-channels";
import { SectionArchetypes } from "./sections/07-archetypes";

// Assembler (main agent owns it). One Section = one file. width=regular + toc.
export function ArticleDoc() {
  return (
    <Article toc width="regular">
      <Hero
        eyebrow="Essay · Human 3.0"
        title="HUMAN 3.0"
        subtitle="A map to reach the top 1% — one model to develop across mind, body, spirit, and vocation."
        meta={[
          { label: "Author", value: "Dan Koe" },
          { label: "Date", value: "August 26, 2025" },
          { label: "Source", value: "thedankoe.com" },
        ]}
      />
      <Lead>
        I've always wanted to become a force to be reckoned with — an absolute unit of an
        individual. Not just a muscular body, but to be fully developed in every domain of
        life: mind, body, spirit, relationships, money. After 15 years researching psychology,
        philosophy, business, and meaning, I've noticed patterns that form a new philosophy for
        today's world. That's where HUMAN 3.0 comes in.
      </Lead>

      <Summary
        title="The map, at a glance"
        points={[
          "Four quadrants — Mind, Body, Spirit, Vocation — map every domain of life (Ken Wilber's AQAL).",
          "Three levels in each quadrant: 1.0 Conformist → 2.0 Individualist → 3.0 Synthesist.",
          "Growth is vertical (phases: Dissonance → Uncertainty → Discovery) and horizontal (traits: knowledge + skill).",
          "Channels are the obsessive quests that move you up a level; Glitches accelerate — at real risk.",
          "Most models are siloed to one domain. HUMAN 3.0 unifies them: map where you are, then transcend and include.",
        ]}
      />

      <SectionWhyOneMap />
      <SectionQuadrants />
      <SectionEvolution />
      <SectionLevels />
      <SectionPhasesTraits />
      <SectionChannels />
      <SectionArchetypes />

      <Conclusion
        title="Only the foundation"
        takeaways={[
          "Map every domain at once — Mind, Body, Spirit, Vocation — instead of optimizing one and neglecting the rest.",
          "Climb deliberately: vertical through the phases, horizontal through the traits, pulled forward by Channels.",
          "You never leave a level — you transcend and include it. Find where you are, then take the next step.",
        ]}
      >
        This is only the foundation of HUMAN 3.0 — a map, not a dogma. Much of it will be wrong,
        and the nuance is yours to fill in. Plot where you stand in each quadrant, notice which
        Channel is calling, and take the uncertain step. The game only becomes infinite once you
        realize you're the one designing it.
      </Conclusion>

      {/* ─── Colophon ─── (required; low-contrast, centered, --ra-* only) */}
      <Raw title="">
        <footer
          style={{
            marginTop: "var(--ra-space-7, 3rem)",
            paddingTop: "var(--ra-space-4, 1rem)",
            borderTop: "1px solid var(--ra-color-border, currentColor)",
            color: "var(--ra-color-muted, inherit)",
            fontSize: "var(--ra-text-xs, 0.78rem)",
            textAlign: "center",
            letterSpacing: "0.02em",
            opacity: 0.85,
          }}
        >
          Made with <strong style={{ fontWeight: 600 }}>NOLAN</strong> · bodoni theme
        </footer>
      </Raw>
    </Article>
  );
}
