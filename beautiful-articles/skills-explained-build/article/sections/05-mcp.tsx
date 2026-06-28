import { Section, Aside, Raw } from "reacticle";
import { HubSpoke } from "../figures";

// Section 05 — What is MCP?  (one Section per file)
// Prose is the body; the client/server diagram is a reusable HubSpoke figure.
// One protocol, many sources.

export function SectionMCP() {
  return (
    <Section index="05" title="What is MCP?">
      <p>
        Subagents, Skills, and Projects all shape how Claude works and what it knows. MCP
        answers a different question: how Claude reaches the systems where your data actually
        lives.{" "}
        <strong>The Model Context Protocol (MCP)</strong> is an open standard for connecting
        AI assistants to the external systems where data actually lives — content
        repositories, business tools, databases, and development environments. It's the
        plumbing that lets Claude reach beyond the chat window and into the places your work
        already happens.
      </p>

      <p>
        <strong>How MCP works.</strong> MCP gives Claude a standardized way to connect to your tools and data sources.
          Instead of building a bespoke integration for every system — one for Drive, another
          for Slack, a third for your database — you build against a <strong>single
          protocol</strong>. MCP servers expose data and capabilities; MCP clients, like
          Claude, connect to those servers and use what they offer.
        </p>

        <Raw title="One protocol, many sources — Claude connects through MCP instead of a tangle of custom integrations">
          <HubSpoke
            center={{ label: "Claude", sub: "MCP client — connects once, then talks to every server" }}
            busLabel="MCP"
            nodesTitle="MCP servers"
            nodes={[
              { label: "Google Drive", sub: "Documents & files" },
              { label: "Slack", sub: "Messages & channels" },
              { label: "GitHub", sub: "Code & version control" },
              { label: "Database", sub: "Records & queries" },
            ]}
          />
        </Raw>

        <p>
          The payoff is in that picture: every new source plugs into the same bus rather than
          demanding its own custom wiring. Add a server, and Claude can talk to it — no new
          integration to design.
        </p>

      <p>
        <strong>When to use MCP.</strong> Reach for MCP when you need Claude to connect to
        systems beyond the conversation:
      </p>
        <ul>
          <li>
            <strong>Access external data</strong> — Google Drive, Slack, GitHub, databases.
          </li>
          <li>
            <strong>Use business tools</strong> — CRM systems, project management platforms.
          </li>
          <li>
            <strong>Connect to development environments</strong> — local files, IDEs, version
            control.
          </li>
          <li>
            <strong>Integrate with custom systems</strong> — your own proprietary tools and
            data sources.
          </li>
        </ul>

        <Aside tone="note" label="Example">
          Connect Claude to your company's Google Drive via MCP. Now Claude can search
          documents, read files, and reference internal knowledge without any manual uploads —
          the connection persists and updates automatically.
        </Aside>

      <Aside tone="principle" label="When to use a Skill instead">
        MCP connects Claude to data; Skills teach Claude what to do with that data. If you're
        explaining how to use a tool or follow a procedure — like "when querying our database,
        always filter by date range first" or "format Excel reports with these specific
        formulas" — that's a Skill. If you need Claude to reach the database or open the Excel
        files in the first place, that's MCP. The two work best together: MCP for connectivity,
        Skills for procedural knowledge.
      </Aside>
    </Section>
  );
}
