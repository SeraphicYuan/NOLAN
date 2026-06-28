import { Section, Raw } from "reacticle";
import { PullQuote } from "../figures";

// Section 01 — Why we need one map. Prose-first; one PullQuote highlight.
export function SectionWhyOneMap() {
  return (
    <Section index="01" title="Why we need one map">
      <p>
        There are plenty of incredible models and gurus already out there. Spiral Dynamics for
        psychology, Buddhism and Christianity for meaning, materialism and mentalism for the
        nature of reality, eCommerce and consulting for business, and so on. Anywhere you look,
        you can find hundreds of models that promise the answer to all your problems.
      </p>
      <p>
        All of them have their truths. But the critical flaw is that they're nearly all
        <strong> isolated to a single domain of life</strong>. We learn math, English, and
        science as separate, siloed classes — when knowledge is really a web.
      </p>

      <Raw title="">
        <PullQuote cite="Human 3.0">
          Many spiritual teachers have frail bodies. Many businessmen can't maintain
          relationships. It is rare that one is truly self-developed.
        </PullQuote>
      </Raw>

      <p>
        Even when a model does connect multiple domains — like the Ancient Greek philosophies —
        it often predates the internet, technology, and AI, which have changed everything. And
        very few touch on work and money, which is surprising, since those dominate most
        people's lives.
      </p>
      <p>
        HUMAN 3.0 is an attempt to take the best parts of the world's greatest theories and
        apply them to the life of one individual — a single map for developing across every
        domain at once. Today, we lay its foundation.
      </p>
    </Section>
  );
}
