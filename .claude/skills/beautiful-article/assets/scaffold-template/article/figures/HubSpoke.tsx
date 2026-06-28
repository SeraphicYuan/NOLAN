// figures/HubSpoke.tsx — "one-to-many" diagram: a central hub connected through one
// bus to many spoke nodes (e.g. an MCP client → one protocol → many servers).
//
// Theme-portable (only --ra-* tokens via primitives/helpers), SSR-safe (presentational),
// responsive (flex + flex-basis reflow, SVG uses viewBox coords only).
import type { ReactNode } from "react";
import {
  FRow,
  FStack,
  Card,
  Sticker,
  FLabel,
  figureTokens as T,
  figureSpace as sp,
  figureText as tx,
} from "./primitives";

export type SpokeNode = { label: ReactNode; sub?: ReactNode };

export function HubSpoke(props: {
  center: { label: ReactNode; sub?: ReactNode };
  nodes: SpokeNode[];
  busLabel?: ReactNode;
  centerTone?: "ink" | "surface";
  nodesTitle?: ReactNode;
}): JSX.Element {
  const { center, nodes, busLabel, centerTone = "ink", nodesTitle } = props;
  const ink = centerTone === "ink";

  // Fan lines: one vertical bus on the left of the connector, lines fanning to N nodes.
  const count = Math.max(nodes.length, 1);
  const busX = 14;
  const lines = nodes.map((_, i) => {
    // Evenly distribute endpoints across the viewBox height (0..100).
    const y = ((i + 0.5) / count) * 100;
    return { y };
  });

  return (
    <FRow gap={3} wrap align="stretch" justify="center">
      {/* Center hub */}
      <div style={{ flex: "1 1 13rem", display: "flex" }}>
        <Card
          variant={ink ? "plain" : "surface"}
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            gap: sp(2),
            ...(ink ? { background: T.accent, border: `1px solid ${T.accent}` } : {}),
          }}
        >
          <span
            style={{
              fontFamily: T.heads,
              fontSize: tx("lg"),
              fontWeight: 700,
              lineHeight: 1.15,
              color: ink ? T.accentContrast : T.heading,
            }}
          >
            {center.label}
          </span>
          {center.sub ? (
            <span
              style={{
                fontSize: tx("sm"),
                lineHeight: 1.35,
                color: ink ? T.accentContrast : T.muted,
                opacity: ink ? 0.72 : 1,
              }}
            >
              {center.sub}
            </span>
          ) : null}
        </Card>
      </div>

      {/* Connector: one bus → many fan lines, with optional sticker */}
      <div
        style={{
          flex: "0 1 5rem",
          minWidth: "3rem",
          position: "relative",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          alignSelf: "stretch",
        }}
      >
        <svg
          viewBox="0 0 60 100"
          preserveAspectRatio="none"
          width="100%"
          height="100%"
          style={{ display: "block", minHeight: "5rem" }}
          aria-hidden="true"
        >
          {/* the bus */}
          <line x1={busX} y1={4} x2={busX} y2={96} stroke={T.borderStrong} strokeWidth={2} />
          {/* fan lines from bus to each node */}
          {lines.map((l, i) => (
            <line
              key={i}
              x1={busX}
              y1={l.y}
              x2={58}
              y2={l.y}
              stroke={T.border}
              strokeWidth={2}
            />
          ))}
        </svg>
        {busLabel ? (
          <span
            style={{
              position: "absolute",
              top: "50%",
              left: "50%",
              transform: "translate(-50%, -50%)",
            }}
          >
            <Sticker rotate={-4}>{busLabel}</Sticker>
          </span>
        ) : null}
      </div>

      {/* Node list */}
      <div style={{ flex: "1 1 14rem", display: "flex" }}>
        <FStack gap={2} style={{ flex: 1 }}>
          {nodesTitle ? <FLabel>{nodesTitle}</FLabel> : null}
          {nodes.map((n, i) => (
            <Card key={i} variant="surface" style={{ padding: `${sp(3)} ${sp(4)}` }}>
              <span style={{ fontWeight: 700, color: T.heading, fontSize: tx("sm") }}>{n.label}</span>
              {n.sub ? (
                <span
                  style={{
                    display: "block",
                    marginTop: sp(1),
                    fontSize: tx("xs"),
                    color: T.muted,
                  }}
                >
                  {n.sub}
                </span>
              ) : null}
            </Card>
          ))}
        </FStack>
      </div>
    </FRow>
  );
}
