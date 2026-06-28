// Example/validation section showing Tier-1 (Mermaid) + Tier-2 (Chart).
// Not part of the article — wired temporarily to verify rendering. These two
// figures are imported from their OWN paths (not the barrel) so they only bundle
// when used.
import { Section, Raw } from "reacticle";
import { Mermaid } from "../figures/Mermaid";
import { Chart } from "../figures/Chart";

export function SectionTiersDemo() {
  return (
    <Section index="99" title="Figure tiers — Mermaid & charts">
      <p>
        Tier 1 — a Mermaid diagram (themed from <strong>--ra-*</strong> tokens), for the long
        tail our house figures don't cover (here, a sequence):
      </p>
      <Raw title="Tier 1 · Mermaid sequence — activating a research agent">
        <Mermaid
          code={`sequenceDiagram
    participant U as You
    participant C as Claude
    participant M as MCP servers
    participant S as Subagents
    U->>C: Analyze our top 3 competitors
    C->>M: Pull Drive + GitHub data
    M-->>C: Documents & repos
    C->>S: Delegate market + technical analysis
    S-->>C: Findings + citations
    C-->>U: Comprehensive competitive analysis`}
        />
      </Raw>

      <p>Tier 2 — a real data chart (Recharts, themed):</p>
      <Raw title="Tier 2 · Chart — tokens loaded per progressive-disclosure stage">
        <Chart
          type="bar"
          xKey="stage"
          height={240}
          series={[{ key: "tokens", label: "Tokens loaded" }]}
          data={[
            { stage: "Metadata", tokens: 100 },
            { stage: "Instructions", tokens: 5000 },
            { stage: "Scripts/files", tokens: 12000 },
          ]}
          caption="Illustrative — progressive disclosure keeps the up-front cost tiny."
        />
      </Raw>
    </Section>
  );
}
